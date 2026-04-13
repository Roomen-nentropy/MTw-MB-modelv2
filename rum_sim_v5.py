#!/usr/bin/env python3
"""
rum_sim_v4.py
-------------
Real-world map + weather simulation using v5_real_world_data package.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from v5_real_world_data.bbbike_map_sampler import suggest_sindelfingen_depot_xy
from v5_real_world_data.config import DepotConfig, FleetTierConfig, SimulationConfig
from v5_real_world_data.open_meteo_weather import fetch_save_default_stuttgart
from v5_real_world_data.simulation import run_simulation


ROOT = Path(__file__).resolve().parent
MAP_XZ = ROOT / "v5_real_world_data" / "planet_8.317,48.426_9.898,49.134.osm.csv.xz"
WEATHER_CSV = ROOT / "v5_real_world_data" / "open_meteo_stuttgart_hourly_14d.csv"


def _ensure_weather_csv() -> str:
    if not WEATHER_CSV.exists():
        fetch_save_default_stuttgart(out_csv=WEATHER_CSV, past_days=7, forecast_days=7)
    return str(WEATHER_CSV)


def build_config() -> SimulationConfig:
    depot_x, depot_y = suggest_sindelfingen_depot_xy(str(MAP_XZ))
    return SimulationConfig(
        # 14 days hourly.
        total_periods=14 * 24,
        planning_horizon_periods=4,
        commitment_window_periods=1,
        # Grid size is ignored when BBBike map sampling is enabled.
        grid_size=100.0,
        tasks_per_period_mean=8.0,
        tasks_per_period_fixed=None,
        max_active_tasks=300,
        road_domain_weights={"Highway": 0.30, "Rural": 0.25, "Urban": 0.45},
        initial_weather="Clear",
        weather_transitions={
            "Clear": {"Clear": 0.70, "Rain": 0.20, "Fog": 0.10},
            "Rain": {"Clear": 0.30, "Rain": 0.60, "Fog": 0.10},
            "Fog": {"Clear": 0.40, "Rain": 0.10, "Fog": 0.50},
        },
        weather_task_rate_multiplier={"Clear": 1.00, "Rain": 1.10, "Fog": 1.15},
        weather_operating_cost_multiplier={"Clear": 1.00, "Rain": 1.10, "Fog": 1.16},
        lighting_cycle=(["Night"] * 6 + ["Dusk"] * 2 + ["Day"] * 12 + ["Dusk"] * 2 + ["Night"] * 2),
        lighting_task_rate_multiplier={"Day": 1.00, "Dusk": 1.05, "Night": 1.10},
        lighting_operating_cost_multiplier={"Day": 1.00, "Dusk": 1.05, "Night": 1.10},
        fleet=[
            FleetTierConfig("Standard", skill_k=1, cost_multiplier=1.0, num_available=5),
            FleetTierConfig("Advanced", skill_k=2, cost_multiplier=1.8, num_available=1),
        ],
        depots=[DepotConfig("MB_Sindelfingen", x=depot_x, y=depot_y)],
        weather_score={"Clear": 0, "Rain": 1, "Fog": 2},
        lighting_score={"Day": 0, "Dusk": 1, "Night": 2},
        road_domain_score={"Highway": 0, "Rural": 1, "Urban": 2},
        req_thresholds=[2],
        req_levels=[1, 2],
        solver_max_runtime=2.0,
        solver_seed=42,
        coord_scale=1.0,
        cost_scale=120.0,
        vehicle_fixed_cost_scale=1200.0,
        vehicle_fixed_cost_exponent=2.4,
        overqualification_cost_penalty_per_level=0.75,
        big_factor=1000.0,
        random_seed=0,
        verbose=True,
        save_results=True,
        results_dir="simulation_results",
        open_meteo_hourly_csv=_ensure_weather_csv(),
        bbbike_xz_path=str(MAP_XZ),
        bbbike_sampling_pool_size=3500,
    )


if __name__ == "__main__":
    config = build_config()
    summary = run_simulation(config)

    print("\n-- Real-World Quick stats -----------------------------------")
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
