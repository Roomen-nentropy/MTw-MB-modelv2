from __future__ import annotations

from typing import List

from .config import FleetTierConfig


def build_control_group_fleet(base_fleet: List[FleetTierConfig]) -> List[FleetTierConfig]:
    """
    Build a control-group fleet with only the highest-capability vehicle type.

    The returned fleet is a single tier:
      - skill/cost from the highest tier in base_fleet,
      - total vehicle count equal to the sum of all base tiers,
      - depot assignment from that highest tier.
    """
    if not base_fleet:
        raise ValueError("base_fleet must contain at least one tier.")

    highest_tier = max(base_fleet, key=lambda tier: tier.skill_k)

    total_vehicles = sum(tier.num_available for tier in base_fleet)
    return [
        FleetTierConfig(
            name=f"{highest_tier.name}_Control",
            skill_k=highest_tier.skill_k,
            cost_multiplier=highest_tier.cost_multiplier,
            num_available=total_vehicles,
            start_depot_idx=highest_tier.start_depot_idx,
        )
    ]
