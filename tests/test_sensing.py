import unittest

import _bootstrap  # noqa: F401

from digital_fruit_fly.sensing import SceneConfig, VirtualEnvironment


class SensingTest(unittest.TestCase):
    def _env(self, **kw):
        cfg = SceneConfig(
            food_position_mm=(20.0, 0.0),
            food_cue_radius_mm=20.0,
            food_contact_radius_mm=2.0,
            dust_accumulation_rate_per_s=0.5,
            dust_threshold=1.0,
            **kw,
        )
        return VirtualEnvironment(cfg)

    def test_food_cue_grows_when_approaching(self):
        env = self._env()
        far = env.observe(0.0, (-10.0, 0.0), (1.0, 0.0))
        env2 = self._env()
        near = env2.observe(0.0, (10.0, 0.0), (1.0, 0.0))
        self.assertGreater(near.food_cue, far.food_cue)
        self.assertGreaterEqual(far.food_cue, 0.0)

    def test_no_cue_outside_radius(self):
        env = self._env()
        s = env.observe(0.0, (-30.0, 0.0), (1.0, 0.0))
        self.assertEqual(s.food_cue, 0.0)

    def test_food_contact(self):
        env = self._env()
        s = env.observe(0.0, (19.0, 0.0), (1.0, 0.0))
        self.assertTrue(s.food_contact)

    def test_dust_accumulates_then_clears(self):
        env = self._env()
        env.observe(0.0, (0.0, 0.0), (1.0, 0.0))
        s = env.observe(3.0, (0.0, 0.0), (1.0, 0.0))  # 3s * 0.5 = 1.5 -> capped at 1.0
        self.assertTrue(s.dust_threshold_reached)
        self.assertEqual(s.dust_level, 1.0)
        env.clear_dust()
        s2 = env.observe(3.1, (0.0, 0.0), (1.0, 0.0))
        self.assertLess(s2.dust_level, 0.2)

    def test_dust_paused_when_not_accumulating(self):
        env = self._env()
        env.observe(0.0, (0.0, 0.0), (1.0, 0.0))
        s = env.observe(2.0, (0.0, 0.0), (1.0, 0.0), accumulate_dust=False)
        self.assertEqual(s.dust_level, 0.0)

    def test_turn_bias_sign_points_toward_food(self):
        # food to the left of a fly heading +x should give positive turn_bias
        env = self._env()
        s = env.observe(0.0, (10.0, -5.0), (1.0, 0.0))  # food at (20,0): dy=+5 -> left
        self.assertGreater(s.turn_bias, 0.0)

    def test_search_turn_is_deterministic(self):
        a = self._env(search_seed=42).observe(0.0, (-30.0, 0.0), (1.0, 0.0))
        b = self._env(search_seed=42).observe(0.0, (-30.0, 0.0), (1.0, 0.0))
        self.assertEqual(a.turn_bias, b.turn_bias)


if __name__ == "__main__":
    unittest.main()
