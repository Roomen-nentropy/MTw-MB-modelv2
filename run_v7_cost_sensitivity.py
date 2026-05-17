#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from statistics import mean

from rum_sim_v7 import build_config
from v7.deployment import choose_optimal_deployment
from v7.fleet_controlgroup import build_control_group_fleet
from v7.simulation import run_simulation


def run_sweep() -> None:
    costs = [1.25, 1.35, 1.50, 1.60, 1.80]
    seeds = [0]

    root = Path(__file__).resolve().parent
    base = replace(
        build_config(),
        bbbike_xz_path=str(root / "v7" / "planet_8.317,48.426_9.898,49.134.osm.csv.xz"),
        bbbike_sampling_pool_size=600,
        total_periods=8,
    )
    total_periods = base.total_periods
    solver_runtime = 0.8

    print("START_SWEEP")
    for c_adv in costs:
        fleet = []
        for tier in base.fleet:
            if tier.name.lower().startswith("advanced"):
                fleet.append(replace(tier, cost_multiplier=float(c_adv)))
            else:
                fleet.append(tier)

        cfg = replace(base, fleet=fleet)
        decision = choose_optimal_deployment(
            cfg,
            cfg.fleet,
            evaluation_periods=6,
            utilization_step=0.2,
        )
        fleet_model = decision.deployed_fleet
        fleet_cg = build_control_group_fleet(fleet_model)

        rows = []
        for seed in seeds:
            cfg_a = replace(
                cfg,
                fleet=fleet_model,
                random_seed=seed,
                total_periods=total_periods,
                solver_max_runtime=solver_runtime,
                verbose=False,
                save_results=False,
            )
            cfg_b = replace(
                cfg,
                fleet=fleet_cg,
                random_seed=seed,
                total_periods=total_periods,
                solver_max_runtime=solver_runtime,
                verbose=False,
                save_results=False,
            )
            sa = run_simulation(cfg_a)
            sb = run_simulation(cfg_b)

            gen_a = max(1, int(sa.total_tasks_generated))
            gen_b = max(1, int(sb.total_tasks_generated))
            rows.append(
                {
                    "dcost": float(sb.total_route_cost - sa.total_route_cost),
                    "dcpt": (
                        float(sb.total_route_cost) / max(1, int(sb.total_tasks_dispatched))
                        - float(sa.total_route_cost) / max(1, int(sa.total_tasks_dispatched))
                    ),
                    "ddisp": float(
                        sa.total_tasks_dispatched / gen_a - sb.total_tasks_dispatched / gen_b
                    ),
                    "dback": float(
                        sb.total_tasks_remaining_at_end / gen_b
                        - sa.total_tasks_remaining_at_end / gen_a
                    ),
                }
            )

        print(
            f"C_ADV={c_adv:.2f} "
            f"util={decision.utilization:.3f} "
            f"deployed={decision.deployed_total}/{decision.owned_total} "
            f"mean_dcost={mean(r['dcost'] for r in rows):+.2f} "
            f"mean_dcpt={mean(r['dcpt'] for r in rows):+.4f} "
            f"mean_ddisp={mean(r['ddisp'] for r in rows):+.4f} "
            f"mean_dback={mean(r['dback'] for r in rows):+.4f}"
        )
    print("END_SWEEP")


if __name__ == "__main__":
    run_sweep()
