from __future__ import annotations

from dataclasses import dataclass, replace
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
    meets_service_constraints: bool


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
    evaluation_periods: int | None = None,
    min_utilization: float | None = None,
    max_utilization: float | None = None,
    utilization_step: float | None = None,
    backlog_penalty: float = 8_000.0,
    undispatched_penalty: float = 6_000.0,
    min_dispatch_rate: float | None = None,
    max_backlog_ratio: float | None = None,
) -> DeploymentDecision:
    if not owned_fleet:
        raise ValueError("owned_fleet must not be empty.")

    eval_periods_in = evaluation_periods if evaluation_periods is not None else config.deployment_eval_periods
    min_util_in = min_utilization if min_utilization is not None else config.deployment_min_utilization
    max_util_in = max_utilization if max_utilization is not None else config.deployment_max_utilization
    util_step_in = utilization_step if utilization_step is not None else config.deployment_utilization_step
    min_dispatch_in = min_dispatch_rate if min_dispatch_rate is not None else config.deployment_min_dispatch_rate
    max_backlog_in = max_backlog_ratio if max_backlog_ratio is not None else config.deployment_max_backlog_ratio

    if util_step_in <= 0:
        raise ValueError("utilization_step must be > 0.")

    owned_total = sum(t.num_available for t in owned_fleet)
    eval_periods = max(1, min(eval_periods_in, int(config.total_periods)))

    candidates: List[int] = []
    util = min_util_in
    while util <= max_util_in + 1e-9:
        n = max(len(owned_fleet), min(owned_total, int(round(owned_total * util))))
        candidates.append(n)
        util += util_step_in
    candidates = sorted(set(candidates))

    best_feasible: Tuple[float, int, Dict[str, float], List[FleetTierConfig]] | None = None
    best_fallback: Tuple[Tuple[float, float, float], int, Dict[str, float], List[FleetTierConfig]] | None = None

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

        generated = max(1, int(summary.total_tasks_generated))
        dispatch_rate = float(summary.total_tasks_dispatched) / generated
        backlog_ratio = float(summary.total_tasks_remaining_at_end) / generated
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
            "dispatch_rate": dispatch_rate,
            "backlog_ratio": backlog_ratio,
            "meets_dispatch_threshold": 1.0 if dispatch_rate >= min_dispatch_in else 0.0,
            "meets_backlog_threshold": 1.0 if backlog_ratio <= max_backlog_in else 0.0,
        }

        is_feasible = (dispatch_rate >= min_dispatch_in) and (backlog_ratio <= max_backlog_in)
        if is_feasible:
            if (
                best_feasible is None
                or objective < best_feasible[0]
                or (objective == best_feasible[0] and deployed_total < best_feasible[1])
            ):
                best_feasible = (objective, deployed_total, comps, deployed_fleet)
        else:
            fallback_key = (-dispatch_rate, backlog_ratio, objective)
            if best_fallback is None or fallback_key < best_fallback[0]:
                best_fallback = (fallback_key, deployed_total, comps, deployed_fleet)

    if best_feasible is not None:
        objective, deployed_total, comps, deployed_fleet = best_feasible
        meets_constraints = True
    elif best_fallback is not None:
        _, deployed_total, comps, deployed_fleet = best_fallback
        objective = (
            comps["route_cost"]
            + comps["backlog_penalty"]
            + comps["undispatched_penalty"]
        )
        meets_constraints = False
    else:
        raise RuntimeError("No deployment candidates were evaluated.")

    return DeploymentDecision(
        owned_total=owned_total,
        deployed_total=deployed_total,
        utilization=deployed_total / max(1, owned_total),
        objective=float(objective),
        objective_components=comps,
        deployed_fleet=deployed_fleet,
        meets_service_constraints=meets_constraints,
    )

