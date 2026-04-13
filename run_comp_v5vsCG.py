#!/usr/bin/env python3
"""
run_comp_RUMv5vsCG.py
---------------------
Paired comparison: real-world run config vs control-group fleet
on identical BBBike map area and Open-Meteo weather timeline.
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


def _same_operating_assumptions(cfg_a, cfg_b) -> bool:
    return (
        cfg_a.open_meteo_hourly_csv == cfg_b.open_meteo_hourly_csv
        and cfg_a.bbbike_xz_path == cfg_b.bbbike_xz_path
        and cfg_a.bbbike_sampling_pool_size == cfg_b.bbbike_sampling_pool_size
        and cfg_a.weather_task_rate_multiplier == cfg_b.weather_task_rate_multiplier
        and cfg_a.lighting_task_rate_multiplier == cfg_b.lighting_task_rate_multiplier
        and cfg_a.weather_operating_cost_multiplier == cfg_b.weather_operating_cost_multiplier
        and cfg_a.lighting_operating_cost_multiplier == cfg_b.lighting_operating_cost_multiplier
        and cfg_a.depots == cfg_b.depots
    )


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
        total_periods = 48
        solver_runtime = 1.2
    elif mode == "full":
        seeds = list(range(7))
        total_periods = base.total_periods
        solver_runtime = base.solver_max_runtime
    else:
        seeds = [0, 1, 2]
        total_periods = 7 * 24
        solver_runtime = 1.6

    fleet_model = base.fleet
    fleet_cg = build_control_group_fleet(base.fleet)

    print("=== Real-World Paired Comparison: Model vs Control Group ===")
    print(f"mode         : {mode}")
    print(f"seeds        : {seeds}")
    print(f"periods      : {total_periods}")
    print(f"solver sec   : {solver_runtime}")
    print(f"map file     : {base.bbbike_xz_path}")
    print(f"weather file : {base.open_meteo_hourly_csv}")
    print(f"model fleet  : {[f'{t.name}(n={t.num_available},k={t.skill_k})' for t in fleet_model]}")
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
        same_assumptions = _same_operating_assumptions(cfg_a, cfg_b)
        if not same_assumptions:
            raise ValueError("Real-world model vs control mismatch: non-fleet assumptions differ.")

        summary_a = run_simulation(cfg_a)
        summary_b = run_simulation(cfg_b)

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
            "delta_dispatch_rate": _dispatch_rate(summary_a) - _dispatch_rate(summary_b),
            "delta_backlog": _backlog_ratio(summary_b) - _backlog_ratio(summary_a),
            "delta_cost_pct": _pct_change(summary_b.total_route_cost, summary_a.total_route_cost),
            "delta_cost_per_task_pct": _pct_change(_cost_per_task(summary_b), _cost_per_task(summary_a)),
            "delta_dispatch_rate_pct": _pct_change(_dispatch_rate(summary_a), _dispatch_rate(summary_b)),
            "delta_backlog_pct": _pct_change(_backlog_ratio(summary_b), _backlog_ratio(summary_a)),
            "same_generated": same_generated,
            "same_weather": same_weather,
            "same_assumptions": same_assumptions,
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
    print(
        f"mean d dispatch rate   : {mean(r['delta_dispatch_rate'] for r in rows):+.4f} "
        f"({mean(r['delta_dispatch_rate_pct'] for r in rows):+.2f}%)"
    )
    print(
        f"mean d backlog ratio   : {mean(r['delta_backlog'] for r in rows):+.4f} "
        f"({mean(r['delta_backlog_pct'] for r in rows):+.2f}%)"
    )

    print("\n=== Pairing sanity checks ===")
    print(f"operating assumptions matched: {all(r['same_assumptions'] for r in rows)}")
    print(f"tasks generated matched      : {all(r['same_generated'] for r in rows)}")
    print(f"weather path matched         : {all(r['same_weather'] for r in rows)}")
