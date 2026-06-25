from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple, Union


JsonScalar = Union[None, bool, int, float, str]
JsonValue = Union[JsonScalar, List["JsonValue"], Dict[str, "JsonValue"]]
JsonObject = Dict[str, JsonValue]

TIMEOUT_EXIT_CODE = 124
_KILL_GRACE_SEC = 1.0


@dataclass(frozen=True)
class SubprocessRunRequest:
    command: Tuple[str, ...]
    timeout_sec: float
    evidence_path: Optional[Path] = None
    cwd: Optional[Path] = None
    env: Optional[Mapping[str, str]] = None


@dataclass(frozen=True)
class SubprocessRunResult:
    command: Tuple[str, ...]
    returncode: Optional[int]
    duration_sec: float
    timed_out: bool
    stdout: str
    stderr: str
    evidence_path: Optional[Path]

    @property
    def exit_code(self) -> int:
        if self.returncode is None:
            return TIMEOUT_EXIT_CODE
        if self.timed_out:
            return TIMEOUT_EXIT_CODE
        return self.returncode

    @property
    def status(self) -> str:
        if self.timed_out:
            return "timeout"
        if self.exit_code == 0:
            return "ok"
        return "failed"

    def to_json(self) -> JsonObject:
        return {
            "command": list(self.command),
            "returncode": self.returncode,
            "exit_code": self.exit_code,
            "duration_sec": self.duration_sec,
            "timed_out": self.timed_out,
            "status": self.status,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass(frozen=True)
class TimeoutConfigError(ValueError):
    field: str
    reason: str
    value_text: Optional[str] = None

    def __str__(self) -> str:
        if self.value_text is None:
            return f"{self.field}: {self.reason}"
        return f"{self.field}: {self.reason}: {self.value_text}"


def run_subprocess(
    command: Sequence[str],
    timeout_sec: float,
    evidence_path: Optional[Path] = None,
) -> SubprocessRunResult:
    request = SubprocessRunRequest(tuple(command), timeout_sec, evidence_path)
    return run_subprocess_request(request)


def run_subprocess_request(request: SubprocessRunRequest) -> SubprocessRunResult:
    _validate_request(request)
    started = time.monotonic()
    process = subprocess.Popen(
        request.command,
        cwd=str(request.cwd) if request.cwd is not None else None,
        env=dict(request.env) if request.env is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=request.timeout_sec)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_group(process)
        try:
            stdout, stderr = process.communicate(timeout=_KILL_GRACE_SEC)
        except subprocess.TimeoutExpired:
            _kill_process_group(process)
            stdout, stderr = process.communicate()
    duration_sec = time.monotonic() - started
    result = SubprocessRunResult(
        command=request.command,
        returncode=process.returncode,
        duration_sec=duration_sec,
        timed_out=timed_out,
        stdout=stdout,
        stderr=stderr,
        evidence_path=request.evidence_path,
    )
    if request.evidence_path is not None:
        write_json_evidence(request.evidence_path, result.to_json())
    return result


def write_json_evidence(path: Path, payload: JsonObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _validate_request(request: SubprocessRunRequest) -> None:
    if len(request.command) == 0:
        raise TimeoutConfigError("command", "must not be empty")
    if request.timeout_sec <= 0.0:
        raise TimeoutConfigError("timeout_sec", "must be positive", str(request.timeout_sec))


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return


def _kill_process_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
