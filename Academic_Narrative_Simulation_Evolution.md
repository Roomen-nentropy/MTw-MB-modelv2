# Evolution of the Heterogeneous-Fleet Rolling-Horizon Simulation: A Methodological Narrative

## Abstract

This document records the relationship between the thesis methodology for skill-based, economically weighted routing under Level 3 (L3) Advanced Driver-Assistance Systems (ADAS) validation constraints and the full coding and iteration trajectory of its implementation. The research extends Morlock’s (2024) Multi-Depot Balanced Open Vehicle Routing Problem (MDBOVRP)—originally formulated for a homogeneous fleet—into a **Heterogeneous Fleet MDBOVRP (HF-MDBOVRP)** with a three-phase structure: probabilistic environmental modelling and compatibility, mathematical formulation with an economic objective and hard skill constraints, and metaheuristic solution via a modified Hybrid Genetic Algorithm (HGA) within PyVRP (Wouda et al., 2024), embedded in a **rolling-horizon** framework after Morlock and the dynamic VRP literature (Pillac et al., 2013; Chand et al., 2002). The codebase began as the `hf_mdbovrp` package implementing that framework on a synthetic environment; subsequent versions (V3–V6) increased economic and environmental realism and external validity (real map sampling, meteorological series, deployment margins), then **standardized** the control-group counterfactual and simplified the implemented routing objective to emphasize equipment-weighted travel cost. The narrative uses language familiar to applied economics: objectives as reduced-form cost minimization, constraints as regulatory and technological feasibility sets, and paired fleet comparisons as controlled policy counterfactuals.

---

## 1. Thesis methodological foundation: from homogeneous routing to capability matching

### 1.1 Problem setting and literature anchor

Validation of L3 autonomy is contingent on the **Operational Design Domain (ODD)**: weather, lighting, and road context jointly determine which sensor configurations may legally and technically collect valid data, consistent with safety-oriented standards such as ISO 26262. Morlock (2024) provides a mathematical foundation for **balanced** multi-depot open routing with a focus on minimizing driving distance and balancing workload, under a **homogeneous** fleet assumption—vehicles and tasks treated as interchangeable at the routing layer.

Manufacturer validation fleets (e.g., Mercedes-Benz) depart from that assumption: **purpose-driven hardware** and differentiated sensor suites imply a spectrum of capabilities and operating costs (Stäblein, 2026, as cited in the thesis). The thesis therefore shifts emphasis from routing-to-locations alone to **matching capabilities**: assigning each environmental scenario to a vehicle tier whose sensors satisfy the scenario’s requirement.

### 1.2 Hierarchical tiered modelling: fleet parameters

Two parameters operationalize heterogeneity:

- **Sensor capability index (Skill_k).** Discrete ordinal tiers \(k\) with \(\mathrm{Skill}_k \in \mathbb{Z}_+\). Higher tiers denote configurations permitted in more demanding ODDs (e.g., adverse weather and night); lower tiers are restricted to favourable conditions. This ordinal structure supports the inequalities used in compatibility rules below.

- **Asymmetric operating costs (\(C_k \geq 1\)).** High-fidelity platforms imply higher capital, maintenance, data volume, and downstream processing cost than standard setups. Pure distance minimization is economically insufficient; the thesis adopts an **economic cost multiplier** \(C_k\) so that arc \((i,j)\) traversed by tier \(k\) contributes proportional cost \(d_{ij} \cdot C_k\) in the objective (see Section 1.4).

### 1.3 Phase 1: Probabilistic environmental modelling and the compatibility matrix

Before geographic routing, each task \(j\) is associated with an environmental state \(E_j = (w_j, \ell_j, r_j)\) with weather \(w_j \in W\), lighting \(\ell_j \in L\), and road domain \(r_j \in R\). A mapping \(f : W \times L \times R \rightarrow \mathbb{Z}_+\) yields the **task requirement level** \(\mathrm{Req}_j = f(w_j,\ell_j,r_j)\), interpreted as the minimum sensor tier legally and technically required.

The **compatibility matrix** \(a_{jk} \in \{0,1\}\) encodes hard feasibility:

\[
a_{jk} = 1 \quad \Leftrightarrow \quad \mathrm{Skill}_k \geq \mathrm{Req}_j .
\]

Thus Phase 1 translates qualitative ODD descriptions into a **deterministic** input for Phase 2: infeasible vehicle–task pairs are excluded from admissible routing.

### 1.4 Phase 2: HF-MDBOVRP formulation

