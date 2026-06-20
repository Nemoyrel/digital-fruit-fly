"""Small shared state objects for the embodied loop."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BehaviorState(str, Enum):
    """Finite behavior states used by the L2 rule bridge."""

    FORAGING = "foraging"
    GROOMING = "grooming"
    FEEDING = "feeding"
    HALTED = "halted"


@dataclass(frozen=True)
class SensoryState:
    """Low-dimensional virtual sensory state produced from the demo scene."""

    time_s: float
    food_cue: float
    turn_bias: float
    dust_level: float
    dust_threshold_reached: bool
    food_contact: bool
    food_distance_mm: float


@dataclass(frozen=True)
class BrainReadout:
    """Low-dimensional brain-like readout consumed by the body controller.

    These L2 values are engineering placeholders, not empirical LIF outputs.
    L3 should replace this source with a lookup table derived from the brain model.
    """

    behavior_state: BehaviorState
    forward_drive: float
    turn_bias: float
    grooming_score: float
    feeding_score: float
    mn9_rate_hz: float
    dust_clearance: float = 0.0
    source: str = "rule_bridge_l2"
