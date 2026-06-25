from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from digital_fruit_fly.body.camera import (
    CameraConfigError,
    CameraMode,
    CameraRecordingRequest,
    ViewerStatus,
    deterministic_probe_frames,
    write_camera_recording,
)
from digital_fruit_fly.runtime.timeouts import JsonObject, write_json_evidence


@dataclass(frozen=True, slots=True)
class BodyVideoRequest:
    output_dir: Path
    result_path: Path
    stem: str
    fps: int
    codec: str
    width_px: int
    height_px: int
    frame_count: int
    mode: CameraMode
    viewer_status: ViewerStatus


def render_body_video(request: BodyVideoRequest) -> JsonObject:
    frames = deterministic_probe_frames(request.width_px, request.height_px, request.frame_count)
    result = write_camera_recording(
        CameraRecordingRequest(
            output_dir=request.output_dir,
            stem=request.stem,
            fps=request.fps,
            codec=request.codec,
            mode=request.mode,
            source="fixture_demo:deterministic_probe_frames",
            viewer_status=request.viewer_status,
        ),
        frames,
    )
    payload = result.to_json()
    payload["artifact_path"] = _artifact_path(payload)
    write_json_evidence(request.result_path, payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        payload = render_body_video(_request(args))
    except CameraConfigError as exc:
        payload: JsonObject = {"status": "failed", "error": str(exc)}
        write_json_evidence(args.result_json, payload)
        print(json.dumps(payload, sort_keys=True))
        return 2
    print(json.dumps(payload, sort_keys=True))
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render deterministic body demo recording.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--result-json", type=Path, required=True)
    parser.add_argument("--stem", default="fly_demo")
    parser.add_argument("--fps", type=int, required=True)
    parser.add_argument("--codec", required=True)
    parser.add_argument("--width-px", type=int, required=True)
    parser.add_argument("--height-px", type=int, required=True)
    parser.add_argument("--frame-count", type=int, required=True)
    parser.add_argument("--mode", choices=("tracking", "fixed"), required=True)
    parser.add_argument("--viewer-status", choices=("not_requested", "skipped_headless", "available_not_launched"), required=True)
    return parser.parse_args(argv)


def _request(args: argparse.Namespace) -> BodyVideoRequest:
    return BodyVideoRequest(
        output_dir=args.output_dir,
        result_path=args.result_json,
        stem=args.stem,
        fps=args.fps,
        codec=args.codec,
        width_px=args.width_px,
        height_px=args.height_px,
        frame_count=args.frame_count,
        mode=args.mode,
        viewer_status=args.viewer_status,
    )


def _artifact_path(payload: JsonObject) -> str:
    video_path = payload.get("video_path")
    if isinstance(video_path, str):
        return video_path
    fallback_frames = payload.get("fallback_frames")
    if isinstance(fallback_frames, list) and len(fallback_frames) > 0 and isinstance(fallback_frames[0], str):
        return fallback_frames[0]
    metadata_path = payload.get("metadata_path")
    if isinstance(metadata_path, str):
        return metadata_path
    return ""


if __name__ == "__main__":
    raise SystemExit(main())

