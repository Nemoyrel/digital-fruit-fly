import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from digital_fruit_fly.brain.shiu_adapter import (
    ShiuDiscoveryError,
    discover_shiu_assets,
    extract_sugar_neuron_ids,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_CONFIG = (REPO_ROOT / "configs/brain_smoke.yaml").read_text(encoding="utf-8")


class TestShiuAdapter(unittest.TestCase):
    def test_discovers_630_when_783_is_missing_a_sugar_id(self) -> None:
        # Given: the real Shiu checkout and notebook sugar-neuron fixture.
        sugar_ids = extract_sugar_neuron_ids(
            REPO_ROOT / "external/drosophila_brain_model/example.ipynb"
        )

        # When: discovery is asked to consider the configured 783 data.
        assets = discover_shiu_assets(
            repo_path=REPO_ROOT / "external/drosophila_brain_model",
            completeness_path=REPO_ROOT
            / "external/drosophila_brain_model/Completeness_783.csv",
            connectivity_path=REPO_ROOT
            / "external/drosophila_brain_model/Connectivity_783.parquet",
            sugar_neuron_ids=sugar_ids,
        )

        # Then: it selects the sugar-complete 630 dataset and reports the 783 gap.
        self.assertEqual(assets.selected_version, "630")
        self.assertEqual(assets.selected.sugar_validation.missing_ids, ())
        self.assertIn(
            720575940620900446,
            assets.available_versions["783"].sugar_validation.missing_ids,
        )

    def test_rejects_missing_configured_completeness_before_fallback(self) -> None:
        # Given: a configured completeness path that does not exist.
        missing_path = REPO_ROOT / "external/drosophila_brain_model/missing.csv"

        # When / Then: discovery fails before selecting another dataset.
        with self.assertRaises(ShiuDiscoveryError) as raised:
            discover_shiu_assets(
                repo_path=REPO_ROOT / "external/drosophila_brain_model",
                completeness_path=missing_path,
                connectivity_path=REPO_ROOT
                / "external/drosophila_brain_model/Connectivity_783.parquet",
                sugar_neuron_ids=(720575940624963786,),
            )
        self.assertIn("completeness", str(raised.exception))
        self.assertIn("missing.csv", str(raised.exception))

    def test_smoke_rejects_invalid_completeness_with_json_error(self) -> None:
        # Given: a valid runtime config except for the Shiu completeness path.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config_path = tmp_path / "brain_smoke_invalid.yaml"
            output_path = tmp_path / "out"
            config_path.write_text(
                BASE_CONFIG.replace(
                    "external/drosophila_brain_model/Completeness_783.csv",
                    "external/drosophila_brain_model/does-not-exist.csv",
                ),
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["PYTHONPATH"] = str(REPO_ROOT / "src")

            # When: the smoke script runs against the malformed config.
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts/smoke_brain.py"),
                    "--config",
                    str(config_path),
                    "--output",
                    str(output_path),
                ],
                cwd=REPO_ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

        # Then: it exits nonzero with a clear JSON failure before Shiu simulation.
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does-not-exist.csv", result.stderr)
        self.assertIn('"status": "failed"', result.stderr)


if __name__ == "__main__":
    unittest.main()
