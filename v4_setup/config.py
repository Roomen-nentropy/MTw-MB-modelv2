"""
config.py – Master simulation configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class FleetTierConfig:
    name: str
    skill_k: int
    cost_multiplier: float
    num_available: int = 1
    start_depot_idx: int = 0


@dataclass
class DepotConfig:
    name: str
    x: float
    y: float


@dataclass
class SimulationConfig:
    total_periods: int = 24
    planning_horizon_periods: int = 4
    commitment_window_periods: int = 1

    grid_size: float = 100.0

    tasks_per_period_mean: float = 6.0
    tasks_per_period_fixed: Optional[int] = None
    max_active_tasks: int = 150

    road_domain_weights: Dict[str, float] = field(default_factory=lambda: {
        "Highway": 0.30,
        "Rural": 0.30,
        "Urban": 0.40,
    })

    initial_weather: str = "Clear"
    weather_transitions: Dict[str, Dict[str, float]] = field(default_factory=lambda: {
        "Clear": {"Clear": 0.70, "Rain": 0.20, "Fog": 0.10},
        "Rain": {"Clear": 0.30, "Rain": 0.60, "Fog": 0.10},
        "Fog": {"Clear": 0.40, "Rain": 0.10, "Fog": 0.50},
    })

    weather_task_rate_multiplier: Dict[str, float] = field(default_factory=lambda: {
        "Clear": 1.00,
        "Rain": 1.08,
        "Fog": 1.12,
    })
    weather_operating_cost_multiplier: Dict[str, float] = field(default_factory=lambda: {
        # Why: adverse weather increases fuel and safety overhead.
        "Clear": 1.00,
        "Rain": 1.10,
        "Fog": 1.16,
    })

    lighting_cycle: List[str] = field(default_factory=lambda:
        ["Night"] * 6 + ["Dusk"] * 2 + ["Day"] * 12 + ["Dusk"] * 2 + ["Night"] * 2
    )
    lighting_task_rate_multiplier: Dict[str, float] = field(default_factory=lambda: {
        "Day": 1.00,
        "Dusk": 1.05,
        "Night": 1.10,
    })
    lighting_operating_cost_multiplier: Dict[str, float] = field(default_factory=lambda: {
        # Why: low-light operation requires extra supervision/compliance effort.
        "Day": 1.00,
        "Dusk": 1.05,
        "Night": 1.10,
    })

    fleet: List[FleetTierConfig] = field(default_factory=lambda: [
        FleetTierConfig("Standard", skill_k=1, cost_multiplier=1.0, num_available=3),
        FleetTierConfig("Advanced", skill_k=2, cost_multiplier=1.5, num_available=2),
    ])
    depots: List[DepotConfig] = field(default_factory=lambda: [DepotConfig("HQ", x=50.0, y=50.0)])

    weather_score: Dict[str, int] = field(default_factory=lambda: {"Clear": 0, "Rain": 1, "Fog": 2})
    lighting_score: Dict[str, int] = field(default_factory=lambda: {"Day": 0, "Dusk": 1, "Night": 2})
    road_domain_score: Dict[str, int] = field(default_factory=lambda: {"Highway": 0, "Rural": 1, "Urban": 2})
    req_thresholds: List[int] = field(default_factory=lambda: [2])
    req_levels: List[int] = field(default_factory=lambda: [1, 2])

    solver_max_runtime: float = 5.0
    solver_seed: int = 42
    coord_scale: float = 1.0
    cost_scale: float = 100.0
    vehicle_fixed_cost_scale: float = 600.0
    vehicle_fixed_cost_exponent: float = 2.0
    # Why: specialist assets have nonlinear readiness/setup burden.
    overqualification_cost_penalty_per_level: float = 0.30
    # Why: using high-end assets on low-req tickets increases avoidable spend.
    big_factor: float = 1000.0

    random_seed: int = 0
    verbose: bool = True
    save_results: bool = True
    results_dir: str = "simulation_results"
