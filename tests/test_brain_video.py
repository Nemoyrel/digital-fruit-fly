from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from digital_fruit_fly.observability.brain_video import (
    BrainActivityInputError,
    RenderRequest,
    render_brain_activity,
)


class TestBrainActivityRenderer(unittest.TestCase):
    def test_renders_summary_artifact_when_fixture_rates_have_empty_spike_windows(self) -> None:
        # Given: a Todo 13 compatible rates.csv with all spike deltas at zero.
        with tempfile.TemporaryDirectory() as temp_root:
            run_dir = Path(temp_root) / "brain_server"
            rates_path = run_dir / "brain" / "rates.csv"
            rates_path.parent.mkdir(parents=True)
            rates_path.write_text(
                "\n".join(
                    (
                        "frame_index,simulation_time_s,readout,rate_hz,spike_delta",
                        "0,0.0,forward,11.0,0",
                        "0,0.0,feed,8.0,0",
                        "1,0.015,forward,12.5,0",
                        "1,0.015,feed,10.5,0",
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            output_path = run_dir / "video" / "brain_activity.mp4"

            # When: the renderer is asked for an MP4.
            result = render_brain_activity(RenderRequest(input_path=run_dir, output_path=output_path))

            # Then: it writes a nonempty video or documented fallback summary.
            self.assertTrue(result.artifact_path.is_file())
            self.assertGreater(result.artifact_path.stat().st_size, 0)
            self.assertTrue(result.metadata_path.is_file())
            self.assertEqual(result.frame_count, 2)
            self.assertEqual(result.row_count, 4)
            self.assertEqual(result.readouts, ("feed", "forward"))

    def test_raises_clear_error_when_rates_log_is_header_only(self) -> None:
        # Given: a rates.csv with the expected header but no activity rows.
        with tempfile.TemporaryDirectory() as temp_root:
            run_dir = Path(temp_root) / "brain_server"
            rates_path = run_dir / "brain" / "rates.csv"
            rates_path.parent.mkdir(parents=True)
            rates_path.write_text("frame_index,simulation_time_s,readout,rate_hz,spike_delta\n", encoding="utf-8")
            output_path = run_dir / "video" / "brain_activity.mp4"

            # When / Then: rendering fails before writing the requested MP4.
            with self.assertRaisesRegex(BrainActivityInputError, "no activity rows"):
                render_brain_activity(RenderRequest(input_path=run_dir, output_path=output_path))
            self.assertFalse(output_path.exists())

    def test_raises_clear_error_when_rates_log_is_missing(self) -> None:
        # Given: a run directory without a Todo 13 rates.csv.
        with tempfile.TemporaryDirectory() as temp_root:
            run_dir = Path(temp_root) / "brain_server"
            output_path = run_dir / "video" / "brain_activity.mp4"

            # When / Then: rendering fails and does not create a corrupt MP4.
            with self.assertRaisesRegex(BrainActivityInputError, "missing brain rates log"):
                render_brain_activity(RenderRequest(input_path=run_dir, output_path=output_path))
            self.assertFalse(output_path.exists())

    def test_removes_stale_requested_mp4_when_rates_log_is_missing(self) -> None:
        # Given: a stale output exists from an earlier render attempt.
        with tempfile.TemporaryDirectory() as temp_root:
            run_dir = Path(temp_root) / "brain_server"
            output_path = run_dir / "video" / "brain_activity.mp4"
            output_path.parent.mkdir(parents=True)
            output_path.write_bytes(b"stale")

            # When / Then: a missing input failure removes the stale requested artifact.
            with self.assertRaisesRegex(BrainActivityInputError, "missing brain rates log"):
                render_brain_activity(RenderRequest(input_path=run_dir, output_path=output_path))
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
