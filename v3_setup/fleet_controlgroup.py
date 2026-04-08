from __future__ import annotations

from typing import List

from .config import FleetTierConfig


def build_control_group_fleet(base_fleet: List[FleetTierConfig]) -> List[FleetTierConfig]:
    """
    Build a control-group fleet where every vehicle has the highest capability.

    The returned fleet preserves:
      - number of vehicles per original tier,
      - depot assignment per original tier,
    while replacing each tier's skill/cost with the highest-tier values.
    """
    if not base_fleet:
        raise ValueError("base_fleet must contain at least one tier.")

    highest_tier = max(base_fleet, key=lambda tier: tier.skill_k)

    return [
        FleetTierConfig(
            name=f"{tier.name}_Control",
            skill_k=highest_tier.skill_k,
            cost_multiplier=highest_tier.cost_multiplier,
            num_available=tier.num_available,
            start_depot_idx=tier.start_depot_idx,
        )
        for tier in base_fleet
    ]
