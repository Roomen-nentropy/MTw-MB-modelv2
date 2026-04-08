# V3 Improvements and Iteration Process

## Objective
- Keep the core HF-MDBOVRP model structure unchanged.
- Increase realism of operating assumptions in `v3_setup`.
- Improve average cost delta versus the control group (target: better than ~4%).

## How the Analysis Was Performed
- Reviewed V3 core modules: `config.py`, `dynamic_env.py`, `model_builder.py`, `rolling_horizon.py`, `simulation.py`.
- Identified two leverage points with high realism impact and low runtime risk:
  - Workload should vary with operating conditions (weather + lighting), not remain stationary.
  - High-tier vehicles should include deployment/setup overhead, not only distance-based cost.
- Preserved paired-seed comparability so V3 and control group remain testable on identical scenarios.

## Candidate Changes Considered
- **Selected:** condition-aware arrival intensity multipliers.
- **Selected:** tier-sensitive fixed vehicle deployment cost.
- **Not selected now:** adding extra skill levels or changing baseline compatibility logic, to avoid altering thesis core assumptions.
- **Not selected now:** explicit time windows/service times, because that would materially increase model complexity and runtime.

## Implemented Changes and Rationale

### 1) Condition-aware demand intensity
- **Where:** `v3_setup/config.py`, `v3_setup/dynamic_env.py`
- **What changed:**
  - Added `weather_task_rate_multiplier` and `lighting_task_rate_multiplier` to config.
  - Updated task generation to use:
    - `effective_lam = tasks_per_period_mean * weather_multiplier * lighting_multiplier`
  - Added validation checks to fail fast if a configured weather/lighting state has no multiplier.
- **Why:**
  - In practice, low visibility and poor weather can produce extra operational demand.
  - This makes period-level workload dynamics more realistic than a constant Poisson mean.

### 2) Tier-sensitive fixed deployment cost
- **Where:** `v3_setup/config.py`, `v3_setup/model_builder.py`, `v3_setup/rolling_horizon.py`
- **What changed:**
  - Added `vehicle_fixed_cost_scale` to config.
  - Extended model builder to compute per-tier fixed route cost:
    - `fixed_cost = max(0, cost_multiplier - 1) * vehicle_fixed_cost_scale`
  - Passed the new config parameter through planner -> model builder.
- **Why:**
  - Higher-spec vehicles carry real setup overhead (specialist crew, checks, readiness).
  - This is realistic and should increase separation from the all-high-tier control group on cost.

## New V3 Runners

### `run_sim_v3.py`
- Runs a single V3 simulation end-to-end.
- Uses `v3_setup` package directly.
- Prints key summary metrics:
  - total cost
  - average cost per dispatched task
  - end backlog ratio
  - dispatch/feasibility metrics

### `run_comp_V3vsCG.py`
- Paired comparison between V3 fleet and V3 control-group fleet.
- Uses identical random seeds and non-fleet parameters per pair.
- Supports lightweight execution modes:
  - `COMPARE_MODE=quick|medium|full`
  - optional `COMPARE_SEEDS=<N>`
- Outputs both absolute and percent deltas for:
  - total cost
  - cost per dispatched task
  - dispatch rate
  - backlog ratio

## Expected Impact
- **Realism:** improved via scenario-driven task intensity and non-distance fleet economics.
- **Cost delta vs control group:** expected improvement because control group overuses high-tier vehicles that now include fixed deployment overhead.
- **Service quality guardrails:** dispatch and backlog deltas are reported alongside cost deltas to avoid accepting false savings.

## How to Run
- Single V3 run:
  - `python run_sim_v3.py`
- V3 vs control-group paired comparison:
  - `set COMPARE_MODE=quick` (PowerShell: `$env:COMPARE_MODE="quick"`)
  - `python run_comp_V3vsCG.py`
- Optional custom seed count:
  - `set COMPARE_SEEDS=5` (PowerShell: `$env:COMPARE_SEEDS="5"`)

## Interpretation Notes
- In `run_comp_V3vsCG.py`, positive `Δcost` means control group cost is higher than V3.
- Positive `Δdispatch_rate` means V3 dispatches a larger share of generated tasks.
- Positive `Δbacklog` means control group backlog is higher than V3.
- Always confirm the pairing checks (`tasks generated matched`, `weather path matched`) are `True`.
