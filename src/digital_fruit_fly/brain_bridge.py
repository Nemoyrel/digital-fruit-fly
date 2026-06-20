"""Rule-based L2 brain-to-body bridge.

This module deliberately uses simple, inspectable rules. It is a placeholder bridge
for L2 and should be swapped for an empirical lookup-table bridge in L3.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .state import BehaviorState, BrainReadout, SensoryState


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class RuleBrainBridge:
    """Map virtual sensory state to behavior and low-dimensional motor readouts."""

    grooming_duration_s: float = 1.0
    feeding_hold_s: float = 0.8
    max_turn_drive: float = 0.55
    min_forward_drive: float = 0.12
    max_forward_drive: float = 1.35

    def __post_init__(self) -> None:
        self.behavior_state = BehaviorState.FORAGING
        self.state_until_s = 0.0
        self.just_completed_grooming = False

    def step(self, sensory_state: SensoryState) -> BrainReadout:
        """Update behavior state and return a bridge readout."""
        now = sensory_state.time_s
        self.just_completed_grooming = False

        if self.behavior_state == BehaviorState.GROOMING and now >= self.state_until_s:
            self.behavior_state = BehaviorState.FORAGING
            self.state_until_s = 0.0
            self.just_completed_grooming = True
            return BrainReadout(
                behavior_state=BehaviorState.FORAGING,
                forward_drive=0.65,
                turn_bias=0.0,
                grooming_score=0.0,
                feeding_score=0.0,
                mn9_rate_hz=5.0,
                dust_clearance=1.0,
            )

        if self.behavior_state == BehaviorState.GROOMING:
            return BrainReadout(
                behavior_state=self.behavior_state,
                forward_drive=0.0,
                turn_bias=0.0,
                grooming_score=1.0,
                feeding_score=0.0,
                mn9_rate_hz=8.0,
            )

        if sensory_state.dust_threshold_reached:
            self.behavior_state = BehaviorState.GROOMING
            self.state_until_s = now + self.grooming_duration_s
        elif sensory_state.food_contact:
            self.behavior_state = BehaviorState.FEEDING
            self.state_until_s = max(self.state_until_s, now + self.feeding_hold_s)
        elif now >= self.state_until_s:
            self.behavior_state = BehaviorState.FORAGING

        if self.behavior_state == BehaviorState.FEEDING:
            return BrainReadout(
                behavior_state=self.behavior_state,
                forward_drive=0.0,
                turn_bias=0.0,
                grooming_score=0.0,
                feeding_score=1.0,
                mn9_rate_hz=120.0,
            )

        if self.behavior_state == BehaviorState.GROOMING:
            return BrainReadout(
                behavior_state=self.behavior_state,
                forward_drive=0.0,
                turn_bias=0.0,
                grooming_score=1.0,
                feeding_score=0.0,
                mn9_rate_hz=8.0,
            )

        food_gain = _clip(sensory_state.food_cue, 0.0, 1.0)
        forward_drive = 0.72 + 0.45 * food_gain - 0.18 * sensory_state.dust_level
        turn_drive = sensory_state.turn_bias * (0.25 + 0.75 * food_gain)
        return BrainReadout(
            behavior_state=BehaviorState.FORAGING,
            forward_drive=_clip(
                forward_drive, self.min_forward_drive, self.max_forward_drive
            ),
            turn_bias=_clip(turn_drive, -self.max_turn_drive, self.max_turn_drive),
            grooming_score=0.25 * sensory_state.dust_level,
            feeding_score=0.1 * food_gain,
            mn9_rate_hz=5.0 + 18.0 * food_gain,
        )


def readout_to_descending_signal(readout: BrainReadout) -> tuple[float, float]:
    """Convert a readout to left/right amplitude inputs for the turning controller."""
    left = readout.forward_drive - readout.turn_bias
    right = readout.forward_drive + readout.turn_bias
    return (_clip(left, 0.0, 1.45), _clip(right, 0.0, 1.45))


class BrainBridge(Protocol):
    """Minimal interface L3 lookup-table bridges should preserve."""

    just_completed_grooming: bool

    def step(self, sensory_state: SensoryState) -> BrainReadout:
        """Return a low-dimensional readout for the current sensory state."""
