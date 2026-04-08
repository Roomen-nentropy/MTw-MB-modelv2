#!/usr/bin/env python3
"""
run_comparative_simulation.py
═════════════════════════════
Paired comparative study for two fleets under identical stochastic scenarios.

Design:
- Fleet A and Fleet B are run with the same random seed per trial.
- This keeps generated weather/task conditions aligned across both fleets.
- Results are compared seed-by-seed (paired deltas), then aggregated.
"""

from __future__ import annotations

import os
import sys
from dataclasses import replace
from statistics import mean
from typing import List

# Keep direct-run behavior consistent with the existing launcher scripts.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hf_mdbovrp.fleet_controlgroup import build_control_group_fleet
from hf_mdbovrp.simulation import SimulationSummary, run_simulation
from run_simulation import config as baseline_config


def _cost_per_task(summary: SimulationSummary) -> float:
    """Schema-tolerant per-task routing cost."""
    if hasattr(summary, "avg_cost_per_dispatched_task"):
        return float(summary.avg_cost_per_dispatched_task)
    return float(summary.total_route_cost) / max(1, int(summary.total_tasks_dispatched))


def _backlog_ratio(summary: SimulationSummary) -> float:
    """Schema-tolerant end-of-run backlog ratio."""
    if hasattr(summary, "backlog_ratio_at_end"):
        return float(summary.backlog_ratio_at_end)
    return float(summary.total_tasks_remaining_at_end) / max(1, int(summary.total_tasks_generated))


def _dispatch_rate(summary: SimulationSummary) -> float:
    """Dispatch ratio over generated tasks."""
    return float(summary.total_tasks_dispatched) / max(1, int(summary.total_tasks_generated))


def _pct_change(new_value: float, base_value: float) -> float:
    """Percent change helper: (new - base) / base * 100."""
    return (new_value - base_value) / max(1e-9, abs(base_value)) * 100.0


