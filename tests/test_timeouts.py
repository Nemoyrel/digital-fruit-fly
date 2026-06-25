from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from digital_fruit_fly.runtime.timeouts import TimeoutConfigError, run_subprocess


class TestTimeouts(unittest.TestCase):
    def test_run_subprocess_terminates_sleeping_child_when_timeout_expires(self) -> None:
        # Given: a Python child process that sleeps longer than the allowed timeout.
        with tempfile.TemporaryDirectory() as tmp_dir:
            evidence_path = Path(tmp_dir) / "timeout.json"
            command = (
                sys.executable,
                "-c",
                "import time; print('started', flush=True); time.sleep(30)",
            )

            # When: the child is launched through the common timeout wrapper.
            result = run_subprocess(command, timeout_sec=0.2, evidence_path=evidence_path)

            # Then: it is terminated and the JSON evidence records the timeout.
            self.assertTrue(result.timed_out)
            self.assertIsNotNone(result.returncode)
            self.assertLess(result.duration_sec, 5.0)
            self.assertIn("started", result.stdout)
            recorded = json.loads(evidence_path.read_text(encoding="utf-8"))
            self.assertTrue(recorded["timed_out"])
            self.assertEqual(recorded["command"], list(command))

    def test_smoke_fixture_records_timeout_when_child_runs_too_long(self) -> None:
        # Given: a smoke probe command that intentionally outlives its timeout.
        with tempfile.TemporaryDirectory() as tmp_dir:
            evidence_path = Path(tmp_dir) / "fixture_timeout.json"
            command = (
                sys.executable,
                "-c",
                "import time; print('fixture-start', flush=True); time.sleep(30)",
            )

            # When: the probe is guarded by the common timeout wrapper.
            result = run_subprocess(command, timeout_sec=0.1, evidence_path=evidence_path)

            # Then: callers receive a non-zero outcome and a structured failure record.
            self.assertTrue(result.timed_out)
            self.assertNotEqual(result.exit_code, 0)
            recorded = json.loads(evidence_path.read_text(encoding="utf-8"))
            self.assertEqual(recorded["status"], "timeout")
            self.assertNotEqual(recorded["exit_code"], 0)

    def test_run_subprocess_rejects_empty_command_with_typed_error(self) -> None:
        # Given: an invalid subprocess request with no executable.
        command: tuple[str, ...] = ()

        # When: the timeout wrapper parses the request boundary.
        with self.assertRaises(TimeoutConfigError) as raised:
            run_subprocess(command, timeout_sec=1.0)

        # Then: callers can inspect the typed field and reason.
        self.assertEqual(raised.exception.field, "command")
        self.assertEqual(raised.exception.reason, "must not be empty")
        self.assertIsNone(raised.exception.value_text)

    def test_run_subprocess_rejects_nonpositive_timeout_with_typed_error(self) -> None:
        # Given: an invalid timeout value.
        timeout_sec = 0.0

        # When: the timeout wrapper parses the request boundary.
        with self.assertRaises(TimeoutConfigError) as raised:
            run_subprocess((sys.executable, "-c", "print('ok')"), timeout_sec=timeout_sec)

        # Then: callers can inspect the offending field and value text.
        self.assertEqual(raised.exception.field, "timeout_sec")
        self.assertEqual(raised.exception.reason, "must be positive")
        self.assertEqual(raised.exception.value_text, "0.0")


if __name__ == "__main__":
    unittest.main()
