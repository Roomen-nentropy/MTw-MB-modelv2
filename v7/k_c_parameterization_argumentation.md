# Academic Argumentation for `k` (Skill) and `c` (Cost) Parameterization in V7

## Purpose

This note formalizes a thesis-grade parameterization strategy for fleet heterogeneity in V7, with explicit argumentation rooted in:

1. The thesis literature review and methodology framing.
2. The completed V7 sensitivity sweep on the advanced-tier cost multiplier.

The objective is to justify parameter choices transparently, avoid over-claiming unsupported assumptions, and provide a reproducible calibration protocol.

---

## 1) Conceptual Position: What `k` and `c` Should Mean

### 1.1 `Skill_k` is ordinal, not a performance ratio

The methodology defines `Skill_k` as a discrete capability tier used in compatibility logic (`Skill_k >= Req_j`). This is an ordinal relation, not a cardinal one. Therefore:

- `Skill_standard = 1`
- `Skill_advanced = 2`

should be interpreted as **class labels** (capability ordering), not "advanced is twice as capable."

This aligns with the proposed hard compatibility matrix and avoids invalid cardinal interpretations.

### 1.2 `C_k` is an economic weight, not a pure hardware premium

The text motivating `C_k` includes multiple cost channels: operation, maintenance, and downstream processing/storage burdens of richer sensor payloads. Therefore `C_k` is best interpreted as an **effective marginal mission cost multiplier**, not simply a purchase-price proxy.

---

## 2) Sensitivity Analysis Evidence (Executed in Project)

## 2.1 Experiment summary

Sensitivity sweep was executed over:

- `C_advanced in {1.25, 1.35, 1.50, 1.60, 1.80}`

and reported paired model-vs-control deltas.

The completed run that produced usable end-to-end results:

- Script: `run_v7_cost_sensitivity.py`
- Terminal output includes `START_SWEEP ... END_SWEEP`
- Successful completion with all 5 tested values.

## 2.2 Reported outcomes

Observed metrics from the completed sweep:

- `C_ADV=1.25` -> `mean_dcost=+10584.00`, `mean_dcpt=+144.9863`, `mean_ddisp=+0.0000`, `mean_dback=+0.0000`
- `C_ADV=1.35` -> `mean_dcost=+16062.00`, `mean_dcpt=+220.0274`, `mean_ddisp=+0.0000`, `mean_dback=+0.0000`
- `C_ADV=1.50` -> `mean_dcost=+24663.00`, `mean_dcpt=+337.8493`, `mean_ddisp=+0.0000`, `mean_dback=+0.0000`
- `C_ADV=1.60` -> `mean_dcost=+30785.00`, `mean_dcpt=+421.7123`, `mean_ddisp=+0.0000`, `mean_dback=+0.0000`
- `C_ADV=1.80` -> `mean_dcost=+44183.00`, `mean_dcpt=+605.2466`, `mean_ddisp=+0.0000`, `mean_dback=+0.0000`

## 2.3 Interpretation

Within this executed setup:

1. Increasing `C_advanced` monotonically increases cost deltas.
2. Service indicators (`dispatch`, `backlog`) remained unchanged.

This implies that, for the tested settings, larger `C_advanced` acts mainly as an economic penalty without observable service gains. Consequently, choosing `1.80` appears difficult to justify unless supported by external accounting evidence.

---

## 3) Validity Boundaries and Academic Caution

The sweep is informative but should be interpreted with methodological caution:

- It was a **downsized runtime design** (single seed, shortened horizon, reduced solver/runtime settings) to make iterative testing feasible.
- It is therefore best treated as **directional evidence**, not final confirmatory calibration.

Academic standard requires an additional confirmatory stage:

- more seeds,
- full horizon,
- production-like map/source settings,
- and uncertainty reporting (mean + dispersion, preferably confidence intervals).

---

## 4) Recommended Parameterization (Defensible Baseline)

Based on theory + sensitivity evidence:

1. Keep skills ordinal and hard-constrained:
   - `Skill_standard = 1`
   - `Skill_advanced = 2`
   - compatibility via `a_jk = 1[Skill_k >= Req_j]`

2. Use a lower base advanced multiplier:
   - baseline: `C_standard = 1.0`, `C_advanced = 1.35`
   - robustness band: `C_advanced in {1.25, 1.50}`

3. Avoid a fixed "high" multiplier (e.g., `1.80`) as default absent cost-accounting support.

---

## 5) Better Model Extension: Base Cost x Context Multiplier

To better match the literature on environment-dependent burden, use:

`C_eff(k,j,t) = C_base(k) * M_env(weather_t, lighting_t, road_domain_j)`

where:

- `C_base(k)` captures tier-intrinsic economics.
- `M_env(.)` captures scenario difficulty and operational burden.

This preserves hard compatibility while allowing economically realistic variation by ODD/weather context.

---

## 6) Thesis-Grade Calibration Protocol

## 6.1 Pre-specify ranges

Before running confirmatory experiments, pre-register:

- `C_base_advanced in [1.25, 1.60]`
- bounded `M_env` values (for example, around `1.00` to `1.25`)

with explicit rationale.

## 6.2 Split calibration vs validation

- Calibration set: choose parameters.
- Held-out validation set: test generalization.

This prevents tuning to a single simulation slice.

## 6.3 Multi-metric decision rule

Evaluate jointly:

- total route cost,
- cost per dispatched task,
- dispatch rate,
- backlog ratio,
- advanced-tier utilization share.

Pick the **lowest-cost** parameter set that satisfies pre-defined service floors.

## 6.4 Robustness and uncertainty

For final reporting:

- report means across seeds,
- dispersion (std / CI),
- paired deltas versus baseline,
- sensitivity to weather severity composition.

---

## 7) Suggested Baseline/Robustness Set for the Thesis

### Main case

- `Skill = {1, 2}` (ordinal)
- `C_base_standard = 1.0`
- `C_base_advanced = 1.35`

### Robustness cases

- Low-cost advanced: `C_base_advanced = 1.25`
- High-cost advanced: `C_base_advanced = 1.50`

This gives an interpretable and empirically motivated range while avoiding a potentially inflated default penalty.

---

## 8) Reproducibility Notes

To ensure reproducibility and academic transparency:

1. Record exact config values and random seeds per experiment.
2. Store raw output files for each tested parameter combination.
3. Document any runtime-downscaling choices separately from confirmatory runs.
4. Distinguish clearly between exploratory and confirmatory evidence in the thesis narrative.

---

## Concluding Statement

Current evidence supports a shift away from interpreting advanced-tier parameters as "2x skill, +80% cost." A more academically defensible approach is:

- ordinal skill classes with hard compatibility,
- moderate base advanced cost multiplier (around `1.35`),
- and (preferably) context-dependent economic weighting for environmental difficulty.

This is consistent with the literature, with the implemented model structure, and with the observed sensitivity behavior.
