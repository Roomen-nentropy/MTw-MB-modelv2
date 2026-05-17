# Model limitations, deliberate exclusions, and improvement options

This note lists **what the simulation does not model** (or only models in reduced form), **why** those choices were made, and **concrete options** to extend the work without pretending the current code already does them. It complements `Simulation_Evolution_V1_Through_V8.md` and the limitations section of `Academic_Narrative_Simulation_Evolution.md`.

---

## 1. Solar geometry, glare, and radiometric realism

### What is excluded

- **Sun angle (elevation and azimuth)** is **not** computed or passed into the ODD mapping. There is no hourly **solar zenith**, **incidence angle on the road**, or **camera-facing glare** model.
- **Open-Meteo** supplies `is_day`, `sunshine_duration` (per hour), `cloud_cover`, and merged daily `daylight_duration_s` and `uv_index_max`, but the simulation’s discrete environment uses only what flows through `map_row_to_sim_weather_lighting()` in `v7/open_meteo_weather.py`: visibility, precipitation, snow (as adverse signal), cloud, `is_day`, and **sunshine fraction of the hour** for a rough **Dusk** heuristic—not true sun position.
- **Temperature**, **UV**, and **daylight_duration** are present in the fetched/merged table for context but **do not** enter `weather_score`, `lighting_score`, or operating multipliers in the default V7/V8 config.

### Why (design rationale)

- The thesis stack uses a **small discrete alphabet** (`Clear | Rain | Fog`, `Day | Dusk | Night`) so that **requirement levels** and **compatibility** stay tractable and reproducible.
- Full radiometric sensor models (exposure, blooming, lens flare) would couple routing to **per-segment geometry** and **vehicle heading**, exploding state size and calibration needs.
- **Sun angle** would require either an external astronomy library and surface orientation or a precomputed radiance proxy; that was out of scope for the rolling VRP layer.

### Options for improvement

- Add **solar elevation** (e.g. `pvlib` or a minimal declination/hour-angle routine) and map **low elevation + clear sky** to a distinct lighting or glare-sensitive **Req** contribution.
- Introduce a **continuous auxiliary variable** (e.g. normalized illuminance) alongside discrete labels for sensitivity analysis.
- Use **temperature** or **UV** as extra thresholds in `map_row_to_sim_weather_lighting` or as separate multipliers on **task rate** / **operating cost** (thermal stress, battery, sensor noise).

---

## 2. Atmosphere and weather state space

### What is excluded or collapsed

- Only **three** weather labels drive the model: `Clear`, `Rain`, `Fog`. **Wind**, **icing**, **hail**, **smoke/aerosols**, and **severe convective** regimes are not separate states.
- **Snow** is folded into adverse precipitation logic that can label **`Rain`** (see `snow_cm` thresholds in `map_row_to_sim_weather_lighting`), not a dedicated winter ODD.
- **Visibility** is used for fog-like classification but does not vary **continuously** inside the solver; it only helps pick the discrete label.
- **Cloud layers** (low/mid/high) are fetched but **not** used in the default mapping beyond aggregate `cloud_cover`.

### Why

- Keeps the **Markov** and **CSV-driven** paths aligned on the **same** key set expected by `environment.py` and config dictionaries.
- Avoids exploding the number of `weather_transitions` rows and multiplier tables that must be filled and validated.

### Options for improvement

- Expand `W` with **WindHigh**, **Snow**, **Ice** after defining transitions and multipliers (and re-validating deployment comparisons).
- Feed **low cloud** or **visibility** as a **continuous severity score** into \(f(W,L,R)\) instead of a single discrete jump.
- Couple to **road maintenance** or **speed reduction** factors by road class (see §5).

---

## 3. Lighting: coarse discretization

### What is excluded

- Lighting is **Day | Dusk | Night**. **Civil/nautical/astronomical** twilight bands are not distinguished.
- **Dusk** is a **heuristic** (low sunshine fraction while `is_day`): it is not tied to sunset time or sun below horizon by degrees.
- **Night** does not distinguish **moonlight**, **urban lighting**, or **tunnel** segments.

### Why

- Matches the **ordinal lighting_score** \(\{0,1,2\}\) in `DEFAULT_MAPPING_2LEVEL` and keeps rolling-horizon recomputation simple.

### Options for improvement

