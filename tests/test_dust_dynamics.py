import json
import unittest

from digital_fruit_fly.arena.dust import (
    DustConfigError,
    DustDynamicsConfig,
    DustState,
    build_dust_config_from_runtime,
)
from digital_fruit_fly.runtime.config import DustConfig


class TestDustDynamics(unittest.TestCase):
    def test_accumulates_caps_and_emits_threshold_once_when_not_grooming(self) -> None:
        # Given: dust dynamics with a low threshold and bounded maximum load.
        config = DustDynamicsConfig(
            accumulation_rate_per_sec=0.25,
            threshold=0.5,
            cleaning_rate_per_sec=1.0,
            max_load=0.8,
        )
        state = DustState.clean()

        # When: the state advances through a dirty non-grooming cycle.
        first = state.advance(config=config, tick_seconds=1.0, grooming_active=False)
        second = first.state.advance(config=config, tick_seconds=1.0, grooming_active=False)
        third = second.state.advance(config=config, tick_seconds=3.0, grooming_active=False)

        # Then: load accumulates, caps at max, and threshold crossing is emitted once.
        self.assertEqual(first.state.dust_load, 0.25)
        self.assertEqual(second.state.dust_load, 0.5)
        self.assertEqual(third.state.dust_load, 0.8)
        self.assertEqual([event.name for event in first.events], [])
        self.assertEqual([event.name for event in second.events], ["dust_threshold_crossed"])
        self.assertEqual([event.name for event in third.events], [])

    def test_grooming_decreases_to_zero_emits_clean_and_restores_locomotion_sensory(self) -> None:
        # Given: a dirty state above the dust sensory threshold.
        config = DustDynamicsConfig(
            accumulation_rate_per_sec=0.25,
            threshold=0.5,
            cleaning_rate_per_sec=0.4,
            max_load=1.0,
        )
        dirty = DustState(dust_load=0.75, threshold_crossed=True)

        # When: grooming cleanup runs until the dust load reaches zero.
        partial = dirty.advance(config=config, tick_seconds=1.0, grooming_active=True)
        clean = partial.state.advance(config=config, tick_seconds=1.0, grooming_active=True)

        # Then: cleanup decreases load, emits clean once, and enables locomotion sensory again.
        self.assertAlmostEqual(partial.state.dust_load, 0.35)
        self.assertEqual([event.name for event in partial.events], [])
        self.assertEqual(clean.state, DustState.clean())
        self.assertEqual([event.name for event in clean.events], ["dust_clean"])
        self.assertTrue(clean.sensory.locomotion_sensory_enabled)
        self.assertFalse(clean.sensory.threshold_crossed)

    def test_events_serialize_as_stable_json_data(self) -> None:
        # Given: a threshold crossing event from a deterministic dust tick.
        config = DustDynamicsConfig(
            accumulation_rate_per_sec=0.6,
            threshold=0.5,
            cleaning_rate_per_sec=0.2,
            max_load=1.0,
        )

        # When: the event is serialized twice.
        result = DustState.clean().advance(config=config, tick_seconds=1.0, grooming_active=False)
        first = json.dumps(result.events[0].to_json_data(), sort_keys=True, separators=(",", ":"))
        second = json.dumps(result.events[0].to_json_data(), sort_keys=True, separators=(",", ":"))

        # Then: event data is stable and includes neutral sensory state, not action commands.
        self.assertEqual(first, second)
        self.assertEqual(
            first,
            '{"dust_load":0.6,"name":"dust_threshold_crossed","threshold":0.5}',
        )
        self.assertNotIn("groom_now", first)
        self.assertNotIn("feed_now", first)

    def test_rejects_malformed_dust_config(self) -> None:
        # Given / When / Then: malformed rates, threshold, max, and tick duration are rejected.
        with self.assertRaises(DustConfigError):
            DustDynamicsConfig(
                accumulation_rate_per_sec=-0.1,
                threshold=0.5,
                cleaning_rate_per_sec=0.4,
                max_load=1.0,
            )
        with self.assertRaises(DustConfigError):
            DustDynamicsConfig(
                accumulation_rate_per_sec=0.1,
                threshold=0.5,
                cleaning_rate_per_sec=-0.4,
                max_load=1.0,
            )
        with self.assertRaises(DustConfigError):
            DustDynamicsConfig(
                accumulation_rate_per_sec=0.1,
                threshold=1.5,
                cleaning_rate_per_sec=0.4,
                max_load=1.0,
            )
        with self.assertRaises(DustConfigError):
            DustState.clean().advance(
                config=DustDynamicsConfig(
                    accumulation_rate_per_sec=0.1,
                    threshold=0.5,
                    cleaning_rate_per_sec=0.4,
                    max_load=1.0,
                ),
                tick_seconds=-1.0,
                grooming_active=False,
            )

    def test_runtime_dust_config_maps_to_unit_max_load(self) -> None:
        # Given: the runtime config shape from Todo 2.
        runtime = DustConfig(
            accumulation_rate_per_sec=0.2,
            threshold=0.4,
            cleaning_rate_per_sec=0.5,
        )

        # When: it is parsed into arena dust dynamics.
        config = build_dust_config_from_runtime(runtime)

        # Then: rates are preserved and load is normalized to a unit maximum.
        self.assertEqual(config.accumulation_rate_per_sec, 0.2)
        self.assertEqual(config.threshold, 0.4)
        self.assertEqual(config.cleaning_rate_per_sec, 0.5)
        self.assertEqual(config.max_load, 1.0)


if __name__ == "__main__":
    unittest.main()
