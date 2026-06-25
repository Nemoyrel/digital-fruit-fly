import json
import tempfile
import unittest
from pathlib import Path

from digital_fruit_fly.runtime.logging import append_jsonl, read_jsonl
from digital_fruit_fly.runtime.run_manifest import (
    OutputRootError,
    create_run_layout,
)


class TestRunManifest(unittest.TestCase):
    def test_run_layout_exists_when_created_under_temp_outputs(self) -> None:
        # Given: a temporary outputs/runs path for an isolated run.
        with tempfile.TemporaryDirectory() as temp_root:
            run_id = "unit_run"
            run_dir = Path(temp_root) / "outputs" / "runs" / run_id

            # When: the run layout is created.
            layout = create_run_layout(run_dir, run_id)

            # Then: the required manifest, logs, and subdirectories exist.
            self.assertEqual(layout.run_id, run_id)
            self.assertTrue(layout.manifest_path.is_file())
            self.assertTrue(layout.events_path.is_file())
            self.assertTrue(layout.control_path.is_file())
            self.assertTrue(layout.arena_path.is_file())
            self.assertTrue(layout.brain_dir.is_dir())
            self.assertTrue(layout.video_dir.is_dir())
            self.assertTrue(layout.logs_dir.is_dir())

    def test_manifest_contains_expected_keys_when_written(self) -> None:
        # Given: a run layout created in a temporary outputs tree.
        with tempfile.TemporaryDirectory() as temp_root:
            run_id = "manifest_keys"
            run_dir = Path(temp_root) / "outputs" / "runs" / run_id

            # When: the manifest is read from disk.
            layout = create_run_layout(run_dir, run_id)
            with layout.manifest_path.open("r", encoding="utf-8") as handle:
                manifest = json.load(handle)

            # Then: the manifest exposes stable identity and path metadata.
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["run_id"], run_id)
            self.assertIn("created_at_utc", manifest)
            self.assertEqual(manifest["run_dir"], str(layout.run_dir))
            self.assertEqual(
                set(manifest["jsonl_files"]),
                {"events", "control", "arena"},
            )
            self.assertEqual(
                set(manifest["directories"]),
                {"brain", "video", "logs"},
            )

    def test_jsonl_round_trips_when_appended(self) -> None:
        # Given: an events log in a temporary run layout.
        with tempfile.TemporaryDirectory() as temp_root:
            run_id = "jsonl_round_trip"
            run_dir = Path(temp_root) / "outputs" / "runs" / run_id
            layout = create_run_layout(run_dir, run_id)

            # When: JSONL records are appended.
            append_jsonl(layout.events_path, {"kind": "run_started", "frame": 0})
            append_jsonl(layout.events_path, {"kind": "tick", "frame": 1})

            # Then: the records are readable from disk in append order.
            self.assertEqual(
                read_jsonl(layout.events_path),
                [
                    {"kind": "run_started", "frame": 0},
                    {"kind": "tick", "frame": 1},
                ],
            )

    def test_reports_root_is_rejected_when_creating_run_layout(self) -> None:
        # Given: a forbidden reports path.
        reports_run = Path("reports") / "runs" / "bad_run"

        # When / Then: creating a run layout refuses the non-output root.
        with self.assertRaises(OutputRootError):
            create_run_layout(reports_run, "bad_run")


if __name__ == "__main__":
    unittest.main()
