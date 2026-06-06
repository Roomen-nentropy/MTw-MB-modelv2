# HF-MDBOVRP — Heterogeneous Fleet Multi-Depot Balanced Open VRP

Skill-based vehicle routing for ADAS data-collection fleets. Extends a homogeneous MDBOVRP baseline with heterogeneous vehicles, operational-design-domain (ODD) compatibility constraints, and an economic routing objective. The final implementation is **Version 8** (`v8/`), built on [PyVRP](https://pyvrp.org/).

---

## What this does

Test fleets for automated-driving validation are heterogeneous: some vehicles carry high-fidelity sensor suites, others standard optical setups. Not every vehicle is permitted in every environmental scenario (e.g. heavy rain at night).

The simulation:

1. Maps each task's environment (weather, lighting, road domain) to a minimum sensor tier `Req_j`.
2. Enforces hard feasibility: a vehicle may serve a task only if `Skill_k >= Req_j`.
3. Minimises economic routing cost (`distance × tier multiplier`), with an optional overqualification surcharge when a higher tier is used where a lower one would suffice.
4. Re-plans on a rolling horizon as weather and demand evolve.

Version 8 adds **service-constrained deployment**: before routing, an optimiser selects how many owned vehicles to activate, subject to dispatch-rate and backlog limits, and compares the heterogeneous fleet to a **tier-matched all-premium control group**.

---

## Installation

```bash
pip install pyvrp numpy
pip install -r v7/requirements_openmeteo.txt   # weather client (V5+)
```

Python 3.9+ recommended.

**Map data:** place the BBBike extract at  
`v7/planet_8.317,48.426_9.898,49.134.osm.xz`  
(large file; not stored in this repository). On first run, weather is fetched from Open-Meteo and cached to `v7/open_meteo_stuttgart_hourly_forecast_1d.csv`.

---

## Repository layout

```
Simulation/
├── v8/                    # Final package (V8): config, deployment, control group + v7 re-exports
├── v7/                    # Shared simulation core (used by v8 at runtime)
├── rum_sim_v8.py          # Single-scenario entry point (V8)
├── run_comp_v8vsCG.py     # Paired model vs control-group comparison (V8)
├── v6_real_world_data/    # Earlier real-world integration (V6)
├── v5_real_world_data/    # Map + Open-Meteo integration (V5)
├── v4_setup/, v3_setup/   # Earlier experimental versions
├── hf_mdbovrp/            # Original baseline package
└── run_*.py, rum_sim_*.py # Version-specific runners (V3–V8)
```

Earlier versions (V3–V7) remain for reproducibility of the development arc reported in the thesis; **V8 is the artefact to run for the final results**.

---

## Quick start (Version 8)

### Single simulation

```bash
python rum_sim_v8.py
```

### Paired comparison (heterogeneous fleet vs tier-matched control)

```bash
python run_comp_v8vsCG.py
```

Comparison modes (default: `medium`):

```bash
COMPARE_MODE=quick    # fewer periods / seeds
COMPARE_MODE=medium
COMPARE_MODE=full     # longest; use for final replication
```

Optional seed count:

```bash
COMPARE_SEEDS=3
```

PowerShell:

```powershell
$env:COMPARE_MODE='medium'; python run_comp_v8vsCG.py
```

---

## Core concepts

### Vehicle tiers

| Field | Meaning |
|--------|---------|
| `skill_k` | Capability tier (ordinal). Higher = more capable. |
| `cost_multiplier` | Distance cost weight (e.g. 1.0 standard, 1.35 advanced). |

### Requirement mapping

Each task has `(weather, lighting, road_domain)`. A scoring function maps this to `Req_j ∈ {1, 2}`. Vehicles with `Skill_k < Req_j` cannot be assigned (prohibitive edges in the PyVRP model).

### Economic objective

The router minimises tier-weighted travel distance. V8 deployment chooses the active fleet size under service gates (default: dispatch rate ≥ 92%, backlog ratio ≤ 8%).

### Control group (V8)

The control fleet matches the deployed model fleet in **count and tier positions**, but every position is upgraded to the highest skill and cost multiplier — a demanding upper reference, not a typical incumbent.

---

## Other version runners

| Version | Single run | Paired comparison |
|---------|------------|-------------------|
| Baseline | `run_simulation.py` | `run_comparative_simulation.py` |
| V3 | `run_sim_v3.py` | `run_comp_V3vsCG.py` |
| V4 | `run_sim_v4.py` | `run_comp_V4vsCG.py` |
| V5 | `rum_sim_v5.py` | `run_comp_v5vsCG.py` |
| V6 | `rum_sim_v6.py` | `run_comp_v6vsCG.py` |
| V7 | `rum_sim_v7.py` | `run_comp_v7vsCG.py` |
| **V8** | **`rum_sim_v8.py`** | **`run_comp_v8vsCG.py`** |

All comparative scripts support `COMPARE_MODE` and `COMPARE_SEEDS` where applicable.

---

## Output

- Console summaries: total cost, cost per task, dispatch rate, backlog.
- Optional JSON under `simulation_results/` when `save_results=True` in config.

---

## Extending the model

- **Third tier:** add `skill_k=3` vehicles and extend requirement thresholds in `v7/config.py` / `v8/config.py`.
- **Real demand:** replace synthetic task generation in `v7/dynamic_env.py` with operational arrival data; the routing interface is unchanged.
- **Cost calibration:** tune `cost_multiplier` and `overqualification_cost_penalty_per_level` in config; V8 sensitivity runs vary these parameters.

---

## Citation / context

Master's thesis simulation artefact (WU). For methodology, results, and limitations, refer to the submitted thesis document; this repository contains the runnable implementation only.
