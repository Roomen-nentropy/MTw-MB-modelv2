# Simulation evolution: from methodological baseline (V1) to V8

This document is a **consolidated, thesis-oriented history** of how the heterogeneous-fleet rolling-horizon simulation grew from the original problem formulation through **`hf_mdbovrp` (treated here as V2)** to **`v8`**. It records **what changed**, **where in the codebase**, and **why each change was argued**—drawing on per-version iteration notes, the repository narrative (`Academic_Narrative_Simulation_Evolution.md`), and V7/V8 argumentation supplements.

**How version labels are used here**

- **V1** denotes the **pre-implementation methodological baseline**: Morlock’s (2024) homogeneous multi-depot balanced open VRP and the thesis’s **conceptual** move to HF-MDBOVRP. There is **no `v1/` package** in this repository; V1 is literature and thesis framing.
- **V2** denotes the **first full code realization**: package **`hf_mdbovrp`** (and a parallel snapshot under `v2 setup/`), with root runners such as `run_simulation.py` / `run_comparative_simulation.py` described in `README_MainSim.md`.
- **V3–V8** denote **numbered packages or stacks** under `v3_setup/`, `v4_setup/`, `v5_real_world_data/`, `v6_real_world_data/`, `v7/`, `v8/`, with associated `run_sim_v*.py` / `rum_sim_v*.py` and `run_comp_*vsCG.py` entry points where applicable.

For command-level detail, see `README_MainSim.md`. For file-level deltas in a single version, see that version’s own markdown (listed in §10).

---

## 1. Methodological baseline (V1): what problem the code eventually encodes

### 1.1 Literature anchor

Morlock (2024) provides a mathematical basis for **balanced multi-depot open routing** with emphasis on distance and workload balance under a **homogeneous fleet**. ADAS validation in the thesis instead assumes **heterogeneous** fleets: tiers differ by sensor capability and cost.

### 1.2 Three-phase HF-MDBOVRP structure (thesis)

1. **Phase 1 — Environment and compatibility.** Each task carries an environmental tuple (weather, lighting, road domain). A mapping \(f: W \times L \times R \to \mathbb{Z}_+\) yields **requirement level** \(\mathrm{Req}_j\). **Hard** feasibility uses \(a_{jk} = \mathbf{1}[\mathrm{Skill}_k \ge \mathrm{Req}_j]\).
2. **Phase 2 — Economic routing.** Minimize **equipment-weighted travel** (conceptually \(\sum d_{ij} C_k x^k_{ij}\)) subject to routing constraints and skill feasibility.
3. **Phase 3 — Metaheuristic.** PyVRP’s HGA; infeasible vehicle–task pairings are **priced out** via very large edge costs (prohibitive distances on incompatible arcs in the implementation).

### 1.3 Rolling horizon

Time is discrete. Each period: update environment, (re)compute \(\mathrm{Req}^t_j\) for pending tasks, solve a static subproblem, **commit** a short execution window, roll forward. This matches Morlock-style planning and dynamic VRP receding-horizon logic.

**Why V1 matters for later versions:** Every subsequent package preserves this **skeleton** unless explicitly noted; changes mostly enrich **data**, **cost structure**, **deployment policy**, and **experimental fairness**—not the core meaning of skill and rolling horizons.

---

## 2. V2: `hf_mdbovrp` — first coded heterogeneous stack

### 2.1 What was built

| Thesis piece | Implementation (conceptual) |
|--------------|------------------------------|
| Phase 1 | `environment.py`: scoring \((w,\ell,r) \to \mathrm{Req}_j\); compatibility from skills vs requirements. |
| Phase 2 | `model_builder.py`: PyVRP model; **unit distance cost** scales with tier `cost_multiplier` (\(C_k\)); **profiles** with prohibitive distances for \(\mathrm{Skill}_k < \mathrm{Req}_j\). |
| Phase 3 | PyVRP solve; prohibitive edges encode hard ODD feasibility. |
| Dynamics | `dynamic_env.py`: Markov weather, lighting cycle, task generation; `rolling_horizon.py` + `simulation.py`: period loop, horizons, backlog. |
| Experiments | `fleet_controlgroup.py`, comparative runners for model vs control group. |

### 2.2 Why it was built

