import json
import unittest

from digital_fruit_fly.bridge.messages import (
    SCHEMA_VERSION,
    BrainFrame,
    ControlFrame,
    ErrorFrame,
    Heartbeat,
    Hello,
    SensoryFrame,
    Shutdown,
    decode_frame,
    decode_message,
    encode_frame,
    encode_message,
    payload_checksum,
)


class TestBridgeMessages(unittest.TestCase):
    def test_round_trip_preserves_hello_when_schema_is_supported(self) -> None:
        # Given: a versioned hello frame for one run.
        frame = Hello(
            schema_version=SCHEMA_VERSION,
            run_id="run-bridge-001",
            frame_index=0,
            simulation_time_s=0.0,
            sent_monotonic_s=12.5,
            role="brain",
        )

        # When: it crosses the JSON protocol boundary.
        decoded = decode_message(encode_message(frame))

        # Then: the typed frame is restored.
        self.assertEqual(decoded, frame)

    def test_verifier_one_liner_shape_round_trips_default_hello(self) -> None:
        # Given: the public ergonomic API used by independent verification.
        frame = Hello(run_id="verify-run")

        # When: the frame crosses the alias codec boundary.
        decoded = decode_frame(encode_frame(frame))

        # Then: default metadata is safe and the run id is preserved.
        self.assertIsInstance(decoded, Hello)
        self.assertEqual(decoded.run_id, "verify-run")
        self.assertEqual(decoded.schema_version, SCHEMA_VERSION)
        self.assertEqual(decoded.role, "unspecified")

    def test_round_trip_preserves_payload_checksum_when_payload_is_valid(self) -> None:
        # Given: a sensory frame with a deterministic checksum.
        payload = {"left_sugar": 0.25, "right_sugar": 0.75, "dust_load": 0.1}
        frame = SensoryFrame(
            schema_version=SCHEMA_VERSION,
            run_id="run-bridge-002",
            frame_index=4,
            simulation_time_s=0.06,
            sent_monotonic_s=100.25,
            payload=payload,
            payload_checksum=payload_checksum(payload),
        )

        # When: the frame is serialized and parsed.
        decoded = decode_message(encode_message(frame))

        # Then: the payload and checksum remain unchanged.
        self.assertEqual(decoded, frame)

    def test_future_schema_decodes_to_error_frame_when_version_is_unsupported(self) -> None:
        # Given: a valid-looking message from a future schema.
        raw = json.dumps(
            {
                "type": "hello",
                "schema_version": SCHEMA_VERSION + 1,
                "run_id": "run-future",
                "frame_index": 0,
                "simulation_time_s": 0.0,
                "sent_monotonic_s": 1.0,
                "role": "body",
            }
        ).encode("utf-8")

        # When: the local schema parser receives it.
        decoded = decode_message(raw)

        # Then: callers receive a typed error instead of an unsafe future frame.
        self.assertIsInstance(decoded, ErrorFrame)
        self.assertEqual(decoded.code, "schema_version_unsupported")
        self.assertEqual(decoded.run_id, "run-future")

    def test_invalid_payload_decodes_to_error_frame_when_checksum_mismatches(self) -> None:
        # Given: a frame whose payload checksum does not match the payload.
        raw = json.dumps(
            {
                "type": "brain_frame",
                "schema_version": SCHEMA_VERSION,
                "run_id": "run-invalid",
                "frame_index": 1,
                "simulation_time_s": 0.015,
                "sent_monotonic_s": 8.0,
                "payload": {"forward": 0.4},
                "payload_checksum": "sha256:not-the-payload",
            }
        ).encode("utf-8")

        # When: the parser verifies the payload at the trust boundary.
        decoded = decode_message(raw)

        # Then: the invalid payload is converted to a typed protocol error.
        self.assertIsInstance(decoded, ErrorFrame)
        self.assertEqual(decoded.code, "invalid_payload")
        self.assertEqual(decoded.run_id, "run-invalid")

    def test_invalid_payload_decodes_to_error_frame_for_behavior_shortcut(self) -> None:
        # Given: a sensory frame that tries to bypass the brain with a behavior label.
        raw = json.dumps(
            {
                "type": "sensory_frame",
                "schema_version": SCHEMA_VERSION,
                "run_id": "run-shortcut",
                "frame_index": 2,
                "simulation_time_s": 0.03,
                "sent_monotonic_s": 9.0,
                "payload": {"groom_now": True},
                "payload_checksum": payload_checksum({"groom_now": True}),
            }
        ).encode("utf-8")

        # When: the parser checks the payload contract.
        decoded = decode_message(raw)

        # Then: the bridge rejects direct behavior shortcuts.
        self.assertIsInstance(decoded, ErrorFrame)
        self.assertEqual(decoded.code, "invalid_payload")

    def test_invalid_payload_decodes_to_error_frame_for_nested_behavior_shortcut(self) -> None:
        # Given: a nested payload that tries to hide a direct behavior label.
        payload = {"arena": {"feed_now": True}}
        raw = json.dumps(
            {
                "type": "sensory_frame",
                "schema_version": SCHEMA_VERSION,
                "run_id": "run-nested-shortcut",
                "frame_index": 3,
                "simulation_time_s": 0.045,
                "sent_monotonic_s": 9.5,
                "payload": payload,
                "payload_checksum": payload_checksum(payload),
            }
        ).encode("utf-8")

        # When: the parser checks the payload contract recursively.
        decoded = decode_message(raw)

        # Then: the bridge rejects hidden direct behavior shortcuts.
        self.assertIsInstance(decoded, ErrorFrame)
        self.assertEqual(decoded.code, "invalid_payload")

    def test_round_trip_preserves_brain_frame_when_payload_is_valid(self) -> None:
        # Given: a brain frame with readout values only.
        payload = {"forward_intensity": 0.8, "turn_bias": -0.1}
        frame = BrainFrame(
            schema_version=SCHEMA_VERSION,
            run_id="run-bridge-003",
            frame_index=5,
            simulation_time_s=0.075,
            sent_monotonic_s=101.25,
            payload=payload,
            payload_checksum=payload_checksum(payload),
        )

        # When: the frame is serialized and parsed.
        decoded = decode_message(encode_message(frame))

        # Then: no behavior-label shortcut is needed or added.
        self.assertEqual(decoded, frame)

    def test_round_trip_preserves_remaining_control_frames(self) -> None:
        # Given: control, heartbeat, error, and shutdown frames.
        payload = {"proboscis_extension": 0.6}
        frames = [
            ControlFrame(
                SCHEMA_VERSION,
                "run-control",
                6,
                0.09,
                102.25,
                payload,
                payload_checksum(payload),
            ),
            Heartbeat(SCHEMA_VERSION, "run-control", 7, 0.105, 103.25),
            ErrorFrame(SCHEMA_VERSION, "run-control", 8, 0.12, 104.25, "invalid_payload", "bad frame", {}),
            Shutdown(SCHEMA_VERSION, "run-control", 9, 0.135, 105.25, "done"),
        ]

        # When: each frame crosses the JSON protocol boundary.
        decoded = [decode_message(encode_message(frame)) for frame in frames]

        # Then: each typed schema is preserved.
        self.assertEqual(decoded, frames)


if __name__ == "__main__":
    unittest.main()
