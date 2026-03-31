#!/usr/bin/env python3
"""
run_simulation.py
═════════════════
Entry point for the HF-MDBOVRP rolling-horizon simulation.

HOW TO USE
──────────
1.  Place this file in the folder that CONTAINS your package folder.
    Your directory layout should look like this:

        your_project/
        ├── run_simulation.py          ← this file
        └── hf_mdbovrp/               ← your package folder
            ├── __init__.py
            ├── config.py
            ├── dynamic_env.py
            ├── environment.py
            ├── fleet.py
            ├── model_builder.py
            ├── rolling_horizon.py
            └── simulation.py

    If your package folder has a DIFFERENT name, change the import on
    line ~50 to match.

2.  Edit the SimulationConfig block (marked ▶ EDIT HERE) below.
    Every parameter has an inline comment explaining what it does
    and what to set it to.

3.  Run from your terminal:
        python run_simulation.py

4.  Results are printed to the console and saved as a JSON file in
    the folder specified by results_dir.

BATCH / PARAMETER SWEEP
────────────────────────
At the bottom of this file there is an optional batch-run example.
Uncomment it to sweep over multiple configurations automatically.

REQUIREMENTS
────────────
    pip install pyvrp
"""

import sys
import os

# ── Make sure Python can find the package ─────────────────────────────────────
# This adds the folder containing run_simulation.py to sys.path so that
# "import hf_mdbovrp" resolves to the sibling package folder.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hf_mdbovrp.config import SimulationConfig, FleetTierConfig, DepotConfig
from hf_mdbovrp.simulation import run_simulation, run_batch


# ══════════════════════════════════════════════════════════════════════════════
# ▶ EDIT HERE – All simulation parameters are set in this block.
#   Read each comment carefully before changing a value.
# ══════════════════════════════════════════════════════════════════════════════

