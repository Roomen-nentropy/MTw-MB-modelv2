#!/usr/bin/env python3
"""
run_cost_optimization.py
════════════════════════
Searches for lower-cost operating settings while keeping the same HF-MDBOVRP model.

Why this file exists:
- We keep the solver/model formulation unchanged.
- We only vary policy/configuration levers (fleet mix, task-pool cap, solver time).
- We compare scenarios with service constraints, so "cheap but poor service" is rejected.
"""

from __future__ import annotations

import os
import sys
from dataclasses import replace
from statistics import mean
from typing import List, Tuple

# Why: mirror the existing launcher pattern so this script can run directly
# from the repository root without installation steps.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hf_mdbovrp.config import FleetTierConfig
from hf_mdbovrp.simulation import SimulationSummary, run_simulation
from run_simulation import config as baseline_config


def _cost_per_task(summary: SimulationSummary) -> float:
    """
    Return per-task cost in a schema-tolerant way.
    """
    # Why: older SimulationSummary schemas may not expose the precomputed field.
    # Falling back to base totals avoids AttributeError and keeps the script usable.
    if hasattr(summary, "avg_cost_per_dispatched_task"):
        return float(summary.avg_cost_per_dispatched_task)
    return float(summary.total_route_cost) / max(1, int(summary.total_tasks_dispatched))


def _backlog_ratio(summary: SimulationSummary) -> float:
    """
    Return end-of-run backlog ratio in a schema-tolerant way.
    """
    # Why: support both old and new summary shapes so optimisation can run even
    # if a user imports from an older module version.
    if hasattr(summary, "backlog_ratio_at_end"):
        return float(summary.backlog_ratio_at_end)
    return float(summary.total_tasks_remaining_at_end) / max(1, int(summary.total_tasks_generated))


def _build_candidate_configs(
    seeds: List[int],
    total_periods: int,
) -> List[Tuple[str, object]]:
    """
    Build a list of candidate configs by changing only operational variables.
    """
    base = baseline_config
    candidates: List[Tuple[str, object]] = []

    # Why: cheaper tiers should handle as many tasks as possible; we test fleet
    # mixes that shift volume toward Standard while retaining some Advanced units.
    fleet_variants = [
        (
            "fleet_4S_2A_baseline",
            [
                FleetTierConfig("Standard", skill_k=1, cost_multiplier=1.0, num_available=4),
                FleetTierConfig("Advanced", skill_k=2, cost_multiplier=1.5, num_available=2),
            ],
        ),
        (
            "fleet_5S_1A",
            [
                FleetTierConfig("Standard", skill_k=1, cost_multiplier=1.0, num_available=5),
                FleetTierConfig("Advanced", skill_k=2, cost_multiplier=1.5, num_available=1),
            ],
        ),
        (
            "fleet_6S_1A",
            [
                FleetTierConfig("Standard", skill_k=1, cost_multiplier=1.0, num_available=6),
                FleetTierConfig("Advanced", skill_k=2, cost_multiplier=1.5, num_available=1),
            ],
        ),
    ]

    # Why: smaller pending pools usually reduce long detours and keep each solve
    # focused on high-value near-term tasks.
    pool_caps = [60, 80, 100]

    # Why: runtime budget influences solution quality vs CPU time; we test a
    # small range to capture cost improvements without changing algorithms.
    solver_runtimes = [3.0, 5.0, 8.0]

    for fleet_name, fleet in fleet_variants:
        for cap in pool_caps:
            for runtime in solver_runtimes:
                for seed in seeds:
                    name = f"{fleet_name}_cap{cap}_rt{runtime:g}_seed{seed}"
                    cfg = replace(
                        base,
                        fleet=fleet,
                        max_active_tasks=cap,
                        solver_max_runtime=runtime,
                        random_seed=seed,
                        # Why: allow fast test runs while preserving the same
                        # optimisation logic and solver/model behaviour.
                        total_periods=total_periods,
                        verbose=False,  # Why: keep sweep output readable/compact.
                        save_results=False,  # Why: avoid producing many JSON files.
                    )
                    candidates.append((name, cfg))

    return candidates


