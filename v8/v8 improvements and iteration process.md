# V8 Improvements and Iteration Process (from V7 Baseline)

## Objective
- Address the main V7 operational realism gap: deployment optimizer frequently selected very low active-fleet counts.
- Preserve V7 core architecture:
  - full-OSM road-domain mapping,
  - rolling-horizon planning,
  - paired model-vs-control comparison workflow.
- Introduce explicit service-level guardrails in deployment selection.

## Why V8 Was Needed
- In V7, deployment optimization is objective-driven with penalties but no explicit service-level feasibility gate.
- Under tested conditions this can produce low active deployment (e.g., `4/12`) when service penalties are still avoided.
- For realistic ADAS campaign operations, staffing/deployment should satisfy explicit minimum service conditions, not only soft penalties.

## Implemented V8 Changes

### 1) New V8 package boundary
- Added a dedicated `v8/` module namespace.
- V8 keeps shared core simulation stack from V7 via module wrappers, while introducing new policy logic in:
  - `v8/config.py`
  - `v8/deployment.py`

### 2) Service-level constrained deployment optimization
- **File:** `v8/deployment.py`
- **Change:**
  - Deployment candidate evaluation is now feasibility-first.
  - Each candidate computes:
    - `dispatch_rate`,
    - `backlog_ratio`.
  - Candidate is feasible only if:
    - `dispatch_rate >= min_dispatch_rate`,
    - `backlog_ratio <= max_backlog_ratio`.
  - Among feasible candidates, optimizer minimizes economic objective.
  - If no candidate is feasible, fallback picks best service candidate and marks:
    - `meets_service_constraints = False`.
- **Why:**
  - Converts deployment from pure penalty optimization to policy-constrained operational selection.

### 3) Deployment policy fields in V8 config
- **File:** `v8/config.py`
- Added explicit policy parameters:
  - `deployment_min_dispatch_rate`
  - `deployment_max_backlog_ratio`
  - `deployment_eval_periods`
  - `deployment_min_utilization`
  - `deployment_max_utilization`
  - `deployment_utilization_step`

### 4) Utilization floor tightened for realism
- **Files:** `v8/config.py`, `rum_sim_v8.py`
- Updated baseline `deployment_min_utilization` to `0.50` (from V7-like low floor behavior).
- **Why:**
  - Ensures active deployment is not trivially minimal even when service thresholds are already met at lower counts.
  - In quick validation this shifted deployment from `4/12` to `6/12`.

### 5) V8 runners and comparison scripts
- Added:
  - `rum_sim_v8.py`
  - `run_comp_v8vsCG.py`
- Both scripts now:
  - use V8 deployment policy fields,
  - print service-rule parameters and whether selected deployment meets constraints.

### 6) Overqualification routing economics (period VRP)
- **Files:** `v7/model_builder.py` (shared builder used by the V8 simulation stack via `v8.simulation` → `v7.simulation` → `v7.rolling_horizon`), `v7/config.py` (parameter semantics).
- **What changed:**
  - `overqualification_cost_penalty_per_level` is now **implemented**: for each vehicle profile with `Skill_k > Req_j`, every directed edge that **enters** or **leaves** client \(j\) gets an **integer distance surcharge**
    \(\Delta \approx \texttt{penalty\_per\_level} \cdot (Skill_k - Req_j) \cdot \max_{uv} d_{uv}\),
    so PyVRP’s cost (unit distance cost × distance) penalizes assigning advanced tiers to low-requirement tickets.
  - **Under-qualification** remains **hard**: `Skill_k < Req_j` still uses the existing prohibitive edge length so an infeasible assignment cannot compete with feasible routes.
- **Why:**
  - Restores an economically interpretable “capability mismatch” channel that was present in the API but not in the edge construction, aligning routing behavior with the thesis narrative on shadow pricing of tier–task mismatch.
- **Note:**
  - The same `build_skill_based_pyvrp_model` is used for V7-style runs; any script that sets `overqualification_cost_penalty_per_level` (e.g. `rum_sim_v8.py` at `0.75`) now affects the solved routes. Set to `0.0` to recover the previous pure travel-cost objective aside from hard incompatibility.

### 7) Manual fleet scaling diagnostic (advanced tier)
- **File:** `rum_sim_v8.py`
- **What changed:**
  - Increased baseline fleet counts manually to:
    - `Standard: 10`
    - `Advanced: 8`
  - Kept multiplier-based scaling disabled.
- **Justification:**
  - In prior V8 runs, the advanced tier was frequently fully deployed.
  - This can indicate either:
    1. a true model-driven need for advanced capability, or
    2. an artificially tight supply assumption imposed by the initial baseline fleet size.
  - The manual doubling is an intentional diagnostic to test whether high advanced utilization is a self-imposed modeling restriction (and therefore a potential specification error) rather than an intrinsic requirement of the optimization logic.
  - This improves internal validity by separating demand-side model behavior from supply-side parameter choices.

## Validation Summary
- Syntax/lint checks pass for all new V8 files.
- Quick behavioral validation against lightweight map setup showed:
  - V7 deployment: `4/12` (`util=0.333`)
  - V8 deployment (default policy): `6/12` (`util=0.500`, constraints met)

## Expected Impact
- More operationally credible active-fleet decisions.
- Policy transparency: deployment assumptions are explicit and auditable.
- Better thesis traceability: service-level constraints are first-class model elements, not implicit penalty artifacts.

## How to Run
- V8 single run:
  - `python rum_sim_v8.py`
- V8 paired comparison:
  - `python run_comp_v8vsCG.py`
  - Optional: `$env:COMPARE_MODE="quick"; python run_comp_v8vsCG.py`

## Interpretation Guide
- V8 output includes whether deployment satisfied service constraints.
- If fallback is used (`meets_service_constraints=False`), report this explicitly in analysis.
- Compare V8 and V7 on both cost and service metrics to show realism vs efficiency trade-offs.
