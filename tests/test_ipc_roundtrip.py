import json
import socket
import struct
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
from digital_fruit_fly.ipc_protocol import (
    BrainReadoutMessage,
    SensoryStateMessage,
    encode_message,
)


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


class SlowStaticBackend(StaticBackend):
    def handle(self, message):
        time.sleep(0.05)
        return super().handle(message)


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

    def test_server_survives_client_disconnect_before_response(self):
        server = L4BrainWorkerServer(
            host="127.0.0.1",
            port=0,
            backend=SlowStaticBackend(),
        )
        thread = server.serve_background()
        for _ in range(20):
            if server.bound_port:
                break
            time.sleep(0.01)
        self.addCleanup(server.shutdown)

        with socket.create_connection(("127.0.0.1", server.bound_port), timeout=1.0) as sock:
            sock.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_LINGER,
                struct.pack("ii", 1, 0),
            )
            sock.sendall(
                encode_message(
                    SensoryStateMessage(
                        request_id=13,
                        time_s=0.1,
                        food_cue=1.0,
                        turn_bias=0.0,
                        dust_level=0.0,
                        dust_threshold_reached=False,
                        food_contact=True,
                        food_distance_mm=0.5,
                    )
                )
            )

        # Send a valid request after the early-disconnect client. The worker
        # should still be alive and able to answer it.
        time.sleep(0.1)
        self.assertTrue(thread.is_alive())
        client = TcpJsonlClient(
            host="127.0.0.1",
            port=server.bound_port,
            timeout_s=1.0,
        )
        response = client.request(
            SensoryStateMessage(
                request_id=14,
                time_s=0.2,
                food_cue=1.0,
                turn_bias=0.0,
                dust_level=0.0,
                dust_threshold_reached=False,
                food_contact=True,
                food_distance_mm=0.5,
            )
        )

        self.assertEqual(response.request_id, 14)

    def test_default_ipc_timeout_is_long_enough_for_full_model_windows(self):
        config = json.loads((PROJECT_ROOT / "configs" / "l4_ipc_embodied_loop.json").read_text())

        self.assertGreaterEqual(float(config["ipc"]["timeout_s"]), 60.0)

    def test_tcp_client_default_timeout_is_full_model_friendly(self):
        client = TcpJsonlClient(host="127.0.0.1", port=8765)

        self.assertGreaterEqual(client.timeout_s, 60.0)

    def test_default_ipc_config_throttles_full_model_requests(self):
        config = json.loads((PROJECT_ROOT / "configs" / "l4_ipc_embodied_loop.json").read_text())

        self.assertGreaterEqual(float(config["ipc"]["brain_sync_interval_s"]), 0.25)


if __name__ == "__main__":
    unittest.main()
