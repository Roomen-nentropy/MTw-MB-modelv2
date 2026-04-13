#!/usr/bin/env python3
"""
run_comp_V3vsCG.py
==================
Paired-seed comparison between the V3 model and its V3 control group.
"""

from __future__ import annotations

import os
import sys
from dataclasses import replace
from statistics import mean
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from run_sim_v3 import config_v3
from v3_setup.fleet_controlgroup import build_control_group_fleet
from v3_setup.simulation import SimulationSummary, run_simulation


def _same_operating_assumptions(cfg_a, cfg_b) -> bool:
    """
    Verify V3 and control runs share identical non-fleet assumptions.
    """
    return (
        cfg_a.weather_task_rate_multiplier == cfg_b.weather_task_rate_multiplier
        and cfg_a.lighting_task_rate_multiplier == cfg_b.lighting_task_rate_multiplier
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
    mode = os.getenv("COMPARE_MODE", "medium").strip().lower()
    if mode not in {"quick", "medium", "full"}:
        mode = "medium"

    if mode == "quick":
        seeds: List[int] = [0]
        total_periods = 6
        solver_runtime = 1.5
    elif mode == "full":
        seeds = list(range(10))
        total_periods = config_v3.total_periods
        solver_runtime = config_v3.solver_max_runtime
    else:
        seeds = [0, 1, 2]
        total_periods = 10
        solver_runtime = 2.0

    seed_count_env = os.getenv("COMPARE_SEEDS")
    if seed_count_env:
        try:
            seed_count = max(1, int(seed_count_env))
            seeds = list(range(seed_count))
        except ValueError:
            pass

    fleet_v3 = config_v3.fleet
    fleet_cg = build_control_group_fleet(config_v3.fleet)

    print("=== Paired Comparison: V3 vs Control Group ===")
    print(f"mode         : {mode}")
    print(f"seeds        : {seeds}")
    print(f"periods      : {total_periods}")
    print(f"solver sec   : {solver_runtime}")
    print(f"v3 fleet     : {[f'{t.name}(n={t.num_available},k={t.skill_k})' for t in fleet_v3]}")
    print(f"cg fleet     : {[f'{t.name}(n={t.num_available},k={t.skill_k})' for t in fleet_cg]}")
    print()

    rows = []
    for i, seed in enumerate(seeds, start=1):
        cfg_v3 = replace(
            config_v3,
            fleet=fleet_v3,
            random_seed=seed,
            total_periods=total_periods,
            solver_max_runtime=solver_runtime,
            verbose=False,
            save_results=False,
        )
        cfg_cg = replace(
            config_v3,
            fleet=fleet_cg,
            random_seed=seed,
            total_periods=total_periods,
            solver_max_runtime=solver_runtime,
            verbose=False,
            save_results=False,
        )
        # Explicit fairness guard: only fleet composition differs between runs.
        same_assumptions = _same_operating_assumptions(cfg_v3, cfg_cg)
        if not same_assumptions:
            raise ValueError("V3 vs control-group config mismatch: non-fleet assumptions differ.")

        summary_v3 = run_simulation(cfg_v3)
        summary_cg = run_simulation(cfg_cg)

        same_generated = summary_v3.total_tasks_generated == summary_cg.total_tasks_generated
        same_weather = summary_v3.weather_period_counts == summary_cg.weather_period_counts

        row = {
            "seed": seed,
            "cost_v3": summary_v3.total_route_cost,
            "cost_cg": summary_cg.total_route_cost,
            "cost_per_task_v3": _cost_per_task(summary_v3),
            "cost_per_task_cg": _cost_per_task(summary_cg),
            "dispatch_rate_v3": _dispatch_rate(summary_v3),
            "dispatch_rate_cg": _dispatch_rate(summary_cg),
            "backlog_v3": _backlog_ratio(summary_v3),
            "backlog_cg": _backlog_ratio(summary_cg),
            # Positive delta means control group is worse on cost and backlog.
            "delta_cost": summary_cg.total_route_cost - summary_v3.total_route_cost,
            "delta_cost_per_task": _cost_per_task(summary_cg) - _cost_per_task(summary_v3),
            # Positive delta means V3 has better service levels.
            "delta_dispatch_rate": _dispatch_rate(summary_v3) - _dispatch_rate(summary_cg),
            "delta_backlog": _backlog_ratio(summary_cg) - _backlog_ratio(summary_v3),
            "delta_cost_pct": _pct_change(summary_cg.total_route_cost, summary_v3.total_route_cost),
            "delta_cost_per_task_pct": _pct_change(_cost_per_task(summary_cg), _cost_per_task(summary_v3)),
            "delta_dispatch_rate_pct": _pct_change(_dispatch_rate(summary_v3), _dispatch_rate(summary_cg)),
            "delta_backlog_pct": _pct_change(_backlog_ratio(summary_cg), _backlog_ratio(summary_v3)),
            "same_generated": same_generated,
            "same_weather": same_weather,
            "same_assumptions": same_assumptions,
        }
        rows.append(row)

        print(
            f"[{i:>2d}/{len(seeds)}] seed={seed:<2d} "
            f"V3(cost={row['cost_v3']:.1f}, disp={row['dispatch_rate_v3']:.3f}, back={row['backlog_v3']:.3f})  "
            f"CG(cost={row['cost_cg']:.1f}, disp={row['dispatch_rate_cg']:.3f}, back={row['backlog_cg']:.3f})  "
            f"dCost={row['delta_cost']:+.1f} ({row['delta_cost_pct']:+.1f}%)"
        )
        if not same_generated or not same_weather:
            print("  [warn] Scenario mismatch detected for this seed.")

    print("\n=== Aggregated paired deltas ===")
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

    all_same_generated = all(r["same_generated"] for r in rows)
    all_same_weather = all(r["same_weather"] for r in rows)
    all_same_assumptions = all(r["same_assumptions"] for r in rows)
    print("\n=== Pairing sanity checks ===")
    print(f"operating assumptions matched: {all_same_assumptions}")
    print(f"tasks generated matched: {all_same_generated}")
    print(f"weather path matched   : {all_same_weather}")
