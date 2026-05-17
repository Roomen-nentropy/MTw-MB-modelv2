from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pyvrp
from pyvrp import stop

from .environment import TaskEnv, compute_task_requirement_level
from .fleet import VehicleTier


@dataclass(frozen=True)
class Task:
    """A data collection ticket represented as a routing client."""

    name: str
    x: float
    y: float
    # Reqj in the thesis notation.
    req_level: int
    # Optional: time window / service duration could be added later.


@dataclass(frozen=True)
class Depot:
    """A start depot (open routing is approximated by depot-to-depot routes)."""

    name: str
    x: float
    y: float


def _euclidean_distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def _overqualification_edge_addition(
    skill_k: int,
    req: int,
    *,
    penalty_per_level: float,
    max_base_dist: int,
) -> int:
    """Extra integer distance for one incident end (enter or leave) of a visit."""
    if penalty_per_level <= 0 or skill_k <= req:
        return 0
    gap = skill_k - req
    scale = max(1, int(max_base_dist))
    return int(round(penalty_per_level * gap * scale))


def build_skill_based_pyvrp_model(
    tasks: Sequence[Task],
    depots: Sequence[Depot],
    vehicle_tiers: Sequence[VehicleTier],
    *,
    coord_scale: float = 1.0,
    cost_scale: float = 100.0,
    big_factor: float = 1000.0,
    vehicle_fixed_cost_scale: float = 600.0,
    vehicle_fixed_cost_exponent: float = 2.0,
    operating_cost_multiplier: float = 1.0,
    overqualification_cost_penalty_per_level: float = 0.30,
) -> Tuple[pyvrp.Model, Dict[str, object]]:
    """
    Build a PyVRP heterogeneous skill-based model (Phase 2/3 scaffold).

    Under-qualification (Skill_k < Req_j) uses profile-specific prohibitive
    edge distances so incompatible visits are effectively forbidden.

    Over-qualification (Skill_k > Req_j) adds finite extra distance on each
    arc end incident to that client so the objective discourages wasting
    high-capability tiers on low-requirement tasks. The penalty scales with
    (Skill_k - Req_j) and with the largest base edge length in the instance.
    """

    if not tasks:
        raise ValueError("tasks must be non-empty.")
    if not depots:
        raise ValueError("depots must be non-empty.")
    if not vehicle_tiers:
        raise ValueError("vehicle_tiers must be non-empty.")

    # Create model and depots.
    model = pyvrp.Model()
    depot_objs: List[pyvrp.Depot] = []
    for d in depots:
        depot_objs.append(model.add_depot(d.x, d.y, name=d.name))

    # One routing profile per vehicle tier (Skill level).
    profiles: List[pyvrp.Profile] = []
    for _ in vehicle_tiers:
        profiles.append(model.add_profile())

    # Add vehicle types. In PyVRP, each vehicle type has a single start depot.
    vehicle_type_objs: List[pyvrp.VehicleType] = []
    for tier, profile in zip(vehicle_tiers, profiles):
        if tier.start_depot_index >= len(depot_objs):
            raise ValueError(
                f"VehicleTier.start_depot_index={tier.start_depot_index} "
                f"out of range for depots (len={len(depot_objs)})."
            )

        # pyvrp expects an int cost per unit distance.
        effective_cost_scale = cost_scale * max(0.0, operating_cost_multiplier)
        unit_distance_cost = int(round(tier.cost_multiplier * effective_cost_scale))
        if unit_distance_cost < 1:
            unit_distance_cost = 1
        # Post-v2 standard: objective uses equipment-weighted travel cost only.
        fixed_cost = 0

        vehicle_type_objs.append(
            model.add_vehicle_type(
                num_available=tier.num_available,
                capacity=[],
                start_depot=depot_objs[tier.start_depot_index],
                end_depot=depot_objs[tier.start_depot_index],
                fixed_cost=fixed_cost,
                unit_distance_cost=unit_distance_cost,
                unit_duration_cost=0,
                profile=profile,
                name=tier.name,
            )
        )

    # Add client nodes (tasks).
    client_objs: List[pyvrp.Client] = []
    for t in tasks:
        # required=True means every client must be visited.
        client_objs.append(model.add_client(t.x, t.y, required=True, name=t.name))

    # Build a single base complete directed distance matrix among all locations.
    loc_objs = depot_objs + client_objs
    loc_is_client = [False] * len(depot_objs) + [True] * len(client_objs)
    client_start_idx = len(depot_objs)  # index into loc_objs where clients begin

    base_dist: List[List[int]] = []
    max_base_dist = 0
    for i, loc_i in enumerate(loc_objs):
        row: List[int] = []
        for j, loc_j in enumerate(loc_objs):
            d = _euclidean_distance(loc_i.x, loc_i.y, loc_j.x, loc_j.y)
            dist_int = max(0, int(round(d * coord_scale)))
            row.append(dist_int)
            if dist_int > max_base_dist:
                max_base_dist = dist_int
        base_dist.append(row)

    # Ensure prohibitive distance dominates any feasible path.
    # For numerical stability, add 1 and cast to int.
    prohibitive_distance = int(round(max_base_dist * big_factor)) + 1

    # Compatibility and overqualification via profile-specific edges.
    # Under-qual: Skill_k < Req -> prohibitive distance (enter and/or leave).
    # Over-qual: Skill_k > Req -> additive distance at each incident arc end.
    alpha = float(overqualification_cost_penalty_per_level)
    for profile_idx, (tier, profile) in enumerate(zip(vehicle_tiers, profiles)):
        skill_k = int(tier.skill_k)
        for i, loc_i in enumerate(loc_objs):
            for j, loc_j in enumerate(loc_objs):
                if i == j:
                    continue

                dist = base_dist[i][j]
                incompatible = False

                if loc_is_client[j]:
                    task_idx = j - client_start_idx
                    req_j = int(tasks[task_idx].req_level)
                    if skill_k < req_j:
                        incompatible = True

                if loc_is_client[i]:
                    task_idx = i - client_start_idx
                    req_i = int(tasks[task_idx].req_level)
                    if skill_k < req_i:
                        incompatible = True

                if incompatible:
                    dist = prohibitive_distance
                else:
                    extra = 0
                    if loc_is_client[j]:
                        req_j = int(tasks[j - client_start_idx].req_level)
                        extra += _overqualification_edge_addition(
                            skill_k,
                            req_j,
                            penalty_per_level=alpha,
                            max_base_dist=max_base_dist,
                        )
                    if loc_is_client[i]:
                        req_i = int(tasks[i - client_start_idx].req_level)
                        extra += _overqualification_edge_addition(
                            skill_k,
                            req_i,
                            penalty_per_level=alpha,
                            max_base_dist=max_base_dist,
                        )
                    dist = dist + extra

                model.add_edge(
                    loc_objs[i],
                    loc_objs[j],
                    distance=int(dist),
                    duration=0,
                    profile=profile,
                )

    meta = {
        "prohibitive_distance": prohibitive_distance,
        "profiles": profiles,
        "vehicle_types": vehicle_type_objs,
        "depot_objs": depot_objs,
        "client_objs": client_objs,
    }
    return model, meta


def solve_pyvrp_model(
    model: pyvrp.Model,
    *,
    max_runtime_seconds: float = 10.0,
    seed: int = 0,
    display: bool = True,
) -> pyvrp.Result:
    """Solve using a runtime-based stopping criterion."""

    stop_crit = stop.MaxRuntime(max_runtime_seconds)
    # SolveParams default is usually fine for a first experiment.
    result = model.solve(stop_crit, seed=seed, display=display, collect_stats=True)
    return result

