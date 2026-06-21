import time
import unittest

from digital_fruit_fly.brain_worker import (
    BrainWorkerConfig,
    Brian2ProxyBackend,
    L4BrainWorkerServer,
)
from digital_fruit_fly.ipc_client import TcpJsonlClient
from digital_fruit_fly.ipc_protocol import BrainReadoutMessage, SensoryStateMessage


class IpcRoundTripTest(unittest.TestCase):
    def test_tcp_jsonl_round_trip(self):
        backend = Brian2ProxyBackend(BrainWorkerConfig())
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
