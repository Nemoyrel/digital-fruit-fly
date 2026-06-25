from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from digital_fruit_fly.arena.model import FlyPose2D
from digital_fruit_fly.bridge.fixture_model import (
    BridgeSmokeError,
    FixtureLoop,
    build_fixture_brain_frame,
    decoder_context_from_sensory,
    feedback_numbers,
    fixture_observation,
    initial_loop,
    next_loop,
    sensory_payload,
)
from digital_fruit_fly.bridge.messages import (
    SCHEMA_VERSION,
    BrainFrame,
    ControlFrame,
    ErrorFrame,
    JsonObject,
    JsonValue,
    SensoryFrame,
    decode_message,
    encode_message,
    payload_checksum,
)
from digital_fruit_fly.bridge.motor_decoder import (
    BrainFrameReadout,
    MotorDecoderRequest,
    decode_motor_control,
)
from digital_fruit_fly.bridge.sensory_encoder import SensoryEncodingRequest
from digital_fruit_fly.runtime.config import RuntimeConfig
from digital_fruit_fly.runtime.timeouts import write_json_evidence

EVENT_TYPES: Final = ("sensory_frame", "brain_frame", "control_frame")
CANONICAL_ARTIFACTS: Final = ("frames.jsonl", "summary.json", "replay_evidence.json", "behavior_summary.json", "error.json")


@dataclass(frozen=True, slots=True)
class BridgeSmokeRequest:
    config_path: Path
    config: RuntimeConfig
    ticks: int
    output_dir: Path


@dataclass(frozen=True, slots=True)
class BridgeSmokeResult:
    run_id: str
    ticks: int
    tick_ms: int
    frame_count: int
    frames_path: Path
    summary_path: Path
    duration_sec: float

    def evidence(self) -> JsonObject:
        return {
            "script": "smoke_bridge",
            "status": "ok",
            "run_id": self.run_id,
            "ticks": self.ticks,
            "tick_ms": self.tick_ms,
            "frame_count": self.frame_count,
            "events_per_tick": list(EVENT_TYPES),
            "duration_sec": self.duration_sec,
            "artifacts": [str(self.frames_path), str(self.summary_path)],
        }


def write_fixture_smoke(request: BridgeSmokeRequest) -> BridgeSmokeResult:
    if request.ticks <= 0:
        raise BridgeSmokeError("ticks must be positive")
    request.output_dir.mkdir(parents=True, exist_ok=True)
    _remove_canonical_artifacts(request.output_dir)
    frames_path = request.output_dir / "frames.jsonl"
    summary_path = request.output_dir / "summary.json"
    run_id = f"bridge-smoke-{time.time_ns()}"
    loop = initial_loop(run_id, request.config)
    started = time.monotonic()
    frame_count = 0
    with frames_path.open("w", encoding="utf-8") as frames_file:
        for tick in range(request.ticks):
            tick_result = _run_tick(loop, tick)
            for frame in tick_result.frames:
                frames_file.write(encode_message(frame).decode("utf-8") + "\n")
                frame_count += 1
            loop = tick_result.loop
    result = BridgeSmokeResult(run_id, request.ticks, request.config.tick_ms, frame_count, frames_path, summary_path, time.monotonic() - started)
    payload = result.evidence()
    payload["config"] = str(request.config_path)
    write_json_evidence(summary_path, payload)
    return result


@dataclass(frozen=True, slots=True)
class TickResult:
    loop: FixtureLoop
    frames: tuple[SensoryFrame, BrainFrame, ControlFrame]


def _run_tick(loop: FixtureLoop, tick: int) -> TickResult:
    sim_time = tick * loop.config.tick_ms / 1000.0
    observation = fixture_observation(loop.body_state, loop.arena, loop.config.arena.dust.threshold)
    encoded = loop.encoder.encode(
        SensoryEncodingRequest(
            observation=observation,
            sugar_cue=loop.arena.sample_sugar_cue(FlyPose2D(loop.body_state.x_mm, loop.body_state.y_mm, loop.body_state.yaw_rad)),
            action_feedback=feedback_numbers(loop.body_state.action_feedback),
            source_metadata={"fixture_tick": tick},
        )
    )
    frame_payload = sensory_payload(tick, observation, encoded.rates_hz, encoded.audit)
    sensory = _decode_sensory(
        encode_message(
            SensoryFrame(
                SCHEMA_VERSION,
                loop.run_id,
                tick,
                sim_time,
                time.monotonic(),
                frame_payload,
                payload_checksum(frame_payload),
            )
        )
    )
    brain = _decode_brain(encode_message(build_fixture_brain_frame(sensory)))
    decoded = decode_motor_control(
        MotorDecoderRequest(
            readout=BrainFrameReadout(brain),
            config=loop.decoder_config,
            sensory=decoder_context_from_sensory(sensory),
            previous_state=loop.decoder_state,
        )
    )
    control = _decode_control(encode_message(decoded.control_frame))
    return TickResult(
        loop=next_loop(loop, control, decoded.state),
        frames=(sensory, brain, control),
    )


def _decode_sensory(data: bytes) -> SensoryFrame:
    frame = decode_message(data)
    match frame:
        case SensoryFrame():
            return frame
        case ErrorFrame(message=message):
            raise BridgeSmokeError(message)
        case _:
            raise BridgeSmokeError("expected sensory frame after protocol round-trip")


def _decode_brain(data: bytes) -> BrainFrame:
    frame = decode_message(data)
    match frame:
        case BrainFrame():
            return frame
        case ErrorFrame(message=message):
            raise BridgeSmokeError(message)
        case _:
            raise BridgeSmokeError("expected brain frame after protocol round-trip")


def _decode_control(data: bytes) -> ControlFrame:
    frame = decode_message(data)
    match frame:
        case ControlFrame():
            return frame
        case ErrorFrame(message=message):
            raise BridgeSmokeError(message)
        case _:
            raise BridgeSmokeError("expected control frame after protocol round-trip")




def _remove_canonical_artifacts(output_dir: Path) -> None:
    for name in CANONICAL_ARTIFACTS:
        (output_dir / name).unlink(missing_ok=True)
