from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VehicleTier:
    """
    Represents one heterogeneous fleet tier in the skill-based routing model.

    SkillK (ordinal) is the maximum Task Requirement Level that the tier can
    legally/technically handle.

    cost_multiplier (Ck) scales distance in the economic objective.
    """

    name: str
    skill_k: int  # Skillk in {1,2,...}
    cost_multiplier: float  # Ck >= 1
    num_available: int = 1
    start_depot_index: int = 0

    def __post_init__(self) -> None:
        if self.skill_k < 1:
            raise ValueError("skill_k must be a positive ordinal (>= 1).")
        if self.cost_multiplier < 1:
            raise ValueError("cost_multiplier must satisfy Ck >= 1.")
        if self.num_available < 1:
            raise ValueError("num_available must be >= 1.")
        if self.start_depot_index < 0:
            raise ValueError("start_depot_index must be >= 0.")

