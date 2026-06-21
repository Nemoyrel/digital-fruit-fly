import unittest

from digital_fruit_fly.brain_worker import (
    BrainWorkerConfig,
    Brian2ProxyBackend,
    ShiuFullBackend,
    select_backend,
)
from digital_fruit_fly.ipc_protocol import SensoryStateMessage


def make_msg(
    time_s,
    *,
    food_cue=0.0,
    dust_level=0.0,
    dust_threshold=False,
    food_contact=False,
):
    return SensoryStateMessage(
        request_id=1,
        time_s=time_s,
        food_cue=food_cue,
        turn_bias=0.2,
        dust_level=dust_level,
        dust_threshold_reached=dust_threshold,
        food_contact=food_contact,
        food_distance_mm=2.0,
    )


class BrainWorkerBackendTest(unittest.TestCase):
    def test_proxy_maps_food_cue_to_mn9_readout(self):
        backend = Brian2ProxyBackend(BrainWorkerConfig())

        response = backend.handle(make_msg(0.1, food_cue=1.0, food_contact=True))

        self.assertEqual(response.backend, "brian2_proxy")
        self.assertEqual(response.behavior_state, "feeding")
        self.assertGreater(response.mn9_rate_hz, 40.0)
        self.assertGreater(response.feeding_score, 0.8)

    def test_proxy_grooms_then_clears_dust(self):
        backend = Brian2ProxyBackend(
            BrainWorkerConfig(brain_window_s=0.01, grooming_duration_s=0.1)
        )

        grooming = backend.handle(
            make_msg(0.02, dust_level=1.0, dust_threshold=True)
        )
        cleared = backend.handle(
            make_msg(0.14, dust_level=1.0, dust_threshold=True)
        )

        self.assertEqual(grooming.behavior_state, "grooming")
        self.assertEqual(grooming.forward_drive, 0.0)
        self.assertEqual(cleared.behavior_state, "foraging")
        self.assertEqual(cleared.dust_clearance, 1.0)

    def test_select_backend_auto_reports_environment(self):
        selection = select_backend("auto", BrainWorkerConfig(max_startup_s=0.0))

        self.assertIsNotNone(selection.backend)
        self.assertIn(selection.backend_name, {"brian2_proxy", "shiu_full"})
        self.assertIn("brian2_version", selection.metadata)
        self.assertIn("codegen_target", selection.metadata)
        self.assertIn("compiler_available", selection.metadata)

    def test_shiu_full_backend_fails_fast_with_zero_budget(self):
        backend = ShiuFullBackend(BrainWorkerConfig(max_startup_s=0.0))

        self.assertFalse(backend.available)
        self.assertTrue(backend.fallback_reason)


if __name__ == "__main__":
    unittest.main()
