from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from digital_fruit_fly.behavior.scenario import BehaviorVerifyRequest, verify_behavior
from digital_fruit_fly.bridge.replay import verify_replay, write_replay_success
from digital_fruit_fly.demo.process_children import json_line, subprocess_env
from digital_fruit_fly.runtime.config import RuntimeConfig
from digital_fruit_fly.runtime.timeouts import (
    JsonObject,
    SubprocessRunRequest,
    run_subprocess_request,
    write_json_evidence,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class LiveSummaryRequest:
    config_path: Path
    output_dir: Path
    evidence_path: Path
    duration_sec: float
    seed: int
    timeout_sec: float


@dataclass(frozen=True, slots=True)
class Success:
    config: RuntimeConfig
    ticks: int
    subprocesses: JsonObject
    wall_duration_sec: float


def write_successful_live_summary(request: LiveSummaryRequest, success: Success) -> int:
    config = success.config
    _write_replay_summary_stub(request, config, success)
    replay = verify_replay(request.output_dir)
    write_replay_success(request.output_dir, replay)
    behavior = verify_behavior(
        BehaviorVerifyRequest(
            request.output_dir,
            request.config_path,
            request.output_dir / "behavior_evidence.json",
        )
    )
    behavior_payload = behavior.evidence()
    rates_path = request.output_dir / "brain" / "rates.csv"
    brain = _render_brain_activity(request, config)
    body = _load_body_recording(request.output_dir / "manifest.json")
    summary: JsonObject = {
        "status": "ok",
        "mode": "separate_processes",
        "config": str(request.config_path),
        "duration_sec": request.duration_sec,
        "seed": request.seed,
        "run_id": request.output_dir.name,
        "ticks": success.ticks,
        "tick_ms": config.tick_ms,
        "frame_count": success.ticks,
        "behavior_metrics": behavior_payload["metrics"],
        "event_sequence": behavior_payload["ordered_events"],
        "behavior_summary_path": str(behavior.summary_path),
        "replay_evidence_path": str(request.output_dir / "replay_evidence.json"),
        "rates_path": str(rates_path),
        "body_recording": body,
        "brain_activity": brain,
        "viewer_status": body.get("viewer_status", "skipped_headless"),
        "subprocesses": success.subprocesses,
        "wall_duration_sec": success.wall_duration_sec,
    }
    write_json_evidence(request.output_dir / "summary.json", summary)
    write_json_evidence(request.evidence_path, summary)
    print(json.dumps(summary, sort_keys=True))
    return 0


def _render_brain_activity(request: LiveSummaryRequest, config: RuntimeConfig) -> JsonObject:
    output = request.output_dir / "video" / "brain_activity.mp4"
    result = run_subprocess_request(
        SubprocessRunRequest(
            (config.body.python, "scripts/render_brain_activity.py", "--input", str(request.output_dir), "--output", str(output)),
            request.timeout_sec,
            cwd=REPO_ROOT,
            env=subprocess_env(REPO_ROOT),
        )
    )
    payload = json_line(result.stdout.splitlines()[-1] if result.stdout.strip() else "")
    payload["renderer"] = result.to_json()
    return payload


def _load_body_recording(manifest_path: Path) -> JsonObject:
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    recording = raw.get("recording")
    if not isinstance(recording, dict):
        return {}
    artifact_path = recording.get("video_path")
    if not isinstance(artifact_path, str):
        fallback = recording.get("fallback_frames")
        if isinstance(fallback, list) and len(fallback) > 0 and isinstance(fallback[0], str):
            artifact_path = fallback[0]
    payload: JsonObject = dict(recording)
    if isinstance(artifact_path, str):
        payload["artifact_path"] = artifact_path
    return payload


def _write_replay_summary_stub(
    request: LiveSummaryRequest, config: RuntimeConfig, success: Success
) -> None:
    stub: JsonObject = {
        "status": "pending",
        "mode": "separate_processes",
        "config": str(request.config_path),
        "duration_sec": request.duration_sec,
        "seed": request.seed,
        "run_id": request.output_dir.name,
        "ticks": success.ticks,
        "tick_ms": config.tick_ms,
        "frame_count": success.ticks,
    }
    write_json_evidence(request.output_dir / "summary.json", stub)