if __name__ == "__main__":
    # Lightweight by default: this script is intended for quick paired comparisons.
    # Modes:
    #   quick  -> very fast sanity pass
    #   medium -> practical default for iteration
    #   full   -> slower, full comparative run
    mode = os.getenv("COMPARE_MODE", "medium").strip().lower()
    if mode not in {"quick", "medium", "full"}:
        mode = "medium"

    if mode == "quick":
        seeds: List[int] = [0]
        total_periods = 6
        solver_runtime = 1.5
    elif mode == "full":
        seeds = list(range(10))
        total_periods = baseline_config.total_periods
        solver_runtime = baseline_config.solver_max_runtime
    else:
        seeds = [0, 1, 2]
        total_periods = 10
        solver_runtime = 2.0

    # Optional override when you explicitly want a custom seed count.
    seed_count_env = os.getenv("COMPARE_SEEDS")
    if seed_count_env:
        try:
            seed_count = max(1, int(seed_count_env))
            seeds = list(range(seed_count))
        except ValueError:
            pass

    # Fleet A: baseline from run_simulation.py.
    fleet_a = baseline_config.fleet
    # Fleet B: control-group fleet with highest capability duplicated across tiers.
    fleet_b = build_control_group_fleet(baseline_config.fleet)

    print("=== Paired Fleet Comparison ===")
    print(f"mode         : {mode}")
    print(f"seeds        : {seeds}")
    print(f"periods      : {total_periods}")
    print(f"solver sec   : {solver_runtime}")
    print(f"fleet A      : {[f'{t.name}(n={t.num_available},k={t.skill_k})' for t in fleet_a]}")
    print(f"fleet B      : {[f'{t.name}(n={t.num_available},k={t.skill_k})' for t in fleet_b]}")
    print()

    rows = []
    for i, seed in enumerate(seeds, start=1):
        print(f"-> running paired seed {seed} ({i}/{len(seeds)})")
        # Paired-run key: same seed and same non-fleet parameters.
        cfg_a = replace(
            baseline_config,
            fleet=fleet_a,
            random_seed=seed,
            total_periods=total_periods,
            solver_max_runtime=solver_runtime,
            verbose=False,
            save_results=False,
        )
        cfg_b = replace(
            baseline_config,
            fleet=fleet_b,
            random_seed=seed,
            total_periods=total_periods,
            solver_max_runtime=solver_runtime,
            verbose=False,
            save_results=False,
        )

        summary_a = run_simulation(cfg_a)
        summary_b = run_simulation(cfg_b)

        # Sanity-check paired comparability assumptions.
        same_generated = summary_a.total_tasks_generated == summary_b.total_tasks_generated
        same_weather = summary_a.weather_period_counts == summary_b.weather_period_counts

        row = {
            "seed": seed,
            "cost_a": summary_a.total_route_cost,
            "cost_b": summary_b.total_route_cost,
            "cost_per_task_a": _cost_per_task(summary_a),
            "cost_per_task_b": _cost_per_task(summary_b),
            "dispatch_rate_a": _dispatch_rate(summary_a),
            "dispatch_rate_b": _dispatch_rate(summary_b),
            "backlog_a": _backlog_ratio(summary_a),
            "backlog_b": _backlog_ratio(summary_b),
            "delta_cost": summary_b.total_route_cost - summary_a.total_route_cost,
            "delta_cost_per_task": _cost_per_task(summary_b) - _cost_per_task(summary_a),
            "delta_dispatch_rate": _dispatch_rate(summary_b) - _dispatch_rate(summary_a),
            "delta_backlog": _backlog_ratio(summary_b) - _backlog_ratio(summary_a),
            "delta_cost_pct": _pct_change(summary_b.total_route_cost, summary_a.total_route_cost),
            "delta_cost_per_task_pct": _pct_change(_cost_per_task(summary_b), _cost_per_task(summary_a)),
            "delta_dispatch_rate_pct": _pct_change(_dispatch_rate(summary_b), _dispatch_rate(summary_a)),
            "delta_backlog_pct": _pct_change(_backlog_ratio(summary_b), _backlog_ratio(summary_a)),
            "same_generated": same_generated,
            "same_weather": same_weather,
        }
        rows.append(row)

        print(
            f"[{i:>2d}/{len(seeds)}] seed={seed:<2d} "
            f"A(cost={row['cost_a']:.1f}, disp={row['dispatch_rate_a']:.3f}, back={row['backlog_a']:.3f})  "
            f"B(cost={row['cost_b']:.1f}, disp={row['dispatch_rate_b']:.3f}, back={row['backlog_b']:.3f})  "
            f"Δcost={row['delta_cost']:+.1f} ({row['delta_cost_pct']:+.1f}%)"
        )

        if not same_generated or not same_weather:
            print("  [warn] Scenario mismatch detected for this seed.")

    print("\n=== Aggregated paired deltas (B - A) ===")
    print(
        f"mean Δ total cost      : {mean(r['delta_cost'] for r in rows):+.2f} "
        f"({mean(r['delta_cost_pct'] for r in rows):+.2f}%)"
    )
    print(
        f"mean Δ cost / task     : {mean(r['delta_cost_per_task'] for r in rows):+.4f} "
        f"({mean(r['delta_cost_per_task_pct'] for r in rows):+.2f}%)"
    )
    print(
        f"mean Δ dispatch rate   : {mean(r['delta_dispatch_rate'] for r in rows):+.4f} "
        f"({mean(r['delta_dispatch_rate_pct'] for r in rows):+.2f}%)"
    )
    print(
        f"mean Δ backlog ratio   : {mean(r['delta_backlog'] for r in rows):+.4f} "
        f"({mean(r['delta_backlog_pct'] for r in rows):+.2f}%)"
    )

    all_same_generated = all(r["same_generated"] for r in rows)
    all_same_weather = all(r["same_weather"] for r in rows)
    print("\n=== Pairing sanity checks ===")
    print(f"tasks generated matched: {all_same_generated}")
    print(f"weather path matched   : {all_same_weather}")
