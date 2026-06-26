"""脑/身体双进程 IPC 的消息定义（JSON-lines，纯标准库，两端各自 import）。

schema 面向「完全保真 DN 控制」设计：
- 身体→脑（``SensoryMessage``）：**双侧**感觉强度（左右触角分别），以便在脑内产生
  左右不对称的下行神经元(DN)放电，从而由 DNa01/DNa02 差分实现转向（而非几何兜底）。
- 脑→身体（``MotorMessage``）：**逐 DN 放电率**读出（dna01/dna02 左右、oDN1、MN9、aDN1 左右），
  由身体侧运动解码层换算成 HybridTurningController 的 [left, right] 驱动与进食/梳理动作。

传输为 TCP JSON-lines（本项目工程桥接，非 Eon 披露协议）：每条消息 = 一行 UTF-8 JSON + ``\\n``。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from typing import Any


@dataclass(frozen=True)
class SensoryMessage:
    """身体 → 脑：一个同步窗的双侧感觉状态。

    强度均为 0..1，由身体侧虚拟感觉编码（嗅觉羽流、接触、灰尘累积）算出，
    脑侧再线性映射到各感觉神经元的 Poisson 频率（默认上限 150 Hz，属本项目工程设定）。
    """

    request_id: int
    time_s: float
    food_cue_left: float          # 左触角嗅觉/味觉线索强度
    food_cue_right: float         # 右触角
    dust_level_left: float        # 左触角累积灰尘（→ 左 JON 机械感受）
    dust_level_right: float       # 右触角
    food_contact: bool            # 喙/腿接触糖（进食门控）
    food_distance_mm: float = -1.0
    type: str = "sensory"


@dataclass(frozen=True)
class MotorMessage:
    """脑 → 身体：一个同步窗后的逐 DN/运动神经元放电率读出（Hz）。

    ``neuron_activity`` 为下采样分箱脉冲数（脑活动面板用）。``readout_rates_hz`` 直接转发
    OnlineBrain 的读出字典，键 = neuron_ids.json 的 readout 组名。
    """

    request_id: int
    readout_rates_hz: dict[str, float] = field(default_factory=dict)
    behavior_state: str = "foraging"
    active_neuron_count: int = 0
    total_neuron_count: int = 0
    neuron_activity: list[int] = field(default_factory=list)
    brain_wall_time_ms: float = 0.0
    window_s: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)
    type: str = "motor"


def encode(message: SensoryMessage | MotorMessage) -> bytes:
    return (json.dumps(asdict(message), ensure_ascii=False) + "\n").encode("utf-8")


def decode(raw: bytes | str) -> SensoryMessage | MotorMessage:
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    payload = json.loads(text.strip())
    msg_type = payload.pop("type", None)
    if msg_type == "sensory":
        return SensoryMessage(**payload)
    if msg_type == "motor":
        return MotorMessage(**payload)
    raise ValueError(f"未知 IPC 消息类型: {msg_type!r}")
