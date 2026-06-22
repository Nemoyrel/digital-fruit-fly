import unittest

import _bootstrap  # noqa: F401

import numpy as np

from digital_fruit_fly.brain_viz import build_brain_layout


class BrainLayoutTest(unittest.TestCase):
    def test_layout_deterministic(self):
        a = build_brain_layout(1000, seed=0)
        b = build_brain_layout(1000, seed=0)
        np.testing.assert_array_equal(a["xy"], b["xy"])
        self.assertEqual(a["xy"].shape, (1000, 2))

    def test_layout_roughly_symmetric(self):
        layout = build_brain_layout(4000, seed=0)
        xs = layout["xy"][:, 0]
        # 左右点数大致平衡（严格对称的视叶 + 镜像的中央/SEZ）
        left = int((xs < -0.05).sum())
        right = int((xs > 0.05).sum())
        self.assertGreater(left, 0)
        self.assertGreater(right, 0)
        self.assertLess(abs(left - right) / max(left, right), 0.2)

    def test_renderer_outputs_expected_shape(self):
        try:
            from digital_fruit_fly.brain_viz import BrainPanelRenderer
        except Exception as exc:  # matplotlib 缺失时跳过
            self.skipTest(f"matplotlib unavailable: {exc}")
        renderer = BrainPanelRenderer(width=120, height=80, n_points=300)
        img = renderer.render(
            np.zeros(300), behavior="foraging", feeding_score=0.0, grooming_score=0.0
        )
        self.assertEqual(img.shape, (80, 120, 3))
        self.assertEqual(img.dtype, np.uint8)
        img2 = renderer.render(
            np.ones(300) * 3, behavior="feeding", feeding_score=1.0, grooming_score=0.0
        )
        # 有活动时整体应比全零更亮
        self.assertGreater(int(img2.sum()), int(img.sum()))


if __name__ == "__main__":
    unittest.main()
