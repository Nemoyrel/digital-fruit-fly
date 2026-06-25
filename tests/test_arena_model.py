import json
import math
import unittest

from digital_fruit_fly.arena.model import (
    ArenaConfigError,
    ArenaDimensions,
    ArenaGeometry,
    CueSensorGeometry,
    FlyPose2D,
    FoodSource,
    Point2D,
    Vector2D,
    build_arena_geometry_from_runtime,
)
from digital_fruit_fly.runtime.config import ArenaConfig, DustConfig, SugarConfig


class TestArenaModel(unittest.TestCase):
    def test_clamp_pose_reports_boundary_collision_when_pose_exits_arena(self) -> None:
        # Given: a bounded arena and a pose outside both maximum boundaries.
        arena = ArenaGeometry(
            dimensions=ArenaDimensions(width_mm=60.0, height_mm=40.0),
            food=FoodSource(center=Point2D(x_mm=30.0, y_mm=20.0), radius_mm=3.0, cue_radius_mm=10.0),
            cue_sensors=CueSensorGeometry(lateral_offset_mm=0.75, forward_offset_mm=0.5),
        )
        pose = FlyPose2D(x_mm=64.5, y_mm=42.0, heading_rad=1.25)

        # When: the arena clamps the pose.
        result = arena.clamp_pose(pose)

        # Then: coordinates are clamped, heading is preserved, and collision axes are reported.
        self.assertEqual(result.pose, FlyPose2D(x_mm=60.0, y_mm=40.0, heading_rad=1.25))
        self.assertTrue(result.collided_x)
        self.assertTrue(result.collided_y)
        self.assertTrue(result.collided)

    def test_sugar_cue_strength_is_positive_inside_radius_and_zero_outside(self) -> None:
        # Given: a cue field with a food source centered at (30, 20).
        arena = ArenaGeometry(
            dimensions=ArenaDimensions(width_mm=60.0, height_mm=40.0),
            food=FoodSource(center=Point2D(x_mm=30.0, y_mm=20.0), radius_mm=3.0, cue_radius_mm=10.0),
            cue_sensors=CueSensorGeometry(lateral_offset_mm=0.75, forward_offset_mm=0.5),
        )

        # When: cue strength is sampled inside and outside the cue radius.
        inside_strength = arena.sugar_cue_strength_at(Point2D(x_mm=35.0, y_mm=20.0))
        outside_strength = arena.sugar_cue_strength_at(Point2D(x_mm=41.0, y_mm=20.0))

        # Then: only the point inside the configured cue radius receives sugar cue.
        self.assertGreater(inside_strength, 0.0)
        self.assertEqual(outside_strength, 0.0)

    def test_left_right_cue_sampling_is_asymmetric_when_food_is_left_of_heading(self) -> None:
        # Given: a fly facing +x with food offset to its left.
        arena = ArenaGeometry(
            dimensions=ArenaDimensions(width_mm=60.0, height_mm=40.0),
            food=FoodSource(center=Point2D(x_mm=10.0, y_mm=2.0), radius_mm=1.0, cue_radius_mm=20.0),
            cue_sensors=CueSensorGeometry(lateral_offset_mm=1.0, forward_offset_mm=0.0),
        )
        pose = FlyPose2D(x_mm=0.0, y_mm=0.0, heading_rad=0.0)

        # When: left and right sensors sample the cue field.
        cue = arena.sample_sugar_cue(pose)

        # Then: the left sensor sees the stronger cue.
        self.assertGreater(cue.left, cue.right)
        self.assertGreater(cue.left, 0.0)
        self.assertGreater(cue.right, 0.0)

    def test_contact_distance_and_vector_to_food_are_deterministic(self) -> None:
        # Given: a pose and a food source separated by a 3-4-5 vector.
        arena = ArenaGeometry(
            dimensions=ArenaDimensions(width_mm=60.0, height_mm=40.0),
            food=FoodSource(center=Point2D(x_mm=13.0, y_mm=14.0), radius_mm=2.0, cue_radius_mm=9.0),
            cue_sensors=CueSensorGeometry(lateral_offset_mm=0.75, forward_offset_mm=0.5),
        )
        pose = FlyPose2D(x_mm=10.0, y_mm=10.0, heading_rad=math.pi / 4.0)

        # When: distance, vector, and contact are queried.
        distance = arena.distance_to_food(pose)
        vector = arena.vector_to_food(pose)
        inside_contact = arena.is_food_contact(FlyPose2D(x_mm=12.0, y_mm=14.0, heading_rad=0.0))
        outside_contact = arena.is_food_contact(pose)

        # Then: metric geometry is deterministic and contact obeys food radius.
        self.assertEqual(distance, 5.0)
        self.assertEqual(vector, Vector2D(dx_mm=3.0, dy_mm=4.0))
        self.assertTrue(inside_contact)
        self.assertFalse(outside_contact)

    def test_runtime_arena_config_rejects_food_outside_arena(self) -> None:
        # Given: runtime config with the sugar source outside arena bounds.
        config = ArenaConfig(
            width_mm=20.0,
            height_mm=10.0,
            sugar=SugarConfig(center_x_mm=21.0, center_y_mm=5.0, radius=1.0, cue_radius=4.0),
            dust=DustConfig(accumulation_rate_per_sec=0.0, threshold=1.0, cleaning_rate_per_sec=0.0),
        )

        # When / Then: parsing into the typed arena model rejects it.
        with self.assertRaises(ArenaConfigError):
            build_arena_geometry_from_runtime(config)

    def test_runtime_arena_config_rejects_food_radius_crossing_boundary(self) -> None:
        # Given: runtime config with a food disk that crosses the arena wall.
        config = ArenaConfig(
            width_mm=20.0,
            height_mm=10.0,
            sugar=SugarConfig(center_x_mm=1.0, center_y_mm=5.0, radius=2.0, cue_radius=4.0),
            dust=DustConfig(accumulation_rate_per_sec=0.0, threshold=1.0, cleaning_rate_per_sec=0.0),
        )

        # When / Then: parsing into the typed arena model rejects it.
        with self.assertRaises(ArenaConfigError):
            build_arena_geometry_from_runtime(config)

    def test_runtime_arena_config_rejects_cue_radius_smaller_than_food_radius(self) -> None:
        # Given: runtime config with cue radius smaller than the food source radius.
        config = ArenaConfig(
            width_mm=20.0,
            height_mm=10.0,
            sugar=SugarConfig(center_x_mm=10.0, center_y_mm=5.0, radius=3.0, cue_radius=2.0),
            dust=DustConfig(accumulation_rate_per_sec=0.0, threshold=1.0, cleaning_rate_per_sec=0.0),
        )

        # When / Then: parsing into the typed arena model rejects it.
        with self.assertRaises(ArenaConfigError):
            build_arena_geometry_from_runtime(config)

    def test_json_serialization_is_stable_and_json_compatible(self) -> None:
        # Given: a deterministic arena geometry.
        arena = ArenaGeometry(
            dimensions=ArenaDimensions(width_mm=60.0, height_mm=40.0),
            food=FoodSource(center=Point2D(x_mm=34.0, y_mm=20.0), radius_mm=3.0, cue_radius_mm=10.0),
            cue_sensors=CueSensorGeometry(lateral_offset_mm=1.0, forward_offset_mm=0.5),
        )

        # When: the arena is converted to JSON-compatible data twice.
        first = json.dumps(arena.to_json_data(), sort_keys=True, separators=(",", ":"))
        second = json.dumps(arena.to_json_data(), sort_keys=True, separators=(",", ":"))

        # Then: serialization is stable and includes geometry needed by downstream logs.
        self.assertEqual(first, second)
        self.assertEqual(
            first,
            '{"cue_sensors":{"forward_offset_mm":0.5,"lateral_offset_mm":1.0},'
            '"dimensions":{"height_mm":40.0,"width_mm":60.0},'
            '"food":{"center":{"x_mm":34.0,"y_mm":20.0},"cue_radius_mm":10.0,"radius_mm":3.0}}',
        )


if __name__ == "__main__":
    unittest.main()
