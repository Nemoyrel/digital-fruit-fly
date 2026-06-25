from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import assert_never

from digital_fruit_fly.bridge.fixture_model import build_fixture_brain_frame, decoder_context_from_sensory
from digital_fruit_fly.bridge.fixture_run import EVENT_TYPES
from digital_fruit_fly.bridge.messages import (
    BrainFrame,
    BridgeFrame,
    ControlFrame,
    ErrorFrame,
    Heartbeat,
    Hello,
    JsonObject,
    PayloadFrame,
    SensoryFrame,
    Shutdown,
    decode_message,
    payload_checksum,
)
from digital_fruit_fly.bridge.motor_decoder import BrainFrameReadout, MotorDecoderConfig, MotorDecoderRequest, MotorDecoderState, decode_motor_control
from digital_fruit_fly.runtime.config import ConfigError, RuntimeConfig, load_config
from digital_fruit_fly.runtime.timeouts import write_json_evidence


@dataclass(frozen=True, slots=True)
class RunSummary:
    run_id: str
    ticks: int
    tick_ms: int
    frame_count: int
    config_path: Path


@dataclass(frozen=True, slots=True)
class ReplayFailure:
    code: str
    message: str
    details: JsonObject


@dataclass(frozen=True, slots=True)
class ReplayVerificationError(Exception):
    failure: ReplayFailure

    def __str__(self) -> str:
        return self.failure.message


@dataclass(frozen=True, slots=True)
class ReplayResult:
    input_dir: Path
    run_id: str
    ticks: int
    event_count: int
    deterministic_controls: bool

    def evidence(self) -> JsonObject:
        return {
            "script": "replay_run",
            "status": "ok",
            "input": str(self.input_dir),
            "run_id": self.run_id,
            "verified_ticks": self.ticks,
            "verified_events": self.event_count,
            "deterministic_controls": self.deterministic_controls,
        }


@dataclass(frozen=True, slots=True)
class ExpectedEvent:
    frame_type: str
    frame_index: int
    sequence: int

    def evidence(self) -> JsonObject:
        return {
            "expected_type": self.frame_type,
            "expected_frame_index": self.frame_index,
            "sequence": self.sequence,
        }


@dataclass(frozen=True, slots=True)
class ControlReplayInput:
    config: MotorDecoderConfig
    previous_state: MotorDecoderState | None
    sensory: SensoryFrame
    brain: BrainFrame
    control: ControlFrame


def verify_replay(input_dir: Path) -> ReplayResult:
    summary = _load_summary(input_dir / "summary.json")
    frames = _load_frames(input_dir / "frames.jsonl")
    _verify_sequence(summary, frames)
    _verify_count(summary, frames)
    config = _load_runtime_config(summary.config_path)
    decoder_config = MotorDecoderConfig.from_runtime_thresholds(config.decoder)
    previous_state: MotorDecoderState | None = None
    for tick in range(summary.ticks):
        sensory = _as_sensory(frames[tick * 3])
        brain = _as_brain(frames[(tick * 3) + 1])
        control = _as_control(frames[(tick * 3) + 2])
        _verify_brain(sensory, brain)
        previous_state = _verify_control(ControlReplayInput(decoder_config, previous_state, sensory, brain, control))
    return ReplayResult(input_dir, summary.run_id, summary.ticks, len(frames), True)


def write_replay_success(input_dir: Path, result: ReplayResult) -> None:
    write_json_evidence(input_dir / "replay_evidence.json", result.evidence())


def write_replay_failure(input_dir: Path, failure: ReplayFailure) -> None:
    payload: JsonObject = {
        "script": "replay_run",
        "status": "failed",
        "input": str(input_dir),
        "error_code": failure.code,
        "error": failure.message,
        "failure": failure.details,
    }
    write_json_evidence(input_dir / "replay_evidence.json", payload)


def summarize_replay(input_dir: Path) -> JsonObject:
    summary = _load_summary(input_dir / "summary.json")
    frames = _load_frames(input_dir / "frames.jsonl")
    return {"script": "replay_run", "status": "summary", "run_id": summary.run_id, "ticks": summary.ticks, "events": len(frames)}


def _load_summary(path: Path) -> RunSummary:
    raw = _load_json(path)
    return RunSummary(
        run_id=_str_field(raw, "run_id"),
        ticks=_int_field(raw, "ticks"),
        tick_ms=_int_field(raw, "tick_ms"),
        frame_count=_int_field(raw, "frame_count"),
        config_path=Path(_str_field(raw, "config")),
    )


def _load_frames(path: Path) -> list[BridgeFrame]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise ReplayVerificationError(ReplayFailure("missing_artifact", f"missing {path}", {"path": str(path)})) from exc
    frames: list[BridgeFrame] = []
    for line_number, line in enumerate(lines, start=1):
        frame = decode_message(line.encode("utf-8"))
        match frame:
            case ErrorFrame(code=code, message=message):
                raise ReplayVerificationError(
                    ReplayFailure("malformed_frame", message, {"line_number": line_number, "decode_code": code})
                )
            case _:
                frames.append(frame)
    return frames


def _verify_count(summary: RunSummary, frames: list[BridgeFrame]) -> None:
    expected = summary.ticks * len(EVENT_TYPES)
    if len(frames) != expected or summary.frame_count != expected:
        missing = _expected_event(min(len(frames), expected - 1))
        details = {"expected_events": expected, "actual_events": len(frames), "summary_frame_count": summary.frame_count}
        details.update(missing.evidence())
        raise ReplayVerificationError(
            ReplayFailure(
                "message_loss",
                "frame count does not match expected ticks/events",
                details,
            )
        )


