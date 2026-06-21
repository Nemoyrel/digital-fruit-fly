import tempfile
import unittest
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from digital_fruit_fly.demo_video import (
    combine_side_by_side_video,
    planned_combined_video_paths,
)
from digital_fruit_fly.telemetry import make_l4_brain_activity_panel_png


class DemoVideoTest(unittest.TestCase):
    def test_planned_combined_video_paths(self):
        paths = planned_combined_video_paths(Path("outputs/demo"), "demo_stem")

        self.assertEqual(paths["body_video_mp4"], "outputs/demo/demo_stem.mp4")
        self.assertEqual(
            paths["brain_state_video_mp4"],
            "outputs/demo/demo_stem_brain_state.mp4",
        )
        self.assertEqual(
            paths["combined_video_mp4"],
            "outputs/demo/demo_stem_combined.mp4",
        )

    def test_combine_side_by_side_video_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            metadata = combine_side_by_side_video(
                body_video=Path(tmp) / "body.mp4",
                brain_video=Path(tmp) / "brain.mp4",
                output_video=Path(tmp) / "combined.mp4",
                dry_run=True,
            )

        self.assertFalse(metadata["combined"])
        self.assertEqual(metadata["reason"], "dry_run")
        self.assertEqual(metadata["layout"], "body_left_brain_right")

    def test_brain_activity_panel_png_is_written(self):
        rows = [
            {
                "time_s": 0.0,
                "behavior_state": "foraging",
                "mn9_rate_hz": 5.0,
                "ipc_grooming_rate_hz": 1.0,
                "ipc_backend": "shiu_full",
                "ipc_brain_wall_time_ms": 12.0,
            },
            {
                "time_s": 0.1,
                "behavior_state": "feeding",
                "mn9_rate_hz": 80.0,
                "ipc_grooming_rate_hz": 10.0,
                "ipc_backend": "shiu_full",
                "ipc_brain_wall_time_ms": 18.0,
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "panel.png"
            self.assertTrue(make_l4_brain_activity_panel_png(rows, path))
            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