V2 **lifts homogeneity** to **tiered skills and asymmetric \(C_k\)**, aligning code with the thesis HF-MDBOVRP while keeping the solver interface manageable (Euclidean distances, complete graph).

### 2.3 Environment

**Synthetic:** tasks on a grid; no real map or external weather files yet.

### 2.4 Note on `v2 setup/`

The folder **`v2 setup/`** mirrors the same architectural pattern as `hf_mdbovrp` (e.g. `model_builder.py` without later V3+ parameters). Treat it as a **frozen snapshot** of the early heterogeneous design, not a separate research generation beyond V2.

---

## 3. Cross-cutting invariants (V2 → V8)

The following were treated as **architectural commitments** across most of the lineage:

- **Rolling-horizon simulation** with finite planning horizon and commitment window.
- **Hard skill feasibility** for under-qualified tiers: incompatible assignments use **prohibitive** edge lengths (until optional softening is discussed for research extensions).
- **Economic core** tied to **distance × tier economics** (\(C_k\)), later augmented by **period operating multipliers** (weather/lighting) where configured.
- **Paired comparisons:** model fleet vs **control group** under shared seeds and shared exogenous scenario where enforced by scripts.

---

## 4. V3 (`v3_setup`): condition-sensitive demand and tier fixed costs

### 4.1 Problem addressed

Constant Poisson arrivals ignore that **workload intensity** may rise in adverse conditions. Distance-only variable cost ignores **setup/readiness** differences between tiers.

### 4.2 Changes implemented

1. **Condition-aware arrival intensity** (`config.py`, `dynamic_env.py`):  
   \(\lambda_{\text{eff}} = \lambda_{\text{base}} \cdot m_W \cdot m_L\) using `weather_task_rate_multiplier` and `lighting_task_rate_multiplier`, with validation so every state has multipliers.

2. **Tier-sensitive fixed route cost** (`config.py`, `model_builder.py`, `rolling_horizon.py`): fixed PyVRP vehicle-type cost derived from `cost_multiplier` and `vehicle_fixed_cost_scale`.

3. **Runners:** `run_sim_v3.py`, `run_comp_V3vsCG.py` with quick/medium/full modes and pairing checks.

### 4.3 Why each change was argued

- **Demand multipliers:** improves **short-run realism** (more tickets or operational load when conditions are hard) without changing the core compatibility algebra.
- **Fixed tier costs:** captures **non-distance deployment overhead** for high-spec assets; expected to **separate** mixed-tier policy from an all-advanced control group on **total cost**, not only kilometers.

### 4.4 What was deliberately *not* changed

Extra requirement levels, time windows, or compatibility rewrites were deferred to limit complexity and runtime.

---

## 5. V4 (`v4_setup`): state-dependent operating economics and mismatch penalties

### 5.1 Problem addressed

V3 did not tie **marginal operating cost** to the **current** weather/lighting period. Specialist readiness was linear in \(C_k\); real specialist assets often have **convex** readiness burden. **Capability mismatch** (advanced vehicle on easy task) was not explicitly priced beyond base \(C_k\).

### 5.2 Changes implemented

1. **Operating cost multipliers** (`weather_operating_cost_multiplier`, `lighting_operating_cost_multiplier`): rolled into `operating_cost_multiplier` in `rolling_horizon.py`, applied in `model_builder.py` to **unit distance cost** and **fixed** cost.

2. **Nonlinear fixed-cost curve:** `vehicle_fixed_cost_exponent` so fixed cost scales with \((C_k^{\text{exponent}} - 1)\) rather than \((C_k - 1)\).

3. **Overqualification parameter** `overqualification_cost_penalty_per_level` documented in V4 iteration notes as increasing edge cost when \(\mathrm{Skill}_k > \mathrm{Req}_j\) (historical V4 intent).

4. **Config validation** in `dynamic_env.py` for complete multiplier coverage.

5. **Runners:** `run_sim_v4.py`, `run_comp_V4vsCG.py` with a more realistic mixed fleet in the single-run script (e.g. 5 Standard / 1 Advanced in the iteration doc).

### 5.3 Why each change was argued

