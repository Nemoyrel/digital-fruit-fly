from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from digital_fruit_fly.arena.dust import DustState
from digital_fruit_fly.arena.model import FlyPose2D
from digital_fruit_fly.body.controllers import BodyCommand, BodyControllerContract
from digital_fruit_fly.bridge.messages import BrainFrame, ControlFrame, SensoryFrame
from digital_fruit_fly.runtime.config import RuntimeConfig
from digital_fruit_fly.runtime.run_manifest import RunLayout
from digital_fruit_fly.runtime.timeouts import JsonObject

BrainMode = Literal["fixture", "connect"]
ServerStatus = Literal["ok", "error"]
BrainReply = BrainFrame | ControlFrame


@dataclass(frozen=True, slots=True)
class BodyServerConfigError(Exception):
    field: str
    reason: str

    def __str__(self) -> str:
        return f"{self.field}: {self.reason}"


@dataclass(frozen=True, slots=True)
class BodyServerRuntimeError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class BodyServerConfig:
    config_path: Path
    output_dir: Path
    brain_mode: BrainMode
    max_ticks: int
    timeout_s: float
    host: str
    brain_port: int
    record_codec: str
    viewer_requested: bool

    def __post_init__(self) -> None:
        if self.brain_mode not in ("fixture", "connect"):
            raise BodyServerConfigError("brain_mode", "must be fixture or connect")
        if self.max_ticks <= 0:
            raise BodyServerConfigError("max_ticks", "must be positive")
        if self.timeout_s <= 0.0:
            raise BodyServerConfigError("timeout_s", "must be positive")
        if self.host == "":
            raise BodyServerConfigError("host", "must not be empty")
        if self.brain_port < 1 or self.brain_port > 65535:
            raise BodyServerConfigError("brain_port", "must be between 1 and 65535")


@dataclass(frozen=True, slots=True)
class BodyServerResult:
    status: ServerStatus
    exit_code: int
    ticks: int
    run_dir: Path
    manifest_path: Path
    events_path: Path
    trajectory_path: Path
    control_path: Path
    arena_path: Path
    recording_metadata_path: Path


@dataclass(frozen=True, slots=True)
class BodyLoopResult:
    ticks: int
    flygym: JsonObject


@dataclass(frozen=True, slots=True)
class BodyArtifacts:
    layout: RunLayout
    frames_path: Path
    trajectory_path: Path


@dataclass(frozen=True, slots=True)
class BodySimulation:
    runtime: RuntimeConfig
    contract: BodyControllerContract


@dataclass(frozen=True, slots=True)
class BodyRunContext:
    config: BodyServerConfig
    artifacts: BodyArtifacts
    simulation: BodySimulation

    @property
    def tick_seconds(self) -> float:
        return self.simulation.runtime.tick_ms / 1000.0


@dataclass(frozen=True, slots=True)
class BodyState:
    pose: FlyPose2D
    dust: DustState


@dataclass(frozen=True, slots=True)
class TickInputs:
    state: BodyState
    sensory: SensoryFrame
    brain: BrainReply
    control: ControlFrame


@dataclass(frozen=True, slots=True)
class TickRecord:
    state: BodyState
    sensory: SensoryFrame
    brain: BrainReply
    control: ControlFrame
    command: BodyCommand
    collided: bool
    dust_events: tuple[JsonObject, ...]


class BrainPeer(Protocol):
    def next_frame(self, source: SensoryFrame) -> BrainReply: ...
    def shutdown(self, frame_index: int, simulation_time_s: float) -> None: ...
