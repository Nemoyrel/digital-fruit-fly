from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))


class TestBodyCamera(unittest.TestCase):
    def test_recorder_writes_fallback_frames_when_codec_is_unsupported(self) -> None:
        # Given: deterministic RGB frames and an unsupported codec request.
        from digital_fruit_fly.body.camera import (
            CameraRecordingRequest,
            RgbFrame,
            rgb_frame_from_rows,
            write_camera_recording,
        )

        frame = rgb_frame_from_rows(
            (
                ((255, 0, 0), (0, 255, 0)),
                ((0, 0, 255), (255, 255, 255)),
            )
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            request = CameraRecordingRequest(
                output_dir=Path(tmp_dir),
                stem="unsupported_codec",
                fps=10,
                codec="definitely-not-a-codec",
                mode="tracking",
                source="unit_test",
                viewer_status="not_requested",
            )

            # When: the recording is written.
            result = write_camera_recording(request, (frame,))

            # Then: a clear fallback artifact is written instead of silent success.
            self.assertEqual(result.status, "fallback_frames")
            self.assertIsNone(result.video_path)
            self.assertEqual(len(result.fallback_frames), 1)
            self.assertIn("unsupported codec", result.warnings[0])
            fallback = result.fallback_frames[0]
            self.assertGreater(fallback.stat().st_size, 0)
            self.assertEqual(fallback.read_bytes()[:2], b"P6")
            metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["status"], "fallback_frames")
            self.assertEqual(metadata["frame_count"], 1)
            self.assertIn("unsupported codec", metadata["warnings"][0])

    def test_recorder_writes_video_when_writer_is_available(self) -> None:
        # Given: a deterministic frame and an available video writer.
        from digital_fruit_fly.body.camera import (
            CameraRecordingRequest,
            RgbFrame,
            VideoWriteRequest,
            write_camera_recording,
        )

        class FakeVideoWriter:
            def write(self, request: VideoWriteRequest) -> None:
                request.path.write_bytes(b"fake mp4 bytes")

        with tempfile.TemporaryDirectory() as tmp_dir:
            request = CameraRecordingRequest(
                output_dir=Path(tmp_dir),
                stem="video",
                fps=10,
                codec="libx264",
                mode="fixed",
                source="unit_test",
                viewer_status="not_requested",
            )
            frame = RgbFrame.from_bytes(1, 1, b"\x01\x02\x03")

            # When: the recording is written with the available writer.
            result = write_camera_recording(request, (frame,), FakeVideoWriter())

            # Then: the MP4 path is reported and no fallback frames are emitted.
            self.assertEqual(result.status, "video")
            self.assertEqual(result.video_path, Path(tmp_dir) / "video.mp4")
            self.assertEqual(result.fallback_frames, ())
            self.assertEqual(result.video_path.read_bytes(), b"fake mp4 bytes")

    def test_smoke_body_record_attaches_camera_artifact_when_probe_succeeds(self) -> None:
        # Given: a successful body probe and a recording request.
        from digital_fruit_fly.body.flygym_probe import ProbeOutcome
        from scripts import smoke_body

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "body"
            evidence_path = Path(tmp_dir) / "evidence.json"
            config = SimpleNamespace(
                body=SimpleNamespace(python="/fake/flygym_env/python"),
                camera=SimpleNamespace(
                    enabled=False,
                    fps=5,
                    width_px=2,
                    height_px=2,
                    follow_fly=True,
                ),
            )
            probe = ProbeOutcome(
                exit_code=0,
                payload={
                    "script": "smoke_body",
                    "status": "ok",
                    "probe_stage": "complete",
                    "renderer": {"status": "skipped", "renderer": "none"},
                    "viewer": {"status": "available_headless_skipped"},
                },
                evidence_path=evidence_path,
            )

            # When: smoke_body runs with recording enabled.
            with (
                contextlib.redirect_stdout(io.StringIO()),
                patch.object(smoke_body, "load_config", return_value=config),
                patch.object(smoke_body, "run_body_probe", return_value=probe),
            ):
                exit_code = smoke_body.main(
                    (
                        "--config",
                        "configs/body_smoke.yaml",
                        "--output",
                        str(output_dir),
                        "--evidence",
                        str(evidence_path),
                        "--headless",
                        "--record",
                        "--record-codec",
                        "definitely-not-a-codec",
                        "--steps",
                        "3",
                    )
                )

            # Then: the smoke payload includes nonempty fallback frame artifacts.
            self.assertEqual(exit_code, 0)
            payload = json.loads((output_dir / "body_env.json").read_text(encoding="utf-8"))
            camera = payload["camera_recording"]
            self.assertEqual(camera["status"], "fallback_frames")
            self.assertEqual(camera["frame_count"], 3)
            self.assertEqual(camera["viewer_status"], "skipped_headless")
            self.assertGreater(Path(camera["fallback_frames"][0]).stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
