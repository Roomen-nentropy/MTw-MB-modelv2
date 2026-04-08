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
├── run_simulation.py            # Baseline simulation entry point
├── run_controlgroup.py          # Control-group single-run entry point
├── run_comparative_simulation.py# Paired A/B comparative study runner
├── run_cost_optimization.py     # Parameter-sweep optimization runner
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

### Baseline vs Control Group (single run)

```bash
python run_controlgroup.py
```

This keeps baseline settings and swaps fleet composition to a control-group construction.

### Paired Comparative Study (same seed conditions, Fleet A vs Fleet B)

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

### Cost Optimization Sweep

```bash
python run_cost_optimization.py
```

Fast smoke mode:

```powershell
$env:FAST_SWEEP='1'; python run_cost_optimization.py
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
