# V7 Full-OSM Road-Domain Integration Process (from V6 Baseline)

## Objective
- Keep the V6 operational flow (owned vs deployed fleet + next-day planning).
- Replace synthetic road-domain assignment with map-derived labels from full OSM.
- Keep backward compatibility with legacy BBBike `.osm.csv.xz` inputs.
- Add V7 run and paired-comparison entry scripts aligned with existing workflows.

## Baseline Limitation in V6/V7-Pre
- Prior BBBike integration sampled task coordinates from lightweight exports but did not use real `highway=*` tags.
- `TaskEnv.road_domain` was assigned from configured probabilities (`road_domain_weights`) rather than actual road classes.
- Result: map realism for coordinates existed, but road-type semantics were synthetic.

## Input Data Upgrade
- Added and validated full Stuttgart-region OSM XML archive:
  - `v7/planet_8.317,48.426_9.898,49.134.osm.xz`
- Confirmed this file contains:
  - `<bounds .../>`,
  - full `<node lat=... lon=.../>`,
  - `<way>` structures with tags including `highway=*`.

## Implemented V7 Changes and Rationale

### 1) Full-OSM parser + road-domain extraction
- **File:** `v7/bbbike_map_sampler.py`
- **What changed:**
  - Added streaming XML parsing for `.osm.xz` via `xml.etree.ElementTree.iterparse`.
  - Added `build_local_task_pool_with_domain_from_bbbike(...)` that returns `(x, y, road_domain)` tuples.
  - Added bbox parsing compatibility for both:
    - filename pattern (`planet_<lon_min>,<lat_min>_<lon_max>,<lat_max>.osm(.csv).xz`),
    - fallback from `<bounds>` in XML.
- **Why:**
  - Enables direct extraction of road semantics from real OSM ways instead of synthetic assignment.

### 2) OSM `highway=*` to simulation domain mapping
- **File:** `v7/bbbike_map_sampler.py`
- **What changed:**
  - Added deterministic mapping:
    - **Highway:** `motorway`, `motorway_link`, `trunk`, `trunk_link`, `primary`, `primary_link`
    - **Urban:** `residential`, `living_street`, `service`, `pedestrian`, `road`
    - **Rural:** default bucket for remaining highway classes
- **Why:**
  - Preserves 3-level thesis domain structure while grounding labels in OSM taxonomy.

### 2b) Fleet cost parameter calibration update (`c`)
- **File:** `rum_sim_v7.py`
- **What changed:**
  - Updated advanced-tier base operating cost multiplier from `1.8` to `1.35`.
  - Kept `Skill` tiers ordinal (`Standard=1`, `Advanced=2`) and compatibility logic unchanged.
- **Why:**
  - Sensitivity testing over `C_advanced in {1.25, 1.35, 1.50, 1.60, 1.80}` showed monotonic cost inflation with larger `C_advanced`, while service indicators (dispatch/backlog) were unchanged in the tested setup.
  - This indicates `1.8` likely over-penalized advanced vehicles economically without observed service-quality benefit.
  - `1.35` is therefore adopted as the V7 baseline as a more defensible middle-ground value, with `1.25` and `1.50` reserved as robustness bounds.

### 3) Task generation uses map-derived road domain
- **File:** `v7/dynamic_env.py`
- **What changed:**
  - `TaskGenerator` now loads map pool entries with optional domain.
  - If a map-derived domain exists, it overrides weighted random domain draw.
  - If unavailable (legacy `.osm.csv.xz`), behavior falls back to existing weighted assignment.
- **Why:**
  - Guarantees semantic upgrade for full OSM while maintaining compatibility with previous data format.

### 4) Parse-cost mitigation through on-disk cache
- **File:** `v7/bbbike_map_sampler.py`
- **What changed:**
  - Added cache output for projected sampled pool:
    - `<map_filename>.pool_<pool_size>.csv`
  - On subsequent runs with same pool size, loader reuses cache instead of re-parsing full XML.
- **Why:**
  - Full OSM parse is expensive; cache keeps operational iteration fast.

### 5) Public API and config notes updated
- **Files:** `v7/__init__.py`, `v7/config.py`
- **What changed:**
  - Exported `build_local_task_pool_with_domain_from_bbbike`.
  - Clarified config comment that both `.osm.csv.xz` and full `.osm.xz` are supported.
- **Why:**
  - Keeps package surface clear and discoverable for runner scripts and future extensions.

## New V7 Runner Files

### 1) `rum_sim_v7.py`
- V7 end-to-end real-world run script.
- Uses:
  - full OSM map (`v7/planet_...osm.xz`),
  - next-day Open-Meteo forecast CSV,
  - owned-vs-deployed fleet optimization flow from V6.
- Prints deployment and KPI summary.

### 2) `run_comp_v7vsCG.py`
- Paired model-vs-control comparison for V7.
- Mirrors V6 comparison logic with V7 package wiring.
- Supports `COMPARE_MODE=quick|medium|full`.

## Compatibility Policy
- **Full `.osm.xz`:** map-derived road domains are used.
- **Legacy `.osm.csv.xz`:** old coordinate-only sampling remains valid; road domains revert to weighted sampling.
- This allows migration without breaking prior experiments.

## Verification Performed
- Python syntax checks passed for all new/edited V7 files.
- Lints are clean on edited scripts.
- Full-OSM parsing path validated structurally and integrated into task generator flow.
- Cost-multiplier sensitivity sweep executed and documented; resulting V7 baseline now uses `C_advanced=1.35`.

## Expected Impact
- **Higher external validity:** road-domain labels now reflect real road classes.
- **Consistent experiment logic:** fleet/deployment comparison design unchanged from V6.
- **Operational usability:** first parse may be heavy, then cached startup becomes much faster.
- **Extension-ready:** future routing realism can use the same OSM parse foundation (edge-level cost/speed models, matrix generation, urbanity refinements).

## How to Run
- V7 single run:
  - `python rum_sim_v7.py`
- V7 paired comparison:
  - PowerShell quick mode:
    - `$env:COMPARE_MODE="quick"; python run_comp_v7vsCG.py`

## Interpretation Guide
- V7 comparison output keeps the same semantics as V6:
  - scenario A = deployed model fleet,
  - scenario B = control-group fleet.
- Positive `dCost` means control group is more expensive than the model policy.
- Evaluate cost deltas together with dispatch and backlog deltas to avoid service-quality regressions.
- When interpreting V7 cost outcomes, use `C_advanced=1.35` as default baseline and compare against robustness settings (`1.25`, `1.50`) for sensitivity reporting.
