#!/usr/bin/env python3
"""
run_sim_v3.py
=============
Single-run launcher for the V3 simulation package.
"""

from __future__ import annotations

import os
import sys

# Keep direct-run behavior consistent with existing launchers.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from v3_setup.config import DepotConfig, FleetTierConfig, SimulationConfig
from v3_setup.simulation import run_simulation


config_v3 = SimulationConfig(
    total_periods=24,
    planning_horizon_periods=4,
    commitment_window_periods=1,
    grid_size=100.0,
    tasks_per_period_mean=6.0,
    tasks_per_period_fixed=None,
    max_active_tasks=120,
    road_domain_weights={
        "Highway": 0.28,
        "Rural": 0.30,
        "Urban": 0.42,
    },
    initial_weather="Clear",
    weather_transitions={
        "Clear": {"Clear": 0.70, "Rain": 0.20, "Fog": 0.10},
        "Rain": {"Clear": 0.30, "Rain": 0.60, "Fog": 0.10},
        "Fog": {"Clear": 0.40, "Rain": 0.10, "Fog": 0.50},
    },
    weather_task_rate_multiplier={
        "Clear": 1.00,
        "Rain": 1.08,
        "Fog": 1.12,
    },
    lighting_cycle=(
        ["Night"] * 6
        + ["Dusk"] * 2
        + ["Day"] * 12
        + ["Dusk"] * 2
        + ["Night"] * 2
    ),
    lighting_task_rate_multiplier={
        "Day": 1.00,
        "Dusk": 1.05,
        "Night": 1.10,
    },
    fleet=[
        FleetTierConfig("Standard", skill_k=1, cost_multiplier=1.0, num_available=4),
        FleetTierConfig("Advanced", skill_k=2, cost_multiplier=1.5, num_available=2),
    ],
    depots=[
        DepotConfig("HQ", x=50.0, y=50.0),
    ],
    weather_score={
        "Clear": 0,
        "Rain": 1,
        "Fog": 2,
    },
    lighting_score={
        "Day": 0,
        "Dusk": 1,
        "Night": 2,
    },
    road_domain_score={
        "Highway": 0,
        "Rural": 1,
        "Urban": 2,
    },
    req_thresholds=[2],
    req_levels=[1, 2],
    solver_max_runtime=4.0,
    solver_seed=42,
    coord_scale=1.0,
    cost_scale=100.0,
    big_factor=1000.0,
    vehicle_fixed_cost_scale=600.0,
    random_seed=0,
    verbose=True,
    save_results=True,
    results_dir="simulation_results",
)


if __name__ == "__main__":
    summary = run_simulation(config_v3)

    print("\n-- V3 Quick stats -------------------------------------------")
    print(f"  Tasks generated      : {summary.total_tasks_generated}")
    print(f"  Tasks dispatched     : {summary.total_tasks_dispatched}")
    print(f"  Tasks remaining      : {summary.total_tasks_remaining_at_end}")
    dispatch_pct = summary.total_tasks_dispatched / max(1, summary.total_tasks_generated) * 100
    print(f"  Dispatch rate        : {dispatch_pct:.1f}%")
    print(f"  Feasible periods     : {summary.feasible_periods}/{summary.total_periods}")
    print(f"  Total route cost     : {summary.total_route_cost:.1f}")
    print(f"  Avg cost / task      : {summary.avg_cost_per_dispatched_task:.3f}")
    print(f"  End backlog ratio    : {summary.backlog_ratio_at_end:.3f}")
    print("-------------------------------------------------------------")