config = SimulationConfig(

    # ── Time ──────────────────────────────────────────────────────────────────
    #
    # total_periods : How many decision points (hours) to simulate.
    #                 24 = one full day.   168 = one week.
    #                 Each period triggers: weather update → new tasks arrive
    #                 → full PyVRP solve → dispatch.
    total_periods=24,

    # planning_horizon_periods : Conceptual look-ahead window.
    #   The current solver uses the full pending pool each period, so this
    #   acts as documentation / future extension hook.  Keep ≥ commitment_window.
    planning_horizon_periods=4,

    # commitment_window_periods : How many periods' routes are "committed"
    #   before re-solving.  Currently 1 = re-solve every period (maximum
    #   adaptivity to weather changes).  Increase to reduce solver calls.
    commitment_window_periods=1,

    # ── Spatial ───────────────────────────────────────────────────────────────
    #
    # grid_size : Task and depot coordinates are drawn from [0, grid_size]².
    #   Units are arbitrary (treated as km-like by the solver).
    #   Larger grid → longer routes → higher cost numbers.
    grid_size=100.0,

    # ── Task arrivals ──────────────────────────────────────────────────────────
    #
    # tasks_per_period_mean : Average number of new data-collection tickets
    #   per period.  Sampled from Poisson(λ).
    #   Set tasks_per_period_fixed to an int to disable the Poisson draw
    #   and use a fixed count instead (useful for controlled benchmarks).
    tasks_per_period_mean=6.0,
    tasks_per_period_fixed=None,   # e.g. set to 5 for exactly 5 tasks/period

    # max_active_tasks : Hard cap on the pending task pool.
    #   Prevents runaway growth if dispatch < arrival over many periods.
    #   Tasks beyond this cap are silently dropped (oldest tasks are kept).
    #   Rule of thumb: keep ≤ 5× your total fleet size for reasonable solve times.
    max_active_tasks=100,

    # road_domain_weights : Relative probability of each road type for new tasks.
    #   Higher Urban weight → more Req=2 tasks → more Advanced vehicles needed.
    #   Weights do not need to sum to 1.0.
    road_domain_weights={
        "Highway": 0.30,   # easiest  (road_domain_score = 0)
        "Rural":   0.30,   # medium   (road_domain_score = 1)
        "Urban":   0.40,   # hardest  (road_domain_score = 2)
    },

    # ── Weather ────────────────────────────────────────────────────────────────
    #
    # initial_weather : Starting weather state at t=0.
    initial_weather="Clear",

    # weather_transitions : Markov transition matrix.
    #   weather_transitions[FROM][TO] = probability.
    #   Each row MUST sum to exactly 1.0.
    #   To simulate stable sunny weather: increase Clear→Clear probability.
    #   To simulate a stormy day: increase Rain→Rain.
    weather_transitions={
        "Clear": {"Clear": 0.70, "Rain": 0.20, "Fog": 0.10},
        "Rain":  {"Clear": 0.30, "Rain": 0.60, "Fog": 0.10},
        "Fog":   {"Clear": 0.40, "Rain": 0.10, "Fog": 0.50},
    },

    # ── Lighting ───────────────────────────────────────────────────────────────
    #
    # lighting_cycle : List of lighting states indexed by [period % len(cycle)].
    #   Default below is a 24-hour day.  Adjust the Night/Dusk/Day split to
    #   match your test region's latitude / season.
    #   For longer simulations (total_periods > 24) the list wraps automatically.
    lighting_cycle=(
        ["Night"] * 6    # t=0..5   (00:00–05:59)
        + ["Dusk"]  * 2  # t=6..7   (06:00–07:59)
        + ["Day"]   * 12 # t=8..19  (08:00–19:59)
        + ["Dusk"]  * 2  # t=20..21 (20:00–21:59)
        + ["Night"] * 2  # t=22..23 (22:00–23:59)
    ),

    # ── Fleet ──────────────────────────────────────────────────────────────────
    #
    # fleet : List of FleetTierConfig objects.  Each represents one tier.
    #
    #   name            : label shown in output and saved to JSON.
    #   skill_k         : ordinal capability level (must be ≥ 1).
    #                     A vehicle of skill_k=1 can only serve Req=1 tasks.
    #                     A vehicle of skill_k=2 can serve Req=1 AND Req=2.
    #   cost_multiplier : per-unit-distance cost factor Ck ≥ 1.
    #                     Advanced vehicles are more expensive.
    #   num_available   : fleet size for this tier.
    #   start_depot_idx : 0-based index into the depots list (multi-depot routing).
    #
    # Add more tiers (e.g. skill_k=3) for finer skill granularity.
    fleet=[
        FleetTierConfig("Standard", skill_k=1, cost_multiplier=1.0, num_available=4),
        FleetTierConfig("Advanced", skill_k=2, cost_multiplier=1.5, num_available=2),
    ],

    # ── Depots ─────────────────────────────────────────────────────────────────
    #
    # depots : List of DepotConfig(name, x, y).
    #   All vehicles start and end their routes at their assigned depot.
    #   For multi-depot: add entries here and set start_depot_idx on each
    #   FleetTierConfig above.
    depots=[
        DepotConfig("HQ", x=50.0, y=50.0),
        # DepotConfig("NorthBase", x=20.0, y=80.0),   # uncomment to add a depot
    ],

    # ── Requirement scoring ────────────────────────────────────────────────────
    #
    # These three dicts define the ordinal component scores that feed into
    # Req_j = f(E_j) (Phase 1a of the thesis).
    # Each key must appear in the corresponding weather_transitions /
    # lighting_cycle / road_domain_weights above.
    # Higher score = harder environment.
    weather_score={
        "Clear": 0,
        "Rain":  1,
        "Fog":   2,
    },
    lighting_score={
        "Day":   0,
        "Dusk":  1,
        "Night": 2,
    },
    road_domain_score={
        "Highway": 0,
        "Rural":   1,
        "Urban":   2,
    },

    # req_thresholds / req_levels : Define the score→requirement mapping.
    #   Combined score = weather_score + lighting_score + road_domain_score.
    #   score <= req_thresholds[0]   → req_levels[0]
    #   score <= req_thresholds[1]   → req_levels[1]   (if exists)
    #   score >  req_thresholds[-1]  → req_levels[-1]
    #   len(req_thresholds) == len(req_levels) - 1  (always).
    #
    # Default (2 levels):
    #   score 0–2 → Req=1 (Standard vehicle sufficient)
    #   score 3–6 → Req=2 (Advanced vehicle required)
    #
    # For 3 levels:
    #   req_thresholds=[1, 3], req_levels=[1, 2, 3]
    #   and add skill_k=3 vehicles to the fleet.
    req_thresholds=[2],
    req_levels=[1, 2],

    # ── Solver ─────────────────────────────────────────────────────────────────
    #
    # solver_max_runtime : PyVRP solve budget per period (seconds).
    #   2–5s  : small instances (< 20 tasks/solve)
    #   5–15s : medium instances (20–50 tasks/solve)
    #   30s+  : large instances (50–150 tasks/solve)
    #   Total wall time ≈ total_periods × solver_max_runtime.
    solver_max_runtime=5.0,

    # solver_seed : Random seed for PyVRP's HGA.
    #   Change this (with the same random_seed) to get solver variance data.
    solver_seed=42,

    # coord_scale : Multiply coordinates before converting to int distances.
    #   Leave at 1.0 unless your coordinates are very small (e.g. fractions).
    coord_scale=1.0,

    # cost_scale : Converts cost_multiplier → PyVRP integer unit cost.
    #   cost_scale=100 means a multiplier of 1.5 → unit cost 150.
    cost_scale=100.0,

    # big_factor : prohibitive_distance = max_edge_distance × big_factor.
    #   Controls the penalty magnitude for incompatible assignments.
    #   Increase if the solver still violates skill constraints.
    big_factor=1000.0,

    # ── Output ─────────────────────────────────────────────────────────────────
    #
    # random_seed : Master RNG seed (task positions, Poisson draws).
    #   Change for a different stochastic run. Keep fixed for reproducibility.
    random_seed=0,

    # verbose : Print per-period progress to the console.
    #   Set to False for batch runs to reduce terminal clutter.
    verbose=True,

    # save_results : Write a timestamped JSON file after the simulation.
    save_results=True,

    # results_dir : Folder for JSON output.  Created if it does not exist.
    results_dir="simulation_results",
)


