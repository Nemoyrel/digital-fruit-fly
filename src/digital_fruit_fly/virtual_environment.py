"""Minimal 2D scene sensing for the L4 embodied loop."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
import random

from .state import SensoryState


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class SceneConfig:
    """Positions and thresholds for the L4 virtual scene."""

    arena_half_size_mm: float = 150.0
    food_position_mm: tuple[float, float] = (80.0, 25.0)
    food_cue_radius_mm: float = 120.0
    food_contact_radius_mm: float = 1.05
    dust_accumulation_rate_per_s: float = 0.22
    dust_threshold: float = 1.0
    search_seed: int = 0
    search_turn_interval_s: float = 0.45
    search_turn_strength: float = 0.45


class VirtualEnvironment:
    """Generate simple sensory state from fly pose and global falling dust."""

    def __init__(self, config: SceneConfig | None = None) -> None:
        self.config = config or SceneConfig()
        self.dust_level = 0.0
        self._last_time_s: float | None = None
        self._rng = random.Random(self.config.search_seed)
        self._search_turn_bias = 0.0
        self._next_search_turn_s = float("-inf")

    @classmethod
    def from_dict(cls, data: dict) -> "VirtualEnvironment":
        config = SceneConfig(
            arena_half_size_mm=float(data.get("arena_half_size_mm", 150.0)),
            food_position_mm=tuple(data.get("food_position_mm", (80.0, 25.0))),
            food_cue_radius_mm=float(data.get("food_cue_radius_mm", 120.0)),
            food_contact_radius_mm=float(data.get("food_contact_radius_mm", 1.05)),
            dust_accumulation_rate_per_s=float(
                data.get("dust_accumulation_rate_per_s", 0.22)
            ),
            dust_threshold=float(data.get("dust_threshold", 1.0)),
            search_seed=int(data.get("search_seed", 0)),
            search_turn_interval_s=float(data.get("search_turn_interval_s", 0.45)),
            search_turn_strength=float(data.get("search_turn_strength", 0.45)),
        )
        return cls(config)

    def clear_dust(self) -> None:
        """Reset accumulated fictive dust after grooming completes."""
        self.dust_level = 0.0

    def _search_turn(self, time_s: float) -> float:
        if time_s >= self._next_search_turn_s:
            strength = max(0.0, float(self.config.search_turn_strength))
            self._search_turn_bias = self._rng.uniform(-strength, strength)
            interval = max(1e-9, float(self.config.search_turn_interval_s))
            self._next_search_turn_s = time_s + interval
        return self._search_turn_bias

    def observe(
        self,
        time_s: float,
        fly_xy_mm: tuple[float, float],
        heading_xy: tuple[float, float],
        *,
        accumulate_dust: bool = True,
    ) -> SensoryState:
        """Return virtual sensory state for the current fly pose."""
        dt = 0.0 if self._last_time_s is None else max(0.0, time_s - self._last_time_s)
        self._last_time_s = time_s

        food_dx = self.config.food_position_mm[0] - fly_xy_mm[0]
        food_dy = self.config.food_position_mm[1] - fly_xy_mm[1]
        food_distance = hypot(food_dx, food_dy)

        if accumulate_dust:
            self.dust_level = _clip(
                self.dust_level + dt * self.config.dust_accumulation_rate_per_s,
                0.0,
                self.config.dust_threshold,
            )

        heading_x, heading_y = heading_xy
        heading_norm = hypot(heading_x, heading_y)
        if heading_norm <= 1e-9:
            heading_x, heading_y = 1.0, 0.0
        else:
            heading_x, heading_y = heading_x / heading_norm, heading_y / heading_norm

        food_cue = _clip(1.0 - food_distance / self.config.food_cue_radius_mm, 0.0, 1.0)
        food_contact = food_distance <= self.config.food_contact_radius_mm
        if food_cue <= 0.0:
            turn_bias = self._search_turn(time_s)
        elif food_distance <= 1e-9:
            turn_bias = 0.0
        else:
            turn_bias = (heading_x * food_dy - heading_y * food_dx) / food_distance

        return SensoryState(
            time_s=time_s,
            food_cue=food_cue,
            turn_bias=_clip(turn_bias, -1.0, 1.0),
            dust_level=self.dust_level,
            dust_threshold_reached=self.dust_level >= self.config.dust_threshold,
            food_contact=food_contact,
            food_distance_mm=food_distance,
        )
