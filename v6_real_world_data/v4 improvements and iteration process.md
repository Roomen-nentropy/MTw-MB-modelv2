# V4 Improvements and Iteration Process

## Objective
- Keep the HF-MDBOVRP core model structure intact.
- Increase realism in `v4_setup`.
- Improve average delta versus the control group beyond the current V3 level (~4.46%).

## Analysis Approach
- Reviewed `v4_setup` equivalents of core files:
  - `config.py`
  - `dynamic_env.py`
  - `model_builder.py`
  - `rolling_horizon.py`
  - `simulation.py`
- Focused on changes that:
  - add operational realism,
  - preserve runtime practicality,
  - and increase economic separation between mixed-skill policy and all-high-skill control policy.

## Candidate Improvements Considered
- Condition-sensitive operating economics (selected).
- Nonlinear specialist readiness costs (selected).
- More standard-heavy but still feasible fleet mix in V4 runner (selected).
- Extra requirement levels or hard service-time windows (not selected now; higher complexity/runtime risk).

## Implemented V4 Changes

### 1) Condition-dependent operating cost realism
- **Files:** `v4_setup/config.py`, `v4_setup/dynamic_env.py`, `v4_setup/rolling_horizon.py`, `v4_setup/model_builder.py`
- **What changed:**
  - Added:
    - `weather_operating_cost_multiplier`
    - `lighting_operating_cost_multiplier`
  - Rolling horizon now computes period-specific:
    - `operating_cost_multiplier = weather_mult * lighting_mult`
  - Model builder now applies this multiplier to both:
    - unit-distance cost,
    - fixed deployment cost.
- **Why:**
  - Real fleets face higher fuel, safety, and compliance overhead in poor visibility/weather.
  - This is more realistic than a static per-km cost across all periods.

### 2) Nonlinear specialist fixed-cost curve
- **Files:** `v4_setup/config.py`, `v4_setup/model_builder.py`, `v4_setup/rolling_horizon.py`
- **What changed:**
  - Added `vehicle_fixed_cost_exponent`.
  - Replaced linear fixed-cost signal:
    - old: `(cost_multiplier - 1)`
    - new: `(cost_multiplier ** exponent - 1)`
  - Formula now:
    - `fixed_cost ~ (cost_multiplier ** exponent - 1) * vehicle_fixed_cost_scale * operating_cost_multiplier`
- **Why:**
  - High-capability assets often have disproportionate readiness overhead.
  - Nonlinear scaling better reflects specialist cost structure than linear scaling.

### 3) Overqualification overhead in assignment economics
- **Files:** `v4_setup/config.py`, `v4_setup/model_builder.py`, `v4_setup/rolling_horizon.py`
- **What changed:**
  - Added `overqualification_cost_penalty_per_level`.
  - In model edges, when a vehicle skill is above required task level, edge cost is increased by:
    - `1 + (skill_k - req_j) * penalty`.
- **Why:**
  - Deploying advanced assets on simple tasks is realistic but economically inefficient.
  - This better represents "capability mismatch" cost and discourages systematic overqualification.

### 4) Config validation hardening
- **File:** `v4_setup/dynamic_env.py`
- **What changed:**
  - Added startup validation that operating-cost multiplier dictionaries cover all configured weather/lighting states.
- **Why:**
  - Prevents silent misconfiguration and keeps comparative runs consistent.

## New V4 Runner Files

### `run_sim_v4.py`
- Runs one V4 simulation end-to-end.
- Uses V4-specific configuration including:
  - condition-dependent task and operating multipliers,
  - nonlinear fixed-cost settings,
  - a realistic mixed fleet (`5 Standard`, `1 Advanced`).
- Prints key metrics:
  - total cost,
  - cost per dispatched task,
  - dispatch rate,
  - backlog ratio.

### `run_comp_V4vsCG.py`
- Paired-seed comparison of V4 vs control group under identical stochastic scenarios.
- Supports lightweight controls:
  - `COMPARE_MODE=quick|medium|full`
  - `COMPARE_SEEDS=<N>`
- Reports absolute and percentage deltas for:
  - total cost,
  - cost per task,
  - dispatch rate,
  - backlog ratio.
- Includes scenario pairing sanity checks.

## Expected Impact
- **Realism:** improved through period-dependent operating economics and nonlinear specialist setup cost.
- **Cost delta vs CG:** expected to increase because control group uses all high-skill tiers and therefore incurs stronger specialist overhead.
- **Service safeguards:** dispatch/backlog deltas remain in output so savings are not accepted if service quality degrades.

## How to Run
- Single V4 run:
  - `python run_sim_v4.py`
- V4 vs control group comparison:
  - PowerShell quick mode:
    - `$env:COMPARE_MODE="quick"; python run_comp_V4vsCG.py`
  - Optional custom seeds:
    - `$env:COMPARE_SEEDS="5"; python run_comp_V4vsCG.py`

## Interpretation Guide
- In `run_comp_V4vsCG.py`, positive `dCost` means control group costs more than V4.
- Positive `d dispatch rate` means V4 serves a higher share of generated tasks.
- Positive `d backlog ratio` means control group leaves more backlog than V4.
- Confirm pairing checks stay `True` for fair A/B interpretation.
