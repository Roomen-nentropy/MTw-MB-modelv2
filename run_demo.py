from __future__ import annotations

from hf_mdbovrp import (
    Depot,
    Task,
    TaskEnv,
    VehicleTier,
    build_skill_based_pyvrp_model,
    compute_task_requirement_level,
    compatibility_matrix,
    solve_pyvrp_model,
)


def main() -> None:
    # Example tasks with different environmental tuples.
    raw_tasks = [
        ("T1", 10, 0, TaskEnv("Clear", "Day", "Highway")),
        ("T2", 0, 10, TaskEnv("Rain", "Day", "Urban")),
        ("T3", -10, 0, TaskEnv("Clear", "Night", "Rural")),
        ("T4", 0, -10, TaskEnv("Fog", "Dusk", "Urban")),
    ]

    tasks = []
    for name, x, y, env in raw_tasks:
        req = compute_task_requirement_level(env)
        tasks.append(Task(name=name, x=x, y=y, req_level=req))

    depots = [Depot(name="Depot0", x=0, y=0)]
    vehicle_tiers = [
        VehicleTier(name="Standard", skill_k=1, cost_multiplier=1, num_available=2, start_depot_index=0),
        VehicleTier(name="Master", skill_k=2, cost_multiplier=3, num_available=1, start_depot_index=0),
    ]

    task_req_levels = [t.req_level for t in tasks]
    vehicle_skills = [vt.skill_k for vt in vehicle_tiers]
    a = compatibility_matrix(task_req_levels, vehicle_skills)
    print("Compatibility matrix a[j][k] (1=compatible):")
    for j, row in enumerate(a):
        print(f"  task {tasks[j].name}: {row}")

    model, meta = build_skill_based_pyvrp_model(tasks, depots, vehicle_tiers, coord_scale=10.0, cost_scale=10.0)
    print("Computed task Req levels:", [(t.name, t.req_level) for t in tasks])
    print("Prohibitive distance:", meta["prohibitive_distance"])

    result = solve_pyvrp_model(model, max_runtime_seconds=5.0, seed=0, display=True)
    print("Result:", result)


if __name__ == "__main__":
    main()

