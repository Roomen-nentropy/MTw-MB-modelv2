#!/usr/bin/env python3
"""
run_controlgroup.py
═══════════════════
Control-group entry point for the HF-MDBOVRP rolling-horizon simulation.

This script keeps the baseline configuration from run_simulation.py and only
changes the fleet so that all vehicles are upgraded to the highest tier level.
"""

from __future__ import annotations

import os
import sys
from dataclasses import replace

# Ensure imports work from the project root (same style as run_simulation.py).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hf_mdbovrp.fleet_controlgroup import build_control_group_fleet
from hf_mdbovrp.simulation import run_simulation
from run_simulation import config as baseline_config


control_config = replace(
    baseline_config,
    fleet=build_control_group_fleet(baseline_config.fleet),
)


if __name__ == "__main__":
    summary = run_simulation(control_config)

    print("\n-- Control Group Quick stats --------------------------------")
    print(f"  Tasks generated      : {summary.total_tasks_generated}")
    print(f"  Tasks dispatched     : {summary.total_tasks_dispatched}")
    print(f"  Tasks remaining      : {summary.total_tasks_remaining_at_end}")
    dispatch_pct = (
        summary.total_tasks_dispatched
        / max(1, summary.total_tasks_generated) * 100
    )
    print(f"  Dispatch rate        : {dispatch_pct:.1f}%")
    print(f"  Feasible periods     : {summary.feasible_periods}/{summary.total_periods}")
    print(f"  Avg cost / period    : {summary.avg_route_cost_per_feasible_period:.1f}")
    print(f"  Weather breakdown    : {summary.weather_period_counts}")
    print("-------------------------------------------------------------")
