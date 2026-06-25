from __future__ import annotations

import json
import os
import selectors
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from digital_fruit_fly.runtime.timeouts import (
    JsonObject,
    SubprocessRunRequest,
    run_subprocess_request,
)


@dataclass(frozen=True, slots=True)
class ChildStartRequest:
    name: str
    command: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class RunningChild:
    name: str
    command: tuple[str, ...]
    process: subprocess.Popen[str]
    stdout_prefix: str


@dataclass(frozen=True, slots=True)
class ChildRecord:
    name: str
    command: tuple[str, ...]
    pid: int | None
    returncode: int | None
    stdout: str
    stderr: str
    status: str
    cleanup: str

    def to_json(self) -> JsonObject:
        return {
            "command": list(self.command),
            "pid": self.pid,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "status": self.status,
            "cleanup": self.cleanup,
        }


def start_child(request: ChildStartRequest) -> RunningChild | ChildRecord:
    try:
        process = subprocess.Popen(
            request.command,
            cwd=request.cwd,
            env=dict(request.env),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return ChildRecord(request.name, request.command, None, None, "", str(exc), "failed", "not_started")
    return RunningChild(request.name, request.command, process, "")


def run_child_to_completion(request: ChildStartRequest, timeout_sec: float) -> ChildRecord:
    result = run_subprocess_request(
        SubprocessRunRequest(
            request.command,
            timeout_sec,
            cwd=request.cwd,
            env=request.env,
        )
    )
    return ChildRecord(
        request.name,
        request.command,
        None,
        result.returncode,
        result.stdout,
        result.stderr,
        result.status,
        "completed",
    )


def wait_for_json_status(child: RunningChild, status: str, timeout_sec: float) -> JsonObject:
    if child.process.stdout is None:
        return {"status": "failed", "error": f"{child.name} stdout was not captured"}
    deadline = time.monotonic() + timeout_sec
    selector = selectors.DefaultSelector()
    selector.register(child.process.stdout, selectors.EVENT_READ)
    try:
        while time.monotonic() < deadline:
            if child.process.poll() is not None:
                return {"status": "failed", "error": f"{child.name} exited before readiness", "returncode": child.process.returncode}
            remaining = max(0.0, deadline - time.monotonic())
            events = selector.select(min(remaining, 0.2))
            if len(events) == 0:
                continue
            line = child.process.stdout.readline()
            payload = json_line(line)
            if payload.get("status") == status:
                return payload
        return {"status": "timeout", "timeout_sec": timeout_sec}
    finally:
        selector.close()


def wait_for_child(child: RunningChild, timeout_sec: float) -> ChildRecord:
    try:
        stdout, stderr = child.process.communicate(timeout=timeout_sec)
        cleanup = "exited"
    except subprocess.TimeoutExpired:
        cleanup = terminate_if_alive(child.process, timeout_sec)
        stdout, stderr = child.process.communicate()
    return ChildRecord(
        child.name,
        child.command,
        child.process.pid,
        child.process.returncode,
        child.stdout_prefix + stdout,
        stderr,
        status_for_returncode(child.process.returncode),
        cleanup,
    )


def cleanup_child(child: RunningChild, reason: str) -> ChildRecord:
    cleanup = terminate_if_alive(child.process, 1.0)
    stdout, stderr = child.process.communicate()
    return ChildRecord(
        child.name,
        child.command,
        child.process.pid,
        child.process.returncode,
        child.stdout_prefix + stdout,
        stderr,
        reason,
        cleanup,
    )


def terminate_if_alive(process: subprocess.Popen[str], timeout_sec: float) -> str:
    if process.poll() is not None:
        return "already_exited"
    _signal_group(process, signal.SIGTERM)
    try:
        process.wait(timeout=min(timeout_sec, 2.0))
    except subprocess.TimeoutExpired:
        _signal_group(process, signal.SIGKILL)
        process.wait(timeout=2.0)
        return "killed"
    return "terminated"


def json_line(line: str) -> JsonObject:
    if line.strip() == "":
        return {}
    raw = json.loads(line)
    if isinstance(raw, dict):
        return raw
    return {}


def status_for_returncode(returncode: int | None) -> str:
    if returncode == 0:
        return "ok"
    if returncode is None:
        return "running"
    return "failed"


def subprocess_env(repo_root: Path) -> Mapping[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root / "src")
    return env


def _signal_group(process: subprocess.Popen[str], sig: int) -> None:
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        return
