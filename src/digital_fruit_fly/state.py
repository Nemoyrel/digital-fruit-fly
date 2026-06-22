"""进程间共享的小型状态对象（纯标准库，导入无需 flygym/brian2）。

- ``BehaviorState``  果蝇行为状态机的有限状态。
- ``SensoryState``   身体侧由场景计算出的低维感觉量（送往脑）。
- ``BrainReadout``   脑侧返回、身体侧消费的低维读出（含用于可视化的神经元活动向量）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class BehaviorState(str, Enum):
    """果蝇脑/身体桥接使用的有限行为状态。"""

    FORAGING = "foraging"   # 觅食：无味觉线索随机搜索 / 有线索趋向食物
    GROOMING = "grooming"   # 梳理：灰尘达阈值，停步梳理
    FEEDING = "feeding"     # 进食：接触食物，停步进食
    HALTED = "halted"       # 停止（异常兜底）


@dataclass(frozen=True)
class SensoryState:
    """身体侧从场景生成、送往脑的低维感觉状态。"""

    time_s: float
    food_cue: float                 # 0..1，糖味觉/嗅觉线索强度
    turn_bias: float                # -1..1，趋向食物的转向偏置（叉积符号）
    dust_level: float               # 0..1，身体累积灰尘量
    dust_threshold_reached: bool    # 灰尘是否达到梳理阈值
    food_contact: bool              # 是否接触到食物
    food_distance_mm: float         # 到食物源中心的距离（mm）


@dataclass(frozen=True)
class BrainReadout:
    """脑侧返回、身体侧消费的低维读出。

    ``neuron_activity`` 是一个固定长度的逐神经元脉冲计数向量（采样子集），
    供右侧脑活动面板着色；为空表示本帧没有新的脑更新。
    """

    behavior_state: BehaviorState
    forward_drive: float
    turn_bias: float
    grooming_score: float
    feeding_score: float
    mn9_rate_hz: float
    dust_clearance: float = 0.0
    source: str = "pending"
    neuron_activity: tuple[int, ...] = field(default_factory=tuple)
    active_neuron_count: int = 0
    total_neuron_count: int = 0
