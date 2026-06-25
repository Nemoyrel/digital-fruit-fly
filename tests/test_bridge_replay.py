from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestBridgeReplay(unittest.TestCase):
    def test_current_smoke_bridge_writes_three_protocol_frames_per_tick(self) -> None:
        # Given: the existing fixture smoke CLI and a temporary output directory.
        with tempfile.TemporaryDirectory() as raw_tmp:
            output = Path(raw_tmp) / "bridge"

            # When: the smoke runs for two ticks.
            result = _run(
                "scripts/smoke_bridge.py",
                "--config",
                "configs/bridge_smoke.yaml",
                "--ticks",
                "2",
                "--output",
                str(output),
            )

            # Then: it exits successfully and writes sensory/brain/control frames for each tick.
            self.assertEqual(result.returncode, 0, result.stderr)
            frames = _read_jsonl(output / "frames.jsonl")
            self.assertEqual([frame["type"] for frame in frames], _expected_types(2))
            self.assertEqual([frame["frame_index"] for frame in frames], [0, 0, 0, 1, 1, 1])

    def test_replay_verify_accepts_integrated_fixture_smoke_output(self) -> None:
        # Given: an integrated fixture bridge smoke output.
        with tempfile.TemporaryDirectory() as raw_tmp:
            output = Path(raw_tmp) / "bridge"
            smoke = _run(
                "scripts/smoke_bridge.py",
                "--config",
                "configs/bridge_smoke.yaml",
                "--ticks",
                "12",
                "--output",
                str(output),
            )
            self.assertEqual(smoke.returncode, 0, smoke.stderr)

            # When: replay verification is run on the artifact directory.
            replay = _run("scripts/replay_run.py", "--input", str(output), "--verify")

            # Then: replay accepts the run and records deterministic verification evidence.
            self.assertEqual(replay.returncode, 0, replay.stderr)
            evidence = json.loads((output / "replay_evidence.json").read_text(encoding="utf-8"))
            self.assertEqual(evidence["status"], "ok")
            self.assertEqual(evidence["verified_ticks"], 12)
            self.assertEqual(evidence["verified_events"], 36)
            self.assertEqual(evidence["deterministic_controls"], True)

    def test_replay_verify_rejects_missing_jsonl_frame_with_evidence(self) -> None:
        # Given: a valid smoke output copied to a corrupt replay directory.
        with tempfile.TemporaryDirectory() as raw_tmp:
            root = Path(raw_tmp)
            output = root / "bridge"
            corrupt = root / "bridge_corrupt"
            smoke = _run(
                "scripts/smoke_bridge.py",
                "--config",
                "configs/bridge_smoke.yaml",
                "--ticks",
                "8",
                "--output",
                str(output),
            )
            self.assertEqual(smoke.returncode, 0, smoke.stderr)
            shutil.copytree(output, corrupt)
            frames_path = corrupt / "frames.jsonl"
            lines = frames_path.read_text(encoding="utf-8").splitlines()
            frames_path.write_text("\n".join(lines[:7] + lines[8:]) + "\n", encoding="utf-8")

            # When: replay verification is run on the corrupted artifact.
            replay = _run("scripts/replay_run.py", "--input", str(corrupt), "--verify")

            # Then: it exits nonzero and names the missing frame/event in evidence.
            self.assertNotEqual(replay.returncode, 0)
            evidence = json.loads((corrupt / "replay_evidence.json").read_text(encoding="utf-8"))
            self.assertEqual(evidence["status"], "failed")
            self.assertEqual(evidence["error_code"], "missing_or_reordered_frame")
            self.assertEqual(evidence["failure"]["expected_type"], "brain_frame")
            self.assertEqual(evidence["failure"]["expected_frame_index"], 2)


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
        timeout=15.0,
        check=False,
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _expected_types(ticks: int) -> list[str]:
    return ["sensory_frame", "brain_frame", "control_frame"] * ticks


if __name__ == "__main__":
    unittest.main()
