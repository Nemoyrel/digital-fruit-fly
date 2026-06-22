"""脑/身体 IPC 桥的 JSON-lines 消息（纯标准库）。

传输格式是本项目自行实现的 TCP JSON-lines，并非 Eon 披露过的协议。
每条消息序列化为一行 UTF-8 JSON（以 ``\\n`` 结尾）。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from typing import Any


@dataclass(frozen=True)
class SensoryStateMessage:
    """身体 loop -> 脑 worker 的感觉状态请求。"""

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
    """脑 worker -> 身体 loop 的读出响应。

    ``neuron_activity`` 为采样子集的逐神经元脉冲计数（固定长度，用于脑活动面板）。
    """

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
    neuron_activity: list[int] = field(default_factory=list)
    active_neuron_count: int = 0
    total_neuron_count: int = 0
    extra: dict[str, Any] = field(default_factory=dict)
    type: str = "brain_readout"


def encode_message(message: SensoryStateMessage | BrainReadoutMessage) -> bytes:
    """把一条消息编码为以换行结尾的 UTF-8 JSON 字节串。"""
    return (json.dumps(asdict(message), sort_keys=True) + "\n").encode("utf-8")


def decode_message(raw: bytes | str) -> SensoryStateMessage | BrainReadoutMessage:
    """解码一行 JSON-lines 消息。"""
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    payload = json.loads(text.strip())
    msg_type = payload.pop("type", None)
    if msg_type == "sensory_state":
        return SensoryStateMessage(**payload)
    if msg_type == "brain_readout":
        return BrainReadoutMessage(**payload)
    raise ValueError(f"未知的 IPC 消息类型: {msg_type!r}")