# ══════════════════════════════════════════════════════════════════════════════
# Run
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    summary = run_simulation(config)

    # Quick recap printed after the simulation banner
    print("\n── Quick stats ─────────────────────────────────────────────")
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
    print("────────────────────────────────────────────────────────────")


# ══════════════════════════════════════════════════════════════════════════════
# OPTIONAL: Batch / parameter sweep
# ──────────────────────────────────────────────────────────────────────────────
# Uncomment this block to run multiple experiments automatically.
# Each entry in `configs` is an independent SimulationConfig.
# Results are saved as separate JSON files.
#
# from dataclasses import replace
# import copy
#
# if __name__ == "__main__":
#
#     base = config                  # reuse the config defined above
#
#     configs = []
#     for seed in [0, 1, 2, 3, 4]:                  # 5 random seeds
#         for solver_t in [2.0, 5.0, 10.0]:          # 3 solver budgets
#             c = replace(
#                 base,
#                 random_seed=seed,
#                 solver_max_runtime=solver_t,
#                 verbose=False,           # suppress console output in batch
#             )
#             configs.append(c)
#
#     print(f"Running {len(configs)} simulations …")
#     summaries = run_batch(configs, parallel=False)
#
#     for cfg, s in zip(configs, summaries):
#         print(
#             f"seed={cfg.random_seed}  solver={cfg.solver_max_runtime}s  "
#             f"dispatched={s.total_tasks_dispatched}  cost={s.total_route_cost:.0f}"
#         )
