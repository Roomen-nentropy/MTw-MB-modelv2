#!/usr/bin/env python3
"""
run_comp_v5_demo_small_area.py
------------------------------
Demo paired run on a smaller sampled map area while keeping
the full 14-day Open-Meteo interval (7 past + 7 forecast).
"""

from __future__ import annotations

import os
import sys
from dataclasses import replace
from statistics import mean
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rum_sim_v5 import build_config
from v5_real_world_data.fleet_controlgroup import build_control_group_fleet
from v5_real_world_data.simulation import SimulationSummary, run_simulation


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

    # Demo profile: smaller sampled area + lighter workload, but full 14-day weather horizon.
    demo = replace(
        base,
        total_periods=14 * 24,
        tasks_per_period_mean=4.0,
        max_active_tasks=120,
        solver_max_runtime=0.9,
        bbbike_sampling_pool_size=3500,
        verbose=False,
        save_results=False,
    )

    seed_count = 1
    seed_count_env = os.getenv("DEMO_SEEDS")
    if seed_count_env:
        try:
            seed_count = max(1, int(seed_count_env))
        except ValueError:
            pass
    seeds: List[int] = list(range(seed_count))

    fleet_model = demo.fleet
    fleet_cg = build_control_group_fleet(demo.fleet)

    print("=== Demo Real-World Comparison (Small Area, Full Weather) ===")
    print(f"seeds        : {seeds}")
    print(f"periods      : {demo.total_periods} (full 14-day interval)")
    print(f"solver sec   : {demo.solver_max_runtime}")
    print(f"map file     : {demo.bbbike_xz_path}")
    print(f"weather file : {demo.open_meteo_hourly_csv}")
    print(f"pool size    : {demo.bbbike_sampling_pool_size}")
    print(f"tasks mean   : {demo.tasks_per_period_mean}")
    print()

    rows = []
    for i, seed in enumerate(seeds, start=1):
        cfg_a = replace(demo, fleet=fleet_model, random_seed=seed)
        cfg_b = replace(
            demo,
            fleet=fleet_cg,
            random_seed=seed,
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

    print("\n=== Demo aggregated deltas (B - A) ===")
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
