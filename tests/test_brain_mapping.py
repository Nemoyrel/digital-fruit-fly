import json
import tempfile
import unittest
from pathlib import Path

from digital_fruit_fly.brain.mapping import (
    MappingValidationError,
    load_brian_index_map,
    load_neural_mapping,
    require_configured_flywire_ids,
    validate_neural_mapping,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
MAPPING_PATH = REPO_ROOT / "configs/brain_mapping.yaml"
COMPLETENESS_PATH = (
    REPO_ROOT / "external/drosophila_brain_model/2023_03_23_completeness_630_final.csv"
)


class TestBrainMapping(unittest.TestCase):
    def test_validates_configured_mapping_against_shiu_completeness(self) -> None:
        # Given: the versioned mapping config and the Shiu completeness table.
        mapping = load_neural_mapping(MAPPING_PATH)
        brian_indices = load_brian_index_map(COMPLETENESS_PATH)

        # When: all configured FlyWire IDs are resolved to Brian indices.
        result = validate_neural_mapping(mapping, brian_indices)

        # Then: every configured channel is usable and reports resolved indices.
        self.assertTrue(result.ok, result.failure_summary())
        self.assertEqual(result.unusable_channels, ())
        self.assertGreaterEqual(len(result.channels), 8)
        self.assertIn("sugar_grn", result.channel_names)
        self.assertIn("forward", result.channel_names)
        for channel in result.channels:
            self.assertEqual(channel.brain_index_resolution_status, "resolved")
            self.assertEqual(channel.missing_flywire_ids, ())

    def test_validation_json_preserves_channel_metadata(self) -> None:
        # Given: a successful mapping validation result.
        mapping = load_neural_mapping(MAPPING_PATH)
        brian_indices = load_brian_index_map(COMPLETENESS_PATH)

        # When: the result is serialized for smoke artifacts.
        payload = validate_neural_mapping(mapping, brian_indices).to_json()

        # Then: every channel keeps the config metadata needed to audit provenance.
        required_fields = {
            "kind",
            "channel_name",
            "flywire_ids",
            "brian_indices",
            "missing_flywire_ids",
            "brain_index_resolution_status",
            "usable",
            "biologically_curated",
            "provisional",
            "source_status",
            "sign",
            "normalization",
            "rationale",
        }
        channels = payload["channels"]
        self.assertIsInstance(channels, list)
        for channel in channels:
            self.assertTrue(required_fields.issubset(channel.keys()), channel)

    def test_rejects_fake_flywire_id_with_channel_name_and_bad_id(self) -> None:
        # Given: a temp mapping fixture containing one impossible FlyWire ID.
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "mapping.json"
            data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
            bad_id = 999999999999999999
            data["sensory_channels"][0]["flywire_ids"] = [bad_id]
            fixture.write_text(json.dumps(data), encoding="utf-8")

            mapping = load_neural_mapping(fixture)
            brian_indices = load_brian_index_map(COMPLETENESS_PATH)

            # When: validation resolves the configured IDs.
            result = validate_neural_mapping(mapping, brian_indices)

        # Then: validation fails and names both the channel and bad ID.
        self.assertFalse(result.ok)
        summary = result.failure_summary()
        self.assertIn("sugar_grn", summary)
        self.assertIn(str(bad_id), summary)

    def test_rejects_flywire_ids_not_declared_in_mapping_config(self) -> None:
        # Given: a loaded mapping and an ID that is not declared in the file.
        mapping = load_neural_mapping(MAPPING_PATH)

        # When / Then: the boundary rejects the undeclared hard-coded ID.
        with self.assertRaises(MappingValidationError) as raised:
            require_configured_flywire_ids(mapping, (999999999999999999,))
        self.assertIn("999999999999999999", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