def _aggregate_by_policy(results: List[Tuple[str, SimulationSummary]]) -> List[dict]:
    """
    Aggregate seed-level runs into policy-level averages.
    """
    buckets = {}
    for scenario_name, summary in results:
        policy_key = scenario_name.rsplit("_seed", 1)[0]
        buckets.setdefault(policy_key, []).append(summary)

    table = []
    for policy, summaries in buckets.items():
        table.append(
            {
                "policy": policy,
                # Why: direct objective for this study.
                "avg_total_cost": mean(s.total_route_cost for s in summaries),
                # Why: normalised cost KPI for fair comparison.
                "avg_cost_per_task": mean(_cost_per_task(s) for s in summaries),
                # Why: service guardrail so we do not accept low-cost under-delivery.
                "avg_dispatch_rate": mean(
                    s.total_tasks_dispatched / max(1, s.total_tasks_generated) for s in summaries
                ),
                # Why: backlog is another guardrail against hidden service debt.
                "avg_backlog_ratio": mean(_backlog_ratio(s) for s in summaries),
            }
        )

    return table


if __name__ == "__main__":
    # Why: FAST_SWEEP=1 gives a short smoke run; default keeps full study mode.
    fast_sweep = os.getenv("FAST_SWEEP", "0") == "1"
    # Why: these knobs control compute budget without changing the optimisation method.
    seeds = [0] if fast_sweep else [0, 1, 2]
    total_periods = 8 if fast_sweep else baseline_config.total_periods

    # Why: benchmark baseline under the same seeds for apples-to-apples comparison.
    baseline_runs: List[SimulationSummary] = []
    for seed in seeds:
        baseline_runs.append(
            run_simulation(
                replace(
                    baseline_config,
                    random_seed=seed,
                    total_periods=total_periods,
                    verbose=False,
                    save_results=False,
                )
            )
        )

    baseline_dispatch_rate = mean(
        s.total_tasks_dispatched / max(1, s.total_tasks_generated) for s in baseline_runs
    )

    # Why: require candidate policies to keep at least 98% of baseline service.
    min_dispatch_rate = baseline_dispatch_rate * 0.98
    # Why: cap backlog to prevent very delayed service from being labeled optimal.
    max_backlog_ratio = 0.20

    candidates = _build_candidate_configs(seeds=seeds, total_periods=total_periods)
    all_results: List[Tuple[str, SimulationSummary]] = []

    print(f"Running {len(candidates)} candidate simulations...")
    for i, (scenario_name, cfg) in enumerate(candidates, start=1):
        summary = run_simulation(cfg)
        all_results.append((scenario_name, summary))
        print(
            f"[{i:>3d}/{len(candidates)}] {scenario_name:<36s} "
            f"cost={summary.total_route_cost:>10.1f} "
            f"dispatch={summary.total_tasks_dispatched / max(1, summary.total_tasks_generated):.3f} "
            f"backlog={_backlog_ratio(summary):.3f}"
        )

    table = _aggregate_by_policy(all_results)

    # Why: filter with explicit service constraints before cost ranking.
    feasible = [
        row for row in table
        if row["avg_dispatch_rate"] >= min_dispatch_rate
        and row["avg_backlog_ratio"] <= max_backlog_ratio
    ]
    feasible.sort(key=lambda x: x["avg_cost_per_task"])

    baseline_cost_per_task = mean(_cost_per_task(s) for s in baseline_runs)

    print("\n=== Baseline (3-seed average) ===")
    print(f"dispatch_rate   : {baseline_dispatch_rate:.3f}")
    print(f"cost_per_task   : {baseline_cost_per_task:.2f}")

    print("\n=== Top cost-reduction policies (service-constrained) ===")
    if not feasible:
        print("No candidate met the service constraints; loosen thresholds and rerun.")
    else:
        for row in feasible[:10]:
            improvement = (baseline_cost_per_task - row["avg_cost_per_task"]) / max(
                1e-9, baseline_cost_per_task
            ) * 100.0
            print(
                f"{row['policy']:<36s} "
                f"cost_per_task={row['avg_cost_per_task']:.2f} "
                f"dispatch={row['avg_dispatch_rate']:.3f} "
                f"backlog={row['avg_backlog_ratio']:.3f} "
                f"improvement={improvement:+.1f}%"
            )
