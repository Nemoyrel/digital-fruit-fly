"""运动解码 + 行为状态机（身体侧）。

把脑返回的 DN 放电率读出（``MotorMessage.readout_rates_hz``）解码成 HybridTurningController
的 [left, right] 下行驱动，并按 grooming > feeding > foraging 优先级做时序仲裁。

解码（觅食 foraging）：
- 前进 = oDN1(L+R 均值)归一化 → forward
- 转向 = (DNa01+DNa02 左) − (右)，归一化 → turn（>0 左转）。单窗单神经元读出很噪，用 EMA 平滑。
- [left, right] = [forward − turn, forward + turn]（与 HybridTurningController 一致：turn>0 右腿驱动强 → 左转）

行为门控：
- 梳理：**脑通路 grooming_readout(aBN1/aDN1/aDN2) 放电过阈** → 进入 grooming（持续 grooming_duration_s），
  结束清零灰尘。灰尘只决定身体侧是否注入 JON_groom；梳理的触发由真脑通路 JON→aBN1→aDN 涌现决定
  （含传导潜伏期，故用 EMA 平滑过阈，见 docs/GROOMING_PATHWAY_VERIFICATION.md）。
- 进食：接触食物且 **MN9 真实放电** > 阈值 → feeding（持续 feeding_hold_s）。MN9 来自糖→连接组真涌现。
- 觅食：其余，按 DN 读出行走/转向。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..bridge.messages import MotorMessage


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


@dataclass
class MotorConfig:
    grooming_duration_s: float = 1.2
    feeding_hold_s: float = 1.5
    feeding_refractory_s: float = 2.5     # 一次进食后多久内不再进食(让果蝇走开)
    feeding_mn9_threshold_hz: float = 25.0
    dust_threshold: float = 1.0
    forward_norm_hz: float = 150.0
    forward_gain: float = 1.1
    max_forward: float = 1.3
    min_forward: float = 0.2
    turn_norm_hz: float = 150.0
    turn_gain: float = 2.0
    max_turn: float = 0.6
    ema_alpha: float = 0.35           # 转向/前进/梳理 EMA 平滑系数
    arrive_slowdown: float = 0.85     # 接近食物(cue→1)时前进减速比例 → 驻留食物附近，不冲出
    grooming_readout_threshold_hz: float = 8.0   # 脑通路 grooming_readout(aBN1/aDN1/aDN2)均值 EMA 过阈→梳理
    grooming_refractory_s: float = 6.0   # 一次梳理后多久内不再梳理(防反复梳理打断觅食/便于演示一次清晰梳理)


@dataclass
class Decision:
    behavior: str
    left: float
    right: float
    forward: float
    turn: float


class MotorController:
    """有状态：行为时序仲裁 + DN 读出解码 + 平滑。"""

    def __init__(self, config: MotorConfig | None = None) -> None:
        self.config = config or MotorConfig()
        self.behavior = "foraging"
        self.state_until_s = 0.0
        self.just_completed_grooming = False
        self._last_feed_end_s = -1e9
        self._last_groom_end_s = -1e9
        self._fwd_ema = 0.6
        self._turn_ema = 0.0
        self._groom_ema = 0.0

    @property
    def grooming_signal_hz(self) -> float:
        """梳理脑通路 grooming_readout(aBN1/aDN1/aDN2 均值) 的 EMA，供 viz/外部判定。

        升级后梳理由真脑通路 JON→aBN1→aDN 驱动，此 EMA 即触发梳理用的信号；
        脑活动面板的 grooming 高亮/读数应取此值（而非 aDN1 单读——在线 15ms 窗量化跳动大）。
        """
        return self._groom_ema

    @staticmethod
    def _g(rates: dict[str, float], *keys: str) -> float:
        return sum(rates.get(k, 0.0) for k in keys)

    def decide(self, motor: MotorMessage, *, time_s: float,
               dust_level: float, food_contact: bool, cue: float = 0.0) -> Decision:
        cfg = self.config
        r = motor.readout_rates_hz
        self.just_completed_grooming = False

        # ---- DN 读出解码（始终平滑，供 foraging 用）----
        fwd_raw = self._g(r, "odn1_left", "odn1_right") / 2.0 / max(1e-6, cfg.forward_norm_hz)
        left_dn = self._g(r, "dna01_left", "dna02_left")
        right_dn = self._g(r, "dna01_right", "dna02_right")
        turn_raw = cfg.turn_gain * (left_dn - right_dn) / max(1e-6, cfg.turn_norm_hz)
        a = cfg.ema_alpha
        self._fwd_ema = (1 - a) * self._fwd_ema + a * fwd_raw
        self._turn_ema = (1 - a) * self._turn_ema + a * turn_raw
        # 梳理脑信号：grooming_readout(aBN1/aDN1/aDN2 均值) EMA。真脑通路 JON→aBN1→aDN 过阈才梳理。
        self._groom_ema = (1 - a) * self._groom_ema + a * r.get("grooming_readout", 0.0)
        forward = _clip(cfg.forward_gain * self._fwd_ema, cfg.min_forward, cfg.max_forward)
        turn = _clip(self._turn_ema, -cfg.max_turn, cfg.max_turn)

        mn9 = r.get("mn9", 0.0)

        # ---- 行为时序仲裁（优先级 grooming > feeding > foraging）----
        # 1) 到时退出当前定时态
        if self.behavior == "grooming" and time_s >= self.state_until_s:
            self.behavior = "foraging"
            self.just_completed_grooming = True       # 触发清零灰尘
            self._last_groom_end_s = time_s           # 起梳理不应期，避免反复梳理
        elif self.behavior == "feeding" and time_s >= self.state_until_s:
            self.behavior = "foraging"
            self._last_feed_end_s = time_s            # 起进食不应期，走开后才会再进食

        # 2) 梳理抢占一切（脑通路 grooming_readout 过阈 → JON→aBN1→aDN 真涌现触发，非灰尘直接拍板）
        #    加梳理不应期：一次梳理后一段时间内不再触发，避免反复梳理把觅食切碎
        can_groom = (time_s - self._last_groom_end_s) >= cfg.grooming_refractory_s
        if (self._groom_ema >= cfg.grooming_readout_threshold_hz
                and self.behavior != "grooming" and can_groom):
            self.behavior = "grooming"
            self.state_until_s = time_s + cfg.grooming_duration_s
        if self.behavior == "grooming":
            return Decision("grooming", 0.0, 0.0, 0.0, 0.0)

        # 3) 进食（定时一段；接触食物 + MN9 真实放电 + 不在不应期）
        can_feed = (time_s - self._last_feed_end_s) >= cfg.feeding_refractory_s
        if (food_contact and mn9 >= cfg.feeding_mn9_threshold_hz
                and self.behavior != "feeding" and can_feed):
            self.behavior = "feeding"
            self.state_until_s = time_s + cfg.feeding_hold_s
        if self.behavior == "feeding":
            return Decision("feeding", 0.0, 0.0, 0.0, 0.0)

        # 4) 觅食：DN 调制行走（接近食物按 cue 减速 → 驻留食物附近，避免冲过/进食后冲出场地）
        self.behavior = "foraging"
        forward *= 1.0 - cfg.arrive_slowdown * _clip(cue, 0.0, 1.0)
        left = _clip(forward - turn, -1.0, cfg.max_forward)
        right = _clip(forward + turn, -1.0, cfg.max_forward)
        return Decision("foraging", left, right, forward, turn)
