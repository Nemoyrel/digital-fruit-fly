from pathlib import Path
import tempfile
import unittest

from digital_fruit_fly.runtime.config import ConfigError, load_config


CONFIG_PATHS = (
    Path("configs/eon_demo.yaml"),
    Path("configs/brain_smoke.yaml"),
    Path("configs/body_smoke.yaml"),
    Path("configs/bridge_smoke.yaml"),
)

BRAIN_PYTHON = "/opt/miniconda3/envs/brain_env/bin/python"
BODY_PYTHON = "/opt/miniconda3/envs/flygym_env/bin/python"
VALID_CONFIG = """\
tick_ms: 15
duration_sec: 1.0
seed: 1
arena:
  width_mm: 120.0
  height_mm: 80.0
  sugar:
    center_x_mm: 30.0
    center_y_mm: 20.0
    radius: 5.0
    cue_radius: 6.0
  dust:
    accumulation_rate_per_sec: 0.01
    threshold: 0.5
    cleaning_rate_per_sec: 0.2
process:
  host: 127.0.0.1
  brain_port: 50051
  body_port: 50052
camera:
  enabled: false
  fps: 30
  width_px: 1280
  height_px: 720
  follow_fly: true
brain:
  python: /opt/miniconda3/envs/brain_env/bin/python
  mapping_path: configs/brain_mapping.yaml
  shiu_repo_path: external/drosophila_brain_model
  completeness_path: external/drosophila_brain_model/Completeness_783.csv
  connectivity_path: external/drosophila_brain_model/Connectivity_783.parquet
body:
  python: /opt/miniconda3/envs/flygym_env/bin/python
decoder:
  locomotion_threshold: 0.2
  turn_threshold: 0.15
  feeding_threshold: 0.4
  grooming_threshold: 0.35
  stop_threshold: 0.6
"""


class TestConfig(unittest.TestCase):
    def test_all_default_configs_load_when_schema_is_valid(self) -> None:
        # Given: the repository ships four runtime config files.
        # When: each config is loaded through the runtime schema.
        loaded = [load_config(path) for path in CONFIG_PATHS]

        # Then: timing, food cue geometry, and env paths match the runtime contract.
        for config in loaded:
            self.assertEqual(config.tick_ms, 15)
            self.assertGreater(config.arena.sugar.cue_radius, config.arena.sugar.radius)
            self.assertEqual(config.brain.python, BRAIN_PYTHON)
            self.assertEqual(config.body.python, BODY_PYTHON)

    def test_loader_rejects_malformed_cue_radius_when_smaller_than_food(self) -> None:
        # Given: a config file with cue radius smaller than the food source radius.
        malformed = VALID_CONFIG.replace("cue_radius: 6.0", "cue_radius: 4.0")
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=True) as file:
            file.write(malformed)
            file.flush()

            # When / Then: loading rejects it with the typed config error.
            with self.assertRaises(ConfigError):
                load_config(Path(file.name))

    def test_loader_rejects_negative_dust_and_invalid_ports(self) -> None:
        # Given: malformed configs for dust rate and process port boundaries.
        cases = (
            VALID_CONFIG.replace(
                "accumulation_rate_per_sec: 0.01", "accumulation_rate_per_sec: -0.01"
            ),
            VALID_CONFIG.replace("brain_port: 50051", "brain_port: 70000"),
        )

        for malformed in cases:
            with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=True) as file:
                file.write(malformed)
                file.flush()

                # When / Then: each invalid config raises the typed loader error.
                with self.assertRaises(ConfigError):
                    load_config(Path(file.name))


if __name__ == "__main__":
    unittest.main()
