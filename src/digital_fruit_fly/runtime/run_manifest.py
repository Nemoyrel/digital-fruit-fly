"""Run output layout and manifest creation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final


MANIFEST_SCHEMA_VERSION: Final = 1
_OUTPUTS_SEGMENT: Final = "outputs"
_EVIDENCE_SEGMENTS: Final = (".omo", "evidence")
_FORBIDDEN_ARTIFACT_SEGMENTS: Final = ("reports", "external")


@dataclass(frozen=True)
class RunLayout:
    """Filesystem paths owned by one simulation run."""

    __slots__ = (
        "run_id",
        "run_dir",
        "manifest_path",
        "events_path",
        "control_path",
        "arena_path",
        "brain_dir",
        "video_dir",
        "logs_dir",
    )

    run_id: str
    run_dir: Path
    manifest_path: Path
    events_path: Path
    control_path: Path
    arena_path: Path
    brain_dir: Path
    video_dir: Path
    logs_dir: Path


class OutputRootError(ValueError):
    """Raised when a run would write outside approved artifact roots."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        super().__init__(
            f"run artifacts must be written under outputs/ or .omo/evidence/: {run_dir}",
        )


def create_run_layout(path: Path, run_id: str) -> RunLayout:
    """Create the canonical output layout and write its manifest."""
    run_dir = _run_dir_for(path, run_id)
    _require_allowed_artifact_root(run_dir)

    layout = RunLayout(
        run_id=run_id,
        run_dir=run_dir,
        manifest_path=run_dir / "manifest.json",
        frames_path=run_dir / "frames.jsonl",
        events_path=run_dir / "events.jsonl",
        control_path=run_dir / "control.jsonl",
        arena_path=run_dir / "arena.jsonl",
        brain_dir=run_dir / "brain",
        video_dir=run_dir / "video",
        logs_dir=run_dir / "logs",
    )
    _create_layout(layout)
    _write_manifest(layout)
    return layout


def _run_dir_for(path: Path, run_id: str) -> Path:
    if path.name == run_id:
        return path
    return path / run_id


def _require_allowed_artifact_root(run_dir: Path) -> None:
    parts = run_dir.parts
    if _contains_forbidden_root(parts):
        raise OutputRootError(run_dir)
    if _OUTPUTS_SEGMENT in parts or _contains_evidence_root(parts):
        return
    raise OutputRootError(run_dir)


def _contains_forbidden_root(parts: tuple[str, ...]) -> bool:
    return any(part in _FORBIDDEN_ARTIFACT_SEGMENTS for part in parts)


def _contains_evidence_root(parts: tuple[str, ...]) -> bool:
    for index, part in enumerate(parts[:-1]):
        if part == _EVIDENCE_SEGMENTS[0] and parts[index + 1] == _EVIDENCE_SEGMENTS[1]:
            return True
    return False


def _create_layout(layout: RunLayout) -> None:
    layout.run_dir.mkdir(parents=True, exist_ok=True)
    layout.brain_dir.mkdir(exist_ok=True)
    layout.video_dir.mkdir(exist_ok=True)
    layout.logs_dir.mkdir(exist_ok=True)
    layout.frames_path.touch(exist_ok=True)
    layout.events_path.touch(exist_ok=True)
    layout.control_path.touch(exist_ok=True)
    layout.arena_path.touch(exist_ok=True)


def _write_manifest(layout: RunLayout) -> None:
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": layout.run_id,
        "created_at_utc": _utc_now(),
        "run_dir": str(layout.run_dir),
        "jsonl_files": {
            "frames": str(layout.frames_path),
            "events": str(layout.events_path),
            "control": str(layout.control_path),
            "arena": str(layout.arena_path),
        },
        "directories": {
            "brain": str(layout.brain_dir),
            "video": str(layout.video_dir),
            "logs": str(layout.logs_dir),
        },
    }
    with layout.manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
