from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from digital_fruit_fly.arena.model import SugarCueSample
from digital_fruit_fly.body.observations import (
    BodyObservation,
    BodyPose,
    FineJointAngles,
    FoodRelative,
)
from digital_fruit_fly.bridge.sensory_encoder import (
    FineJointDofConfig,
    ForbiddenSensoryField,
    SensoryChannelRateConfig,
    SensoryEncoder,
    SensoryEncodingConfig,
    SensoryEncodingRequest,
    SensoryNormalizationConfig,
    encode_sensory_observation,
)


class TestSensoryEncoder(unittest.TestCase):
    def test_sugar_rates_are_monotonic_and_lateralized_when_cue_changes(self) -> None:
        # Given: a configured encoder and two sugar cue samples.
        config = _config()
        low = _request(SugarCueSample(left=0.1, right=0.1))
        high_left = _request(SugarCueSample(left=0.8, right=0.2))

        # When: both samples are encoded as upward sensory rates.
        low_result = encode_sensory_observation(config, low)
        high_result = encode_sensory_observation(config, high_left)

        # Then: stronger sugar produces higher rates and preserves left/right asymmetry.
        self.assertGreater(high_result.rates_hz["sugar_left"], low_result.rates_hz["sugar_left"])
        self.assertGreater(high_result.rates_hz["sugar_right"], low_result.rates_hz["sugar_right"])
        self.assertGreater(high_result.rates_hz["sugar_left"], high_result.rates_hz["sugar_right"])

    def test_food_direction_distance_contact_and_dust_are_encoded_when_present(self) -> None:
        # Given: a body observation near food with positive bearing, negative elevation, and dusty state.
        observation = replace(
            _observation(),
            food_contact=True,
            food_relative=FoodRelative(bearing_rad=0.5, elevation_rad=-0.25, distance_mm=5.0),
            dust={"dust_load": 0.75, "threshold_crossed": True},
        )

        # When: the observation is encoded.
        result = encode_sensory_observation(_config(), _request(SugarCueSample(0.0, 0.0), observation))

        # Then: signed direction, distance/contact, and dust threshold channels are present.
        self.assertGreater(result.rates_hz["food_bearing_left"], 0.0)
        self.assertEqual(result.rates_hz["food_bearing_right"], 0.0)
        self.assertGreater(result.rates_hz["food_elevation_down"], 0.0)
        self.assertEqual(result.rates_hz["food_elevation_up"], 0.0)
        self.assertEqual(result.rates_hz["food_contact"], 100.0)
        self.assertEqual(result.rates_hz["dust_threshold"], 100.0)
        self.assertAlmostEqual(result.rates_hz["food_distance"], 50.0)

    def test_fine_proprioception_and_action_feedback_channels_when_configured(self) -> None:
        # Given: configured fine DOFs and numeric body-action feedback.
        request = _request(
            SugarCueSample(0.0, 0.0),
            action_feedback={"proboscis_extension": 0.4, "sweep_phase": 0.75},
        )

        # When: the encoder maps proprioception and feedback into sensory rates.
        result = encode_sensory_observation(_config(), request)

        # Then: all configured proboscis, antenna, front-leg, head, and feedback channels exist.
        for channel in (
            "proboscis_rostrum_pitch",
            "antenna_left_antenna_yaw",
            "front_leg_left_front_tarsus",
            "head_head_pitch",
            "proprioception_summary",
            "action_feedback_proboscis_extension",
            "action_feedback_sweep_phase",
        ):
            self.assertIn(channel, result.rates_hz)
            self.assertGreater(result.rates_hz[channel], 0.0)

    def test_clips_out_of_range_inputs_to_channel_limits(self) -> None:
        # Given: raw values far outside configured normalization ranges.
        observation = replace(
            _observation(),
            food_relative=FoodRelative(bearing_rad=9.0, elevation_rad=9.0, distance_mm=99.0),
            dust={"dust_load": 9.0, "threshold_crossed": True},
            proprioception={"joint_angle_mean_abs": 9.0, "joint_velocity_mean_abs": 9.0},
        )

        # When: the encoder processes those values.
        result = encode_sensory_observation(
            _config(),
            _request(
                SugarCueSample(left=3.0, right=-1.0),
                observation,
                action_feedback={"proboscis_extension": 9.0, "sweep_phase": -2.0},
            ),
        )

        # Then: every rate is clipped into the configured 0..100 Hz interval.
        self.assertEqual(result.rates_hz["sugar_left"], 100.0)
        self.assertEqual(result.rates_hz["sugar_right"], 0.0)
        self.assertEqual(result.rates_hz["dust_load"], 100.0)
        self.assertEqual(result.rates_hz["food_bearing_left"], 100.0)
        self.assertTrue(all(0.0 <= value <= 100.0 for value in result.rates_hz.values()))

    def test_latency_delays_configured_output_by_ticks(self) -> None:
        # Given: a stateful encoder with one tick of latency.
        config = replace(_config(), latency_ticks=1)
        encoder = SensoryEncoder(config)

        # When: a high-sugar frame is followed by a low-sugar frame.
        first = encoder.encode(_request(SugarCueSample(1.0, 0.0)))
        second = encoder.encode(_request(SugarCueSample(0.0, 0.0)))

        # Then: the first output is priming silence and the second emits the delayed frame.
        self.assertEqual(first.rates_hz["sugar_left"], 0.0)
        self.assertEqual(second.rates_hz["sugar_left"], 100.0)
        self.assertEqual(second.audit["latency_ticks"], 1)

    def test_audit_and_rates_exclude_forbidden_behavior_label_fields(self) -> None:
        # Given: a normal body observation without behavior shortcuts.
        request = _request(SugarCueSample(0.5, 0.25))

        # When: the encoder emits rates and audit data.
        result = encode_sensory_observation(_config(), request)

        # Then: neither output surface contains behavior labels or direct action decisions.
        rendered = str({"rates": result.rates_hz, "audit": result.audit})
        self.assertNotIn("behavior", rendered)
        self.assertNotIn("groom_now", rendered)
        self.assertNotIn("feed_now", rendered)
        self.assertNotIn("'groom'", rendered)

    def test_rejects_forbidden_behavior_label_observation(self) -> None:
        # Given: source metadata tries to smuggle a direct behavior label upward.
        request = replace(
            _request(SugarCueSample(0.0, 0.0)),
            source_metadata={"behavior": "groom"},
        )

        # When / Then: the schema boundary rejects it before producing rates or audit data.
        with self.assertRaises(ForbiddenSensoryField):
            encode_sensory_observation(_config(), request)


