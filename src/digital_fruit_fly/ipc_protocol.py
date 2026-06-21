"""JSON-lines messages for the L4 brain/body IPC bridge."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from typing import Any


@dataclass(frozen=True)
class SensoryStateMessage:
    """Serializable sensory-state request sent from body loop to brain worker."""

    request_id: int
    time_s: float
    food_cue: float
    turn_bias: float
    dust_level: float
    dust_threshold_reached: bool
    food_contact: bool
    food_distance_mm: float
    type: str = "sensory_state"


@dataclass(frozen=True)
class BrainReadoutMessage:
    """Serializable readout response sent from brain worker to body loop."""

    request_id: int
    behavior_state: str
    forward_drive: float
    turn_bias: float
    grooming_score: float
    feeding_score: float
    mn9_rate_hz: float
    dust_clearance: float
    source: str
    backend: str
    brain_wall_time_ms: float
    brain_simulated_window_s: float
    cache_hit: bool
    extra: dict[str, Any] = field(default_factory=dict)
    type: str = "brain_readout"


def encode_message(message: SensoryStateMessage | BrainReadoutMessage) -> bytes:
    """Encode one message as newline-delimited UTF-8 JSON."""
    return (json.dumps(asdict(message), sort_keys=True) + "\n").encode("utf-8")


def decode_message(raw: bytes | str) -> SensoryStateMessage | BrainReadoutMessage:
    """Decode one newline-delimited JSON message."""
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    payload = json.loads(text.strip())
    msg_type = payload.pop("type", None)
    if msg_type == "sensory_state":
        return SensoryStateMessage(**payload)
    if msg_type == "brain_readout":
        return BrainReadoutMessage(**payload)
    raise ValueError(f"Unknown IPC message type: {msg_type!r}")
