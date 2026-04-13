"""
rolling_horizon.py – The rolling-horizon planning engine.

Implements the four-step cycle from the thesis (Section 3.4):
  1. Look Ahead   – re-evaluate Req^t_j for all pending tasks via Eq. 5
  2. Optimise     – solve the skill-constrained HF-MDBOVRP with PyVRP
  3. Execute      – commit dispatched routes, filter truly incompatible tasks
  4. Roll Forward – caller advances t; deferred tasks stay in pending pool
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple

import pyvrp

from .config import SimulationConfig
from .environment import TaskEnv, TaskRequirementMapping, compute_task_requirement_level
from .fleet import VehicleTier
from .model_builder import Depot, Task, build_skill_based_pyvrp_model, solve_pyvrp_model


# ─────────────────────────────────────────────────────────────────────────────
# Result data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DispatchedRoute:
    """One vehicle's route committed in a single period."""
    period: int
    vehicle_tier_name: str
    task_names: List[str]
    route_distance: float


@dataclass
class PeriodResult:
    """All statistics produced by one rolling-horizon cycle."""
    period: int
    weather: str
    lighting: str

    # Task counts
    tasks_in_pool: int          # tasks that entered this period's solve
    tasks_dispatched: int       # tasks committed after solving
    tasks_deferred: int         # tasks skipped (incompatible with all tiers)
    tasks_remaining: int        # pool size after dispatch (passed back to sim)

    # Routes
    routes: List[DispatchedRoute]

    # Performance
    solve_time_s: float
    total_route_cost: float     # PyVRP objective value (scaled ints)
    pyvrp_feasible: bool        # True if PyVRP reports a feasible solution


# ─────────────────────────────────────────────────────────────────────────────
# Planner
# ─────────────────────────────────────────────────────────────────────────────