def _config() -> SensoryEncodingConfig:
    return SensoryEncodingConfig(
        channel_rates=SensoryChannelRateConfig(default_max_rate_hz=100.0),
        normalization=SensoryNormalizationConfig(
            max_dust_load=1.0,
            dust_threshold=0.5,
            max_food_distance_mm=10.0,
            max_joint_abs=1.0,
            max_velocity_abs=2.0,
            max_feedback_abs=1.0,
        ),
        fine_joint_dofs=FineJointDofConfig(
            proboscis=("rostrum_pitch",),
            antenna=("left_antenna_yaw",),
            front_leg=("left_front_tarsus",),
            head=("head_pitch",),
        ),
        action_feedback_channels=("proboscis_extension", "sweep_phase"),
    )


def _request(
    sugar: SugarCueSample,
    observation: BodyObservation | None = None,
    action_feedback: dict[str, float] | None = None,
) -> SensoryEncodingRequest:
    return SensoryEncodingRequest(
        observation=_observation() if observation is None else observation,
        sugar_cue=sugar,
        action_feedback={} if action_feedback is None else action_feedback,
    )


def _observation() -> BodyObservation:
    return BodyObservation(
        pose=BodyPose(x_mm=1.0, y_mm=2.0, z_mm=0.3, yaw_rad=0.0),
        food_contact=False,
        food_relative=FoodRelative(bearing_rad=0.0, elevation_rad=0.0, distance_mm=10.0),
        ground_contact={"active_fraction": 0.5},
        contact_forces={},
        proprioception={"joint_angle_mean_abs": 0.25, "joint_velocity_mean_abs": 0.5},
        dust={"dust_load": 0.25, "threshold_crossed": False},
        joint_angles=FineJointAngles(
            proboscis={"rostrum_pitch": 0.5},
            antenna={"left_antenna_yaw": -0.5},
            front_leg={"left_front_tarsus": 0.25},
            head={"head_pitch": -0.25},
        ),
        site_positions={},
    )


if __name__ == "__main__":
    unittest.main()