On a directed graph \(G=(V,A)\) with tasks \(N\), depots \(D\), and vehicles \(K\), binary routing variables (e.g., \(x^k_{ij}\), \(y^k_j\)) describe assignments and arcs. The **economic objective** minimizes total economic travel cost:

\[
\min \sum_{k \in K} \sum_{i \in V} \sum_{j \in V} d_{ij} \, C_k \, x^k_{ij},
\]

subject to standard routing structure inherited from the MDBOVRP baseline **plus** **hard skill constraints** linking assignment indicators to \(a_{jk}\), so that incompatible pairs cannot appear in a feasible solution. In the thesis, this is the bridge between Phase 1’s regulatory logic and Phase 2’s optimization layer.

### 1.5 Phase 3: Algorithm adaptation—the modified HGA and compatibility penalties

Large instances are NP-hard; exact methods are impractical at operational scale. The thesis adopts PyVRP’s **Hybrid Genetic Algorithm** (Wouda et al., 2024). Strictly discarding every infeasible crossover offspring can harm exploration; the implementation therefore uses a **large compatibility penalty** on violations of \(a_{jk}\) during search so that infeasible assignments are effectively priced out while the metaheuristic retains diversity. In the implemented codebase, this role is fulfilled by **prohibitive edge distances** for incompatible vehicle–task pairs under profile-specific matrices, steering local search toward feasible, low-economic-cost solutions.

### 1.6 Dynamic tour planning: rolling horizon and time-dependent compatibility

Real operations are not static: tickets arrive over the day and environmental conditions change. The thesis inherits **rolling-horizon** planning from Morlock (2024) and the DVRP literature (Pillac et al., 2013), conceptually related to receding-horizon control (Chand et al., 2002). Time is discretized into periods \(t \in T\). At each \(t\), the planner observes the available task pool, updates forecasts, recomputes \(\mathrm{Req}_j(t)\) and hence \(a_{jk}(t)\), solves a finite-horizon subproblem, **commits** only over a short execution window, then rolls forward. The simulation implementation mirrors this loop: period-wise weather (and, in integrated versions, exogenous hourly weather files), task generation, solve, and backlog update.

---

## 2. Software implementation baseline: `hf_mdbovrp` (internal Version 2)

The **first coded realization** of the thesis framework is the package **`hf_mdbovrp`**, together with entry scripts `run_simulation.py`, `run_controlgroup.py`, `run_comparative_simulation.py`, and `run_cost_optimization.py` (see `README_MainSim.md`). This baseline maps the three phases as follows:

| Thesis phase | Implementation locus (conceptual) |
|--------------|-----------------------------------|
| Phase 1 | `environment.py`: scoring of \((w,\ell,r)\) into \(\mathrm{Req}_j\); `compatibility_matrix` from \(\mathrm{Skill}_k\) and \(\mathrm{Req}_j\). |
| Phase 2 | `model_builder.py`: economic unit costs \(d \cdot C_k\) (via `cost_multiplier` and `cost_scale`); hard skill structure via prohibitive distances on incompatible edges. |
| Phase 3 | PyVRP solve loop with the above penalized / prohibitive structure; `rolling_horizon.py` orchestrates repeated static solves. |
| Rolling horizon | `simulation.py` + `rolling_horizon.py`: period loop, planning horizon, commitment, pending tasks. |

The environment is **synthetic**: tasks on a grid, Markov weather and cyclic lighting unless replaced in later versions. Internally, this line of code is treated as **Version 2**: the homogeneous-fleet assumption of the original Morlock-style narrative is **lifted** here via tiers and \(C_k\), while preserving balanced open routing semantics at the package level.

**Everything that follows in the repository**—`v3_setup`, `v4_setup`, `v5_real_world_data`, `v6_real_world_data`, and root runners `run_sim_v3.py` through `run_comp_v6_demo_small_area.py`—extends or replicates this core **without abandoning** the skill-equality and economic-arc-cost logic of Phase 2, until the late standardization described in Section 8 adjusts which *additional* penalty terms enter the PyVRP objective.

---

## 3. Architectural invariants (across V2–V6 lineage)

- **Rolling-horizon simulation.** Periods advance; environment and compatibility inputs update; tasks are generated, queued, and solved under a finite horizon and commitment structure.
- **Skill-based feasibility.** Incompatible vehicle–task pairs remain structurally infeasible via large penalties on corresponding edges (thesis Phase 3).
- **Economic routing core.** Arc costs reflect distance scaled by tier-specific \(C_k\) (`cost_multiplier`), optionally scaled by period-specific operating conditions in V4+ packages.
- **Paired experimentation.** Model fleet versus control-group fleet under identical seeds and shared non-fleet assumptions where enforced by comparison scripts, so differences attribute primarily to fleet policy.

