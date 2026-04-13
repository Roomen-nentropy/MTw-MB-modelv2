# HF-MDBOVRP — Heterogeneous Fleet Multi-Depot Balanced Open VRP

A skill-based vehicle routing solver for ADAS data collection fleets. Extends Morlock's (2024) MDBOVRP baseline with heterogeneous vehicle support, environmental compatibility constraints, and economic cost optimization.

Built on top of [PyVRP](https://pyvrp.org/).

---

## What This Does

Standard VRP solvers assume all vehicles are equal. This one doesn't.

Test fleets for Level 3 ADAS validation are heterogeneous — some vehicles carry high-fidelity LIDAR and thermal cameras, others carry standard optical setups. Not every vehicle is legally or technically permitted to collect data in every environmental scenario (e.g., a standard-sensor vehicle cannot operate in heavy rain at night).

This solver:
- Maps each driving task's environmental conditions (weather, lighting, road domain) to a minimum required sensor tier
- Builds a binary compatibility matrix that hard-blocks invalid vehicle–task assignments
- Replaces the standard distance objective with an economic cost objective (`distance × cost_multiplier`)
- Runs a modified Hybrid Genetic Algorithm (HGA) via PyVRP that respects all of the above

---

## Installation

```bash
pip install pyvrp numpy
```

Python 3.9+ recommended.

---

## Project Structure

```
Simulation/
├── hf_mdbovrp/
│   ├── config.py                # Simulation and fleet/depot configuration dataclasses
│   ├── dynamic_env.py           # Weather, lighting, task generation
│   ├── environment.py           # Req mapping and compatibility logic
│   ├── fleet.py                 # Vehicle tier definition
│   ├── fleet_controlgroup.py    # Control-group fleet constructor
│   ├── model_builder.py         # PyVRP model build + solve wrappers
│   ├── rolling_horizon.py       # Period-by-period planning engine
│   ├── simulation.py            # Main simulation orchestration + summaries
│   └── __init__.py
├── v3_setup/                    # V3 package (realism + comparative upgrades)
├── v4_setup/                    # V4 package (further realism/cost upgrades)
├── v5_real_world_data/          # V5 package (BBBike area + Open-Meteo integration)
├── run_simulation.py            # Baseline simulation entry point (base package)
├── run_controlgroup.py          # Baseline control-group single-run entry point
├── run_comparative_simulation.py# Baseline paired comparative runner
├── run_cost_optimization.py     # Baseline parameter-sweep optimization runner
├── run_sim_v3.py                # V3 single-run
├── run_comp_V3vsCG.py           # V3 vs control-group paired comparison
├── run_sim_v4.py                # V4 single-run
├── run_comp_V4vsCG.py           # V4 vs control-group paired comparison
├── rum_sim_v5.py                # V5 real-world single-run (BBBike + weather)
├── run_comp_v5vsCG.py           # V5 real-world paired comparison
├── run_comp_v5_demo_small_area.py # V5 demo: small area + full weather interval
└── run_demo.py                  # Small demo/legacy helper script
```

---

## Quick Start (Baseline Run)

```bash
python run_simulation.py
```

Edit parameters in `run_simulation.py` (fleet mix, task rates, weather transitions, solver runtime, etc.), then rerun.

---

## Experiment Runners

### Base / V2 Setup (`hf_mdbovrp`, `run_simulation.py`, `run_controlgroup.py`, `run_comparative_simulation.py`, `run_cost_optimization.py`)

#### Baseline vs control group (single run)

```bash
python run_controlgroup.py
```

This keeps baseline settings and swaps fleet composition to a control-group construction.

#### Paired comparative study (same seed conditions, Fleet A vs Fleet B)

```bash
python run_comparative_simulation.py
```

Useful env options:

```bash
# quick / medium / full (default: medium)
COMPARE_MODE=quick

# optional explicit number of seeds
COMPARE_SEEDS=5
```

Windows PowerShell example:

```powershell
$env:COMPARE_MODE='quick'; python run_comparative_simulation.py
```

#### Cost optimization sweep

```bash
python run_cost_optimization.py
```

Fast smoke mode:

```powershell
$env:FAST_SWEEP='1'; python run_cost_optimization.py
```

---

### V3 & V4 Setup (`run_sim_v3.py`, `run_comp_V3vsCG.py`, `run_sim_v4.py`, `run_comp_V4vsCG.py`)

These versioned runners share the same command pattern and comparison environment controls.

#### Single-run simulations

```bash
python run_sim_v3.py
python run_sim_v4.py
```

#### Paired comparisons vs control group

```bash
python run_comp_V3vsCG.py
python run_comp_V4vsCG.py
```

Shared comparison settings:

```bash
# quick / medium / full (default: medium)
COMPARE_MODE=quick

# optional explicit number of seeds
COMPARE_SEEDS=5
```

PowerShell example:

```powershell
$env:COMPARE_MODE='quick'; python run_comp_V4vsCG.py
```

---

### V5 Real-World Setup (separate instructions) (`rum_sim_v5.py`, `run_comp_v5vsCG.py`, `run_comp_v5_demo_small_area.py`)

V5 is separate because it uses:
- BBBike `.xz` area data (`v5_real_world_data/planet_8.317,48.426_9.898,49.134.osm.csv.xz`)
- Open-Meteo 14-day weather interval (7 past + 7 forecast), cached to CSV
- Real-world map sampling + Sindelfingen depot projection

Install V5 weather dependencies:

```bash
pip install -r v5_real_world_data/requirements_openmeteo.txt
```

#### Real-world single run

```bash
python rum_sim_v5.py
```

#### Real-world paired comparison (model vs control group)

```bash
python run_comp_v5vsCG.py
```

Settings for `run_comp_v5vsCG.py`:

```bash
# quick / medium / full
COMPARE_MODE=quick
```

#### Demo comparison: small map sample + full weather interval

```bash
python run_comp_v5_demo_small_area.py
```

Demo settings:

```bash
# number of paired seeds for demo script (default: 1)
DEMO_SEEDS=2
```

---

## Core Concepts

### Vehicle Tiers (`hf_mdbovrp/fleet.py`)

Each vehicle has two parameters:

| Parameter | Type | Description |
|---|---|---|
| `skill_k` | `int` | Sensor capability tier. Higher means more capable tier. |
| `cost_multiplier` | `float` | Economic cost weight. `1.0` for standard, `>1.0` for high-end |

```python
@dataclass
class VehicleTier:
    name: str
    skill_k: int
    cost_multiplier: float
```

### Task Requirement Mapping (`hf_mdbovrp/environment.py`)

Each task carries an environmental tuple `(weather, lighting, road_domain)`. The function `map_requirement()` converts this into a minimum skill level `req_j`:

```python
def compute_task_requirement_level(env: TaskEnv, mapping: TaskRequirementMapping) -> int:
    s = mapping.score(env)
    return mapping.req_from_score(s)
```

Default scoring weights (edit in `run_simulation.py` and/or `hf_mdbovrp/config.py`):

| Dimension | Value | Score |
|---|---|---|
| Weather | Clear / Rain / Fog | 0 / 1 / 2 |
| Lighting | Day / Dusk / Night | 0 / 1 / 2 |
| Road Domain | Highway / Rural / Urban | 0 / 1 / 1 |

> **These thresholds are placeholders.** Calibrate them with your domain/legal team before running production jobs.

### Compatibility Matrix (`hf_mdbovrp/environment.py`)

```python
a[j][k] = 1  if vehicle[k].skill_k >= task[j].req_j
           0  otherwise
```

A `0` entry is a hard block — that vehicle will never be assigned that task, regardless of how geographically convenient it is.

Print and manually sanity-check this matrix before running the solver.

### Economic Cost Modeling (`hf_mdbovrp/model_builder.py`)

```python
unit_distance_cost = round(tier.cost_multiplier * cost_scale)
```

PyVRP vehicle types receive tier-specific unit distance costs. This forces the solver to prefer cheaper tiers for routine tasks and reserve expensive tiers for harder cases.

### Hard Skill Constraint

Enforced via profile-specific prohibitive distances for incompatible task-tier edges in `model_builder.py`:

```python
prohibitive_distance = max_base_dist * big_factor + 1
```

See `hf_mdbovrp/model_builder.py` for implementation details.

---

## Configuration (`config.py`)

```python
# Scoring weights for requirement mapping
WEATHER_SCORES  = {"Clear": 0, "Rain": 1, "Fog": 2}
LIGHTING_SCORES = {"Day": 0, "Dusk": 1, "Night": 2}
DOMAIN_SCORES   = {"Highway": 0, "Rural": 1, "Urban": 1}
REQ_THRESHOLD   = 2          # score >= this → skill level 2 required

# Solver
BIG_PENALTY     = 1e9        # infeasibility penalty for incompatible assignments
MAX_ITERATIONS  = 10_000     # HGA stopping criterion
```

---

## Output and Results

- `run_simulation.py` and `run_controlgroup.py` print period and end-of-run summaries.
- JSON results are saved when `save_results=True` to `results_dir` (default: `simulation_results`).
- Comparative and optimization scripts print aggregate metrics directly in console.

---

## Extending the Model

### Adding a third vehicle tier

1. Add `skill_k=3` vehicles to your fleet
2. Add the corresponding `req_j=3` logic to `map_requirement()` in `config.py`
3. The compatibility matrix and constraints update automatically

### Swapping in real environmental data

Replace the static `(weather, lighting, road_domain)` tuples on each `Task` with live forecast data. The `map_requirement()` function interface stays the same.

### Adjusting cost multipliers

Cost multipliers are empirical. Start with rough ratios based on actual vehicle operating costs, then tune based on how aggressively you want the solver to conserve high-fidelity assets.
