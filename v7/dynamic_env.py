"""
dynamic_env.py – Time-varying environment components.

Implements:
  WeatherSimulator  – first-order Markov chain over weather states
  LightingSimulator – deterministic day/night cycle
  TaskGenerator     – Poisson arrivals with random spatial placement
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple

from .bbbike_map_sampler import (
    build_local_task_pool_from_bbbike,
    build_local_task_pool_with_domain_from_bbbike,
)
from .config import SimulationConfig
from .environment import TaskEnv


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

def _poisson_sample(rng: random.Random, lam: float) -> int:
    """
    Draw a single Poisson(lam) sample without numpy.
    Uses Knuth's algorithm for lam ≤ 30, Normal approximation otherwise.
    """
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, round(rng.gauss(lam, math.sqrt(lam))))
    # Knuth
    L = math.exp(-lam)
    k, p = 0, 1.0
    while p > L:
        k += 1
        p *= rng.random()
    return k - 1


# ─────────────────────────────────────────────────────────────────────────────
# Weather
# ─────────────────────────────────────────────────────────────────────────────

class WeatherSimulator:
    """
    First-order Markov chain over weather states.

    State transitions are governed by SimulationConfig.weather_transitions.
    Call .step() once per period to advance the chain.
    """

    def __init__(self, config: SimulationConfig, rng: random.Random) -> None:
        self._transitions = config.weather_transitions
        self._state = config.initial_weather
        self._rng = rng
        self._history: List[str] = [self._state]

        # Validate that all destination states are also defined as source states
        all_states = set(self._transitions.keys())
        for src, row in self._transitions.items():
            for dst in row:
                if dst not in all_states:
                    raise ValueError(
                        f"Weather transition {src!r} → {dst!r}: "
                        f"{dst!r} is not defined as a source state."
                    )
            s = sum(row.values())
            if not math.isclose(s, 1.0, abs_tol=1e-6):
                raise ValueError(
                    f"Weather transition probabilities for {src!r} sum to {s:.6f}, not 1.0."
                )

    @property
    def current(self) -> str:
        return self._state

    @property
    def history(self) -> List[str]:
        return list(self._history)

    def step(self) -> str:
        """Advance one period and return the new weather state."""
        row = self._transitions[self._state]
        states = list(row.keys())
        weights = [row[s] for s in states]
        self._state = self._rng.choices(states, weights=weights, k=1)[0]
        self._history.append(self._state)
        return self._state


# ─────────────────────────────────────────────────────────────────────────────
# Lighting
# ─────────────────────────────────────────────────────────────────────────────

class LightingSimulator:
    """
    Deterministic lighting state from a repeating cycle.

    lighting_cycle[period % len(lighting_cycle)] gives the state at `period`.
    """

    def __init__(self, config: SimulationConfig) -> None:
        if not config.lighting_cycle:
            raise ValueError("lighting_cycle must be non-empty.")
        self._cycle = config.lighting_cycle

    def get(self, period: int) -> str:
        return self._cycle[period % len(self._cycle)]


# ─────────────────────────────────────────────────────────────────────────────
# Task generator
# ─────────────────────────────────────────────────────────────────────────────

class TaskGenerator:
    """
    Generates new task dicts at each period.

    Each task is a plain dict with keys:
        name           : unique string identifier
        x, y           : coordinates in [0, grid_size]²
        env            : TaskEnv(weather, lighting, road_domain)
                         – weather and lighting reflect the period at arrival
                         – road_domain is static for the task's lifetime
        arrival_period : int period when the task entered the system
    """

    def __init__(self, config: SimulationConfig, rng: random.Random) -> None:
        self._cfg = config
        self._rng = rng
        self._counter = 0
        self._map_xy_pool = None
        self._map_xy_domain_pool: Optional[List[Tuple[float, float, Optional[str]]]] = None

        # Pre-normalise road weights once
        domains = list(config.road_domain_weights.keys())
        raw_w = [config.road_domain_weights[d] for d in domains]
        total = sum(raw_w)
        if total <= 0:
            raise ValueError("road_domain_weights must have at least one positive entry.")
        self._road_domains = domains
        self._road_weights = [w / total for w in raw_w]

        # Validate workload multipliers up front for clearer config errors.
        for weather in config.weather_transitions.keys():
            if weather not in config.weather_task_rate_multiplier:
                raise ValueError(
                    f"Missing weather_task_rate_multiplier for weather state: {weather!r}."
                )
            if weather not in config.weather_operating_cost_multiplier:
                raise ValueError(
                    f"Missing weather_operating_cost_multiplier for weather state: {weather!r}."
                )
        for light in set(config.lighting_cycle):
            if light not in config.lighting_task_rate_multiplier:
                raise ValueError(
                    f"Missing lighting_task_rate_multiplier for lighting state: {light!r}."
                )
            if light not in config.lighting_operating_cost_multiplier:
                raise ValueError(
                    f"Missing lighting_operating_cost_multiplier for lighting state: {light!r}."
                )

        # Optional real-world spatial sampling from BBBike .xz area file.
        if config.bbbike_xz_path:
            self._map_xy_domain_pool = build_local_task_pool_with_domain_from_bbbike(
                config.bbbike_xz_path,
                pool_size=int(config.bbbike_sampling_pool_size),
            )
            # Backward compatibility for code that only expects xy points.
            self._map_xy_pool = [(x, y) for x, y, _ in self._map_xy_domain_pool]

    def generate(self, period: int, weather: str, lighting: str) -> List[dict]:
        """
        Return a (possibly empty) list of new task dicts for this period.
        """
        cfg = self._cfg
        if cfg.tasks_per_period_fixed is not None:
            n = int(cfg.tasks_per_period_fixed)
        else:
            # Realism: demand intensity varies by current operating conditions.
            weather_mult = cfg.weather_task_rate_multiplier[weather]
            lighting_mult = cfg.lighting_task_rate_multiplier[lighting]
            effective_lam = cfg.tasks_per_period_mean * weather_mult * lighting_mult
            n = _poisson_sample(self._rng, effective_lam)

        tasks: List[dict] = []
        for _ in range(n):
            self._counter += 1
            road = self._rng.choices(self._road_domains, weights=self._road_weights, k=1)[0]
            if self._map_xy_domain_pool:
                x, y, map_domain = self._map_xy_domain_pool[self._rng.randrange(len(self._map_xy_domain_pool))]
                if map_domain in self._road_domains:
                    road = map_domain
            elif self._map_xy_pool:
                x, y = self._map_xy_pool[self._rng.randrange(len(self._map_xy_pool))]
            else:
                x = self._rng.uniform(0.0, cfg.grid_size)
                y = self._rng.uniform(0.0, cfg.grid_size)
            tasks.append({
                "name": f"T{self._counter:05d}",
                "x": x,
                "y": y,
                "env": TaskEnv(
                    weather=weather,
                    lighting=lighting,
                    road_domain=road,
                ),
                "arrival_period": period,
            })
        return tasks
