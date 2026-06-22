import socket
from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from digital_fruit_fly.ipc_protocol import BrainReadoutMessage
from digital_fruit_fly.l4_ipc_bridge import IpcBrainBridge
from digital_fruit_fly.state import BehaviorState, SensoryState


class FakeClient:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.requests = []

    def request(self, message):
        self.requests.append(message)
        if self.exc is not None:
            raise self.exc
        return self.response


def make_response(request_id=1, behavior_state="feeding"):
    return BrainReadoutMessage(
        request_id=request_id,
        behavior_state=behavior_state,
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
    )


def make_state(time_s=0.1):
    return SensoryState(
        time_s=time_s,
        food_cue=1.0,
        turn_bias=0.2,
        dust_level=0.0,
        dust_threshold_reached=False,
        food_contact=True,
        food_distance_mm=0.5,
    )


class IpcBrainBridgeTest(unittest.TestCase):
    def test_exposes_behavior_state_for_embodied_loop(self):
        client = FakeClient(
            BrainReadoutMessage(
                request_id=1,
                behavior_state="grooming",
                forward_drive=0.0,
                turn_bias=0.0,
                grooming_score=1.0,
                feeding_score=0.0,
                mn9_rate_hz=8.0,
                dust_clearance=0.0,
                source="brain_worker:shiu_full",
                backend="shiu_full",
                brain_wall_time_ms=1.0,
                brain_simulated_window_s=0.015,
                cache_hit=False,
            )
        )
        bridge = IpcBrainBridge(client=client)

        self.assertEqual(bridge.behavior_state, BehaviorState.FORAGING)
        bridge.step(make_state())

        self.assertEqual(bridge.behavior_state, BehaviorState.GROOMING)

    def test_successful_response_converts_to_readout(self):
        client = FakeClient(make_response())
        bridge = IpcBrainBridge(client=client)

        readout = bridge.step(make_state())

        self.assertEqual(readout.behavior_state, BehaviorState.FEEDING)
        self.assertEqual(readout.source, "brain_worker:shiu_full")
        self.assertEqual(bridge.request_count, 1)

    def test_timeout_returns_previous_readout(self):
        bridge = IpcBrainBridge(
            client=FakeClient(exc=socket.timeout("slow worker")),
        )
        previous = bridge.last_readout

        readout = bridge.step(make_state())

        self.assertEqual(readout, previous)
        self.assertEqual(bridge.timeout_count, 1)

    def test_reuses_cached_readout_between_brain_sync_intervals(self):
        client = FakeClient(make_response())
        bridge = IpcBrainBridge(client=client, brain_sync_interval_s=0.5)

        first = bridge.step(make_state(time_s=0.0))
        second = bridge.step(make_state(time_s=0.1))
        cached_fields = bridge.telemetry_fields()
        third = bridge.step(make_state(time_s=0.5))

        self.assertIs(second, first)
        self.assertEqual(third.behavior_state, BehaviorState.FEEDING)
        self.assertEqual(len(client.requests), 2)
        self.assertEqual(bridge.request_count, 2)
        self.assertEqual(bridge.step_count, 3)
        self.assertEqual(bridge.cached_step_count, 1)
        self.assertEqual(bridge.last_backend, "shiu_full")
        self.assertEqual(cached_fields["ipc_cache_hit"], 1)
        self.assertEqual(cached_fields["ipc_backend"], "shiu_full")
        self.assertEqual(bridge.telemetry_fields()["ipc_cache_hit"], 0)

    def test_from_config_reads_brain_sync_interval(self):
        bridge = IpcBrainBridge.from_config(
            {
                "host": "127.0.0.1",
                "port": 8765,
                "timeout_s": 600.0,
                "brain_sync_interval_s": 0.75,
            }
        )

        self.assertEqual(bridge.brain_sync_interval_s, 0.75)

    def test_from_config_default_timeout_is_full_model_friendly(self):
        bridge = IpcBrainBridge.from_config({})

        self.assertGreaterEqual(bridge.client.timeout_s, 60.0)

    def test_telemetry_fields_include_ipc_status(self):
        bridge = IpcBrainBridge(
            client=FakeClient(exc=socket.timeout("slow worker")),
        )
        bridge.step(make_state())

        fields = bridge.telemetry_fields()

        self.assertEqual(fields["ipc_request_count"], 1)
        self.assertEqual(fields["ipc_step_count"], 1)
        self.assertEqual(fields["ipc_timeout_count"], 1)
        self.assertEqual(fields["ipc_cached_step_count"], 0)
        self.assertEqual(fields["ipc_cache_hit"], 0)
        self.assertEqual(fields["ipc_backend"], "timeout_cache")
        self.assertIn("ipc_brain_wall_time_ms", fields)

    def test_telemetry_fields_include_full_backend_extras(self):
        client = FakeClient(
            BrainReadoutMessage(
                request_id=1,
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
                extra={
                    "grooming_rate_hz": 22.0,
                    "shiu_full_used": True,
                    "brain_window_s": 0.015,
                },
            )
        )
        bridge = IpcBrainBridge(client=client)
        bridge.step(make_state())

        fields = bridge.telemetry_fields()

        self.assertEqual(fields["ipc_grooming_rate_hz"], 22.0)
        self.assertEqual(fields["ipc_shiu_full_used"], 1)
        self.assertEqual(fields["ipc_brain_window_s"], 0.015)


if __name__ == "__main__":
    unittest.main()
