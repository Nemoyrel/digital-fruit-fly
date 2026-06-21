import unittest
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from digital_fruit_fly.ipc_protocol import (
    BrainReadoutMessage,
    SensoryStateMessage,
    decode_message,
    encode_message,
)


class IpcProtocolTest(unittest.TestCase):
    def test_sensory_state_round_trip(self):
        msg = SensoryStateMessage(
            request_id=7,
            time_s=0.15,
            food_cue=0.8,
            turn_bias=-0.2,
            dust_level=0.4,
            dust_threshold_reached=False,
            food_contact=True,
            food_distance_mm=1.2,
        )
        decoded = decode_message(encode_message(msg))
        self.assertEqual(decoded, msg)

    def test_brain_readout_round_trip(self):
        msg = BrainReadoutMessage(
            request_id=7,
            behavior_state="feeding",
            forward_drive=0.0,
            turn_bias=0.0,
            grooming_score=0.1,
            feeding_score=0.95,
            mn9_rate_hz=88.0,
            dust_clearance=0.0,
            source="brain_worker:shiu_full",
            backend="shiu_full",
            brain_wall_time_ms=1.5,
            brain_simulated_window_s=0.015,
            cache_hit=False,
            extra={"shiu_full_used": True},
        )
        decoded = decode_message(encode_message(msg))
        self.assertEqual(decoded, msg)

    def test_unknown_type_raises_value_error(self):
        with self.assertRaises(ValueError):
            decode_message(b'{"type":"surprise"}\n')


if __name__ == "__main__":
    unittest.main()
