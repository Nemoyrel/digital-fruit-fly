from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, assert_never

from digital_fruit_fly.behavior.scenario import BehaviorVerificationError, BehaviorVerifyRequest, verify_behavior
from digital_fruit_fly.bridge.fixture_run import BridgeSmokeError, BridgeSmokeRequest, write_fixture_smoke
from digital_fruit_fly.bridge.replay import ReplayVerificationError, verify_replay, write_replay_success
from digital_fruit_fly.demo.process_run import SeparateProcessRequest, run_separate_process_demo
from digital_fruit_fly.demo.process_qa import FailureQaRequest, run_killed_brain_failure_qa
from digital_fruit_fly.demo.rates import RatesSynthesisError, synthesize_rates_csv
from digital_fruit_fly.runtime.config import ConfigError, RuntimeConfig, load_config
from digital_fruit_fly.runtime.timeouts import JsonObject, SubprocessRunRequest, run_subprocess_request, write_json_evidence


ProcessMode = Literal["separate_processes", "fixture_demo", "failure_qa_kill_brain"]
REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class DemoRequest:
    config_path: Path
    output_dir: Path
    evidence_path: Path
    duration_sec: float
    seed: int
    process_mode: ProcessMode
    timeout_sec: float
    video_frame_cap: int
    brain_frame_cap: int
    video_width_px: int | None
    video_height_px: int | None
    record_codec: str
    failure_qa_delay_sec: float


def run_demo(request: DemoRequest) -> int:
    match request.process_mode:
        case "separate_processes":
            return run_separate_process_demo(
                SeparateProcessRequest(
                    config_path=request.config_path,
                    output_dir=request.output_dir,
                    evidence_path=request.evidence_path,
                    duration_sec=request.duration_sec,
                    seed=request.seed,
                    timeout_sec=request.timeout_sec,
                    record_codec=request.record_codec,
                )
            )
        case "fixture_demo":
            return _run_fixture_demo(request)
        case "failure_qa_kill_brain":
            payload = run_killed_brain_failure_qa(
                FailureQaRequest(
                    request.config_path,
                    request.output_dir,
                    request.evidence_path,
                    request.failure_qa_delay_sec,
                    request.timeout_sec,
                )
            )
            print(json.dumps(payload, sort_keys=True), file=sys.stderr)
            return 1
        case unreachable:
            assert_never(unreachable)


def _run_fixture_demo(request: DemoRequest) -> int:
    started = time.monotonic()
    try:
        config = _load_runtime_config(request)
        ticks = _ticks_for_duration(request.duration_sec, config)
        smoke = write_fixture_smoke(BridgeSmokeRequest(request.config_path, config, ticks, request.output_dir))
        replay = verify_replay(request.output_dir)
        write_replay_success(request.output_dir, replay)
        behavior = verify_behavior(BehaviorVerifyRequest(request.output_dir, request.config_path, request.output_dir / "behavior_evidence.json"))
        rates_path = synthesize_rates_csv(request.output_dir, request.brain_frame_cap)
        brain = _render_brain_activity(request, config)
        body = _render_body_recording(request, config)
    except (ConfigError, BridgeSmokeError, ReplayVerificationError, BehaviorVerificationError, RatesSynthesisError) as exc:
        return _write_failure(request, FailureReport("demo_artifact_error", str(exc), {}, 1))
    if brain.exit_code != 0:
        return _write_failure(request, FailureReport("brain_activity_render_failed", brain.stderr, {"subprocess": brain.to_json()}, 1))
    body_payload = _load_json(request.output_dir / "video" / "fly_demo.result.json")
    if body.exit_code != 0:
        return _write_failure(request, FailureReport("body_video_render_failed", body.stderr, {"subprocess": body.to_json()}, 1))
    if body_payload.get("status") != "video":
        return _write_failure(
            request,
            FailureReport("p0_body_video_unavailable", "body MP4 writer produced fallback output", {"body_recording": body_payload}, 1),
        )
    smoke_payload = smoke.evidence()
    behavior_payload = behavior.evidence()
    summary: JsonObject = {
        "status": "ok",
        "mode": request.process_mode,
        "config": str(request.config_path),
        "duration_sec": request.duration_sec,
        "seed": request.seed,
        "run_id": smoke_payload["run_id"],
        "ticks": smoke_payload["ticks"],
        "tick_ms": smoke_payload["tick_ms"],
        "frame_count": smoke_payload["frame_count"],
        "behavior_metrics": behavior_payload["metrics"],
        "event_sequence": behavior_payload["ordered_events"],
        "replay_evidence_path": str(request.output_dir / "replay_evidence.json"),
        "behavior_summary_path": str(request.output_dir / "behavior_summary.json"),
        "rates_path": str(rates_path),
        "brain_activity_frame_cap": request.brain_frame_cap,
        "body_recording": body_payload,
        "brain_activity": brain.payload,
        "viewer_status": body_payload.get("viewer_status", "skipped_headless"),
        "subprocesses": {
            "brain": {"status": "not_started_fixture_mode", "configured_python": config.brain.python},
            "body": {"status": "not_started_fixture_mode", "configured_python": config.body.python},
            "brain_activity_renderer": brain.to_json(),
            "body_video_renderer": body.to_json(),
        },
        "runtime_limitations": ["fixture bridge mode; live FlyGym/Brian2 processes were not launched"],
    }
    summary["wall_duration_sec"] = time.monotonic() - started
    write_json_evidence(request.output_dir / "summary.json", summary)
    write_json_evidence(request.evidence_path, summary)
    print(json.dumps(summary, sort_keys=True))
    return 0


