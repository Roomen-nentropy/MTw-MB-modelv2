# V8 Service-Level Deployment Argumentation (Academic Rationale)

## 1) Problem Statement

V7 deployment optimization can under-deploy active vehicles when objective penalties are not sufficient to force larger activation. This is not always operationally realistic for ADAS pre-release campaigns, where service-quality expectations are policy constraints, not merely soft costs.

V8 introduces an explicit service-level constrained deployment policy to align optimization behavior with operational governance.

---

## 2) Policy Formulation

For each candidate deployed fleet size, simulate over an evaluation horizon and compute:

- Dispatch rate:  
  `dispatch_rate = tasks_dispatched / tasks_generated`
- End backlog ratio:  
  `backlog_ratio = tasks_remaining / tasks_generated`

Candidate feasibility condition:

- `dispatch_rate >= min_dispatch_rate`
- `backlog_ratio <= max_backlog_ratio`

Selection rule:

1. Keep feasible candidates.
2. Choose feasible candidate with minimum economic objective.
3. If no candidate feasible, fallback to best service candidate and mark policy violation.

This turns service levels into first-order constraints in deployment selection.

---

## 3) Why This Is Methodologically Stronger

### 3.1 Separation of concerns
- Service acceptability is enforced by explicit thresholds.
- Economic optimization is performed only within acceptable service region.

This avoids conflating operational validity with objective tuning.

### 3.2 Reproducibility and transparency
- Policy parameters are explicit in config and runner logs.
- Every deployment decision can be audited against the same threshold set.

### 3.3 Consistency with ADAS validation context
- Pre-release data campaigns are constrained by coverage sufficiency and backlog risk.
- Representing these as hard policy filters is closer to governance practice than relying only on soft penalties.

---

## 4) Parameterization Used In V8

Baseline V8 policy fields:

- `deployment_min_dispatch_rate = 0.92`
- `deployment_max_backlog_ratio = 0.08`
- `deployment_min_utilization = 0.50`
- `deployment_max_utilization = 1.00`
- `deployment_utilization_step = 0.05`
- `deployment_eval_periods = 24`

Rationale:
- Service thresholds establish minimum acceptable outcomes.
- Utilization floor prevents structurally trivial low-activation solutions when service metrics alone are permissive.

---

## 5) Validation Evidence (Development-Stage)

In quick validation with a lightweight test setup:

- V7-style behavior selected: `4/12` active.
- V8 default policy selected: `6/12` active, with service constraints satisfied.

This confirms the intended directional effect: V8 reduces under-deployment risk.

---

## 6) Threats to Validity

1. **Development runtime settings:** quick checks are directional, not final inferential evidence.
2. **Scenario dependence:** deployment thresholds may need recalibration by region/weather mix.
3. **Threshold arbitrariness risk:** values should be justified via calibration protocol and robustness reporting.

Mitigation:
- Run medium/full seed sets for confirmatory evaluation.
- Report both policy metrics and economic metrics across scenarios.
- Perform threshold sensitivity analysis.

---

## 7) Recommended Thesis Reporting Structure

1. Define policy thresholds and candidate generation formally.
2. Present feasibility-first selection algorithm.
3. Report calibration grid and holdout validation.
4. Provide robustness checks for threshold variation.
5. Disclose fallback frequency (`meets_service_constraints=False`) as a diagnostic KPI.

---

## 8) Conclusion

V8 improves operational realism by promoting service-level requirements from implicit penalty effects to explicit deployment feasibility constraints. This strengthens methodological clarity, improves interpretability of deployment outcomes, and supports academically defensible evaluation of trade-offs between cost and service quality.
