import socket
import unittest

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
    def test_successful_response_converts_to_readout(self):
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
                source="brain_worker:brian2_proxy",
                backend="brian2_proxy",
                brain_wall_time_ms=1.0,
                brain_simulated_window_s=0.015,
                cache_hit=False,
            )
        )
        bridge = IpcBrainBridge(client=client)

        readout = bridge.step(make_state())

        self.assertEqual(readout.behavior_state, BehaviorState.FEEDING)
        self.assertEqual(readout.source, "brain_worker:brian2_proxy")
        self.assertEqual(bridge.request_count, 1)

    def test_timeout_returns_previous_readout(self):
        bridge = IpcBrainBridge(
            client=FakeClient(exc=socket.timeout("slow worker")),
        )
        previous = bridge.last_readout

        readout = bridge.step(make_state())

        self.assertEqual(readout, previous)
        self.assertEqual(bridge.timeout_count, 1)

    def test_telemetry_fields_include_ipc_status(self):
        bridge = IpcBrainBridge(
            client=FakeClient(exc=socket.timeout("slow worker")),
        )
        bridge.step(make_state())

        fields = bridge.telemetry_fields()

        self.assertEqual(fields["ipc_request_count"], 1)
        self.assertEqual(fields["ipc_timeout_count"], 1)
        self.assertEqual(fields["ipc_backend"], "timeout_cache")
        self.assertIn("ipc_brain_wall_time_ms", fields)


if __name__ == "__main__":
    unittest.main()
