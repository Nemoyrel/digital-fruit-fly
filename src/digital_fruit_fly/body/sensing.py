"""身体侧虚拟感觉编码 —— 产出**双侧**感觉强度，喂给脑模型。

flygym 2.0.2 没有气味物理，故由果蝇位姿几何合成感觉输入：
- 嗅觉/味觉线索：到食物源的高斯羽流强度（覆盖一定面积），并按食物相对航向的左右偏置
  拆成 ``food_cue_left`` / ``food_cue_right``。**左右不对称的感觉输入是脑内 DNa01/DNa02
  差分放电（→ 转向）的来源**——转向决策在脑里做，这里只提供不对称的感觉刺激。
- 机械感受：灰尘随时间累积（无方向性，左右对称），达阈值触发梳理；梳理后清零。
- 接触：到食物中心距离 ≤ 接触半径 → ``food_contact``（进食门控）。

纯标准库（导入无需 flygym/brian2）。这是本项目的工程桥接，非 Shiu 模型组成部分。
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, hypot
from typing import Any


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


@dataclass(frozen=True)
class SceneConfig:
    arena_half_size_mm: float = 60.0
    food_position_mm: tuple[float, float] = (30.0, 20.0)
    food_cue_radius_mm: float = 20.0          # 嗅觉羽流半径
    food_contact_radius_mm: float = 3.0       # 接触/进食判定半径
    dust_accumulation_rate_per_s: float = 0.6  # 每秒灰尘累积
    dust_threshold: float = 1.0
    bilateral_gain: float = 0.6               # 左右感觉不对称增益（驱动 DN 差分）

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SceneConfig":
        return cls(
            arena_half_size_mm=float(d.get("arena_half_size_mm", 60.0)),
            food_position_mm=tuple(d.get("food_position_mm", (30.0, 20.0))),
            food_cue_radius_mm=float(d.get("food_cue_radius_mm", 20.0)),
            food_contact_radius_mm=float(d.get("food_contact_radius_mm", 3.0)),
            dust_accumulation_rate_per_s=float(d.get("dust_accumulation_rate_per_s", 0.6)),
            dust_threshold=float(d.get("dust_threshold", 1.0)),
            bilateral_gain=float(d.get("bilateral_gain", 0.6)),
        )


@dataclass(frozen=True)
class BilateralSensory:
    time_s: float
    food_cue_left: float
    food_cue_right: float
    dust_level_left: float
    dust_level_right: float
    food_contact: bool
    food_distance_mm: float
    dust_threshold_reached: bool


class SensoryEncoder:
    """由果蝇位姿生成双侧感觉状态。"""

    def __init__(self, config: SceneConfig | None = None) -> None:
        self.config = config or SceneConfig()
        self.dust_level = 0.0
        self._last_time_s: float | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SensoryEncoder":
        return cls(SceneConfig.from_dict(d))

    def clear_dust(self) -> None:
        self.dust_level = 0.0

    def observe(
        self,
        time_s: float,
        fly_xy_mm: tuple[float, float],
        heading_xy: tuple[float, float],
        *,
        accumulate_dust: bool = True,
    ) -> BilateralSensory:
        cfg = self.config
        dt = 0.0 if self._last_time_s is None else max(0.0, time_s - self._last_time_s)
        self._last_time_s = time_s

        fx, fy = cfg.food_position_mm
        dx, dy = fx - fly_xy_mm[0], fy - fly_xy_mm[1]
        dist = hypot(dx, dy)

        # 高斯羽流基线强度（cue 半径外置 0）
        sigma = max(1e-6, cfg.food_cue_radius_mm) / 1.5
        base = _clip(exp(-((dist / sigma) ** 2)), 0.0, 1.0)
        if dist > cfg.food_cue_radius_mm:
            base = 0.0

        # 左右不对称：叉积符号判断食物在航向左/右侧
        hx, hy = heading_xy
        hn = hypot(hx, hy)
        if hn <= 1e-9:
            hx, hy = 1.0, 0.0
        else:
            hx, hy = hx / hn, hy / hn
        if base > 0.0 and dist > 1e-9:
            lateral = (hx * dy - hy * dx) / dist     # >0 食物在左侧
        else:
            lateral = 0.0
        g = cfg.bilateral_gain
        cue_left = _clip(base * (1.0 + g * lateral), 0.0, 1.0)
        cue_right = _clip(base * (1.0 - g * lateral), 0.0, 1.0)

        if accumulate_dust:
            self.dust_level = _clip(
                self.dust_level + dt * cfg.dust_accumulation_rate_per_s, 0.0, cfg.dust_threshold
            )

        return BilateralSensory(
            time_s=time_s,
            food_cue_left=cue_left,
            food_cue_right=cue_right,
            dust_level_left=self.dust_level,
            dust_level_right=self.dust_level,
            food_contact=dist <= cfg.food_contact_radius_mm,
            food_distance_mm=dist,
            dust_threshold_reached=self.dust_level >= cfg.dust_threshold,
        )
