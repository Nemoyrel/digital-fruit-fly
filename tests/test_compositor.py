import unittest

import _bootstrap  # noqa: F401

import numpy as np

from digital_fruit_fly.compositor import _to_even, hstack_frame


class CompositorTest(unittest.TestCase):
    def test_hstack_same_height(self):
        body = np.zeros((40, 50, 3), dtype=np.uint8)
        brain = np.ones((40, 60, 3), dtype=np.uint8)
        out = hstack_frame(body, brain, gap_px=4)
        self.assertEqual(out.shape, (40, 50 + 4 + 60, 3))

    def test_hstack_pads_shorter_height(self):
        body = np.zeros((30, 50, 3), dtype=np.uint8)
        brain = np.ones((40, 60, 3), dtype=np.uint8)
        out = hstack_frame(body, brain, gap_px=0)
        self.assertEqual(out.shape, (40, 110, 3))

    def test_to_even_crops_odd_dims(self):
        frame = np.zeros((41, 51, 3), dtype=np.uint8)
        out = _to_even(frame)
        self.assertEqual(out.shape, (40, 50, 3))


if __name__ == "__main__":
    unittest.main()
