import unittest

from digital_fruit_fly.l4_online_lif import OnlineLIFBrainBridge
from digital_fruit_fly.state import BehaviorState, SensoryState


def make_state(
    time_s,
    *,
    food_cue=0.0,
    turn_bias=0.25,
    dust_level=0.0,
    dust_threshold=False,
    contact=False,
):
    return SensoryState(
        time_s=time_s,
        food_cue=food_cue,
        turn_bias=turn_bias,
        dust_level=dust_level,
        dust_threshold_reached=dust_threshold,
        food_contact=contact,
        food_distance_mm=5.0,
    )


class OnlineLIFBrainBridgeTest(unittest.TestCase):
    def test_bridge_caches_between_sync_ticks(self):
        bridge = OnlineLIFBrainBridge(brain_sync_interval_s=0.05)
        first = bridge.step(make_state(0.00, food_cue=0.4))
        cached = bridge.step(make_state(0.01, food_cue=1.0))

        self.assertFalse(bridge.last_runtime_state.brain_updated)
        self.assertEqual(bridge.cached_step_count, 1)
        self.assertEqual(cached.mn9_rate_hz, first.mn9_rate_hz)

    def test_dust_threshold_grooms_then_clears(self):
        bridge = OnlineLIFBrainBridge(
            brain_sync_interval_s=0.01,
            grooming_duration_s=0.1,
        )

        grooming = bridge.step(make_state(0.02, dust_level=1.0, dust_threshold=True))
        self.assertEqual(grooming.behavior_state, BehaviorState.GROOMING)
        self.assertEqual(grooming.forward_drive, 0.0)

        cleared = bridge.step(make_state(0.14, dust_level=1.0, dust_threshold=True))
        self.assertEqual(cleared.behavior_state, BehaviorState.FORAGING)
        self.assertEqual(cleared.dust_clearance, 1.0)
        self.assertTrue(bridge.just_completed_grooming)

    def test_food_contact_feeds_with_mn9_readout(self):
        bridge = OnlineLIFBrainBridge(
            brain_sync_interval_s=0.01,
            feeding_hold_s=0.2,
        )

        feeding = bridge.step(make_state(0.02, food_cue=1.0, contact=True))

        self.assertEqual(feeding.behavior_state, BehaviorState.FEEDING)
        self.assertEqual(feeding.forward_drive, 0.0)
        self.assertGreater(feeding.feeding_score, 0.8)
        self.assertGreater(feeding.mn9_rate_hz, 40.0)

    def test_off_cue_search_uses_search_turn_gain(self):
        bridge = OnlineLIFBrainBridge(
            brain_sync_interval_s=0.01,
            search_turn_gain=0.75,
        )

        readout = bridge.step(make_state(0.02, food_cue=0.0, turn_bias=0.4))

        self.assertAlmostEqual(readout.turn_bias, 0.3)

    def test_food_cue_keeps_chemotaxis_gain_curve(self):
        bridge = OnlineLIFBrainBridge(
            brain_sync_interval_s=0.01,
            search_turn_gain=0.75,
        )

        readout = bridge.step(make_state(0.02, food_cue=0.4, turn_bias=0.4))

        self.assertAlmostEqual(readout.turn_bias, 0.4 * (0.25 + 0.75 * 0.4))

    def test_runtime_summary_reports_update_costs(self):
        bridge = OnlineLIFBrainBridge(brain_sync_interval_s=0.01)
        bridge.step(make_state(0.00, food_cue=0.2))
        bridge.step(make_state(0.02, dust_level=0.4))

        summary = bridge.benchmark_summary()

        self.assertEqual(summary["target_sync_interval_s"], 0.01)
        self.assertGreaterEqual(summary["brain_update_count"], 1)
        self.assertGreaterEqual(summary["mean_update_wall_time_ms"], 0.0)
        self.assertIn("realtime_target_met", summary)


if __name__ == "__main__":
    unittest.main()
