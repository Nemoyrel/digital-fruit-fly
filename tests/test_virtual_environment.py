import unittest

from digital_fruit_fly.virtual_environment import SceneConfig, VirtualEnvironment


class VirtualEnvironmentSearchTest(unittest.TestCase):
    def test_no_food_cue_uses_seeded_search_not_food_direction(self):
        left_food = VirtualEnvironment(
            SceneConfig(
                food_position_mm=(0.0, 50.0),
                food_cue_radius_mm=1.0,
                search_seed=11,
                search_turn_strength=0.5,
            )
        )
        right_food = VirtualEnvironment(
            SceneConfig(
                food_position_mm=(0.0, -50.0),
                food_cue_radius_mm=1.0,
                search_seed=11,
                search_turn_strength=0.5,
            )
        )

        left_state = left_food.observe(
            time_s=0.0,
            fly_xy_mm=(0.0, 0.0),
            heading_xy=(1.0, 0.0),
        )
        right_state = right_food.observe(
            time_s=0.0,
            fly_xy_mm=(0.0, 0.0),
            heading_xy=(1.0, 0.0),
        )

        self.assertEqual(left_state.food_cue, 0.0)
        self.assertEqual(right_state.food_cue, 0.0)
        self.assertAlmostEqual(left_state.turn_bias, right_state.turn_bias)
        self.assertNotAlmostEqual(left_state.turn_bias, 1.0)
        self.assertNotAlmostEqual(right_state.turn_bias, -1.0)

    def test_food_cue_enables_chemotaxis_direction(self):
        left_food = VirtualEnvironment(
            SceneConfig(
                food_position_mm=(10.0, 4.0),
                food_cue_radius_mm=20.0,
                search_seed=11,
            )
        )
        right_food = VirtualEnvironment(
            SceneConfig(
                food_position_mm=(10.0, -4.0),
                food_cue_radius_mm=20.0,
                search_seed=11,
            )
        )

        left_state = left_food.observe(
            time_s=0.0,
            fly_xy_mm=(0.0, 0.0),
            heading_xy=(1.0, 0.0),
        )
        right_state = right_food.observe(
            time_s=0.0,
            fly_xy_mm=(0.0, 0.0),
            heading_xy=(1.0, 0.0),
        )

        self.assertGreater(left_state.food_cue, 0.0)
        self.assertGreater(right_state.food_cue, 0.0)
        self.assertGreater(left_state.turn_bias, 0.0)
        self.assertLess(right_state.turn_bias, 0.0)

    def test_search_turn_updates_at_configured_interval(self):
        scene = VirtualEnvironment(
            SceneConfig(
                food_position_mm=(0.0, 50.0),
                food_cue_radius_mm=1.0,
                search_seed=3,
                search_turn_interval_s=0.5,
                search_turn_strength=0.5,
            )
        )

        first = scene.observe(
            time_s=0.0,
            fly_xy_mm=(0.0, 0.0),
            heading_xy=(1.0, 0.0),
        )
        cached = scene.observe(
            time_s=0.1,
            fly_xy_mm=(0.0, 0.0),
            heading_xy=(1.0, 0.0),
        )
        updated = scene.observe(
            time_s=0.6,
            fly_xy_mm=(0.0, 0.0),
            heading_xy=(1.0, 0.0),
        )

        self.assertAlmostEqual(first.turn_bias, cached.turn_bias)
        self.assertNotAlmostEqual(first.turn_bias, updated.turn_bias)


if __name__ == "__main__":
    unittest.main()