---

## 4. Version 3: condition-sensitive demand intensity and tier fixed costs (historical extension)

### 4.1 Economic rationale

Stationary arrival rates ignore that adverse conditions may shift short-run demand for validation or support tasks. **Tier-sensitive fixed deployment costs** capture setup and readiness not proportional to distance alone.

### 4.2 Implementation

Package `v3_setup`; runners `run_sim_v3.py`, `run_comp_V3vsCG.py`. Configuration adds weather- and lighting-linked multipliers to effective arrival intensity; model builder initially added fixed route costs tied to tier (later neutralized in the standardized objective; see Section 8).

---

## 5. Version 4: state-dependent operating costs and nonlinear mismatch channels (historical extension)

### 5.1 Economic rationale

Marginal operating cost varies with environment (fuel, risk, compliance). Nonlinear functions of \(C_k\) and explicit overqualification surcharges on edges were introduced to penalize deploying advanced tiers on low-requirement tasks—internal shadow pricing of capability mismatch.

### 5.2 Implementation

Package `v4_setup`; runners `run_sim_v4.py`, `run_comp_V4vsCG.py`. Operating-cost multipliers enter the rolling horizon and model builder.

---

## 6. Version 5: external validity—real geography and exogenous weather

### 6.1 Motivation

Synthetic grids support internal validity; **external validity** calls for realistic spatial support and weather paths. V5 integrates a BBBike OSM extract (`planet_8.317,48.426_9.898,49.134.osm.csv.xz`) and Open-Meteo hourly series (default: seven days past plus seven days forecast), depot projection in the Stuttgart/Sindelfingen region, and map-driven task sampling.

### 6.2 Implementation

Package `v5_real_world_data`; `rum_sim_v5.py`, `run_comp_v5vsCG.py`, `run_comp_v5_demo_small_area.py`; dependencies in `requirements_openmeteo.txt`.

---

## 7. Version 6: owned capacity, selective deployment, and short-horizon forecast

### 7.1 Economic rationale

Firms may **own** more vehicles than they **activate** on a given day. V6 scales owned fleet size, evaluates candidate deployed fleet sizes using a short forecast window, then runs the rolling simulation with the selected deployment— a stylized two-stage **capacity** and **routing** problem.

### 7.2 Implementation

Package `v6_real_world_data`; `rum_sim_v6.py`, `run_comp_v6vsCG.py`, `run_comp_v6_demo_small_area.py`; deployment logic in `deployment.py`.

---

## 8. Late standardization: control group and objective parsimony (post–Version 2 packages)

Two tensions motivated consolidation: (i) the control group should be an unambiguous **homogeneous high-capability** benchmark; (ii) stacking many penalty terms obscures attribution to equipment prices \(C_k\).

Across `v3_setup`, `v4_setup`, `v5_real_world_data`, and `v6_real_world_data`:

1. **Control group** is a **single tier** at maximum \(\mathrm{Skill}_k\) and associated \(C_k\), with vehicle count equal to the sum of (deployed) model vehicles—sharp counterfactual versus mixed tiers.
2. **PyVRP objective** in these packages **drops** fixed per-route surcharges and overqualification edge surcharges; economic cost is driven by **equipment-weighted travel** (and, where configured, period operating multipliers), while **hard incompatibility** remains via prohibitive edges—consistent with the thesis core objective \(d_{ij} C_k\) plus hard feasibility, without extra ad hoc penalty layers.
3. **Comparison runners** no longer apply separate penalty calibration to the control group; paired runs share the same cost environment.
4. **Legacy config fields** for removed penalties are retained for compatibility but documented as **ignored** by the current builder.

### 8.1 Process of abandoning the auxiliary penalty system

The move away from the layered penalty structure was **incremental and diagnostic** rather than arbitrary. Intermediate versions (notably V3 and V4) had added: (a) **tier-sensitive fixed route costs**—intended to mimic readiness and deployment overhead beyond distance; (b) **nonlinear transforms** of the equipment multiplier in that fixed-cost term; (c) **overqualification surcharges** on edges when \(\mathrm{Skill}_k > \mathrm{Req}_j\), to discourage economically wasteful matching of high-capability assets to simple tickets; and (d) in real-world paired runs, **asymmetric calibration** of some of these parameters for the control group relative to the model fleet, motivated by the fear that an all-advanced counterfactual would otherwise face an unrealistically harsh cost landscape under the same penalty stack.

