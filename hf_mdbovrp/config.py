"""
config.py – Master simulation configuration.

Everything in SimulationConfig is a parameter you can change
before calling run_simulation(). See run_simulation.py for a
fully-annotated example of how to set each field.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Sub-configs (nested inside SimulationConfig)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FleetTierConfig:
    """
    One tier of the heterogeneous fleet.

    name            : Display name (e.g. "Standard", "Advanced").
    skill_k         : Ordinal skill level (1 = base, 2 = advanced, …).
                      A vehicle can only legally serve tasks whose
                      req_level ≤ skill_k.
    cost_multiplier : Per-unit-distance cost factor Ck ≥ 1.
                      A value of 1.5 means this tier costs 50 % more per km.
    num_available   : Fleet size for this tier.
    start_depot_idx : Which depot index (0-based) this tier starts from.
    """
    name: str
    skill_k: int
    cost_multiplier: float
    num_available: int = 1
    start_depot_idx: int = 0


@dataclass
class DepotConfig:
    """A depot location in coordinate space."""
    name: str
    x: float
    y: float


# ─────────────────────────────────────────────────────────────────────────────
# Master config
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SimulationConfig:
    """
    Complete parameter set for one rolling-horizon simulation run.

    All fields have sensible defaults so you only need to touch
    the parameters you want to change.
    """

    # ── Time ─────────────────────────────────────────────────────────────────
    total_periods: int = 24
    """
    Number of planning periods (decision points) to simulate.
    Each period corresponds to one rolling-horizon cycle
    (look-ahead → optimise → commit → roll-forward).
    With lighting_cycle of length 24, one period ≈ 1 hour of a real day.
    """

    planning_horizon_periods: int = 4
    """
    How many future periods each solve looks ahead.
    Stored in the results for analysis; in the current single-solve-per-period
    implementation the full pending task pool already acts as the look-ahead.
    Extend rolling_horizon.py to use this for explicit horizon filtering.
    """

    commitment_window_periods: int = 1
    """
    How many periods' routes are committed before re-solving.
    A value of 1 means we dispatch everything computed this period and
    re-optimise next period with updated weather/task information.
    """

    # ── Spatial ───────────────────────────────────────────────────────────────
    grid_size: float = 100.0
    """
    Task and depot coordinates are drawn from [0, grid_size]².
    Increase for a more spread-out geography.
    """

    # ── Task arrival ──────────────────────────────────────────────────────────
    tasks_per_period_mean: float = 6.0
    """
    Mean number of new data-collection tasks arriving each period.
    Sampled from a Poisson distribution unless tasks_per_period_fixed is set.
    """

    tasks_per_period_fixed: Optional[int] = None
    """
    If not None, exactly this many tasks arrive each period (overrides Poisson).
    Useful for controlled experiments with a constant workload.
    """

    max_active_tasks: int = 150
    """
    Hard cap on unfinished tasks in the pending pool at any time.
    Arriving tasks beyond this cap are silently dropped (oldest tasks stay).
    Prevents the VRP instance from growing without bound.
    """

    # ── Road domain ────────────────────────────────────────────────────────────
    road_domain_weights: Dict[str, float] = field(default_factory=lambda: {
        "Highway": 0.30,
        "Rural":   0.30,
        "Urban":   0.40,
    })
    """
    Relative probability weights for the road domain of newly arriving tasks.
    Does not need to sum to 1.0 (normalised internally).
    Urban tasks are hardest (score=2), Highway easiest (score=0).
    """

    # ── Weather Markov chain ───────────────────────────────────────────────────
    initial_weather: str = "Clear"
    """Starting weather state at period 0."""

    weather_transitions: Dict[str, Dict[str, float]] = field(default_factory=lambda: {
        "Clear": {"Clear": 0.70, "Rain": 0.20, "Fog": 0.10},
        "Rain":  {"Clear": 0.30, "Rain": 0.60, "Fog": 0.10},
        "Fog":   {"Clear": 0.40, "Rain": 0.10, "Fog": 0.50},
    })
    """
    First-order Markov transition matrix for weather.
    weather_transitions[current_state][next_state] = probability.
    Probabilities for each row must sum to 1.0.
    Add extra weather states (e.g. "Snow") by extending this dict AND
    weather_score below.
    """

    # ── Lighting ──────────────────────────────────────────────────────────────
    lighting_cycle: List[str] = field(default_factory=lambda:
        ["Night"] * 6   # periods  0–5   midnight → early morning
        + ["Dusk"]  * 2 # periods  6–7   dawn
        + ["Day"]   * 12# periods  8–19  full daylight
        + ["Dusk"]  * 2 # periods 20–21  dusk
        + ["Night"] * 2 # periods 22–23  night
    )
    """
    Deterministic lighting schedule.  lighting_cycle[period % len(lighting_cycle)]
    gives the lighting state for that period.
    Default is a 24-entry day cycle. For longer simulations (total_periods > 24)
    the list wraps around automatically.
    """

    # ── Fleet ─────────────────────────────────────────────────────────────────
    fleet: List[FleetTierConfig] = field(default_factory=lambda: [
        FleetTierConfig("Standard", skill_k=1, cost_multiplier=1.0, num_available=3),
        FleetTierConfig("Advanced", skill_k=2, cost_multiplier=1.5, num_available=2),
    ])
    """
    List of vehicle tier configurations.
    Add more tiers for finer skill granularity (skill_k=3, etc.).
    The sum of num_available across tiers is your total fleet size.
    """

    # ── Depots ────────────────────────────────────────────────────────────────
    depots: List[DepotConfig] = field(default_factory=lambda: [
        DepotConfig("HQ", x=50.0, y=50.0),
    ])
    """
    Depot locations.  Multi-depot routing is supported: add more entries and
    set start_depot_idx on each FleetTierConfig to assign tiers to depots.
    """

    # ── Requirement scoring ────────────────────────────────────────────────────
    weather_score: Dict[str, int] = field(default_factory=lambda: {
        "Clear": 0, "Rain": 1, "Fog": 2,
    })
    """
    Ordinal degradation score per weather state.
    Higher = harder environment.  Must cover every state in weather_transitions.
    """

    lighting_score: Dict[str, int] = field(default_factory=lambda: {
        "Day": 0, "Dusk": 1, "Night": 2,
    })
    """Ordinal degradation score per lighting state."""

    road_domain_score: Dict[str, int] = field(default_factory=lambda: {
        "Highway": 0, "Rural": 1, "Urban": 2,
    })
    """
    Ordinal degradation score per road domain.
    Must cover every key in road_domain_weights.
    """

    req_thresholds: List[int] = field(default_factory=lambda: [2])
    """
    Score breakpoints for the requirement mapping f: score → Req_j.
    With thresholds=[2] and req_levels=[1,2]:
        score 0–2 → Req_j = 1  (standard task)
        score 3–6 → Req_j = 2  (advanced task)
    Add more breakpoints for finer granularity, e.g.
        thresholds=[1, 3], req_levels=[1, 2, 3]  gives three requirement levels.
    len(req_thresholds) must equal len(req_levels) - 1.
    """

    req_levels: List[int] = field(default_factory=lambda: [1, 2])
    """Requirement levels output by the mapping. See req_thresholds."""

    # ── Solver ────────────────────────────────────────────────────────────────
    solver_max_runtime: float = 5.0
    """
    PyVRP solve-time budget in seconds per planning period.
    Larger values give better solutions at the cost of wall time.
    Rule of thumb: 2–5 s for < 30 tasks/period, 10–30 s for 50+ tasks/period.
    """

    solver_seed: int = 42
    """Random seed passed to PyVRP's HGA for reproducible solutions."""

    coord_scale: float = 1.0
    """Multiplier applied to coordinates before converting to integer distances."""

    cost_scale: float = 100.0
    """Multiplier that converts cost_multiplier to PyVRP's integer unit cost."""

    big_factor: float = 1000.0
    """
    Prohibitive distance = max_edge_distance × big_factor.
    Controls how strongly incompatible assignments are penalised.
    Increase if the solver occasionally violates skill constraints.
    """

    # ── Reproducibility & output ───────────────────────────────────────────────
    random_seed: int = 0
    """Master RNG seed. Change this to get a different stochastic trajectory."""

    verbose: bool = True
    """Print per-period progress to stdout."""

    save_results: bool = True
    """Write a JSON results file to results_dir after the simulation."""

    results_dir: str = "simulation_results"
    """Directory for JSON output files (created if it does not exist)."""
