import unittest

import _bootstrap  # noqa: F401

from digital_fruit_fly.brain_link import IpcBrainBridge
from digital_fruit_fly.messages import BrainReadoutMessage, SensoryStateMessage
from digital_fruit_fly.state import BehaviorState, SensoryState


class FakeClient:
    def __init__(self, response: BrainReadoutMessage):
        self.response = response
        self.calls = 0

    def request(self, message: SensoryStateMessage) -> BrainReadoutMessage:
        self.calls += 1
        return self.response


def _response(behavior="foraging", dust_clearance=0.0):
    return BrainReadoutMessage(
        request_id=0,
        behavior_state=behavior,
        forward_drive=0.8,
        turn_bias=0.1,
        grooming_score=0.0,
        feeding_score=0.5,
        mn9_rate_hz=60.0,
        dust_clearance=dust_clearance,
        source="brain_worker:shiu_full",
        backend="shiu_full",
        brain_wall_time_ms=5.0,
        brain_simulated_window_s=0.02,
        neuron_activity=[0, 2, 0, 1],
        active_neuron_count=2,
        total_neuron_count=1000,
        extra={"grooming_rate_hz": 0.0, "brain_window_s": 0.02},
    )


def _sensory(t):
    return SensoryState(
        time_s=t, food_cue=0.3, turn_bias=0.0, dust_level=0.1,
        dust_threshold_reached=False, food_contact=False, food_distance_mm=10.0,
    )


class BrainLinkTest(unittest.TestCase):
    def test_first_step_requests_and_converts_activity(self):
        client = FakeClient(_response())
        bridge = IpcBrainBridge(client=client, brain_sync_interval_s=0.5)
        r = bridge.step(_sensory(0.0))
        self.assertEqual(client.calls, 1)
        self.assertEqual(r.feeding_score, 0.5)
        self.assertEqual(r.neuron_activity, (0, 2, 0, 1))
        self.assertEqual(r.total_neuron_count, 1000)

    def test_throttle_uses_cache_between_intervals(self):
        client = FakeClient(_response())
        bridge = IpcBrainBridge(client=client, brain_sync_interval_s=0.5)
        bridge.step(_sensory(0.0))
        bridge.step(_sensory(0.1))  # within interval -> cached
        bridge.step(_sensory(0.2))  # within interval -> cached
        self.assertEqual(client.calls, 1)
        self.assertTrue(bridge.last_cache_hit)
        bridge.step(_sensory(0.6))  # beyond interval -> new request
        self.assertEqual(client.calls, 2)
        self.assertFalse(bridge.last_cache_hit)

    def test_dust_clearance_sets_just_completed_grooming_once(self):
        client = FakeClient(_response(dust_clearance=1.0))
        bridge = IpcBrainBridge(client=client, brain_sync_interval_s=0.0)
        bridge.step(_sensory(0.0))
        self.assertTrue(bridge.just_completed_grooming)

    def test_behavior_state_tracks_response(self):
        client = FakeClient(_response(behavior="feeding"))
        bridge = IpcBrainBridge(client=client, brain_sync_interval_s=0.0)
        bridge.step(_sensory(0.0))
        self.assertEqual(bridge.behavior_state, BehaviorState.FEEDING)

    def test_timeout_falls_back_to_last_readout(self):
        class BoomClient:
            def request(self, message):
                raise TimeoutError("boom")

        bridge = IpcBrainBridge(client=BoomClient(), brain_sync_interval_s=0.0)
        r = bridge.step(_sensory(0.0))
        self.assertEqual(bridge.timeout_count, 1)
        self.assertEqual(bridge.last_backend, "timeout_cache")
        self.assertIsNotNone(r)


if __name__ == "__main__":
    unittest.main()
