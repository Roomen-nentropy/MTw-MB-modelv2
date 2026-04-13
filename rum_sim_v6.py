#!/usr/bin/env python3
"""
rum_sim_v6.py
-------------
Real-world map + next-day forecast simulation using v6_real_world_data package.

V6 objective:
  - Keep a larger owned fleet (2x baseline),
  - Deploy only an optimizer-selected active subset for tomorrow's forecast.
"""

from __future__ import annotations

import os
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from v6_real_world_data.bbbike_map_sampler import suggest_sindelfingen_depot_xy
from v6_real_world_data.config import DepotConfig, FleetTierConfig, SimulationConfig
from v6_real_world_data.deployment import choose_optimal_deployment, scale_owned_fleet
from v6_real_world_data.open_meteo_weather import fetch_save_default_stuttgart
from v6_real_world_data.simulation import run_simulation


ROOT = Path(__file__).resolve().parent
MAP_XZ = ROOT / "v6_real_world_data" / "planet_8.317,48.426_9.898,49.134.osm.csv.xz"
WEATHER_CSV = ROOT / "v6_real_world_data" / "open_meteo_stuttgart_hourly_forecast_1d.csv"


def _ensure_weather_csv() -> str:
    if not WEATHER_CSV.exists():
        fetch_save_default_stuttgart(out_csv=WEATHER_CSV, past_days=0, forecast_days=1)
    return str(WEATHER_CSV)


def build_config() -> SimulationConfig:
    depot_x, depot_y = suggest_sindelfingen_depot_xy(str(MAP_XZ))

    # Baseline fleet from v5 profile, then owned fleet is scaled by 2x in v6.
    base_fleet = [
        FleetTierConfig("Standard", skill_k=1, cost_multiplier=1.0, num_available=5),
        FleetTierConfig("Advanced", skill_k=2, cost_multiplier=1.8, num_available=1),
    ]
    owned_fleet = scale_owned_fleet(base_fleet, multiplier=2.0)

    return SimulationConfig(
        total_periods=24,  # next-day forecast horizon
        planning_horizon_periods=4,
        commitment_window_periods=1,
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
        fleet=owned_fleet,
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
    owned_cfg = build_config()
    decision = choose_optimal_deployment(owned_cfg, owned_cfg.fleet, evaluation_periods=24)
    deployed_cfg = replace(owned_cfg, fleet=decision.deployed_fleet)
    summary = run_simulation(deployed_cfg)

    print("\n-- V6 deployment decision ------------------------------------")
    print(f"  Owned fleet total     : {decision.owned_total}")
    print(f"  Deployed fleet total  : {decision.deployed_total} ({decision.utilization:.1%} utilization)")
    print(f"  Objective (24h)       : {decision.objective:.1f}")
    print(f"  Owned fleet by tier   : {[f'{t.name}(n={t.num_available},k={t.skill_k})' for t in owned_cfg.fleet]}")
    print(f"  Active fleet by tier  : {[f'{t.name}(n={t.num_available},k={t.skill_k})' for t in decision.deployed_fleet]}")

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