Three problems accumulated. **Identification:** observed cost gaps between model and control group conflated (i) true differences in fleet design, (ii) differences in implicit shadow prices from auxiliary penalties, and (iii) deliberate tuning of control-group parameters—making it difficult to state cleanly *what* was being compared. **Coherence with the core thesis formulation:** the published HF-MDBOVRP objective emphasizes \(\sum d_{ij} C_k\); additional terms risk drifting the implementation toward an ad hoc composite objective whose weights lack a clear welfare or accounting interpretation. **Counterfactual clarity:** the control group needed to represent a single, well-defined policy—“dispatch only the highest tier at common scale”—not a hybrid of relabeled tiers with uneven penalty treatment.

The abandonment therefore proceeded in two steps in code: **removing** fixed-cost and overqualification channels from the PyVRP cost construction in the post–V2 packages, while **retaining** the thesis-consistent mechanism for infeasibility (prohibitive costs on incompatible vehicle–task edges). **Eliminating** per-run overrides that reset penalty parameters for the control group in comparison scripts. **Preserving** the old configuration keys with documentation that they no longer feed the objective, so existing experiments and scripts fail softly rather than through silent semantic change. Hard ODD feasibility was never abandoned—only the *economic* penalties that sat on top of the core distance-times-\(C_k\) structure.

### 8.2 Effects of the new approach

**Interpretability.** Total route cost in the standardized packages is now predominantly **equipment-weighted travel** (and, where V4-style logic applies, **period-specific operating multipliers** tied to weather and lighting). The researcher can attribute differences between policies to (a) **which tiers are used**, (b) **how far** they drive, and (c) **exogenous state-dependent scaling**—without decomposing an opaque stack of penalty parameters.

**Counterfactual discipline.** The control group is a **single homogeneous tier** with the same aggregate vehicle count as the comparison fleet (or the deployed subset in V6). Paired runs share **identical** penalty-related configuration in the sense that no branch applies extra tuning to the control group. The estimated “treatment effect” of mixed-tier policy versus all-advanced policy is therefore **less confounded** by auxiliary calibration choices.

**Magnitude and ranking of outcomes.** Dropping fixed and overqualification surcharges generally **compresses** the spread of reported costs relative to the richer penalty regime: high-tier vehicles are still expensive via \(C_k\) on every kilometre, but they no longer incur additional artificial charges per route or per overqualified edge. **Relative** rankings of model versus control group may shift; **dispatch and backlog** metrics become even more important as guards against interpreting pure cost reductions that coincide with worse service. The researcher should re-baseline any empirical claims that were calibrated under the old penalty stack.

**Alignment with the methodological chapter.** The streamlined implementation sits **closer** to the stated Phase 2 objective (economic distance with \(C_k\)) and Phase 1/3 logic (hard feasibility via the compatibility structure, implemented as prohibitive edges). Auxiliary penalties, where they were motivated by operational storytelling, are **explicitly retired** from the objective rather than left implicit in composite “fitness” functions—improving transparency for thesis readers and referees.

**Costs of simplification.** The new approach **understates** some real phenomena the old penalties tried to mimic: setup time, crew calibration, and the internal charge for “using a Ferrari for a grocery run” beyond what \(C_k\) already implies on distance. If those margins matter for managerial conclusions, they must be reintroduced either as **observable data** (e.g., time windows, fixed charges tied to accounting) or as a **sensitivity layer** documented separately—not as undocumented composite weights inside the solver.

---

## 9. Software engineering and reproducibility

Version-specific packages freeze lineages for citation and replication; root-level runners provide stable invocation. Multi-seed modes approximate Monte Carlo evaluation of policy deltas. Granular change logs live in per-version markdown files; this document integrates them for thesis exposition.

---

## 10. Limitations

- **Geometry:** BBBike integration uses a reproducible planar embedding; distances are not full road-network shortest paths.
- **Demand:** Task processes remain stylized relative to proprietary order data.
- **Optimality:** PyVRP returns heuristic solutions, not proven global optima.
- **Data replication:** Open-Meteo CSVs should be archived for bit-exact reproduction.

---

## 11. Conclusion

The coded artefact begins as **`hf_mdbovrp`**, the direct computational encoding of the thesis’s three-phase HF-MDBOVRP and rolling-horizon design. Subsequent versions enrich state dynamics, costs, and data realism—culminating in map- and weather-integrated experiments and a deployment margin—while a final standardization aligns the **control group** and **implemented objective** with the clearest economic interpretation: **heterogeneous versus homogeneous high-capability fleets** under **equipment-weighted routing costs** and **hard ODD-driven feasibility**, as laid out in the methodological chapter.

For commands and file layout, see `README_MainSim.md`. For file-level iteration detail, see the version-specific process notes under each package.

