"""
simulation.py – Orchestrates the full rolling-horizon simulation.

Responsibilities:
  • Drive the period loop (weather, lighting, task arrival)
  • Call RollingHorizonPlanner.run_period() each step
  • Maintain the pending task pool
  • Collect and serialise statistics
  • Save JSON results to disk
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from .config import SimulationConfig
from .dynamic_env import LightingSimulator, TaskGenerator, WeatherSimulator
from .rolling_horizon import PeriodResult, RollingHorizonPlanner

import random


# ─────────────────────────────────────────────────────────────────────────────
# Summary dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SimulationSummary:
    """Aggregate statistics for a completed simulation run."""

    # Config snapshot (serialisable)
    config_snapshot: dict

    # Counts
    total_periods: int
    total_tasks_generated: int
    total_tasks_dispatched: int
    total_tasks_remaining_at_end: int
    total_tasks_ever_deferred: int     # cumulative deferral events (not unique)

    # Cost / time
    total_route_cost: float
    total_solve_time_s: float
    wall_time_s: float

    # Period-level feasibility
    feasible_periods: int
    infeasible_periods: int

    # Averages
    avg_tasks_generated_per_period: float
    avg_tasks_dispatched_per_period: float
    avg_route_cost_per_feasible_period: float
    avg_solve_time_per_period_s: float
    # Why: cost-focused tuning needs a normalised KPI; this makes runs with
    # different workload sizes directly comparable.
    avg_cost_per_dispatched_task: float
    # Why: cheap but low-service policies can hide unmet demand in backlog;
    # this ratio helps reject such "false savings".
    backlog_ratio_at_end: float

    # Weather breakdown
    weather_period_counts: Dict[str, int]

    # Per-period detail
    period_results: List[dict]


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_simulation(config: SimulationConfig) -> SimulationSummary:
    """
    Execute a complete rolling-horizon simulation.

    Parameters
    ----------
    config : SimulationConfig instance with all parameters set.

    Returns
    -------
    SimulationSummary with full per-period statistics, plus a JSON file
    written to config.results_dir if config.save_results is True.
    """
    # ── Initialise components ─────────────────────────────────────────────────
    rng = random.Random(config.random_seed)
    weather_sim   = WeatherSimulator(config, rng)
    lighting_sim  = LightingSimulator(config)
    task_gen      = TaskGenerator(config, rng)
    planner       = RollingHorizonPlanner(config)

    # ── State ─────────────────────────────────────────────────────────────────
    pending_tasks: List[dict] = []   # unfinished tasks (dicts from TaskGenerator)
    all_results:   List[PeriodResult] = []

    total_generated    = 0
    total_dispatched   = 0
    total_deferred_ev  = 0   # cumulative deferral events across all periods
    total_cost         = 0.0
    total_solve_time   = 0.0
    feasible_count     = 0
    infeasible_count   = 0
    weather_counts: Dict[str, int] = {}

    # ── Banner ────────────────────────────────────────────────────────────────
    if config.verbose:
        _print_banner(config)

    wall_start = time.perf_counter()

    # ── Main period loop ──────────────────────────────────────────────────────
    for t in range(config.total_periods):

        # Step: update environment
        weather = (
            config.initial_weather if t == 0
            else weather_sim.step()
        )
        lighting = lighting_sim.get(t)
        weather_counts[weather] = weather_counts.get(weather, 0) + 1

        # Step: task arrivals
        new_tasks = task_gen.generate(t, weather, lighting)
        total_generated += len(new_tasks)

        # Enforce max_active_tasks cap (oldest tasks remain; newest overflow dropped)
        headroom = config.max_active_tasks - len(pending_tasks)
        if headroom > 0:
            pending_tasks.extend(new_tasks[:headroom])
        dropped = max(0, len(new_tasks) - headroom)

        # Step: print period header
        if config.verbose:
            print(
                f"\n[t={t:>3d}/{config.total_periods - 1}] "
                f"{weather:<6s} / {lighting:<8s}  "
                f"arrived={len(new_tasks):>3d}"
                + (f"  dropped={dropped}" if dropped else "")
                + f"  pool={len(pending_tasks):>4d}"
            )

        # Step: rolling horizon solve
        result, dispatched_names = planner.run_period(
            period=t,
            pending_tasks=pending_tasks,
            weather=weather,
            lighting=lighting,
        )
        all_results.append(result)

        # Step: update accumulators
        total_dispatched   += result.tasks_dispatched
        total_deferred_ev  += result.tasks_deferred
        total_solve_time   += result.solve_time_s

        if result.pyvrp_feasible:
            feasible_count += 1
            total_cost     += result.total_route_cost
        else:
            infeasible_count += 1

        # Step: remove dispatched tasks from pool
        dispatched_set = set(dispatched_names)
        pending_tasks  = [tk for tk in pending_tasks if tk["name"] not in dispatched_set]

        # Step: per-period console output
        if config.verbose:
            status = "✓" if result.pyvrp_feasible else "✗"
            print(
                f"  [{status}] dispatched={result.tasks_dispatched:>3d}  "
                f"deferred={result.tasks_deferred:>3d}  "
                f"pool_after={len(pending_tasks):>4d}  "
                f"cost={result.total_route_cost:>12.1f}  "
                f"routes={len(result.routes):>2d}  "
                f"solve={result.solve_time_s:.2f}s"
            )
            if result.routes:
                for r in result.routes:
                    print(
                        f"      {r.vehicle_tier_name:<12s} "
                        f"{len(r.task_names):>2d} tasks  "
                        f"dist={r.route_distance:.1f}"
                    )

    wall_time = time.perf_counter() - wall_start

    # ── Final summary ─────────────────────────────────────────────────────────
    if config.verbose:
        _print_footer(
            config, wall_time, total_generated, total_dispatched,
            len(pending_tasks), total_cost, feasible_count, infeasible_count,
        )

    summary = SimulationSummary(
        config_snapshot=_config_to_dict(config),
        total_periods=config.total_periods,
        total_tasks_generated=total_generated,
        total_tasks_dispatched=total_dispatched,
        total_tasks_remaining_at_end=len(pending_tasks),
        total_tasks_ever_deferred=total_deferred_ev,
        total_route_cost=total_cost,
        total_solve_time_s=total_solve_time,
        wall_time_s=wall_time,
        feasible_periods=feasible_count,
        infeasible_periods=infeasible_count,
        avg_tasks_generated_per_period=total_generated / max(1, config.total_periods),
        avg_tasks_dispatched_per_period=total_dispatched / max(1, config.total_periods),
        avg_route_cost_per_feasible_period=total_cost / max(1, feasible_count),
        avg_solve_time_per_period_s=total_solve_time / max(1, config.total_periods),
        # Why: this is the primary cost-efficiency metric for optimisation:
        # "how much routing cost we spend per completed task".
        avg_cost_per_dispatched_task=total_cost / max(1, total_dispatched),
        # Why: expose end-of-run congestion explicitly so low-cost policies
        # still have to keep service quality acceptable.
        backlog_ratio_at_end=len(pending_tasks) / max(1, total_generated),
        weather_period_counts=weather_counts,
        period_results=[_period_to_dict(r) for r in all_results],
    )

    if config.save_results:
        _save_json(summary, config.results_dir)

    return summary


# ─────────────────────────────────────────────────────────────────────────────
# Helper: run a batch of simulations (parameter sweep)
# ─────────────────────────────────────────────────────────────────────────────

def run_batch(
    configs: List[SimulationConfig],
    parallel: bool = False,
) -> List[SimulationSummary]:
    """
    Run multiple SimulationConfig instances sequentially (or in parallel).

    Parameters
    ----------
    configs  : List of SimulationConfig objects (one per experiment).
    parallel : If True, uses multiprocessing.Pool. Requires that your
               run_simulation.py is in an if __name__ == "__main__": guard.

    Returns
    -------
    List of SimulationSummary in the same order as configs.
    """
    if parallel:
        import multiprocessing
        with multiprocessing.Pool() as pool:
            return pool.map(run_simulation, configs)
    else:
        return [run_simulation(cfg) for cfg in configs]


# ─────────────────────────────────────────────────────────────────────────────
# Serialisation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _period_to_dict(r: PeriodResult) -> dict:
    return {
        "period":           r.period,
        "weather":          r.weather,
        "lighting":         r.lighting,
        "tasks_in_pool":    r.tasks_in_pool,
        "tasks_dispatched": r.tasks_dispatched,
        "tasks_deferred":   r.tasks_deferred,
        "tasks_remaining":  r.tasks_remaining,
        "solve_time_s":     round(r.solve_time_s, 4),
        "total_route_cost": r.total_route_cost,
        "pyvrp_feasible":   r.pyvrp_feasible,
        "routes": [
            {
                "vehicle_tier":    rt.vehicle_tier_name,
                "num_tasks":       len(rt.task_names),
                "task_names":      rt.task_names,
                "route_distance":  round(rt.route_distance, 2),
            }
            for rt in r.routes
        ],
    }


def _config_to_dict(config: SimulationConfig) -> dict:
    try:
        return asdict(config)
    except Exception:
        return {"error": "could not serialise config"}


def _save_json(summary: SimulationSummary, results_dir: str) -> None:
    os.makedirs(results_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(results_dir, f"sim_{ts}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(asdict(summary), fh, indent=2, default=str)
    print(f"\n  Results saved → {path}")


# ─────────────────────────────────────────────────────────────────────────────
# Console formatting
# ─────────────────────────────────────────────────────────────────────────────

def _print_banner(config: SimulationConfig) -> None:
    tier_str = ", ".join(
        f"{t.name}(skill={t.skill_k}, n={t.num_available})" for t in config.fleet
    )
    depot_str = ", ".join(f"{d.name}({d.x},{d.y})" for d in config.depots)
    print()
    print("=" * 66)
    print("  HF-MDBOVRP  Rolling-Horizon Simulation")
    print("=" * 66)
    print(f"  Periods         : {config.total_periods}")
    print(f"  Grid size       : {config.grid_size}²")
    print(f"  Tasks/period    : "
          + (f"fixed={config.tasks_per_period_fixed}"
             if config.tasks_per_period_fixed is not None
             else f"Poisson(λ={config.tasks_per_period_mean})"))
    print(f"  Max active tasks: {config.max_active_tasks}")
    print(f"  Fleet           : {tier_str}")
    print(f"  Depots          : {depot_str}")
    print(f"  Solver budget   : {config.solver_max_runtime}s / period")
    print(f"  Random seed     : {config.random_seed}")
    print("=" * 66)


def _print_footer(
    config, wall_time, generated, dispatched,
    remaining, cost, feasible, infeasible,
) -> None:
    print()
    print("=" * 66)
    print("  SIMULATION COMPLETE")
    print(f"  Wall time            : {wall_time:.1f}s")
    print(f"  Tasks generated      : {generated}")
    print(f"  Tasks dispatched     : {dispatched}")
    print(f"  Tasks remaining      : {remaining}")
    dispatch_rate = dispatched / max(1, generated) * 100
    print(f"  Dispatch rate        : {dispatch_rate:.1f}%")
    print(f"  Feasible periods     : {feasible}/{config.total_periods}")
    print(f"  Total route cost     : {cost:.1f}")
    print("=" * 66)
