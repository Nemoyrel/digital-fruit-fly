"""Low-dimensional L4 brain-readout helpers consumed by the body loop."""

from __future__ import annotations

from .state import BrainReadout


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def readout_to_descending_signal(readout: BrainReadout) -> tuple[float, float]:
    """Convert an L4 brain readout to left/right controller amplitudes."""
    forward = _clip(readout.forward_drive, -1.0, 1.5)
    turn = _clip(readout.turn_bias, -1.0, 1.0)
    left = _clip(forward - turn, -1.0, 1.5)
    right = _clip(forward + turn, -1.0, 1.5)
    return left, right