- **Period \(M_W \cdot M_L\):** fuel, risk, compliance, and slower operations in poor visibility justify **higher marginal cost** in bad periods.
- **Nonlinear fixed cost:** reflects **disproportionate** readiness for highest tiers.
- **Overqualification:** internal **shadow price** so the solver prefers matching capability to difficulty when routes allow.

### 5.4 Deliberate exclusions

More discrete requirement levels and hard service-time windows were still deferred (complexity/runtime).

---

## 6. V5 (`v5_real_world_data`): external validity — real map support and Open-Meteo

### 6.1 Problem addressed

Synthetic grids support **internal validity**; thesis-grade claims about Stuttgart-region-style operations need **geographic support** and **exogenous weather paths**.

### 6.2 Changes implemented

1. **`bbbike_map_sampler.py`:** Parse BBBike **`planet_...osm.csv.xz`**: bbox from filename, stream nodes, deterministic embedding to local \((x,y)\) in km; `suggest_sindelfingen_depot_xy()` for a Mercedes-Benz–aligned depot.

2. **`dynamic_env.py`:** If `bbbike_xz_path` set, sample task coordinates from the map pool instead of a uniform grid.

3. **`open_meteo_weather.py`:** Hourly weather (rain, visibility, cloud layers, `is_day`, etc.) for **7 days past + 7 days forecast** (14-day hourly table).

4. **`config.py` / `simulation.py`:** `open_meteo_hourly_csv`, `bbbike_xz_path`, `bbbike_sampling_pool_size`.

5. **Runners:** `rum_sim_v5.py`, `run_comp_v5vsCG.py`, `run_comp_v5_demo_small_area.py`.

### 6.3 Major methodological pivot: **post–V2 standardization** (documented in V5 process note and `Academic_Narrative_Simulation_Evolution.md` §8)

**Why standardization was argued**

- **Identification:** Stacking fixed costs, nonlinear transforms, overqualification, and **asymmetric** control-group tuning made it unclear whether cost gaps reflected **fleet policy** or **hidden penalty engineering**.
- **Thesis coherence:** The published Phase-2 story emphasizes **\(\sum d_{ij} C_k\)** with **hard** feasibility—not an opaque composite objective.
- **Counterfactual clarity:** Control group should be a **single homogeneous top-tier** fleet at **comparable scale**, not a relabeled mix with different penalty treatment.

**What was standardized in V5**

1. **Control group:** one **all-advanced** tier; `num_available = sum` of model fleet counts; depot logic aligned with highest-capability tier convention.

2. **PyVRP objective:** **Removed** from the objective construction: per-route **fixed deployment surcharges** and **overqualification edge surcharges**. **Kept:** equipment-weighted travel + **prohibitive** edges for \(\mathrm{Skill}_k < \mathrm{Req}_j\). **Kept (conceptually):** period **operating** multipliers where the rolling horizon applies them—V5 remains “V4-style” on **marginal conditions** while stripping auxiliary penalty layers.

3. **Comparison scripts:** no special penalty overrides for the control group.

**Legacy config keys** (e.g. fixed-cost and overqualification fields) were **retained** for API stability but documented as **not feeding** the simplified objective—avoiding silent breakage of old configs.

### 6.4 Why this design (map + weather + standardization)

- **Minimal disruption** to rolling-horizon architecture.
- **Fair A/B:** identical map, weather, and horizons for model vs control.
- **Clear interpretation:** heterogeneous policy vs homogeneous high-capability benchmark under the **same** environmental path.

### 6.5 Limitation recorded in V5 docs

The early BBBike **`.osm.csv.xz`** pipeline was **coordinate-oriented**; it did **not** expose rich `highway=*` semantics for per-task road class (addressed in V7 with full OSM).

---

## 7. V6 (`v6_real_world_data`): owned capacity, deployment optimization, next-day forecast

### 7.1 Problem addressed

V5 assumes **all** `num_available` vehicles are active. Real fleets often **own** reserve capacity but **activate** a subset daily. V5’s 14-day replay is less aligned with **daily planning with a short forecast**.

### 7.2 Changes implemented

1. **Owned vs deployed:** scale to a larger **owned** pool (e.g. `scale_owned_fleet(..., 2.0)` in the V6 iteration doc), then **`deployment.py`** selects an **active** subset.

