import time
from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from digital_fruit_fly.brain_worker import L4BrainWorkerServer
from digital_fruit_fly.ipc_client import TcpJsonlClient
from digital_fruit_fly.ipc_protocol import BrainReadoutMessage, SensoryStateMessage


class StaticBackend:
    def handle(self, message):
        return BrainReadoutMessage(
            request_id=message.request_id,
            behavior_state="feeding",
            forward_drive=0.0,
            turn_bias=0.0,
            grooming_score=0.0,
            feeding_score=1.0,
            mn9_rate_hz=90.0,
            dust_clearance=0.0,
            source="brain_worker:shiu_full",
            backend="shiu_full",
            brain_wall_time_ms=1.0,
            brain_simulated_window_s=0.015,
            cache_hit=False,
            extra={"shiu_full_used": True},
        )


class IpcRoundTripTest(unittest.TestCase):
    def test_tcp_jsonl_round_trip(self):
        backend = StaticBackend()
        server = L4BrainWorkerServer(host="127.0.0.1", port=0, backend=backend)
        server.serve_background()
        for _ in range(20):
            if server.bound_port:
                break
            time.sleep(0.01)
        self.addCleanup(server.shutdown)

        client = TcpJsonlClient(
            host="127.0.0.1",
            port=server.bound_port,
            timeout_s=1.0,
        )
        response = client.request(
            SensoryStateMessage(
                request_id=12,
                time_s=0.1,
                food_cue=1.0,
                turn_bias=0.0,
                dust_level=0.0,
                dust_threshold_reached=False,
                food_contact=True,
                food_distance_mm=0.5,
            )
        )

        self.assertIsInstance(response, BrainReadoutMessage)
        self.assertEqual(response.request_id, 12)
        self.assertEqual(response.behavior_state, "feeding")


if __name__ == "__main__":
    unittest.main()
