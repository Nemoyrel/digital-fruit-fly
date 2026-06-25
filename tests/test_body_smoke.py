from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE_BODY = REPO_ROOT / "scripts" / "smoke_body.py"
CONFIG = REPO_ROOT / "configs" / "body_smoke.yaml"


class TestBodySmoke(unittest.TestCase):
    def test_smoke_body_records_error_json_when_fixture_child_times_out(self) -> None:
        # Given: a fixture child that outlives the smoke timeout.
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "body"
            evidence_path = Path(tmp_dir) / "evidence.json"
            command = (
                sys.executable,
                str(SMOKE_BODY),
                "--config",
                str(CONFIG),
                "--output",
                str(output_dir),
                "--evidence",
                str(evidence_path),
                "--fixture-sleep-sec",
                "30",
                "--timeout-sec",
                "0.1",
            )

            # When: the smoke command runs under the fixture-only path.
            result = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=_clean_env_without_pythonpath(),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            # Then: it exits nonzero and records a body_env_error.json timeout.
            self.assertNotEqual(result.returncode, 0)
            error_path = output_dir / "body_env_error.json"
            self.assertTrue(error_path.exists(), result.stdout + result.stderr)
            recorded = json.loads(error_path.read_text(encoding="utf-8"))
            self.assertEqual(recorded["status"], "timeout")
            self.assertTrue(recorded["timed_out"])
            self.assertEqual(recorded["probe_stage"], "fixture")

    def test_smoke_body_ignores_stale_child_payload_when_current_child_times_out(self) -> None:
        # Given: a stale child success artifact in the output directory.
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "body"
            output_dir.mkdir()
            stale_child = output_dir / "child_probe.json"
            stale_child.write_text(
                json.dumps(
                    {
                        "status": "ok",
                        "probe_stage": "complete",
                        "error": "stale success should not be trusted",
                    }
                ),
                encoding="utf-8",
            )

            # When: the current child times out before writing a new payload.
            result = subprocess.run(
                (
                    sys.executable,
                    str(SMOKE_BODY),
                    "--config",
                    str(CONFIG),
                    "--output",
                    str(output_dir),
                    "--fixture-sleep-sec",
                    "30",
                    "--timeout-sec",
                    "0.1",
                ),
                cwd=REPO_ROOT,
                env=_clean_env_without_pythonpath(),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            # Then: failure evidence describes the current timeout, not stale success.
            self.assertNotEqual(result.returncode, 0)
            recorded = json.loads(
                (output_dir / "body_env_error.json").read_text(encoding="utf-8")
            )
            self.assertEqual(recorded["status"], "timeout")
            self.assertEqual(recorded["probe_stage"], "fixture")
            self.assertNotEqual(recorded["probe_stage"], "complete")
            self.assertNotEqual(recorded["error"], "stale success should not be trusted")

    def test_smoke_body_rejects_invalid_renderer_without_starting_probe(self) -> None:
        # Given: an unsupported renderer name.
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "body"
            command = (
                sys.executable,
                str(SMOKE_BODY),
                "--config",
                str(CONFIG),
                "--output",
                str(output_dir),
                "--renderer",
                "invalid-renderer",
            )

            # When: the smoke command parses the request boundary.
            result = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=_clean_env_without_pythonpath(),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            # Then: it exits with a usage error and writes structured evidence.
            self.assertEqual(result.returncode, 2)
            recorded = json.loads(
                (output_dir / "body_env_error.json").read_text(encoding="utf-8")
            )
            self.assertEqual(recorded["status"], "failed")
            self.assertIn("renderer", recorded["error"])

    def test_child_probe_sets_glfw_null_platform_before_flygym_import(self) -> None:
        # Given: a headless child probe running without a renderer.
        from digital_fruit_fly.body import flygym_probe

        events: list[str] = []

        class FakeGlfw:
            PLATFORM = 1
            PLATFORM_NULL = 2

            def init_hint(self, platform_value: int, target_value: int) -> None:
                events.append(f"glfw.init_hint:{platform_value}:{target_value}")

        def import_module(name: str) -> SimpleNamespace | FakeGlfw:
            if name == "glfw":
                return FakeGlfw()
            if name == "flygym":
                self.assertEqual(events, ["glfw.init_hint:1:2"])
                return SimpleNamespace(__name__="flygym")
            if name == "mujoco":
                return SimpleNamespace(__name__="mujoco")
            raise AssertionError(f"unexpected import: {name}")

        request = flygym_probe.ChildProbeRequest(
            output_path=Path("unused.json"),
            steps=1,
            headless=True,
            renderer="none",
            api_report=False,
            fixture_sleep_sec=0.0,
        )

        # When: the real probe enters its import path.
        with (
            patch.object(flygym_probe.importlib, "import_module", side_effect=import_module),
            patch.object(flygym_probe, "_run_mujoco_step_probe", return_value={"status": "ok"}),
            patch.object(flygym_probe, "_run_renderer_probe", return_value={"status": "skipped"}),
            patch.object(flygym_probe, "_run_viewer_probe", return_value={"status": "available_headless_skipped"}),
        ):
            payload = flygym_probe._run_real_probe(request, started=0.0)

        # Then: the payload records the headless GLFW platform hint.
        self.assertEqual(payload["glfw"], {"platform_hint": "null", "reason": "headless"})

    def test_child_probe_skips_auto_renderer_when_headless(self) -> None:
        # Given: a headless child probe using the default renderer.
        from digital_fruit_fly.body import flygym_probe

        renderer_values: list[str] = []

        class FakeGlfw:
            PLATFORM = 1
            PLATFORM_NULL = 2

            def init_hint(self, platform_value: int, target_value: int) -> None:
                return None

        def import_module(name: str) -> SimpleNamespace | FakeGlfw:
            if name == "glfw":
                return FakeGlfw()
            if name == "flygym":
                return SimpleNamespace(__name__="flygym")
            if name == "mujoco":
                return SimpleNamespace(__name__="mujoco")
            raise AssertionError(f"unexpected import: {name}")

        def renderer_probe(mujoco_module: SimpleNamespace, renderer: str) -> dict[str, str]:
            renderer_values.append(renderer)
            return {"status": "skipped", "renderer": renderer}

        request = flygym_probe.ChildProbeRequest(
            output_path=Path("unused.json"),
            steps=1,
            headless=True,
            renderer="auto",
            api_report=False,
            fixture_sleep_sec=0.0,
        )

        # When: the real probe reaches renderer selection.
        with (
            patch.object(flygym_probe.importlib, "import_module", side_effect=import_module),
            patch.object(flygym_probe, "_run_mujoco_step_probe", return_value={"status": "ok"}),
            patch.object(flygym_probe, "_run_renderer_probe", side_effect=renderer_probe),
            patch.object(flygym_probe, "_run_viewer_probe", return_value={"status": "available_headless_skipped"}),
        ):
            payload = flygym_probe._run_real_probe(request, started=0.0)

        # Then: auto rendering is skipped in headless mode.
        self.assertEqual(renderer_values, ["none"])
        self.assertEqual(payload["renderer"], {"status": "skipped", "renderer": "none"})

    def test_child_probe_requests_glfw_null_before_flygym_import_for_api_report(self) -> None:
        # Given: an API-report child probe using the default non-headless renderer.
        from digital_fruit_fly.body import flygym_probe

        events: list[str] = []
        renderer_values: list[str] = []

        class FakeGlfw:
            PLATFORM = 1
            PLATFORM_NULL = 2

            def init_hint(self, platform_value: int, target_value: int) -> None:
                events.append(f"glfw.init_hint:{platform_value}:{target_value}")

        def import_module(name: str) -> SimpleNamespace | FakeGlfw:
            if name == "glfw":
                return FakeGlfw()
            if name == "flygym":
                self.assertEqual(events, ["glfw.init_hint:1:2"])
                return SimpleNamespace(__name__="flygym")
            if name == "mujoco":
                return SimpleNamespace(__name__="mujoco")
            raise AssertionError(f"unexpected import: {name}")

        def renderer_probe(mujoco_module: SimpleNamespace, renderer: str) -> dict[str, str]:
            renderer_values.append(renderer)
            return {"status": "skipped", "renderer": renderer}

        request = flygym_probe.ChildProbeRequest(
            output_path=Path("unused.json"),
            steps=1,
            headless=False,
            renderer="auto",
            api_report=True,
            fixture_sleep_sec=0.0,
        )

        # When: the API report runs without an explicit renderer request.
        with (
            patch.object(flygym_probe.importlib, "import_module", side_effect=import_module),
            patch.object(flygym_probe, "_run_mujoco_step_probe", return_value={"status": "ok"}),
            patch.object(flygym_probe, "_run_renderer_probe", side_effect=renderer_probe),
            patch.object(flygym_probe, "_run_viewer_probe", return_value={"status": "available_not_launched"}),
            patch.object(flygym_probe, "build_installed_api_report", return_value={"schema_version": 1}),
            patch.object(flygym_probe, "write_api_artifacts", return_value=SimpleNamespace(json_path=Path("api.json"), markdown_path=Path("doc.md"))),
        ):
            payload = flygym_probe._run_real_probe(request, started=0.0)

        # Then: the report path avoids the windowed GLFW path before importing FlyGym.
        self.assertEqual(renderer_values, ["none"])
        self.assertEqual(payload["renderer"], {"status": "skipped", "renderer": "none"})
        self.assertEqual(payload["glfw"], {"platform_hint": "null", "reason": "renderer_none"})


def _clean_env_without_pythonpath() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    return env


if __name__ == "__main__":
    unittest.main()
