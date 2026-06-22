import unittest

import _bootstrap  # noqa: F401

from digital_fruit_fly.drive import readout_to_descending_signal
from digital_fruit_fly.state import BehaviorState, BrainReadout


def _readout(forward, turn):
    return BrainReadout(
        behavior_state=BehaviorState.FORAGING,
        forward_drive=forward,
        turn_bias=turn,
        grooming_score=0.0,
        feeding_score=0.0,
        mn9_rate_hz=0.0,
    )


class DriveTest(unittest.TestCase):
    def test_straight(self):
        left, right = readout_to_descending_signal(_readout(0.8, 0.0))
        self.assertAlmostEqual(left, right)

    def test_right_turn_increases_right(self):
        left, right = readout_to_descending_signal(_readout(0.8, 0.5))
        self.assertGreater(right, left)

    def test_clamped(self):
        left, right = readout_to_descending_signal(_readout(5.0, 0.0))
        self.assertLessEqual(left, 1.5)
        self.assertLessEqual(right, 1.5)


if __name__ == "__main__":
    unittest.main()