def _verify_sequence(summary: RunSummary, frames: list[BridgeFrame]) -> None:
    for sequence, frame in enumerate(frames):
        expected = _expected_event(sequence)
        actual_type = _frame_type(frame)
        actual_index = frame.frame_index
        if actual_type != expected.frame_type or actual_index != expected.frame_index:
            details = expected.evidence()
            details.update({"actual_type": actual_type, "actual_frame_index": actual_index, "sequence": sequence})
            raise ReplayVerificationError(ReplayFailure("missing_or_reordered_frame", "frame continuity/order mismatch", details))
        if frame.run_id != summary.run_id:
            raise ReplayVerificationError(
                ReplayFailure("run_id_mismatch", "frame run_id does not match summary", {"sequence": sequence, "expected_run_id": summary.run_id, "actual_run_id": frame.run_id})
            )
        expected_time = expected.frame_index * summary.tick_ms / 1000.0
        if not math.isclose(frame.simulation_time_s, expected_time, rel_tol=0.0, abs_tol=1e-12):
            raise ReplayVerificationError(
                ReplayFailure("frame_time_mismatch", "frame simulation time is not continuous", {"sequence": sequence, "expected_simulation_time_s": expected_time, "actual_simulation_time_s": frame.simulation_time_s})
            )
        if isinstance(frame, PayloadFrame) and payload_checksum(frame.payload) != frame.payload_checksum:
            raise ReplayVerificationError(ReplayFailure("checksum_mismatch", "payload checksum mismatch", {"sequence": sequence}))


def _verify_brain(sensory: SensoryFrame, brain: BrainFrame) -> None:
    expected = build_fixture_brain_frame(sensory)
    if brain.payload != expected.payload or brain.payload_checksum != expected.payload_checksum:
        raise ReplayVerificationError(
            ReplayFailure("brain_replay_mismatch", "deterministic fixture brain payload changed", {"frame_index": sensory.frame_index})
        )


def _verify_control(data: ControlReplayInput) -> MotorDecoderState:
    expected = decode_motor_control(
        MotorDecoderRequest(
            readout=BrainFrameReadout(data.brain),
            config=data.config,
            sensory=decoder_context_from_sensory(data.sensory),
            previous_state=data.previous_state,
        )
    )
    if data.control.payload != expected.payload or data.control.payload_checksum != expected.control_frame.payload_checksum:
        raise ReplayVerificationError(
            ReplayFailure("control_replay_mismatch", "deterministic decoded control payload changed", {"frame_index": data.control.frame_index})
        )
    return expected.state


def _expected_event(sequence: int) -> ExpectedEvent:
    return ExpectedEvent(EVENT_TYPES[sequence % len(EVENT_TYPES)], sequence // len(EVENT_TYPES), sequence)


def _load_runtime_config(path: Path) -> RuntimeConfig:
    try:
        return load_config(path)
    except ConfigError as exc:
        raise ReplayVerificationError(ReplayFailure("config_error", str(exc), {"config": str(path)})) from exc


def _load_json(path: Path) -> JsonObject:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReplayVerificationError(ReplayFailure("missing_artifact", f"missing {path}", {"path": str(path)})) from exc
    except json.JSONDecodeError as exc:
        raise ReplayVerificationError(ReplayFailure("malformed_artifact", str(exc), {"path": str(path)})) from exc
    if isinstance(raw, dict):
        return raw
    raise ReplayVerificationError(ReplayFailure("malformed_artifact", "summary must be a JSON object", {"path": str(path)}))


def _str_field(raw: JsonObject, field: str) -> str:
    value = raw.get(field)
    if isinstance(value, str) and value != "":
        return value
    raise ReplayVerificationError(ReplayFailure("malformed_artifact", f"{field} must be a non-empty string", {"field": field}))


def _int_field(raw: JsonObject, field: str) -> int:
    value = raw.get(field)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise ReplayVerificationError(ReplayFailure("malformed_artifact", f"{field} must be an integer", {"field": field}))


def _as_sensory(frame: BridgeFrame) -> SensoryFrame:
    match frame:
        case SensoryFrame():
            return frame
        case _:
            raise ReplayVerificationError(ReplayFailure("internal_sequence_error", "expected sensory frame", {"actual_type": _frame_type(frame)}))


def _as_brain(frame: BridgeFrame) -> BrainFrame:
    match frame:
        case BrainFrame():
            return frame
        case _:
            raise ReplayVerificationError(ReplayFailure("internal_sequence_error", "expected brain frame", {"actual_type": _frame_type(frame)}))


def _as_control(frame: BridgeFrame) -> ControlFrame:
    match frame:
        case ControlFrame():
            return frame
        case _:
            raise ReplayVerificationError(ReplayFailure("internal_sequence_error", "expected control frame", {"actual_type": _frame_type(frame)}))


def _frame_type(frame: BridgeFrame) -> str:
    match frame:
        case Hello():
            return "hello"
        case SensoryFrame():
            return "sensory_frame"
        case BrainFrame():
            return "brain_frame"
        case ControlFrame():
            return "control_frame"
        case Heartbeat():
            return "heartbeat"
        case ErrorFrame():
            return "error"
        case Shutdown():
            return "shutdown"
        case unreachable:
            assert_never(unreachable)
