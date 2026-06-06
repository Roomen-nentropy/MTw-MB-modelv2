"""
config.py – V8 simulation configuration with deployment policy fields.
"""

from __future__ import annotations

from dataclasses import dataclass

from v7.config import DepotConfig, FleetTierConfig, SimulationConfig as V7SimulationConfig


@dataclass
class SimulationConfig(V7SimulationConfig):
    # V8 deployment-policy controls: enforce realistic service levels during
    # active-fleet selection.
    deployment_min_dispatch_rate: float = 0.92
    deployment_max_backlog_ratio: float = 0.08
    deployment_eval_periods: int = 24
    # 0.0 = no utilization floor; search from one vehicle per tier upward.
    deployment_min_utilization: float = 0.0
    deployment_max_utilization: float = 1.0
    # >= 1: step in whole vehicles when enumerating deployment candidates.
    deployment_utilization_step: float = 1.0