- Drive lighting from **solar elevation** thresholds (e.g. Day: \(> 6°\), Dusk: \(-6°\) to \(6°\), Night: \(< -6°\)).
- Add **urban light pollution** as a function of `road_domain` (Urban vs Rural) for night driving.

---

## 4. Geometry, topology, and traffic

### What is excluded

- **Distances are Euclidean** on a **planar** embedding of lat/lon (BBBike / OSM-derived sample points), not **shortest paths on the road graph** (`Academic_Narrative` §10).
- **V7 full OSM** enriches **road domain** labels from `highway=*`; it does **not** build a routable network or turn restrictions.
- **Dynamic traffic**, **incidents**, **closures**, and **time-of-day speed profiles** are absent; arc **duration** in PyVRP is **zero** (`duration=0` in `v7/model_builder.py`), so there is no time-feasible routing.
- **Multi-depot** is supported in data structures but typical runners use a **single** Sindelfingen-style depot.

### Why

- PyVRP integration stays a **complete graph** with integer distances; road-network preprocessing (contraction hierarchies, matrices) is a separate engineering workstream.
- Zero duration keeps the model focused on **economic distance** and **skill feasibility** first.

### Options for improvement

- Replace Euclidean edges with **OSRM / Valhalla** distance/duration matrices per period or per road class.
- Add **nonzero durations** and **time windows** on clients (see §7).
- Model **congestion** as a period multiplier on distance or duration by `road_domain` or by hour-of-day from external data.

---

## 5. Road domain and spatial correlation

### What is simplified

- **Road domain** \(r_j\) is **fixed at task arrival**; it does not update if a vehicle crosses domains within one ticket (tickets are points, not corridors).
- **OSM → {Highway, Urban, Rural}** is a **bucket mapping**; many `highway=*` values are lumped into **Rural** by default (`v7` sampler).
- Task locations are **sampled** from a node/way pool; they are **not** empirical event locations from fleet logs.

### Why

- Aligns with the thesis **three-level** \(R\) while using real OSM semantics where possible.
- Keeps the rolling horizon’s **Eq. 5** form \(\mathrm{Req}^t_j = f(w^t, \ell^t, r_j)\) with **static** \(r_j\).

### Options for improvement

- **Split tickets** or **chain** subtasks if a campaign requires multi-segment ODD coverage.
- Finer **urbanity** or **speed limit** classes if data are available.
- Calibrate sampling to **real** anonymized heatmaps or fleet traces.

---

## 6. Demand generation and task semantics

### What is excluded

- Arrivals are **Poisson** (or fixed per period) with **scalar multipliers**; not fitted to **real order books** or campaign schedules.
- No **priorities**, **deadlines**, **SLA tiers**, or **contractual quotas** beyond implicit backlog statistics.
- **No stochastic correlation** across space (clustered incidents) unless introduced indirectly by map sampling density.

### Why

- **V3** explicitly chose not to add time windows to limit complexity; demand remains a stylized stress test for routing + deployment.

### Options for improvement

- **Nonhomogeneous Poisson** by region or road class; **marked** point processes for bursts.
- **Priority weights** in the objective (penalize late service) or **hard deadlines** (time windows).

---

## 7. Time windows, service times, and shift constraints

### What is excluded

- `Task` in `v7/model_builder.py` notes that **time windows / service duration could be added later**; they are **not** implemented.
- No **driver shift lengths**, **mandatory breaks**, or **crew pairing**.
- **Maintenance** and **vehicle downtime** are not modeled.

### Why

- Adds **VRPTW** complexity, tuning, and runtime; deployment layer (V6/V8) already adds a second optimization loop.

### Options for improvement

- PyVRP supports time windows when **duration** and **time matrices** are set; integrate service times per tier (sensor setup time).
- Layer **shift calendars** on deployment (`deployment.py`) before routing.

---

## 8. Fleet, energy, and vehicle physics

### What is excluded

- **No fuel or battery state**, **range limits**, **charging stops**, or **payload** (capacity lists are empty in vehicle types).
- **Speed** is implicit in distance scaling only, not physics-limited by weather (e.g. aquaplaning risk as a cap).

### Why

- **HF-MDBOVRP** focus is **capability matching** and **economic distance**, not full EV energy logistics.

### Options for improvement

- Capacities for **range** or **energy**; **refuel/charge** nodes; weather-dependent **energy per km**.

---

## 9. ODD, risk, and compatibility structure

### What is simplified

