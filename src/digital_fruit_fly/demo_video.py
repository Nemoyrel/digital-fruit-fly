"""Helpers for Eon-style side-by-side demo video outputs."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
from typing import Any


def planned_combined_video_paths(output_dir: Path, stem: str) -> dict[str, str]:
    """Return conventional body, brain, and combined video paths."""
    return {
        "body_video_mp4": str(output_dir / f"{stem}.mp4"),
        "brain_state_video_mp4": str(output_dir / f"{stem}_brain_state.mp4"),
        "brain_state_animation_gif": str(output_dir / f"{stem}_brain_state.gif"),
        "combined_video_mp4": str(output_dir / f"{stem}_combined.mp4"),
    }


def combine_side_by_side_video(
    *,
    body_video: Path,
    brain_video: Path,
    output_video: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Compose body footage left and brain-state footage right when ffmpeg exists."""
    metadata = {
        "combined": False,
        "layout": "body_left_brain_right",
        "body_video": str(body_video),
        "brain_video": str(brain_video),
        "output_video": str(output_video),
        "method": None,
        "reason": "",
    }
    if dry_run:
        metadata["reason"] = "dry_run"
        return metadata
    if not body_video.exists():
        metadata["reason"] = "missing_body_video"
        return metadata
    if not brain_video.exists():
        metadata["reason"] = "missing_brain_video"
        return metadata

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        metadata["reason"] = "ffmpeg_unavailable"
        return metadata

    output_video.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(body_video),
        "-i",
        str(brain_video),
        "-filter_complex",
        "[0:v]scale=640:-2[left];[1:v]scale=640:-2[right];[left][right]hstack=inputs=2[v]",
        "-map",
        "[v]",
        "-an",
        str(output_video),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        metadata["reason"] = "ffmpeg_failed"
        metadata["stderr"] = result.stderr[-1000:]
        return metadata
    metadata["combined"] = True
    metadata["method"] = "ffmpeg_hstack"
    return metadata
