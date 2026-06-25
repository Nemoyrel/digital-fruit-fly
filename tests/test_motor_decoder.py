from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from digital_fruit_fly.bridge.messages import (
    SCHEMA_VERSION,
    BrainFrame,
    ControlFrame,
    payload_checksum,
)
from digital_fruit_fly.runtime.timeouts import JsonObject, JsonValue


class TestMotorDecoder(unittest.TestCase):
    def test_brain_rates_decode_locomotion_turn_and_provenance_payload(self) -> None:
        # Given: a brain frame with forward and signed turn readout above threshold.
        from digital_fruit_fly.body.controllers import decoded_control_from_frame
        from digital_fruit_fly.bridge.motor_decoder import (
            BrainFrameReadout,
            MotorDecoderRequest,
            decode_motor_control,
        )

        brain = _brain_frame({"forward": 40.0, "turn": -10.0, "feed": 3.0, "groom": 1.0, "stop": 1.0})

        # When: the downward decoder emits a body-compatible control frame.
        result = decode_motor_control(MotorDecoderRequest(readout=BrainFrameReadout(brain)))
        control = decoded_control_from_frame(result.control_frame)

        # Then: locomotion fields are clipped, signed, and audited without arena shortcuts.
        self.assertIsInstance(result.control_frame, ControlFrame)
        self.assertAlmostEqual(control.forward, 0.8)
        self.assertAlmostEqual(control.turn_bias, -1.0)
        self.assertEqual(result.payload["decoder_audit"]["selected_action"], "locomotion")
        self.assertEqual(result.payload["decoder_audit"]["arena_state_used_for_mode"], False)
        self.assertEqual(result.payload["decoder_audit"]["source"]["frame_index"], 7)

    def test_feed_requires_explicit_food_direction_and_logs_sensory_provenance(self) -> None:
        # Given: a feeding readout above threshold and an explicit sensory-derived food direction.
        from digital_fruit_fly.body.controllers import decoded_control_from_frame
        from digital_fruit_fly.bridge.motor_decoder import (
            BrainFrameReadout,
            FoodDirectionContext,
            MotorDecoderRequest,
            SensoryDecoderContext,
            decode_motor_control,
        )

        context = SensoryDecoderContext(
            food_direction=FoodDirectionContext(0.35, -0.08, 2.4, "sensory_frame:7/food_relative"),
        )
        brain = _brain_frame({"forward": 8.0, "turn": 2.0, "feed": 27.0, "groom": 1.0, "stop": 1.0})

        # When: the frame is decoded.
        result = decode_motor_control(MotorDecoderRequest(BrainFrameReadout(brain), sensory=context))
        control = decoded_control_from_frame(result.control_frame)

        # Then: feeding carries directional proboscis fields and provenance into the payload.
        self.assertGreater(control.feeding, 0.9)
        self.assertAlmostEqual(control.proboscis_extension, control.feeding)
        self.assertIsNotNone(control.food_direction)
        self.assertAlmostEqual(result.payload["proboscis_yaw"], 0.35)
        self.assertAlmostEqual(result.payload["proboscis_pitch"], -0.08)
        audit = result.payload["decoder_audit"]
        self.assertEqual(audit["selected_action"], "feeding")
        self.assertEqual(audit["sensory_provenance"]["food_direction"], "sensory_frame:7/food_relative")

    def test_feeding_without_direction_raises_typed_error(self) -> None:
        # Given: feeding is selected but no sensory-to-brain-to-decoder direction is present.
        from digital_fruit_fly.bridge.motor_decoder import (
            BrainFrameReadout,
            MissingFoodDirection,
            MotorDecoderRequest,
            decode_motor_control,
        )

        brain = _brain_frame({"forward": 8.0, "turn": 2.0, "feed": 25.0, "groom": 1.0, "stop": 1.0})

        # When / Then: the decoder refuses to invent or reuse direction.
        with self.assertRaises(MissingFoodDirection) as raised:
            decode_motor_control(MotorDecoderRequest(BrainFrameReadout(brain)))
        self.assertEqual(raised.exception.selected_action, "feeding")

    def test_stop_wins_and_feed_groom_conflict_uses_configured_priority(self) -> None:
        # Given: conflicting stop, feed, and groom readouts.
        from digital_fruit_fly.bridge.motor_decoder import (
            BrainFrameReadout,
            FoodDirectionContext,
            MotorAction,
            MotorDecoderConfig,
            MotorDecoderRequest,
            SensoryDecoderContext,
            decode_motor_control,
        )

        config = MotorDecoderConfig.default().with_priority(
            (MotorAction.STOP, MotorAction.FEEDING, MotorAction.GROOMING, MotorAction.LOCOMOTION)
        )
        sensory = SensoryDecoderContext(FoodDirectionContext(0.2, 0.0, 1.5, "encoded_food_direction"))
        conflict = _brain_frame({"forward": 8.0, "turn": 2.0, "feed": 26.0, "groom": 25.0, "stop": 1.0})
        stop = _brain_frame({"forward": 45.0, "turn": 2.0, "feed": 28.0, "groom": 25.0, "stop": 7.0})

        # When: priority is applied.
        feed_result = decode_motor_control(MotorDecoderRequest(BrainFrameReadout(conflict), config, sensory))
        stop_result = decode_motor_control(MotorDecoderRequest(BrainFrameReadout(stop), config, sensory))

        # Then: configured feed/groom order is deterministic, but stop is always highest.
        self.assertEqual(feed_result.payload["decoder_audit"]["selected_action"], "feeding")
        self.assertEqual(feed_result.payload["grooming"], 0.0)
        self.assertEqual(stop_result.payload["decoder_audit"]["selected_action"], "stop")
        self.assertEqual(stop_result.payload["forward"], 0.0)
        self.assertEqual(stop_result.payload["feeding"], 0.0)

    def test_smoothing_uses_previous_decoder_state_and_rejects_stale_state(self) -> None:
        # Given: a previous decoder state and a new high forward readout.
        from digital_fruit_fly.bridge.motor_decoder import (
            BrainFrameReadout,
            MotorDecoderRequest,
            StaleDecoderState,
            decode_motor_control,
        )

        first = decode_motor_control(MotorDecoderRequest(BrainFrameReadout(_brain_frame({"forward": 8.0}, index=7))))
        second = decode_motor_control(
            MotorDecoderRequest(
                BrainFrameReadout(_brain_frame({"forward": 48.0}, index=8)),
                previous_state=first.state,
            )
        )

        # When / Then: smoothing damps the step and stale frame indexes are rejected.
        self.assertGreater(second.payload["forward"], 0.0)
        self.assertLess(second.payload["forward"], 1.0)
        with self.assertRaises(StaleDecoderState):
            decode_motor_control(
                MotorDecoderRequest(
                    BrainFrameReadout(_brain_frame({"forward": 48.0}, index=8)),
                    previous_state=second.state,
                )
            )

    def test_spike_fallback_malformed_input_and_missing_group_are_rejected(self) -> None:
        # Given: spike-only input, malformed rate values, and an incomplete mapping.
        from digital_fruit_fly.brain.mapping import load_neural_mapping
        from digital_fruit_fly.bridge.motor_decoder import (
            BrainFrameReadout,
            MalformedBrainReadout,
            MissingReadoutGroup,
            MotorDecoderConfig,
            MotorDecoderRequest,
            RateReadout,
            decode_motor_payload,
            validate_motor_decoder_readouts,
        )

        spike_result = decode_motor_payload(
            MotorDecoderRequest(readout=RateReadout(rates_hz={}, spike_deltas={"forward": 1, "turn": 0, "feed": 0, "groom": 0, "stop": 0}))
        )
        malformed = _brain_frame({"forward": "fast"})
        mapping = load_neural_mapping(REPO_ROOT / "configs" / "brain_mapping.yaml")
        available = tuple(group.channel_name for group in mapping.motor_readout_groups if group.channel_name != "feed")

        # When / Then: spikes can drive output, but bad frame data and missing groups fail early.
        self.assertGreater(spike_result.payload["forward"], 0.0)
        with self.assertRaises(MalformedBrainReadout):
            decode_motor_payload(MotorDecoderRequest(readout=BrainFrameReadout(malformed)))
        with self.assertRaises(MissingReadoutGroup) as raised:
            validate_motor_decoder_readouts(MotorDecoderConfig.default(), available)
        self.assertEqual(raised.exception.group, "feed")

    def test_food_context_alone_cannot_select_action_mode(self) -> None:
        # Given: food direction context exists, but brain readouts stay at baseline.
        from digital_fruit_fly.bridge.motor_decoder import (
            FoodDirectionContext,
            MotorDecoderRequest,
            RateReadout,
            SensoryDecoderContext,
            decode_motor_payload,
        )

        context = SensoryDecoderContext(FoodDirectionContext(0.7, 0.1, 1.0, "arena-derived-via-sensory-encoder"))

        # When: rates are decoded.
        result = decode_motor_payload(MotorDecoderRequest(RateReadout(_baseline_rates()), sensory=context))

        # Then: the action remains a configured stop fallback, not feed/groom from arena facts.
        self.assertEqual(result.payload["decoder_audit"]["selected_action"], "stop")
        self.assertEqual(result.payload["feeding"], 0.0)
        self.assertEqual(result.payload["grooming"], 0.0)


def _brain_frame(rates: dict[str, JsonValue], index: int = 7) -> BrainFrame:
    full_rates = _baseline_rates()
    full_rates.update(rates)
    payload: JsonObject = {"rates_hz": full_rates, "spike_deltas": {}, "tick_index": index}
    return BrainFrame(SCHEMA_VERSION, "motor-decoder-test", index, index * 0.015, 10.0, payload, payload_checksum(payload))


def _baseline_rates() -> dict[str, JsonValue]:
    return {"forward": 8.0, "turn": 2.0, "feed": 3.0, "groom": 1.0, "stop": 1.0}


if __name__ == "__main__":
    unittest.main()