2. **Deployment search:** sweep utilization (or deployed count) between `min_utilization` and `max_utilization` by step; for each candidate, proportional tier allocation within per-tier caps; short **evaluation simulation**; score = route cost + **backlog** + **undispatched** penalties; tie-break toward **smaller** deployment when objectives tie.

3. **Forecast cadence:** default **next-day** Open-Meteo path (`past_days=0`, `forecast_days=1`), `total_periods=24`, forecast CSV workflow.

4. **Paired comparison:** control group matches **deployed** totals (not raw owned totals) so the benchmark reflects **tactical** scale.

5. **Runners:** `rum_sim_v6.py`, `run_comp_v6vsCG.py`, `run_comp_v6_demo_small_area.py`.

### 7.3 Why each change was argued

- **Ownership margin:** separates **strategic asset base** from **tactical activation**.
- **Objective-guided deployment:** avoids always-on full fleet while still penalizing poor service outcomes.
- **Next-day horizon:** aligns with operational **staffing** decisions under forecast uncertainty.
- **Fair CG under deployment:** preserves **paired** interpretation after a new decision layer.

### 7.4 Deliberate exclusions

No change to core skill algebra; no shift/labor calendars in V6.

---

## 8. V7 (`v7/`): full OSM road domains, calibration, tooling

### 8.1 Problem addressed

V5/V6 map sampling gave **realistic coordinates** but **synthetic road-domain labels** (`road_domain_weights`). For thesis claims tying ODD to **road context**, domains should be **grounded in OSM** where possible.

### 8.2 Changes implemented

1. **Full OSM XML** `planet_...osm.xz` with `<way>` tags and `highway=*`.

2. **`bbbike_map_sampler.py`:** streaming parse; `build_local_task_pool_with_domain_from_bbbike` returning `(x, y, road_domain)`; mapping **Highway / Urban / Rural** from OSM highway classes; bbox from filename or `<bounds>`; optional **pool cache** `*.pool_<N>.csv` to avoid repeated full parses.

3. **`dynamic_env.py`:** if the map pool carries a domain, it **overrides** weighted random domain for that task; legacy `.osm.csv.xz` keeps old behavior.

4. **Cost calibration (`C_advanced`):** baseline advanced **`cost_multiplier` moved from 1.8 to 1.35** in `rum_sim_v7.py` (and sensitivity via `run_v7_cost_sensitivity.py`).

5. **Argumentation:** `v7/k_c_parameterization_argumentation.md` — ordinal `Skill`, \(C_k\) as **effective marginal mission cost**, sensitivity monotonicity in cost deltas without service metric movement in the downsized sweep, robustness band `{1.25, 1.50}`.

6. **Runners:** `rum_sim_v7.py`, `run_comp_v7vsCG.py`.

### 8.3 Why each change was argued

- **OSM domains:** increases **external validity** of \(r_j\) in \(\mathrm{Req}_j = f(w_j,\ell_j,r_j)\).
- **Cache:** pragmatic **reproducibility and iteration speed** on large extracts.
- **Lower `C_advanced` default:** sensitivity suggested **1.8** inflated economic penalty **without** corresponding service-side differentiation in the tested design—**1.35** is a defensible middle ground with explicit robustness bounds.

### 8.4 Compatibility policy

Full `.osm.xz` → map-derived domains; legacy extract → weighted domains. This supports **migration** without invalidating old experiments.

---

## 9. V8 (`v8/`): service-level deployment constraints + V8 runners

### 9.1 Problem addressed

V7 **deployment** remains **penalty-driven**. In tests, the optimizer could pick **very low** active counts (e.g. **4/12**) while still avoiding catastrophic penalty—**under-deployment** vs real **governance** on dispatch and backlog.

### 9.2 Changes implemented

1. **`v8/config.py`:** extends V7 `SimulationConfig` with **deployment policy** fields: `deployment_min_dispatch_rate`, `deployment_max_backlog_ratio`, `deployment_eval_periods`, utilization range and step (baseline **`deployment_min_utilization = 0.50`**).

2. **`v8/deployment.py`:** **feasibility-first** selection: candidate feasible iff dispatch rate and backlog ratio meet thresholds; among feasible, minimize economic objective; else **fallback** to best service candidate and `meets_service_constraints = False`.

