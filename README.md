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
hf_mdbovrp/
│
├── main.py                  # Entry point — build model and run solver
├── fleet.py                 # Vehicle class with skill_k and cost_multiplier_k
├── tasks.py                 # Task/ticket class with environmental tuple and req_j
├── compatibility.py         # Requirement mapping function + compatibility matrix builder
├── cost_matrix.py           # Per-vehicle economic cost matrix builder
├── model.py                 # PyVRP model construction and HGA configuration
├── validate.py              # Post-solve compliance checker
└── config.py                # Thresholds, penalty values, solver settings
```

---

## Quick Start

```python
from fleet import Vehicle
from tasks import Task
from compatibility import build_compatibility_matrix
from cost_matrix import build_cost_matrix
from model import build_and_solve

# 1. Define your fleet
vehicles = [
    Vehicle(id=0, skill_k=1, cost_multiplier_k=1.0),   # Standard
    Vehicle(id=1, skill_k=2, cost_multiplier_k=2.0),   # High-Fidelity
]

# 2. Define your tasks (tickets)
tasks = [
    Task(id=0, weather="Clear",  lighting="Day",   road_domain="Highway"),
    Task(id=1, weather="Rain",   lighting="Night",  road_domain="Urban"),
    Task(id=2, weather="Fog",    lighting="Dusk",   road_domain="Rural"),
]

# 3. Provide your distance matrix (n_tasks × n_tasks, in metres or seconds)
distance_matrix = ...  # your numpy array here

# 4. Run
solution = build_and_solve(vehicles, tasks, distance_matrix)
```

---

## Core Concepts

### Vehicle Tiers (`fleet.py`)

Each vehicle has two parameters:

| Parameter | Type | Description |
|---|---|---|
| `skill_k` | `int` | Sensor capability tier. `1` = Standard, `2` = High-Fidelity |
| `cost_multiplier_k` | `float` | Economic cost weight. `1.0` for standard, `>1.0` for high-end |

```python
@dataclass
class Vehicle:
    id: int
    skill_k: int           # 1 or 2
    cost_multiplier_k: float  # >= 1.0
```

### Task Requirement Mapping (`compatibility.py`)

Each task carries an environmental tuple `(weather, lighting, road_domain)`. The function `map_requirement()` converts this into a minimum skill level `req_j`:

```python
def map_requirement(weather: str, lighting: str, road_domain: str) -> int:
    score = weather_score[weather] + lighting_score[lighting] + domain_score[road_domain]
    return 2 if score >= 2 else 1
```

Default scoring weights (edit in `config.py`):

| Dimension | Value | Score |
|---|---|---|
| Weather | Clear / Rain / Fog | 0 / 1 / 2 |
| Lighting | Day / Dusk / Night | 0 / 1 / 2 |
| Road Domain | Highway / Rural / Urban | 0 / 1 / 1 |

> **These thresholds are placeholders.** Calibrate them with your domain/legal team before running production jobs.

### Compatibility Matrix (`compatibility.py`)

```python
a[j][k] = 1  if vehicle[k].skill_k >= task[j].req_j
           0  otherwise
```

A `0` entry is a hard block — that vehicle will never be assigned that task, regardless of how geographically convenient it is.

Print and manually sanity-check this matrix before running the solver.

### Economic Cost Matrix (`cost_matrix.py`)

```python
cost_matrix_k[i][j] = distance_matrix[i][j] * vehicle_k.cost_multiplier_k
```

One cost matrix is generated per vehicle tier. PyVRP receives the appropriate matrix for each vehicle type. This forces the solver to prefer cheaper vehicles for routine tasks and only deploy expensive high-fidelity setups when the compatibility matrix requires it.

### Hard Skill Constraint

Enforced in the HGA via a large penalty on any assignment where `a[j][k] == 0`:

```python
BIG_PENALTY = 1e9  # defined in config.py
```

If PyVRP's version supports native per-client vehicle filtering, use that instead (preferred). Check `model.py` for the current enforcement method.

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

## Validating a Solution

Always run the compliance check before accepting any output:

```python
from validate import validate_solution

is_valid = validate_solution(solution, compatibility_matrix)
# Prints any vehicle–task violations found
# Returns True only if zero violations exist
```

Zero violations is a hard requirement. A solution with any compatibility violations must be discarded.

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
