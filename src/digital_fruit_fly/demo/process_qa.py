from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from digital_fruit_fly.runtime.timeouts import JsonObject, write_json_evidence


@dataclass(frozen=True, slots=True)
class FailureQaRequest:
    config_path: Path
    output_dir: Path
    evidence_path: Path
    delay_sec: float
    timeout_sec: float


def run_killed_brain_failure_qa(request: FailureQaRequest) -> JsonObject:
    request.output_dir.mkdir(parents=True, exist_ok=True)
    brain = _start_brain_child(request)
    time.sleep(request.delay_sec)
    brain_cleanup = _kill_child(brain)
    body = _start_body_child(request)
    body_cleanup = _terminate_child(body, request.timeout_sec)
    alive = _alive_children((("brain", brain), ("body", body)))
    payload: JsonObject = {
        "status": "failed",
        "error_code": "brain_subprocess_killed",
        "error": "failure QA intentionally killed the brain subprocess",
        "subprocesses": {
            "brain": {"pid": brain.pid, "returncode": brain.returncode, "cleanup": brain_cleanup},
            "body": {"pid": body.pid, "returncode": body.returncode, "cleanup": body_cleanup},
        },
        "children_alive_after_cleanup": alive,
    }
    write_json_evidence(request.output_dir / "failure_manifest.json", payload)
    write_json_evidence(request.evidence_path, payload)
    return payload


def _start_brain_child(request: FailureQaRequest) -> subprocess.Popen[str]:
    return subprocess.Popen(
        (
            sys.executable,
            "scripts/run_brain.py",
            "--config",
            str(request.config_path),
            "--mode",
            "fixture",
            "--max-ticks",
            "100000",
            "--output",
            str(_child_run_dir(request)),
            "--timeout-sec",
            str(request.timeout_sec),
        ),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )


def _start_body_child(request: FailureQaRequest) -> subprocess.Popen[str]:
    return subprocess.Popen(
        (
            sys.executable,
            "scripts/run_body.py",
            "--config",
            str(request.config_path),
            "--brain-mode",
            "connect",
            "--max-ticks",
            "100000",
            "--output",
            str(_child_run_dir(request)),
            "--timeout-sec",
            str(request.timeout_sec),
        ),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )


def _child_run_dir(request: FailureQaRequest) -> Path:
    return request.output_dir / "outputs" / "failure_qa_process"


def _kill_child(process: subprocess.Popen[str]) -> str:
    if process.poll() is not None:
        return "already_exited"
    os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=2.0)
    return "killed"


def _terminate_child(process: subprocess.Popen[str], timeout_sec: float) -> str:
    if process.poll() is not None:
        return "already_exited"
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=min(timeout_sec, 2.0))
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=2.0)
        return "killed"
    return "terminated"


def _alive_children(children: tuple[tuple[str, subprocess.Popen[str]], ...]) -> list[str]:
    return [label for label, process in children if process.poll() is None]
