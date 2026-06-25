from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from digital_fruit_fly.behavior.scenario import BehaviorVerificationError
from digital_fruit_fly.bridge.replay import ReplayVerificationError
from digital_fruit_fly.demo.process_children import (
    ChildRecord,
    ChildStartRequest,
    RunningChild,
    cleanup_child,
    run_child_to_completion,
    start_child,
    status_for_returncode,
    subprocess_env,
    terminate_if_alive,
    wait_for_child,
    wait_for_json_status,
)
from digital_fruit_fly.demo.process_summary import LiveSummaryRequest, Success, write_successful_live_summary
from digital_fruit_fly.runtime.config import ConfigError, RuntimeConfig, load_config
from digital_fruit_fly.runtime.timeouts import JsonObject, write_json_evidence


REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class SeparateProcessRequest:
    config_path: Path
    output_dir: Path
    evidence_path: Path
    duration_sec: float
    seed: int
    timeout_sec: float
    record_codec: str


@dataclass(frozen=True, slots=True)
class Failure:
    code: str
    message: str
    details: JsonObject
    subprocesses: JsonObject


_LIVE_CHILD_WALL_TIME_PER_TICK_SEC: Final = 0.8
_LIVE_CHILD_STARTUP_CUSHION_SEC: Final = 120.0


def run_separate_process_demo(request: SeparateProcessRequest) -> int:
    started = time.monotonic()
    _remove_stale_acceptance_artifacts(request.output_dir)
    try:
        config = _load_checked_config(request)
    except ConfigError as exc:
        return _write_failure(request, Failure("p0_invalid_demo_config", str(exc), {}, {}))
    missing = _missing_python_paths(config)
    if missing:
        return _write_failure(
            request,
            Failure(
                "p0_missing_configured_python",
                "configured brain/body Python interpreter is unavailable",
                {"missing": missing},
                _not_started_records(config),
            ),
        )
    ticks = max(1, int(request.duration_sec * 1000.0 / config.tick_ms))
    child_timeout_sec = _live_child_timeout_sec(request.timeout_sec, ticks)
    brain = _start_brain(request, config, ticks, child_timeout_sec)
    match brain:
        case ChildRecord():
            return _write_failure(
                request,
                Failure("p0_brain_start_failed", "brain subprocess did not start", {}, {"brain": brain.to_json()}),
            )
        case RunningChild():
            pass
    ready = wait_for_json_status(brain, "ready", child_timeout_sec)
    if ready.get("status") != "ready":
        brain_record = cleanup_child(brain, "brain_not_ready")
        return _write_failure(
            request,
            Failure("p0_brain_not_ready", "brain subprocess did not report readiness", ready, {"brain": brain_record.to_json()}),
        )
    body = _run_body(request, config, ticks, child_timeout_sec)
    brain_record = wait_for_child(brain, child_timeout_sec)
    subprocesses = {"brain": brain_record.to_json(), "body": body.to_json()}
    if _exited_with_failure(brain_record):
        return _write_failure(
            request,
            Failure("p0_brain_process_failed", "brain subprocess failed while connected to body", {}, subprocesses),
        )
    if body.returncode != 0:
        cleanup = terminate_if_alive(brain.process, child_timeout_sec)
        brain_record = ChildRecord(
            brain.name,
            brain.command,
            brain.process.pid,
            brain.process.returncode,
            brain_record.stdout,
            brain_record.stderr,
            status_for_returncode(brain.process.returncode),
            cleanup,
        )
        subprocesses["brain"] = brain_record.to_json()
        code = "p0_body_process_timeout" if body.status == "timeout" else "p0_body_process_failed"
        message = (
            "body subprocess timed out while connected to brain"
            if body.status == "timeout"
            else "body subprocess failed while connected to brain"
        )
        return _write_failure(
            request,
            Failure(code, message, {"requested_ticks": ticks, "duration_sec": request.duration_sec}, subprocesses),
        )
    if brain_record.returncode != 0:
        return _write_failure(
            request,
            Failure("p0_brain_process_failed", "brain subprocess did not shut down cleanly", {}, subprocesses),
        )
    try:
        return write_successful_live_summary(
            _live_summary_request(request),
            Success(
                config=config,
                ticks=ticks,
                subprocesses=subprocesses,
                wall_duration_sec=time.monotonic() - started,
            ),
        )
    except (ReplayVerificationError, BehaviorVerificationError) as exc:
        stage = "replay" if isinstance(exc, ReplayVerificationError) else "behavior"
        return _write_failure(
            request,
            _live_verification_failure(stage, exc, subprocesses),
        )


def _exited_with_failure(record: ChildRecord) -> bool:
    return record.cleanup == "exited" and record.returncode not in (0, None)


