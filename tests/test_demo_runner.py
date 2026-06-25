from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from digital_fruit_fly.demo import process_run
from digital_fruit_fly.demo.process_children import ChildRecord, RunningChild, terminate_if_alive
from digital_fruit_fly.demo.process_run import SeparateProcessRequest
from digital_fruit_fly.runtime.timeouts import JsonObject


REPO_ROOT = Path(__file__).resolve().parents[1]


class TestDemoRunner(unittest.TestCase):
    def test_default_demo_is_honest_about_real_subprocess_acceptance(self) -> None:
        # Given: the final demo CLI is invoked the same way as the acceptance command.
        with tempfile.TemporaryDirectory() as raw_tmp:
            output = Path(raw_tmp) / "demo"

            # When: the caller does not opt into the fixture-only demo mode.
            result = _run(
                "scripts/run_demo.py",
                "--config",
                "configs/eon_demo.yaml",
                "--output",
                str(output),
                "--duration-sec",
                "10",
                "--seed",
                "1",
                "--timeout-sec",
                "30",
                "--video-frame-cap",
                "2",
                "--brain-frame-cap",
                "4",
                "--evidence",
                str(output / "task-23-evidence.json"),
            )

            # Then: acceptance is either a real subprocess success or a documented P0 blocker.
            if result.returncode == 0:
                summary = _read_json(output / "summary.json")
                self.assertEqual(summary["status"], "ok")
                self.assertEqual(summary["mode"], "separate_processes")
                self.assertNotEqual(summary["subprocesses"]["brain"]["status"], "not_started_fixture_mode")
                self.assertNotEqual(summary["subprocesses"]["body"]["status"], "not_started_fixture_mode")
                _assert_brain_command_mode(self, summary, "brian2")
            else:
                manifest = _read_json(output / "failure_manifest.json")
                self.assertEqual(manifest["status"], "failed")
                self.assertTrue(str(manifest["error_code"]).startswith("p0_"))
                self.assertEqual(manifest["mode"], "separate_processes")
                self.assertIn("subprocesses", manifest)
                _assert_brain_command_mode(self, manifest, "brian2")
                brain = _brain_subprocess(manifest)
                if (
                    manifest["error_code"] != "p0_brain_not_ready"
                    and brain.get("returncode") not in (0, None)
                    and brain.get("cleanup") in ("exited", "already_exited")
                ):
                    self.assertEqual(manifest["error_code"], "p0_brain_process_failed")
                self.assertFalse((output / "summary.json").is_file())

    def test_demo_writes_summary_artifacts_when_fixture_mode_runs(self) -> None:
        # Given: a stale output directory and the final demo CLI.
        with tempfile.TemporaryDirectory() as raw_tmp:
            output = Path(raw_tmp) / "demo"
            video_dir = output / "video"
            video_dir.mkdir(parents=True)
            stale = video_dir / "fly_demo.mp4"
            stale.write_bytes(b"stale")

            # When: the fixture demo runs long enough to hit all behavior events.
            result = _run(
                "scripts/run_demo.py",
                "--config",
                "configs/eon_demo.yaml",
                "--output",
                str(output),
                "--duration-sec",
                "10",
                "--seed",
                "1",
                "--process-mode",
                "fixture_demo",
                "--video-frame-cap",
                "2",
                "--brain-frame-cap",
                "4",
                "--video-width-px",
                "64",
                "--video-height-px",
                "36",
                "--evidence",
                str(output / "task-23-evidence.json"),
            )

            # Then: it exits successfully and writes replay-verifiable artifacts.
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = _read_json(output / "summary.json")
            self.assertEqual(summary["status"], "ok")
            self.assertEqual(summary["mode"], "fixture_demo")
            self.assertEqual(summary["duration_sec"], 10.0)
            self.assertEqual(summary["seed"], 1)
            self.assertTrue((output / "frames.jsonl").is_file())
            self.assertTrue((output / "replay_evidence.json").is_file())
            self.assertTrue((output / "behavior_summary.json").is_file())
            self.assertGreater(Path(summary["body_recording"]["artifact_path"]).stat().st_size, 0)
            self.assertGreater(Path(summary["brain_activity"]["artifact_path"]).stat().st_size, 0)
            self.assertNotEqual(stale.read_bytes(), b"stale")
            self.assertEqual(summary["subprocesses"]["brain"]["status"], "not_started_fixture_mode")

    def test_failure_qa_writes_manifest_and_terminates_body_when_brain_is_killed(self) -> None:
        # Given: the failure QA mode starts real child processes.
        with tempfile.TemporaryDirectory() as raw_tmp:
            output = Path(raw_tmp) / "killed_brain"

            # When: the brain child is intentionally killed.
            result = _run(
                "scripts/run_demo.py",
                "--config",
                "configs/eon_demo.yaml",
                "--output",
                str(output),
                "--duration-sec",
                "1",
                "--seed",
                "1",
                "--process-mode",
                "failure_qa_kill_brain",
                "--failure-qa-delay-sec",
                "0.2",
                "--timeout-sec",
                "5",
                "--evidence",
                str(output / "task-23-evidence.json"),
            )

            # Then: failure is explicit and the body child is terminated.
            self.assertNotEqual(result.returncode, 0)
            manifest = _read_json(output / "failure_manifest.json")
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["error_code"], "brain_subprocess_killed")
            self.assertEqual(manifest["subprocesses"]["brain"]["cleanup"], "killed")
            self.assertIn(manifest["subprocesses"]["body"]["cleanup"], ("terminated", "already_exited"))
            self.assertEqual(manifest["children_alive_after_cleanup"], [])

    def test_default_failure_reports_brain_process_failed_when_ready_brian2_child_exits_nonzero(self) -> None:
        # Given: the default separate-process path has a Brian2 brain child that becomes ready and then exits nonzero.
        with tempfile.TemporaryDirectory() as raw_tmp:
            output = Path(raw_tmp) / "demo"
            command = _brain_command(output)
            process = subprocess.Popen(
                (sys.executable, "-c", "import time; time.sleep(30)"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            running = RunningChild("brain", command, process, "")
            brain_record = ChildRecord("brain", command, process.pid, 1, "", "brian2 traceback", "failed", "exited")
            body_record = ChildRecord("body", ("body",), None, 1, "", "body lost connection", "failed", "completed")

            # When: both body and brain are failed in the final manifest.
            try:
                with (
                    mock.patch.object(process_run, "_start_brain", return_value=running),
                    mock.patch.object(process_run, "wait_for_json_status", return_value={"status": "ready"}),
                    mock.patch.object(process_run, "_run_body", return_value=body_record),
                    mock.patch.object(process_run, "wait_for_child", return_value=brain_record),
                    mock.patch("sys.stderr", new_callable=io.StringIO),
                ):
                    result = process_run.run_separate_process_demo(
                        SeparateProcessRequest(
                            config_path=Path("configs/eon_demo.yaml"),
                            output_dir=output,
                            evidence_path=output / "task-23-evidence.json",
                            duration_sec=10.0,
                            seed=1,
                            timeout_sec=30.0,
                            record_codec="libx264",
                        )
                    )
            finally:
                terminate_if_alive(process, 1.0)
                process.communicate(timeout=1.0)

            # Then: the blocker names the failed Brian2 brain process, not the secondary body failure.
            self.assertEqual(result, 1)
            manifest = _read_json(output / "failure_manifest.json")
            self.assertEqual(manifest["error_code"], "p0_brain_process_failed")
            _assert_brain_command_mode(self, manifest, "brian2")


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


def _brain_command(output: Path) -> tuple[str, ...]:
    return (
        "/opt/miniconda3/envs/brain_env/bin/python",
        "scripts/run_brain.py",
        "--config",
        "configs/eon_demo.yaml",
        "--mode",
        "brian2",
        "--max-ticks",
        "666",
        "--output",
        str(output),
        "--timeout-sec",
        "30.0",
    )


def _assert_brain_command_mode(test_case: unittest.TestCase, payload: JsonObject, expected_mode: str) -> None:
    brain = _brain_subprocess(payload)
    command = brain.get("command")
    if not isinstance(command, list):
        raise AssertionError("brain subprocess command is not a list")
    test_case.assertIn("--mode", command)
    mode_index = command.index("--mode")
    test_case.assertLess(mode_index + 1, len(command), command)
    test_case.assertEqual(command[mode_index + 1], expected_mode, command)


def _brain_subprocess(payload: JsonObject) -> JsonObject:
    subprocesses = payload.get("subprocesses")
    if not isinstance(subprocesses, dict):
        raise AssertionError("manifest/summary subprocesses field is not an object")
    brain = subprocesses.get("brain")
    if not isinstance(brain, dict):
        raise AssertionError("brain subprocess field is not an object")
    return brain


def _read_json(path: Path) -> JsonObject:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"{path} did not contain a JSON object")
    return payload


if __name__ == "__main__":
    unittest.main()
