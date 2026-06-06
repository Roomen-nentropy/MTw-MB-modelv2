from __future__ import annotations

from typing import List

from .config import FleetTierConfig


def total_vehicles(fleet: List[FleetTierConfig]) -> int:
    return sum(int(tier.num_available) for tier in fleet)


def build_control_group_fleet(base_fleet: List[FleetTierConfig]) -> List[FleetTierConfig]:
    """
    Build a control-group fleet with the same vehicle count and tier mix as the
    deployed model fleet.

    Each tier keeps its slot count but is upgraded to the highest capability and
    cost profile found in the model fleet. This preserves paired-comparison parity
    (same N, same Standard:Advanced ratio) while representing an all-premium-spec
    counterfactual.
    """
    if not base_fleet:
        raise ValueError("base_fleet must contain at least one tier.")

    highest_tier = max(base_fleet, key=lambda tier: tier.skill_k)
    control: List[FleetTierConfig] = []

    for tier in base_fleet:
        if tier.num_available <= 0:
            continue
        control.append(
            FleetTierConfig(
                name=f"{tier.name}_Control",
                skill_k=highest_tier.skill_k,
                cost_multiplier=highest_tier.cost_multiplier,
                num_available=tier.num_available,
                start_depot_idx=tier.start_depot_idx,
            )
        )

    if not control:
        raise ValueError("base_fleet must contain at least one active tier.")

    if total_vehicles(control) != total_vehicles(base_fleet):
        raise RuntimeError("Control-group fleet size must match the model fleet size.")

    return control
