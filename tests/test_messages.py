import unittest

import _bootstrap  # noqa: F401

from digital_fruit_fly.messages import (
    BrainReadoutMessage,
    SensoryStateMessage,
    decode_message,
    encode_message,
)


class MessageRoundTripTest(unittest.TestCase):
    def test_sensory_state_round_trip(self):
        msg = SensoryStateMessage(
            request_id=3,
            time_s=1.5,
            food_cue=0.4,
            turn_bias=-0.2,
            dust_level=0.8,
            dust_threshold_reached=True,
            food_contact=False,
            food_distance_mm=12.3,
        )
        decoded = decode_message(encode_message(msg))
        self.assertEqual(decoded, msg)

    def test_brain_readout_round_trip_with_activity(self):
        msg = BrainReadoutMessage(
            request_id=3,
            behavior_state="feeding",
            forward_drive=0.9,
            turn_bias=0.0,
            grooming_score=0.0,
            feeding_score=0.7,
            mn9_rate_hz=70.0,
            dust_clearance=0.0,
            source="brain_worker:shiu_full",
            backend="shiu_full",
            brain_wall_time_ms=12.0,
            brain_simulated_window_s=0.02,
            neuron_activity=[0, 1, 2, 0, 3],
            active_neuron_count=3,
            total_neuron_count=130000,
            extra={"grooming_rate_hz": 0.0},
        )
        decoded = decode_message(encode_message(msg))
        self.assertEqual(decoded, msg)
        self.assertEqual(decoded.neuron_activity, [0, 1, 2, 0, 3])

    def test_encode_is_one_json_line(self):
        msg = SensoryStateMessage(
            request_id=0, time_s=0.0, food_cue=0.0, turn_bias=0.0,
            dust_level=0.0, dust_threshold_reached=False, food_contact=False,
            food_distance_mm=0.0,
        )
        raw = encode_message(msg)
        self.assertTrue(raw.endswith(b"\n"))
        self.assertEqual(raw.count(b"\n"), 1)

    def test_unknown_type_raises(self):
        with self.assertRaises(ValueError):
            decode_message('{"type": "nope"}')


if __name__ == "__main__":
    unittest.main()