- \(\mathrm{Req}_j\) comes from a **sum of integer scores** and **thresholds** → small set of levels; this is **not** a full ISO 26262 evidence model.
- **Under-qualification** is **hard** (prohibitive edges); **graded regulatory risk** (soft violations) is not the default.
- **Over-qualification** is an **optional distance surcharge** (`overqualification_cost_penalty_per_level`); set to `0` removes it.

### Why

- **Hard** feasibility matches the thesis **\(a_{jk}\)** story and keeps solutions interpretable as **ODD-compliant** dispatch.
- Parsimony after **V5 standardization** removed stacked penalty layers from the core narrative (`Academic_Narrative` §8).

### Options for improvement

- **Finite penalties** for under-qualification instead of prohibition (risk-weighted routing)—policy choice with legal interpretation care.
- More **Req levels** or **vector-valued** requirements (separate weather vs night sensors).

---

## 10. Deployment and organization

### What is simplified

- **V6/V8 deployment** uses a **utilization sweep** and **short evaluation simulation**; it is not a full **stochastic program** over weather uncertainty.
- **V8 service constraints** use **dispatch rate** and **backlog ratio** thresholds—reasonable governance proxies, not contractual KPIs from a specific OEM.
- **Labor law**, **union rules**, and **multi-site** staffing are absent.

### Why

- Keeps deployment **transparent** and **cheap to rerun** while addressing “always activate minimal fleet” artifacts.

### Options for improvement

- **Chance constraints** on service metrics across seeds; **robust** deployment under forecast ensembles.
- **Separate** maintenance and ops budgets in the deployment objective.

---

## 11. Solver and optimality

### What is excluded

- PyVRP returns **heuristic** solutions; no **optimality gap** certificate.
- **Solver runtime** caps can leave room for improvement on large pools.

### Why

- Real instances are **large**; exact methods are impractical at thesis scale.

### Options for improvement

- Longer runs, **seed portfolios**, **lower bounds** from relaxed problems on small instances.

---

## 12. Data, calibration, and external validity

### What is excluded

- **Open-Meteo** is a **public forecast/archive**, not OEM-internal meteorology or **in-vehicle** sensor logs.
- **Cost multipliers** \(C_k\) are **research parameters**; sensitivity is argued (e.g. `v7/k_c_parameterization_argumentation.md`) but not replaced by proprietary accounting.
- **Control group** is a **sharp** homogeneous high-tier benchmark, not a “clone” of a legacy mixed fleet.

### Why

- **Transparency** and **replication** without confidential data; **clean counterfactual** interpretation.

### Options for improvement

- **Joint calibration** to internal cost sheets and dispatch logs (under NDA).
- **Holdout** regions or weeks for validation.

---

## 13. Summary table

| Domain | Excluded / reduced | Primary reason | Improvement lever |
|--------|--------------------|----------------|-------------------|
| Sun & glare | No sun angle; coarse lighting | Discrete ODD + scope | Solar elevation + illuminance |
| Weather | 3-state W; no wind/ice | Config tractability | Expand W or continuous severity |
| Roads | Euclidean; no network routing | Solver simplicity | OSRM matrices, durations |
| Time | No TW, zero duration | VRPTW complexity | PyVRP time windows + shifts |
| Demand | Poisson, stylized | No proprietary logs | Empirical processes, clusters |
| Tasks | Point ODD, static \(r_j\) | Rolling-horizon Eq. 5 | Multi-leg tickets, dynamic \(r\) |
| Fleet | No range/energy | Problem focus | Capacities, charging |
| Feasibility | Hard under-qual | Thesis clarity | Soft penalties (risk model) |
| Optimality | Heuristic VRP | Scale | Bounds, more search time |
| Economics | Simplified deployment | Transparency | Stochastic/robust deployment |

---

## 14. How to cite these limitations in the thesis

- State explicitly that **lighting** is a **discrete proxy** driven by API fields, **not** a radiometric or **sun-angle** simulation.
- Pair **map realism** claims with the caveat **planar Euclidean** distances unless/until network matrices are adopted.
- Treat **weather** labels as **operational categories** aligned with the thesis \(f(W,L,R)\), not a full mesoscale meteorology model.
- List **time windows, traffic, and energy** among **future work** if conclusions depend on them.

This keeps academic claims **proportionate** to the implemented artifact while giving reviewers a clear **roadmap** for extensions.