def _load_runtime_config(request: DemoRequest) -> RuntimeConfig:
    if request.duration_sec <= 0.0:
        raise ConfigError(str(request.config_path), "duration-sec must be positive")
    if request.seed < 0:
        raise ConfigError(str(request.config_path), "seed must be non-negative")
    if request.timeout_sec <= 0.0:
        raise ConfigError(str(request.config_path), "timeout-sec must be positive")
    if request.video_frame_cap <= 0:
        raise ConfigError(str(request.config_path), "video-frame-cap must be positive")
    if request.brain_frame_cap <= 0:
        raise ConfigError(str(request.config_path), "brain-frame-cap must be positive")
    if request.video_width_px is not None and request.video_width_px <= 0:
        raise ConfigError(str(request.config_path), "video-width-px must be positive")
    if request.video_height_px is not None and request.video_height_px <= 0:
        raise ConfigError(str(request.config_path), "video-height-px must be positive")
    return load_config(request.config_path)


def _ticks_for_duration(duration_sec: float, config: RuntimeConfig) -> int:
    return max(1, int(duration_sec * 1000.0 / config.tick_ms))


@dataclass(frozen=True, slots=True)
class ChildRender:
    exit_code: int
    stdout: str
    stderr: str
    payload: JsonObject

    def to_json(self) -> JsonObject:
        return {"exit_code": self.exit_code, "stdout": self.stdout, "stderr": self.stderr, "payload": self.payload}


@dataclass(frozen=True, slots=True)
class FailureReport:
    code: str
    message: str
    details: JsonObject
    exit_code: int


def _render_brain_activity(request: DemoRequest, config: RuntimeConfig) -> ChildRender:
    output = request.output_dir / "video" / "brain_activity.mp4"
    result = run_subprocess_request(
        SubprocessRunRequest(
            (config.body.python, "scripts/render_brain_activity.py", "--input", str(request.output_dir), "--output", str(output)),
            request.timeout_sec,
            cwd=REPO_ROOT,
            env=_subprocess_env(),
        )
    )
    return ChildRender(result.exit_code, result.stdout, result.stderr, _json_from_stdout(result.stdout))


def _render_body_recording(request: DemoRequest, config: RuntimeConfig) -> ChildRender:
    result_json = request.output_dir / "video" / "fly_demo.result.json"
    frame_count = min(request.video_frame_cap, max(1, int(request.duration_sec * config.camera.fps)))
    mode = "tracking" if config.camera.follow_fly else "fixed"
    width_px = config.camera.width_px if request.video_width_px is None else request.video_width_px
    height_px = config.camera.height_px if request.video_height_px is None else request.video_height_px
    result = run_subprocess_request(
        SubprocessRunRequest(
            (
                config.body.python,
                "-m",
                "digital_fruit_fly.demo.body_video",
                "--output-dir",
                str(request.output_dir / "video"),
                "--result-json",
                str(result_json),
                "--stem",
                "fly_demo",
                "--fps",
                str(config.camera.fps),
                "--codec",
                request.record_codec,
                "--width-px",
                str(width_px),
                "--height-px",
                str(height_px),
                "--frame-count",
                str(frame_count),
                "--mode",
                mode,
                "--viewer-status",
                "skipped_headless",
            ),
            request.timeout_sec,
            cwd=REPO_ROOT,
            env=_subprocess_env(),
        )
    )
    return ChildRender(result.exit_code, result.stdout, result.stderr, _json_from_stdout(result.stdout))


def _write_failure(request: DemoRequest, report: FailureReport) -> int:
    payload: JsonObject = {
        "status": "failed",
        "mode": request.process_mode,
        "error_code": report.code,
        "error": report.message,
        "failure": report.details,
    }
    write_json_evidence(request.output_dir / "failure_manifest.json", payload)
    write_json_evidence(request.evidence_path, payload)
    print(json.dumps(payload, sort_keys=True), file=sys.stderr)
    return report.exit_code


def _json_from_stdout(stdout: str) -> JsonObject:
    if stdout.strip() == "":
        return {}
    raw = json.loads(stdout.splitlines()[-1])
    if isinstance(raw, dict):
        return raw
    return {}


def _load_json(path: Path) -> JsonObject:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return raw
    return {}


def _subprocess_env() -> Mapping[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    return env
