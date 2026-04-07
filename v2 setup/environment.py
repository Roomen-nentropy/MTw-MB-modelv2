from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple


@dataclass(frozen=True)
class TaskEnv:
    """Environmental tuple Ej = (wj, lj, rj)."""

    weather: str  # W
    lighting: str  # L
    road_domain: str  # R


@dataclass(frozen=True)
class TaskRequirementMapping:
    """
    Maps an environmental tuple Ej into a discrete ordinal requirement level.

    The thesis text specifies f: W x L x R -> Zx and Reqj = f(Ej).
    Here we implement a configurable ordinal mapping based on component scores.
    """

    weather_score: Dict[str, int]
    lighting_score: Dict[str, int]
    road_domain_score: Dict[str, int]

    # score_to_req maps the summed degradation score -> requirement level.
    # Use a callable-like dict form:
    #   if score <= thresholds[0] -> req_levels[0]
    #   elif score <= thresholds[1] -> req_levels[1]
    #   else -> req_levels[-1]
    thresholds: Sequence[int]
    req_levels: Sequence[int]

    def __post_init__(self) -> None:
        if len(self.thresholds) != len(self.req_levels) - 1:
            raise ValueError(
                "thresholds must have length len(req_levels)-1 "
                "(e.g. thresholds=[2], req_levels=[1,2])."
            )

    def score(self, env: TaskEnv) -> int:
        try:
            w = self.weather_score[env.weather]
            l = self.lighting_score[env.lighting]
            r = self.road_domain_score[env.road_domain]
        except KeyError as e:
            raise ValueError(f"Unknown env component value: {e}") from e
        return w + l + r

    def req_from_score(self, s: int) -> int:
        # thresholds define the upper bounds for each but the last req level.
        for idx, t in enumerate(self.thresholds):
            if s <= t:
                return int(self.req_levels[idx])
        return int(self.req_levels[-1])


DEFAULT_MAPPING_2LEVEL = TaskRequirementMapping(
    # Default ordinal scoring that yields Req in {1,2}.
    weather_score={"Clear": 0, "Rain": 1, "Fog": 2},
    lighting_score={"Day": 0, "Dusk": 1, "Night": 2},
    road_domain_score={"Highway": 0, "Rural": 1, "Urban": 2},
    thresholds=[2],
    req_levels=[1, 2],
)


def compute_task_requirement_level(
    env: TaskEnv,
    mapping: TaskRequirementMapping = DEFAULT_MAPPING_2LEVEL,
) -> int:
    """
    Phase 1a: compute Reqj = f(Ej).
    """

    s = mapping.score(env)
    return mapping.req_from_score(s)


def compatibility_matrix(
    task_req_levels: Sequence[int],
    vehicle_skills: Sequence[int],
) -> List[List[int]]:
    """
    Phase 1b: binary compatibility matrix a_jk.

    a_jk = 1 if Skill_k >= Req_j else 0.
    """

    if not task_req_levels:
        raise ValueError("task_req_levels must be non-empty.")
    if not vehicle_skills:
        raise ValueError("vehicle_skills must be non-empty.")

    # Basic validation: ordinals should be positive integers.
    for req in task_req_levels:
        if int(req) < 1:
            raise ValueError("Task requirement levels must be >= 1.")
    for sk in vehicle_skills:
        if int(sk) < 1:
            raise ValueError("Vehicle skills must be >= 1.")

    a: List[List[int]] = []
    for req in task_req_levels:
        row = []
        for skill in vehicle_skills:
            row.append(1 if int(skill) >= int(req) else 0)
        a.append(row)
    return a

