"""场景感觉计算：把果蝇位姿 + 全局落尘转成低维 ``SensoryState``。

只依赖标准库（导入无需 flygym/brian2）。这里实现的是身体侧的**虚拟感觉编码**——
本项目自己的工程桥接，并非来自 Shiu 模型：
- 糖味觉/嗅觉线索 ``food_cue`` 由果蝇到食物源中心的距离按高斯羽流衰减得到（覆盖一定面积）；
- ``turn_bias`` 由航向与“指向食物”方向的叉积符号得到（有线索时趋向食物）；
- 无线索时做周期性随机转向（随机搜索）；
- ``dust_level`` 随时间累积，达阈值触发梳理。
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, hypot
import random

from .state import SensoryState


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class SceneConfig:
    """L 场景的位置与阈值。"""

    arena_half_size_mm: float = 60.0
    food_position_mm: tuple[float, float] = (28.0, 6.0)
    food_cue_radius_mm: float = 26.0          # 嗅觉羽流半径（覆盖面积）
    food_contact_radius_mm: float = 3.0       # 接触/进食判定半径
    dust_accumulation_rate_per_s: float = 0.5  # 每秒灰尘累积速率
    dust_threshold: float = 1.0
    search_seed: int = 7
    search_turn_interval_s: float = 0.5
    search_turn_strength: float = 0.6

    @classmethod
    def from_dict(cls, data: dict) -> "SceneConfig":
        return cls(
            arena_half_size_mm=float(data.get("arena_half_size_mm", 60.0)),
            food_position_mm=tuple(data.get("food_position_mm", (28.0, 6.0))),
            food_cue_radius_mm=float(data.get("food_cue_radius_mm", 26.0)),
            food_contact_radius_mm=float(data.get("food_contact_radius_mm", 3.0)),
            dust_accumulation_rate_per_s=float(data.get("dust_accumulation_rate_per_s", 0.5)),
            dust_threshold=float(data.get("dust_threshold", 1.0)),
            search_seed=int(data.get("search_seed", 7)),
            search_turn_interval_s=float(data.get("search_turn_interval_s", 0.5)),
            search_turn_strength=float(data.get("search_turn_strength", 0.6)),
        )


class VirtualEnvironment:
    """由果蝇位姿与全局落尘生成感觉状态。"""

    def __init__(self, config: SceneConfig | None = None) -> None:
        self.config = config or SceneConfig()
        self.dust_level = 0.0
        self._last_time_s: float | None = None
        self._rng = random.Random(self.config.search_seed)
        self._search_turn_bias = 0.0
        self._next_search_turn_s = float("-inf")

    @classmethod
    def from_dict(cls, data: dict) -> "VirtualEnvironment":
        return cls(SceneConfig.from_dict(data))

    def clear_dust(self) -> None:
        """梳理完成后清零累积灰尘。"""
        self.dust_level = 0.0

    def _search_turn(self, time_s: float) -> float:
        if time_s >= self._next_search_turn_s:
            strength = max(0.0, float(self.config.search_turn_strength))
            self._search_turn_bias = self._rng.uniform(-strength, strength)
            interval = max(1e-9, float(self.config.search_turn_interval_s))
            self._next_search_turn_s = time_s + interval
        return self._search_turn_bias

    def observe(
        self,
        time_s: float,
        fly_xy_mm: tuple[float, float],
        heading_xy: tuple[float, float],
        *,
        accumulate_dust: bool = True,
    ) -> SensoryState:
        """返回当前果蝇位姿对应的虚拟感觉状态。"""
        dt = 0.0 if self._last_time_s is None else max(0.0, time_s - self._last_time_s)
        self._last_time_s = time_s

        fx, fy = self.config.food_position_mm
        dx, dy = fx - fly_xy_mm[0], fy - fly_xy_mm[1]
        food_distance = hypot(dx, dy)

        if accumulate_dust:
            self.dust_level = _clip(
                self.dust_level + dt * self.config.dust_accumulation_rate_per_s,
                0.0,
                self.config.dust_threshold,
            )

        hx, hy = heading_xy
        hnorm = hypot(hx, hy)
        if hnorm <= 1e-9:
            hx, hy = 1.0, 0.0
        else:
            hx, hy = hx / hnorm, hy / hnorm

        # 高斯羽流：在 cue 半径处约衰减到 ~0.1，半径内平滑升高
        sigma = max(1e-6, self.config.food_cue_radius_mm) / 1.5
        food_cue = _clip(exp(-((food_distance / sigma) ** 2)), 0.0, 1.0)
        if food_distance > self.config.food_cue_radius_mm:
            food_cue = 0.0
        food_contact = food_distance <= self.config.food_contact_radius_mm

        if food_cue <= 0.0:
            turn_bias = self._search_turn(time_s)
        elif food_distance <= 1e-9:
            turn_bias = 0.0
        else:
            # 叉积符号：>0 表示食物在航向左侧，需要左转
            turn_bias = (hx * dy - hy * dx) / food_distance

        return SensoryState(
            time_s=time_s,
            food_cue=food_cue,
            turn_bias=_clip(turn_bias, -1.0, 1.0),
            dust_level=self.dust_level,
            dust_threshold_reached=self.dust_level >= self.config.dust_threshold,
            food_contact=food_contact,
            food_distance_mm=food_distance,
        )
