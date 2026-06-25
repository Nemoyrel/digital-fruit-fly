import importlib.util
import unittest
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from digital_fruit_fly.brain.tickable_network import (
    ChannelConfig,
    ReadoutConfig,
    TickableBrainConfig,
    TickableBrainNetwork,
    UnknownSensoryChannelError,
    validate_sensory_channel_values,
)

BRIAN2_AVAILABLE = importlib.util.find_spec("brian2") is not None


class TestTickableBrainNetwork(unittest.TestCase):
    @unittest.skipUnless(BRIAN2_AVAILABLE, "requires brian2 in brain_env")
    def test_updates_fixture_channel_and_returns_readout_deltas(self) -> None:
        # Given: a tiny Brian2 fixture network with one controllable sensory channel.
        config = TickableBrainConfig(
            tick_ms=15.0,
            sensory_channels=(
                ChannelConfig(name="sugar_grn", target_indices=(0,), max_rate_hz=250.0),
            ),
            readout_groups=(
                ReadoutConfig(name="fixture_output", neuron_indices=(0,)),
            ),
        )
        network = TickableBrainNetwork.fixture(config)

        # When: the sugar channel is driven for one tick.
        result = network.tick({"sugar_grn": 1.0})

        # Then: the result reports only this tick's rates and spike deltas.
        self.assertEqual(result.tick_index, 1)
        self.assertAlmostEqual(result.duration_ms, 15.0)
        self.assertIn("fixture_output", result.spike_deltas)
        self.assertIn("fixture_output", result.rate_hz)
        self.assertGreater(result.spike_deltas["fixture_output"], 0)
        self.assertGreater(result.rate_hz["fixture_output"], 0.0)

    @unittest.skipUnless(BRIAN2_AVAILABLE, "requires brian2 in brain_env")
    def test_rejects_unknown_sensory_channel_before_running(self) -> None:
        # Given: a fixture network with a single configured input channel.
        config = TickableBrainConfig(
            tick_ms=15.0,
            sensory_channels=(
                ChannelConfig(name="sugar_grn", target_indices=(0,), max_rate_hz=250.0),
            ),
            readout_groups=(ReadoutConfig(name="fixture_output", neuron_indices=(0,)),),
        )
        network = TickableBrainNetwork.fixture(config)
        before_tick = network.tick_index

        # When / Then: an undeclared channel is refused before the Brian2 network advances.
        with self.assertRaises(UnknownSensoryChannelError) as raised:
            network.tick({"unknown_sense": 1.0})
        self.assertEqual(network.tick_index, before_tick)
        self.assertIn("unknown_sense", str(raised.exception))

    def test_rejects_unknown_sensory_channel_at_config_boundary(self) -> None:
        # Given: configured sensory inputs before any Brian2 runtime is constructed.
        config = TickableBrainConfig(
            tick_ms=15.0,
            sensory_channels=(
                ChannelConfig(name="sugar_grn", target_indices=(0,), max_rate_hz=250.0),
            ),
            readout_groups=(ReadoutConfig(name="fixture_output", neuron_indices=(0,)),),
        )

        # When / Then: validation rejects undeclared inputs at the config boundary.
        with self.assertRaises(UnknownSensoryChannelError):
            validate_sensory_channel_values(config, {"unknown_sense": 1.0})

    def test_importing_module_does_not_require_brian2(self) -> None:
        # Given / When / Then: importing dataclasses from the module succeeds at package import time.
        self.assertEqual(ChannelConfig(name="x", target_indices=(0,), max_rate_hz=1.0).name, "x")


if __name__ == "__main__":
    unittest.main()