def _load_checked_config(request: SeparateProcessRequest) -> RuntimeConfig:
    if request.duration_sec <= 0.0:
        raise ConfigError(str(request.config_path), "duration-sec must be positive")
    if request.seed < 0:
        raise ConfigError(str(request.config_path), "seed must be non-negative")
    if request.timeout_sec <= 0.0:
        raise ConfigError(str(request.config_path), "timeout-sec must be positive")
    return load_config(request.config_path)


def _start_brain(
    request: SeparateProcessRequest, config: RuntimeConfig, ticks: int, timeout_sec: float
) -> RunningChild | ChildRecord:
    command = (
        config.brain.python,
        "scripts/run_brain.py",
        "--config",
        str(request.config_path),
        "--mode",
        "brian2",
        "--max-ticks",
        str(ticks),
        "--output",
        str(request.output_dir),
        "--timeout-sec",
        str(timeout_sec),
    )
    return start_child(ChildStartRequest("brain", command, REPO_ROOT, subprocess_env(REPO_ROOT)))


def _run_body(
    request: SeparateProcessRequest, config: RuntimeConfig, ticks: int, timeout_sec: float
) -> ChildRecord:
    command = (
        config.body.python,
        "scripts/run_body.py",
        "--config",
        str(request.config_path),
        "--brain-mode",
        "connect",
        "--max-ticks",
        str(ticks),
        "--output",
        str(request.output_dir),
        "--host",
        config.process.host,
        "--brain-port",
        str(config.process.brain_port),
        "--timeout-sec",
        str(timeout_sec),
        "--record-codec",
        request.record_codec,
    )
    return run_child_to_completion(
        ChildStartRequest("body", command, REPO_ROOT, subprocess_env(REPO_ROOT)),
        timeout_sec,
    )


def _live_summary_request(request: SeparateProcessRequest) -> LiveSummaryRequest:
    return LiveSummaryRequest(
        config_path=request.config_path,
        output_dir=request.output_dir,
        evidence_path=request.evidence_path,
        duration_sec=request.duration_sec,
        seed=request.seed,
        timeout_sec=request.timeout_sec,
    )


def _write_failure(request: SeparateProcessRequest, failure: Failure) -> int:
    _remove_live_success_artifacts(request.output_dir)
    payload: JsonObject = {
        "status": "failed",
        "mode": "separate_processes",
        "error_code": failure.code,
        "error": failure.message,
        "failure": failure.details,
        "subprocesses": failure.subprocesses,
        "children_alive_after_cleanup": [],
    }
    write_json_evidence(request.output_dir / "failure_manifest.json", payload)
    write_json_evidence(request.evidence_path, payload)
    print(json.dumps(payload, sort_keys=True), file=sys.stderr)
    return 1


def _missing_python_paths(config: RuntimeConfig) -> list[str]:
    paths = (config.brain.python, config.body.python)
    return [path for path in paths if not Path(path).is_file()]


def _not_started_records(config: RuntimeConfig) -> JsonObject:
    return {
        "brain": {"configured_python": config.brain.python, "status": "not_started_missing_python"},
        "body": {"configured_python": config.body.python, "status": "not_started_missing_python"},
    }


def _remove_stale_acceptance_artifacts(output_dir: Path) -> None:
    for path in (
        output_dir / "frames.jsonl",
        output_dir / "summary.json",
        output_dir / "failure_manifest.json",
        output_dir / "replay_evidence.json",
        output_dir / "behavior_summary.json",
        output_dir / "behavior_evidence.json",
        output_dir / "video" / "fly_demo.mp4",
        output_dir / "video" / "fly_demo.result.json",
    ):
        path.unlink(missing_ok=True)


def _remove_live_success_artifacts(output_dir: Path) -> None:
    for path in (
        output_dir / "summary.json",
        output_dir / "replay_evidence.json",
        output_dir / "behavior_summary.json",
        output_dir / "behavior_evidence.json",
    ):
        path.unlink(missing_ok=True)


def _live_child_timeout_sec(request_timeout_sec: float, ticks: int) -> float:
    minimum = (ticks * _LIVE_CHILD_WALL_TIME_PER_TICK_SEC) + _LIVE_CHILD_STARTUP_CUSHION_SEC
    return max(request_timeout_sec, minimum)


def _live_verification_failure(
    stage: str,
    exc: ReplayVerificationError | BehaviorVerificationError,
    subprocesses: JsonObject,
) -> Failure:
    return Failure(
        f"p0_live_{stage}_verification_failed",
        exc.failure.message,
        {
            "verification_error_code": exc.failure.code,
            "verification_failure": exc.failure.details,
        },
        subprocesses,
    )
