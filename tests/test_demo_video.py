import tempfile
import unittest
from pathlib import Path

from digital_fruit_fly.demo_video import (
    combine_side_by_side_video,
    planned_combined_video_paths,
)


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


if __name__ == "__main__":
    unittest.main()
