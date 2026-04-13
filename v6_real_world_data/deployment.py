from __future__ import annotations

from dataclasses import dataclass, replace
from math import ceil
from typing import Dict, List, Sequence, Tuple

from .config import FleetTierConfig, SimulationConfig
from .simulation import run_simulation


@dataclass(frozen=True)
class DeploymentDecision:
    owned_total: int
    deployed_total: int
    utilization: float
    objective: float
    objective_components: Dict[str, float]
    deployed_fleet: List[FleetTierConfig]


def scale_owned_fleet(base_fleet: Sequence[FleetTierConfig], multiplier: float = 2.0) -> List[FleetTierConfig]:
    if multiplier < 1.0:
        raise ValueError("multiplier must be >= 1.0")
    return [replace(t, num_available=max(1, int(round(t.num_available * multiplier)))) for t in base_fleet]


def _allocate_total_across_tiers(
    owned_fleet: Sequence[FleetTierConfig],
    deployed_total: int,
) -> List[FleetTierConfig]:
    if not owned_fleet:
        raise ValueError("owned_fleet must not be empty.")
    if deployed_total < len(owned_fleet):
        raise ValueError("deployed_total must be at least number of tiers.")

    owned_counts = [t.num_available for t in owned_fleet]
    owned_total = sum(owned_counts)
    if deployed_total > owned_total:
        deployed_total = owned_total

    # Keep at least one vehicle per tier, then distribute proportional extras.
    deployed = [1] * len(owned_counts)
    remaining = deployed_total - len(owned_counts)
    if remaining <= 0:
        return [replace(t, num_available=n) for t, n in zip(owned_fleet, deployed)]

    capacities = [owned - 1 for owned in owned_counts]
    weighted_targets = [remaining * (owned / owned_total) for owned in owned_counts]
    assigned = [min(cap, int(target)) for cap, target in zip(capacities, weighted_targets)]
    deployed = [base + add for base, add in zip(deployed, assigned)]

    still_needed = deployed_total - sum(deployed)
    while still_needed > 0:
        best_idx = None
        best_gap = float("-inf")
        for i, (cap, target) in enumerate(zip(capacities, weighted_targets)):
            extra_assigned = deployed[i] - 1
            if extra_assigned >= cap:
                continue
            gap = target - extra_assigned
            if gap > best_gap:
                best_gap = gap
                best_idx = i
        if best_idx is None:
            break
        deployed[best_idx] += 1
        still_needed -= 1

    return [replace(t, num_available=n) for t, n in zip(owned_fleet, deployed)]


def choose_optimal_deployment(
    config: SimulationConfig,
    owned_fleet: Sequence[FleetTierConfig],
    evaluation_periods: int = 24,
    min_utilization: float = 0.35,
    max_utilization: float = 1.0,
    utilization_step: float = 0.05,
    backlog_penalty: float = 8_000.0,
    undispatched_penalty: float = 6_000.0,
) -> DeploymentDecision:
    if not owned_fleet:
        raise ValueError("owned_fleet must not be empty.")
    if utilization_step <= 0:
        raise ValueError("utilization_step must be > 0.")

    owned_total = sum(t.num_available for t in owned_fleet)
    eval_periods = max(1, min(evaluation_periods, int(config.total_periods)))

    candidates: List[int] = []
    util = min_utilization
    while util <= max_utilization + 1e-9:
        n = max(len(owned_fleet), min(owned_total, int(round(owned_total * util))))
        candidates.append(n)
        util += utilization_step
    candidates = sorted(set(candidates))

    best: Tuple[float, int, Dict[str, float], List[FleetTierConfig]] | None = None
    for deployed_total in candidates:
        deployed_fleet = _allocate_total_across_tiers(owned_fleet, deployed_total)
        eval_cfg = replace(
            config,
            fleet=deployed_fleet,
            total_periods=eval_periods,
            verbose=False,
            save_results=False,
        )
        summary = run_simulation(eval_cfg)
        undispatched = max(0, summary.total_tasks_generated - summary.total_tasks_dispatched)
        objective = (
            float(summary.total_route_cost)
            + backlog_penalty * float(summary.total_tasks_remaining_at_end)
            + undispatched_penalty * float(undispatched)
        )
        comps = {
            "route_cost": float(summary.total_route_cost),
            "backlog_penalty": backlog_penalty * float(summary.total_tasks_remaining_at_end),
            "undispatched_penalty": undispatched_penalty * float(undispatched),
            "tasks_generated": float(summary.total_tasks_generated),
            "tasks_dispatched": float(summary.total_tasks_dispatched),
            "tasks_remaining": float(summary.total_tasks_remaining_at_end),
        }

        if best is None or objective < best[0] or (objective == best[0] and deployed_total < best[1]):
            best = (objective, deployed_total, comps, deployed_fleet)

    if best is None:
        raise RuntimeError("No deployment candidates were evaluated.")

    objective, deployed_total, comps, deployed_fleet = best
    return DeploymentDecision(
        owned_total=owned_total,
        deployed_total=deployed_total,
        utilization=deployed_total / max(1, owned_total),
        objective=objective,
        objective_components=comps,
        deployed_fleet=deployed_fleet,
    )
