# V6 Real-World Map + Weather + Deployment Standardization Process

## Goal
- Integrate the BBBike `.xz` area file in `v5_real_world_data`.
- Integrate Open-Meteo weather for operational forecasting.
- Run model fleet and control-group fleet on the **same map and same weather**.
- Keep simulation architecture compatible with existing rolling-horizon model.

## What We Found In the BBBike File
- File used: `planet_8.317,48.426_9.898,49.134.osm.csv.xz`.
- The stream contains tab-separated OSM element rows (mostly `node <id>`) and does **not** expose lat/lon columns directly.
- The filename itself contains the area bounding box:
  - `lon_min=8.317`, `lat_min=48.426`
  - `lon_max=9.898`, `lat_max=49.134`

## Implementation Strategy (Map)

### 1) BBBike adapter module
- Added `v5_real_world_data/bbbike_map_sampler.py`.
- Core logic:
  1. Parse bbox from filename.
  2. Read node IDs from `.xz`.
  3. Deterministically map IDs into bbox coordinates (reproducible embedding).
  4. Convert lat/lon to local `(x, y)` in km for current model compatibility.
- This gives a stable real-area spatial pool without changing solver interfaces.

### 2) Task generation from map area
- Updated `v5_real_world_data/dynamic_env.py`.
- If `bbbike_xz_path` is set in config:
  - build a local task point pool from `.xz`.
  - sample task coordinates from this pool instead of uniform synthetic grid.
- If no map path is set, old grid-based behavior still works.

### 3) Sindelfingen depot
- `bbbike_map_sampler.py` includes `suggest_sindelfingen_depot_xy()`.
- Depot is projected from Mercedes-Benz Sindelfingen plant area coordinates into the same local `(x, y)` frame.

## Implementation Strategy (Weather)

### 1) Open-Meteo module
- Added `v5_real_world_data/open_meteo_weather.py`.
- Uses `openmeteo-requests` + cache + retry.
- Pulls hourly variables:
  - rain, showers, snowfall, visibility, cloud cover (+ low/mid/high),
  - sunshine duration, temperature, is_day.
- Pulls daily variables:
  - daylight duration, uv index max.
- Combines into one hourly table for **14 days (7 past + 7 forecast)**.

### 2) Simulation wiring
- Updated `v5_real_world_data/simulation.py` and `config.py`.
- New config keys:
  - `open_meteo_hourly_csv`
  - `bbbike_xz_path`
  - `bbbike_sampling_pool_size`
- If weather CSV is provided, weather/lighting in the period loop come from that file.

## New Run Files

### 1) `rum_sim_v6.py`
- Real-world single-run entry script for v6.
- Uses:
  - BBBike `.xz` map area sampling,
  - Open-Meteo **next-day forecast** CSV,
  - Sindelfingen depot projection.
- Includes deployment optimization before the final simulation run.

### 2) `run_comp_v6vsCG.py`
- Paired comparison of model fleet vs control-group fleet for v6.
- Uses the same:
  - map file,
  - weather file,
  - deployment decision basis.

### 3) `run_comp_v6_demo_small_area.py`
- Demo paired comparison with reduced map sampling pool and lighter workload.
- Keeps the same deployment-selection logic and fairness structure.

## V6 Fleet & Objective Policy

### A) Larger owned fleet with optimized deployment
- V6 models a larger owned fleet (2x baseline) and selects an active subset
  from forecast-driven evaluation.
- Deployment optimizer evaluates candidate active fleet sizes on 24-hour data
  and picks the minimum objective policy.

### B) Control-group standardization
- Control group is standardized as a **single all-advanced tier**:
  - highest capability/cost profile,
  - vehicle count equal to deployed total in the model scenario.

### C) Equipment-only objective economics
- Penalty-factor effects were removed from objective construction:
  - no fixed deployment surcharge term,
  - no overqualification surcharge term.
- Cost modeling now follows equipment-weighted distance economics.

## Data Quick Selection Process

Use this quick checklist for area/data quality:

1. **Area relevance**
   - bbox must include your operation center and task area.
   - for this setup: Stuttgart region + Sindelfingen included.

2. **Topology richness**
   - `.xz` should contain a large node universe (not tiny extracts).
   - enough spatial variety for task sampling.

3. **Temporal continuity**
   - weather must cover full experiment horizon.
   - here: exactly 14 days hourly (336 slots).

4. **Variable coverage**
   - required: rain/showers/snowfall, visibility, cloud layers, sunshine/daylight.
   - all included in Open-Meteo fetch profile.

5. **Comparability**
   - identical map/weather/time horizon between model and control group.
   - enforced in comparison script.

## Why This Design
- Minimizes disruption to existing model architecture.
- Introduces real-world geography and weather quickly.
- Preserves paired experimental rigor (fair A/B fleet comparison).
- Adds operational realism for staffing/deployment decisions:
  - own more vehicles than actively deploy,
  - deploy based on forecast-day conditions.
- Keeps extension path open for future upgrades:
  - full OSM geometry routing,
  - historical route replay,
  - multi-depot real operations.
