# V6 Improvements and Iteration Process (from V5 Baseline)

## Objective
- Keep the V5 real-world stack (BBBike map + Open-Meteo integration) intact.
- Add an operational deployment layer that separates **owned fleet size** from **active deployed fleet size**.
- Shift from 14-day weather replay to **next-day forecast planning** for more operationally realistic daily staffing/deployment decisions.
- Preserve fair paired comparison against control-group policy under identical scenario assumptions.

## Analysis Approach
- Reviewed V5 and V6 run paths and package modules:
  - `rum_sim_v5.py` vs `rum_sim_v6.py`
  - `run_comp_v5vsCG.py` vs `run_comp_v6vsCG.py`
  - `v6_real_world_data/deployment.py`
  - `v6_real_world_data/config.py`, `simulation.py`, `fleet_controlgroup.py`
- Isolated the main V6 design gap addressed:
  - V5 assumes all available vehicles are always deployed.
  - Real operations often own more vehicles than are activated in a given day.
- Selected changes that add operational realism while keeping solver interfaces and map/weather integration stable.

## Candidate Changes Considered
- **Selected:** 2x owned fleet representation with optimizer-based active deployment.
- **Selected:** objective-guided deployment search over utilization candidates.
- **Selected:** next-day forecast horizon and dedicated forecast CSV workflow.
- **Selected:** control-group normalization to deployed totals (not owned totals).
- **Not selected now:** changing routing objective architecture or adding new skill levels in V6.
- **Not selected now:** introducing explicit labor shift calendars or maintenance downtime constraints.

## Implemented V6 Changes and Rationale

### 1) Owned-vs-deployed fleet architecture
- **Files:** `rum_sim_v6.py`, `v6_real_world_data/deployment.py`
- **What changed:**
  - V6 starts from the V5 baseline fleet and scales it to a larger **owned fleet** (`scale_owned_fleet(..., multiplier=2.0)`).
  - A deployment optimizer selects an active subset before running the operational simulation.
  - Deployment output includes:
    - owned total,
    - deployed total,
    - utilization ratio,
    - objective value and components.
- **Why:**
  - Better reflects practical operations where reserve capacity exists but is not always activated.
  - Enables economics-aware daily deployment decisions instead of fixed all-in dispatching.

### 2) Forecast-driven deployment optimization
- **File:** `v6_real_world_data/deployment.py`
- **What changed:**
  - Added candidate search over utilization levels (`min_utilization` to `max_utilization` by step).
  - For each candidate deployed count, V6:
    - allocates vehicles across tiers proportionally with per-tier availability limits,
    - runs a short evaluation simulation,
    - scores with a composite objective:
      - route cost
      - backlog penalty
      - undispatched-task penalty
  - Tie-break rule favors lower deployed count when objective is equal.
- **Why:**
  - Prevents over-deployment while still protecting service quality through backlog/undispatched penalties.
  - Converts deployment into an explicit optimization decision instead of a fixed assumption.

### 3) Horizon shift to next-day weather operations
- **Files:** `rum_sim_v6.py`, `v6_real_world_data/open_meteo_weather.py`
- **What changed:**
  - V6 uses a 24-hour next-day forecast path (`past_days=0`, `forecast_days=1`) and `total_periods=24`.
  - Weather source defaults to `open_meteo_stuttgart_hourly_forecast_1d.csv`.
  - BBBike map sampling and Sindelfingen depot projection remain aligned with V5.
- **Why:**
  - Aligns model execution with daily planning cadence rather than multi-day replay.
  - Keeps geographic realism from V5 while tightening operational decision timing.

### 4) Paired comparison logic updated for deployment fairness
- **Files:** `run_comp_v6vsCG.py`, `run_comp_v6_demo_small_area.py`
- **What changed:**
  - Comparison now builds model scenario from optimizer-selected deployed fleet.
  - Control-group fleet is generated to match the deployed vehicle count/capacity basis.
  - Reporting includes owned vs deployed totals and utilization to make staffing choice explicit.
- **Why:**
  - Ensures comparison remains fair after introducing deployment selection.
  - Separates strategic ownership (asset pool) from tactical activation (daily operations).

## New V6 Runner Files

### `rum_sim_v6.py`
- End-to-end V6 single run with:
  - 2x owned fleet,
  - deployment optimization,
  - next-day forecast execution.
- Prints deployment decision diagnostics and simulation KPI summary.

### `run_comp_v6vsCG.py`
- Paired model-vs-control evaluation under V6 assumptions.
- Supports `COMPARE_MODE=quick|medium|full`.
- Uses optimizer-selected deployed fleet as the model baseline for comparison.

### `run_comp_v6_demo_small_area.py`
- Lightweight demonstration run with smaller demand/active-task settings.
- Keeps the same deployment-selection and control-group comparison policy.

## Expected Impact
- **Operational realism:** improved through explicit own-vs-deploy separation.
- **Decision quality:** deployment becomes objective-driven instead of fixed fleet activation.
- **Comparative rigor:** model vs control remains paired and fair under identical external assumptions.
- **Scalability path:** framework now supports future enhancements such as shift constraints, maintenance windows, and depot-specific deployment caps.

## How to Run
- Single V6 run:
  - `python rum_sim_v6.py`
- V6 vs control-group paired comparison:
  - PowerShell quick mode:
    - `$env:COMPARE_MODE="quick"; python run_comp_v6vsCG.py`
- Demo small-area comparison:
  - `python run_comp_v6_demo_small_area.py`
  - Optional custom seeds:
    - `$env:DEMO_SEEDS="3"; python run_comp_v6_demo_small_area.py`

## Interpretation Guide
- In V6 comparison outputs, scenario A is the deployed model fleet and scenario B is the control-group fleet.
- Positive `dCost` means control-group cost is higher than the model deployment policy.
- Monitor dispatch-rate and backlog deltas together with cost deltas to avoid accepting cost gains that degrade service.
- Read deployment utilization jointly with outcome metrics to understand whether V6 savings come from efficient activation or under-capacity behavior.
