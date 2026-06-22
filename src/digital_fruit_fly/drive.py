"""脑读出 -> 身体下行驱动 的映射（纯标准库）。"""

from __future__ import annotations

from .state import BrainReadout


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def readout_to_descending_signal(readout: BrainReadout) -> tuple[float, float]:
    """把脑读出转成 HybridTurningController 的 [left, right] 下行驱动幅值。

    ``forward_drive`` 提供前进分量，``turn_bias`` 提供左右差分（正=右转）。
    """
    forward = _clip(readout.forward_drive, -1.0, 1.5)
    turn = _clip(readout.turn_bias, -1.0, 1.0)
    left = _clip(forward - turn, -1.0, 1.5)
    right = _clip(forward + turn, -1.0, 1.5)
    return left, right
