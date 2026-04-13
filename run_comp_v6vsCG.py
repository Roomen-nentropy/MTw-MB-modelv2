#!/usr/bin/env python3
"""
run_comp_v6vsCG.py
------------------
Paired comparison for v6:
  - 2x owned fleet,
  - deployment optimizer chooses active vehicles from next-day forecast,
  - compare model fleet vs control-group fleet with the same active counts.
"""

from __future__ import annotations

import os
import sys
from dataclasses import replace
from statistics import mean
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rum_sim_v6 import build_config
from v6_real_world_data.deployment import choose_optimal_deployment
from v6_real_world_data.fleet_controlgroup import build_control_group_fleet
from v6_real_world_data.simulation import SimulationSummary, run_simulation


def _cost_per_task(summary: SimulationSummary) -> float:
    return float(summary.total_route_cost) / max(1, int(summary.total_tasks_dispatched))


def _dispatch_rate(summary: SimulationSummary) -> float:
    return float(summary.total_tasks_dispatched) / max(1, int(summary.total_tasks_generated))


def _backlog_ratio(summary: SimulationSummary) -> float:
    return float(summary.total_tasks_remaining_at_end) / max(1, int(summary.total_tasks_generated))


def _pct_change(new_value: float, base_value: float) -> float:
    return (new_value - base_value) / max(1e-9, abs(base_value)) * 100.0


if __name__ == "__main__":
    base = build_config()
    mode = os.getenv("COMPARE_MODE", "medium").strip().lower()
    if mode not in {"quick", "medium", "full"}:
        mode = "medium"

    if mode == "quick":
        seeds: List[int] = [0]
        total_periods = 24
        solver_runtime = 1.2
    elif mode == "full":
        seeds = list(range(7))
        total_periods = base.total_periods
        solver_runtime = base.solver_max_runtime
    else:
        seeds = [0, 1, 2]
        total_periods = base.total_periods
        solver_runtime = 1.6

    decision = choose_optimal_deployment(base, base.fleet, evaluation_periods=24)
    fleet_model = decision.deployed_fleet
    fleet_cg = build_control_group_fleet(fleet_model)

    print("=== Real-World Paired Comparison (v6): Model vs Control Group ===")
    print(f"mode         : {mode}")
    print(f"seeds        : {seeds}")
    print(f"periods      : {total_periods}")
    print(f"solver sec   : {solver_runtime}")
    print(f"map file     : {base.bbbike_xz_path}")
    print(f"weather file : {base.open_meteo_hourly_csv} (next-day forecast)")
    print(f"owned fleet  : {[f'{t.name}(n={t.num_available},k={t.skill_k})' for t in base.fleet]}")
    print(
        f"deployed     : {[f'{t.name}(n={t.num_available},k={t.skill_k})' for t in fleet_model]} "
        f"(total={decision.deployed_total}/{decision.owned_total}, util={decision.utilization:.1%})"
    )
    print(f"cg fleet     : {[f'{t.name}(n={t.num_available},k={t.skill_k})' for t in fleet_cg]}")
    print()

    rows = []
    for i, seed in enumerate(seeds, start=1):
        cfg_a = replace(
            base,
            fleet=fleet_model,
            random_seed=seed,
            total_periods=total_periods,
            solver_max_runtime=solver_runtime,
            verbose=False,
            save_results=False,
        )
        cfg_b = replace(
            base,
            fleet=fleet_cg,
            random_seed=seed,
            total_periods=total_periods,
            solver_max_runtime=solver_runtime,
            verbose=False,
            save_results=False,
        )

        summary_a = run_simulation(cfg_a)
        summary_b = run_simulation(cfg_b)

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
            "delta_dispatch_rate": _dispatch_rate(summary_a) - _dispatch_rate(summary_b),
            "delta_backlog": _backlog_ratio(summary_b) - _backlog_ratio(summary_a),
            "delta_cost_pct": _pct_change(summary_b.total_route_cost, summary_a.total_route_cost),
            "delta_cost_per_task_pct": _pct_change(_cost_per_task(summary_b), _cost_per_task(summary_a)),
        }
        rows.append(row)

        print(
            f"[{i:>2d}/{len(seeds)}] seed={seed:<2d} "
            f"A(cost={row['cost_a']:.1f}, disp={row['dispatch_rate_a']:.3f}, back={row['backlog_a']:.3f})  "
            f"B(cost={row['cost_b']:.1f}, disp={row['dispatch_rate_b']:.3f}, back={row['backlog_b']:.3f})  "
            f"dCost={row['delta_cost']:+.1f} ({row['delta_cost_pct']:+.1f}%)"
        )

    print("\n=== Aggregated paired deltas (B - A) ===")
    print(
        f"mean d total cost      : {mean(r['delta_cost'] for r in rows):+.2f} "
        f"({mean(r['delta_cost_pct'] for r in rows):+.2f}%)"
    )
    print(
        f"mean d cost / task     : {mean(r['delta_cost_per_task'] for r in rows):+.4f} "
        f"({mean(r['delta_cost_per_task_pct'] for r in rows):+.2f}%)"
    )
    print(f"mean d dispatch rate   : {mean(r['delta_dispatch_rate'] for r in rows):+.4f}")
    print(f"mean d backlog ratio   : {mean(r['delta_backlog'] for r in rows):+.4f}")
