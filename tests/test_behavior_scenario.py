from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ORDERED_EVENTS = [
    "search_started",
    "sugar_cue_acquired",
    "food_contact",
    "feeding_started",
    "proboscis_extended",
    "dust_threshold_crossed",
    "grooming_started",
    "face_grooming_sweep_detected",
    "dust_clean",
    "locomotion_resumed",
]


class TestBehaviorScenario(unittest.TestCase):
    def test_eon_behavior_verifier_accepts_ordered_scenario(self) -> None:
        # Given: a deterministic Eon-style fixture smoke run.
        with tempfile.TemporaryDirectory() as raw_tmp:
            output = Path(raw_tmp) / "bridge"
            smoke = _run(
                "scripts/smoke_bridge.py",
                "--config",
                "configs/eon_demo.yaml",
                "--ticks",
                "720",
                "--output",
                str(output),
            )
            self.assertEqual(smoke.returncode, 0, smoke.stderr)

            # When: replay behavior verification is run against the same config.
            replay = _run("scripts/replay_run.py", "--input", str(output), "--verify-behavior", "configs/eon_demo.yaml")

            # Then: the summary records the ordered scenario and brain-frame links.
            self.assertEqual(replay.returncode, 0, replay.stderr)
            summary = _read_json(output / "behavior_summary.json")
            self.assertEqual([event["name"] for event in summary["ordered_events"]], ORDERED_EVENTS)
            for event in summary["ordered_events"]:
                self.assertIsInstance(event["brain_frame_id"], str)
                self.assertIsInstance(event["control_frame_id"], str)
            self.assertIn("proboscis_angular_error_rad", summary["metrics"])
            self.assertIn("grooming_sweep_amplitude", summary["metrics"])

    def test_behavior_verifier_reports_missing_grooming_when_dust_threshold_is_impossible(self) -> None:
        # Given: a fixture smoke run generated from a config whose dust threshold cannot be reached.
        with tempfile.TemporaryDirectory() as raw_tmp:
            root = Path(raw_tmp)
            config = _config_with(root / "impossible.yaml", {"threshold": "5000.0"})
            output = root / "bridge"
            smoke = _run("scripts/smoke_bridge.py", "--config", str(config), "--ticks", "720", "--output", str(output))
            self.assertEqual(smoke.returncode, 0, smoke.stderr)

            # When: behavior verification is run.
            replay = _run("scripts/replay_run.py", "--input", str(output), "--verify-behavior", str(config))

            # Then: it fails with missing dust/grooming sequence evidence instead of passing stale output.
            self.assertNotEqual(replay.returncode, 0)
            evidence = _read_json(output / "replay_evidence.json")
            self.assertEqual(evidence["status"], "failed")
            self.assertEqual(evidence["error_code"], "missing_behavior_event")
            self.assertIn(evidence["failure"]["missing_event"], ["dust_threshold_crossed", "grooming_started"])

    def test_proboscis_direction_metric_changes_sign_for_left_and_right_food_bearing(self) -> None:
        # Given: two mirrored deterministic fixture configs with left and right food bearings.
        with tempfile.TemporaryDirectory() as raw_tmp:
            root = Path(raw_tmp)
            left_config = _config_with(root / "left.yaml", {"center_x_mm": "26.0", "center_y_mm": "52.0", "cue_radius": "18.0"})
            right_config = _config_with(root / "right.yaml", {"center_x_mm": "26.0", "center_y_mm": "28.0", "cue_radius": "18.0"})

            # When: both runs are verified behaviorally.
            left_metric = _verified_proboscis_target(root / "left", left_config)
            right_metric = _verified_proboscis_target(root / "right", right_config)

            # Then: the signed proboscis target follows the side of the food bearing.
            self.assertGreater(left_metric, 0.0)
            self.assertLess(right_metric, 0.0)


def _verified_proboscis_target(output: Path, config: Path) -> float:
    smoke = _run("scripts/smoke_bridge.py", "--config", str(config), "--ticks", "720", "--output", str(output))
    if smoke.returncode != 0:
        raise AssertionError(smoke.stderr)
    replay = _run("scripts/replay_run.py", "--input", str(output), "--verify-behavior", str(config))
    if replay.returncode != 0:
        raise AssertionError(replay.stderr)
    summary = _read_json(output / "behavior_summary.json")
    metric = summary["metrics"]["proboscis_target_bearing_rad"]
    if not isinstance(metric, (int, float)):
        raise AssertionError("proboscis_target_bearing_rad must be numeric")
    return float(metric)


def _config_with(path: Path, replacements: dict[str, str]) -> Path:
    text = (REPO_ROOT / "configs/eon_demo.yaml").read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = _replace_yaml_scalar(text, key, value)
    path.write_text(text, encoding="utf-8")
    return path


def _replace_yaml_scalar(text: str, key: str, value: str) -> str:
    lines = []
    replaced = False
    for line in text.splitlines():
        stripped = line.lstrip(" ")
        if stripped.startswith(f"{key}: ") and not replaced:
            indent = line[: len(line) - len(stripped)]
            lines.append(f"{indent}{key}: {value}")
            replaced = True
        else:
            lines.append(line)
    if not replaced:
        raise AssertionError(f"missing config key {key}")
    return "\n".join(lines) + "\n"


def _run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = "src"
    return subprocess.run(
        (sys.executable, script, *args),
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30.0,
        check=False,
    )


def _read_json(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise AssertionError(f"{path} must contain a JSON object")
    return raw


if __name__ == "__main__":
    unittest.main()