3. **Academic rationale:** `v8/v8_service_level_argumentation.md` — separation of service acceptability from pure cost tuning; transparency; ADAS campaign governance metaphor.

4. **Runners:** `rum_sim_v8.py`, `run_comp_v8vsCG.py`; print policy parameters and constraint satisfaction.

5. **Manual fleet diagnostic:** `rum_sim_v8.py` baseline **Standard=10, Advanced=8**, multiplier-based owned scaling off—tests whether **full advanced utilization** is **supply-imposed** vs **parameter-imposed**.

6. **Shared stack:** `v8` re-exports **`v7.simulation`**, **`v7.rolling_horizon`**, etc., so period routing uses **`v7.model_builder`**.

### 9.3 Overqualification **reinstated** in `v7/model_builder.py` (V8-era routing economics)

After V5 standardization, **`overqualification_cost_penalty_per_level` existed in config but did not affect edges** in the V7 builder. V8 documentation records **implementation**:

- For \(\mathrm{Skill}_k > \mathrm{Req}_j\), **additive integer distance** on arcs **entering and leaving** client \(j\), scaled by \((\mathrm{Skill}_k - \mathrm{Req}_j)\), `penalty_per_level`, and **max base edge length** in the instance.
- **Under-qualification** remains **hard** (prohibitive distance).

**Why this was argued (post hoc to standardization):** restores an interpretable **“waste of capability”** channel that the thesis narrative discusses, **without** reintroducing the full V3/V4 **fixed-route** stack or asymmetric CG tuning. **`0.0`** disables the surcharge for sensitivity / parity with the stripped objective.

**Consistency note:** `Academic_Narrative_Simulation_Evolution.md` §8 describes **removing** overqualification as part of **parsimony**; the **current** shared builder **optionally** applies it again. Thesis text should state explicitly whether the **main results** use `0.0` or a positive value (e.g. `rum_sim_v8.py` uses **0.75**).

### 9.4 Quick validation cited in V8 docs

Under development settings: V7-style deployment **4/12** vs V8 policy **6/12** with constraints met—**directional** evidence, not final inferential proof.

---

## 10. Index of per-version documentation in the repository

| Version | Primary markdown |
|--------|-------------------|
| Cross-version narrative | `Academic_Narrative_Simulation_Evolution.md` |
| V3 | `v3_setup/v3 improvements and iteration process.md` |
| V4 | `v4_setup/v4 improvements and iteration process.md` |
| V5 | `v5_real_world_data/v5 real-world map+weather integration process.md` |
| V6 | `v6_real_world_data/v6 improvements and iteration process.md` |
| V7 | `v7/v7 improvements and iteration process.md`, `v7/k_c_parameterization_argumentation.md` |
| V8 | `v8/v8 improvements and iteration process.md`, `v8/v8_service_level_argumentation.md` |
| Main README | `README_MainSim.md` |

---

## 11. Known limitations (carried forward)

- **Geometry:** planar embedding / Euclidean distances—not full road-network shortest paths.
- **Demand:** stylized Poisson (with condition multipliers), not proprietary order streams.
- **Optimality:** PyVRP heuristic solutions.
- **Reproducibility:** archive Open-Meteo CSVs and OSM files for bit-exact replication.

---

## 12. One-page “story arc” for the thesis

1. **V1:** From homogeneous MDBOVRP to **HF-MDBOVRP** with **ODD-driven** requirements and **economic** routing.
2. **V2:** Encode Phases 1–3 + rolling horizon in **`hf_mdbovrp`**.
3. **V3–V4:** Enrich **dynamics and economics** (demand intensity, operating multipliers, nonlinear readiness, mismatch intent).
4. **V5:** Add **real map + weather**; **standardize** control group and **strip** composite penalties from the objective for **clean attribution**; keep hard feasibility.
5. **V6:** Add **owned vs deployed** and **next-day** planning realism.
6. **V7:** Ground **road domain** in **full OSM**; **calibrate \(C_{\text{advanced}}\)** with sensitivity argumentation.
7. **V8:** Make **service levels** explicit in **deployment**; tighten utilization floor; optionally restore **overqualification** in the period VRP via **`v7.model_builder`**.

This is the full lineage **as implemented in this repository** from the **conceptual V1 baseline** through **V8**.