class RollingHorizonPlanner:
    """
    Executes one rolling-horizon cycle per call to run_period().

    The planner is stateless between calls (no memory of past routes).
    The simulation loop in simulation.py owns the pending task pool and
    removes dispatched tasks after each call.
    """

    def __init__(self, config: SimulationConfig) -> None:
        self._cfg = config

        # Build TaskRequirementMapping from config
        self._mapping = TaskRequirementMapping(
            weather_score=config.weather_score,
            lighting_score=config.lighting_score,
            road_domain_score=config.road_domain_score,
            thresholds=config.req_thresholds,
            req_levels=config.req_levels,
        )

        # Build VehicleTier objects (used for compatibility pre-filtering)
        self._vehicle_tiers: List[VehicleTier] = [
            VehicleTier(
                name=t.name,
                skill_k=t.skill_k,
                cost_multiplier=t.cost_multiplier,
                num_available=t.num_available,
                start_depot_index=t.start_depot_idx,
            )
            for t in config.fleet
        ]

        # Build Depot objects
        self._depots: List[Depot] = [
            Depot(name=d.name, x=d.x, y=d.y)
            for d in config.depots
        ]

        # Maximum skill in the fleet – tasks requiring more are always deferred
        self._max_skill = max(t.skill_k for t in self._vehicle_tiers)

        self._history: List[PeriodResult] = []

    # ──────────────────────────────────────────────────────────────────────────
    # Public interface
    # ──────────────────────────────────────────────────────────────────────────

    def run_period(
        self,
        period: int,
        pending_tasks: List[dict],
        weather: str,
        lighting: str,
    ) -> Tuple[PeriodResult, List[str]]:
        """
        Execute one rolling-horizon cycle.

        Parameters
        ----------
        period        : Current period index (0-based).
        pending_tasks : All undispatched task dicts (from simulation's pool).
        weather       : Current weather state (re-evaluates all req_levels).
        lighting      : Current lighting state.

        Returns
        -------
        result        : PeriodResult with full statistics.
        dispatched    : List of task names that were committed this period.
                        The simulation removes these from pending_tasks.
        """
        # ── Step 1: Look Ahead – recompute time-dependent req_levels (Eq. 5) ──
        # Road domain is static; weather and lighting vary each period.
        task_objs, deferred_names = self._recompute_requirements(
            pending_tasks, weather, lighting
        )
        # Why: operating economics should reflect current conditions, not just
        # task generation. This yields more realistic period-specific routing cost.
        weather_cost_mult = self._cfg.weather_operating_cost_multiplier.get(weather, 1.0)
        lighting_cost_mult = self._cfg.lighting_operating_cost_multiplier.get(lighting, 1.0)
        operating_cost_multiplier = weather_cost_mult * lighting_cost_mult

        t0 = time.perf_counter()

        # ── Empty pool guard ──────────────────────────────────────────────────
        if not task_objs:
            result = PeriodResult(
                period=period,
                weather=weather,
                lighting=lighting,
                tasks_in_pool=0,
                tasks_dispatched=0,
                tasks_deferred=len(deferred_names),
                tasks_remaining=len(pending_tasks),
                routes=[],
                solve_time_s=0.0,
                total_route_cost=0.0,
                pyvrp_feasible=True,
            )
            self._history.append(result)
            return result, []

        # ── Step 2: Optimise – build and solve the PyVRP model ────────────────
        try:
            model, meta = build_skill_based_pyvrp_model(
                tasks=task_objs,
                depots=self._depots,
                vehicle_tiers=self._vehicle_tiers,
                coord_scale=self._cfg.coord_scale,
                cost_scale=self._cfg.cost_scale,
                big_factor=self._cfg.big_factor,
                vehicle_fixed_cost_scale=self._cfg.vehicle_fixed_cost_scale,
                vehicle_fixed_cost_exponent=self._cfg.vehicle_fixed_cost_exponent,
                operating_cost_multiplier=operating_cost_multiplier,
                overqualification_cost_penalty_per_level=self._cfg.overqualification_cost_penalty_per_level,
            )
            pyvrp_result = solve_pyvrp_model(
                model,
                max_runtime_seconds=self._cfg.solver_max_runtime,
                seed=self._cfg.solver_seed,
                display=False,
            )
        except Exception as exc:
            if self._cfg.verbose:
                print(f"    [Period {period}] Solver exception: {exc}")
            result = PeriodResult(
                period=period,
                weather=weather,
                lighting=lighting,
                tasks_in_pool=len(task_objs),
                tasks_dispatched=0,
                tasks_deferred=len(deferred_names),
                tasks_remaining=len(pending_tasks),
                routes=[],
                solve_time_s=time.perf_counter() - t0,
                total_route_cost=float("inf"),
                pyvrp_feasible=False,
            )
            self._history.append(result)
            return result, []

        solve_time = time.perf_counter() - t0
        feasible = pyvrp_result.is_feasible()

        # ── Step 3: Execute – extract routes and commit dispatched tasks ──────
        if feasible:
            routes, dispatched_names = self._extract_routes(
                pyvrp_result, task_objs, meta, period
            )
            total_cost = float(pyvrp_result.cost())
        else:
            # Solution infeasible (e.g. capacity violated) – dispatch nothing,
            # tasks stay in the pool for the next period.
            routes, dispatched_names = [], []
            total_cost = float("inf")

        result = PeriodResult(
            period=period,
            weather=weather,
            lighting=lighting,
            tasks_in_pool=len(task_objs),
            tasks_dispatched=len(dispatched_names),
            tasks_deferred=len(deferred_names),
            tasks_remaining=len(pending_tasks) - len(dispatched_names),
            routes=routes,
            solve_time_s=solve_time,
            total_route_cost=total_cost,
            pyvrp_feasible=feasible,
        )
        self._history.append(result)
        # Step 4 (Roll Forward) is handled by the simulation loop.
        return result, dispatched_names

    @property
    def history(self) -> List[PeriodResult]:
        return list(self._history)

    # ──────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _recompute_requirements(
        self,
        pending: List[dict],
        weather: str,
        lighting: str,
    ) -> Tuple[List[Task], Set[str]]:
        """
        Equation 5: Req^t_j = f(w^t_j, l^t_j, r_j).

        Weather and lighting are updated to the current period values.
        Road domain r_j is the static value assigned at task arrival.

        Returns
        -------
        routable_tasks : Task objects compatible with at least one fleet tier.
        deferred_names : Names of tasks whose req_level exceeds max fleet skill
                         (incompatible with ALL tiers given current conditions).
                         These are held in the pending pool and re-evaluated
                         next period when conditions may improve.
        """
        routable: List[Task] = []
        deferred: Set[str] = set()

        for raw in pending:
            # Re-evaluate env with current weather & lighting (road domain static)
            current_env = TaskEnv(
                weather=weather,
                lighting=lighting,
                road_domain=raw["env"].road_domain,
            )
            req = compute_task_requirement_level(current_env, self._mapping)

            if req > self._max_skill:
                # No vehicle in the fleet can legally handle this task right now.
                # It will be re-evaluated next period (rolling horizon handles this
                # automatically – the task stays in pending_tasks).
                deferred.add(raw["name"])
            else:
                routable.append(Task(
                    name=raw["name"],
                    x=raw["x"],
                    y=raw["y"],
                    req_level=req,
                ))

        return routable, deferred

    def _extract_routes(
        self,
        pyvrp_result: pyvrp.Result,
        task_objs: List[Task],
        meta: dict,
        period: int,
    ) -> Tuple[List[DispatchedRoute], List[str]]:
        """
        Parse the best PyVRP solution into DispatchedRoute objects.

        PyVRP's route.visits() returns 0-based client indices in the order
        clients were added to the model (= order of task_objs).
        route.vehicle_type() returns the 0-based index into the vehicle
        types list, which matches self._vehicle_tiers order.
        """
        client_names = [t.name for t in task_objs]
        tier_names = [t.name for t in self._vehicle_tiers]

        dispatched_routes: List[DispatchedRoute] = []
        dispatched_names: List[str] = []

        best = pyvrp_result.best
        for route in best.routes():
            visits = list(route.visits())
            if not visits:
                continue

            vt_idx = route.vehicle_type()
            tier_name = (
                tier_names[vt_idx]
                if vt_idx < len(tier_names)
                else f"tier_{vt_idx}"
            )

            names_on_route: List[str] = []
            for client_idx in visits:
                if client_idx < len(client_names):
                    names_on_route.append(client_names[client_idx])

            dispatched_routes.append(DispatchedRoute(
                period=period,
                vehicle_tier_name=tier_name,
                task_names=names_on_route,
                route_distance=float(route.distance()),
            ))
            dispatched_names.extend(names_on_route)

        return dispatched_routes, dispatched_names
