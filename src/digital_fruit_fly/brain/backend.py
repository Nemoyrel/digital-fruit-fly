"""脑后端：把身体侧 ``SensoryMessage`` 映射成脑内 Poisson 注入，推进一个同步窗，
读出 MN9 与各下行神经元(DN)放电率，返回 ``MotorMessage``。

注入分两类（依据实测，见项目记忆 dn-emergence-does-not-work）：
1. **真涌现通路**：味觉(接触)→ 糖 GRN → 下游 → MN9 放电（进食由连接组真正算出）；
   嗅觉(气味)→ ORN（双侧，主要点亮嗅觉区供可视化）。
2. **直驱 DN 控制句柄**（Eon「人工指定的控制句柄」做法）：身体侧感觉算出意图后，
   直接注入 oDN1(前进)/DNa01·DNa02(左右转向)/aDN1(梳理)，经全脑连接组传播，
   读出其放电率交给身体侧解码。直驱使读出干净跟随意图（实测句柄注入压过 ORN 涌现偏置）。

后端**无状态**：行为仲裁(grooming>feeding>foraging 的时序状态机)放在身体侧 MotorController。
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sin, pi

from .online_brain import OnlineBrain, OnlineBrainConfig
from ..bridge.messages import MotorMessage, SensoryMessage


@dataclass
class BackendConfig:
    # 感觉 → Poisson 频率(Hz)标定（本项目工程设定；Eon 未公布，博客列为开放问题）
    #
    # ⚠ 重要：实测连续积分下，强驱**大群感觉神经元**(ORN 35/侧、JON 165/侧)会触发全脑
    # 自持递归活动「锁死」（active 飙到 ~5500 且去刺激后回不来；ORN 低至 ~8Hz 即触发）。
    # 故 ORN/JON 注入默认**关闭**——本项目转向/前进/梳理走直驱 DN 句柄、进食走糖→MN9，
    # 均不需要这两条感觉群涌现。仅糖(20)+DN 句柄(单神经元)注入时全程低活动(active<260)、稳定。
    orn_max_hz: float = 0.0           # 嗅觉(双侧)；>0 会锁死，仅在确需嗅觉 viz 且接受锁死时启用
    sugar_max_hz: float = 150.0       # 味觉(接触) → 驱动 MN9 进食涌现（唯一保留的涌现通路）
    jon_max_hz: float = 0.0           # 机械感受(灰尘)；同样会锁死，默认关
    # DN 控制句柄驱动频率
    forward_hz: float = 150.0         # oDN1 前进
    forward_base: float = 0.6         # 觅食基线前进占比（无气味也前行以便搜索）
    turn_hz: float = 150.0            # DNa01/02 转向(按同侧气味)
    search_hz: float = 90.0           # 无气味时的搜索摆动幅度
    search_freq_hz: float = 0.3       # 搜索摆动频率
    groom_hz: float = 150.0           # aDN1 梳理
    dust_threshold: float = 1.0
    cue_eps: float = 0.05


class BrainBackend:
    """无状态脑后端：SensoryMessage -> 注入 -> 推进 -> MotorMessage。"""

    def __init__(self, brain: OnlineBrain, config: BackendConfig | None = None) -> None:
        self.brain = brain
        self.config = config or BackendConfig()
        self.request_count = 0

    @classmethod
    def build(cls, *, window_ms: float = 15.0, backend_config: BackendConfig | None = None) -> "BrainBackend":
        brain = OnlineBrain(OnlineBrainConfig(window_ms=window_ms, continuous=True))
        return cls(brain, backend_config)

    def _injection(self, msg: SensoryMessage) -> dict[str, float]:
        c = self.config
        cl, cr = msg.food_cue_left, msg.food_cue_right
        cue = max(cl, cr)
        inj: dict[str, float] = {
            # 真涌现 + viz
            "orn_left": c.orn_max_hz * cl,
            "orn_right": c.orn_max_hz * cr,
            "sugar_grn": c.sugar_max_hz if msg.food_contact else 0.0,
            "jon_left": c.jon_max_hz * msg.dust_level_left,
            "jon_right": c.jon_max_hz * msg.dust_level_right,
            # 直驱 DN 句柄：前进
            "odn1_left": c.forward_hz * (c.forward_base + (1 - c.forward_base) * cue),
            "odn1_right": c.forward_hz * (c.forward_base + (1 - c.forward_base) * cue),
        }
        inj["odn1_right"] = inj["odn1_left"]
        # 转向 DNa01/02：按同侧气味强度（气味强的一侧 DN 更活跃）
        turn_l = c.turn_hz * cl
        turn_r = c.turn_hz * cr
        # 无气味时叠加搜索摆动（沿时间正弦左右扫）
        if cue < c.cue_eps:
            osc = sin(2 * pi * c.search_freq_hz * msg.time_s)
            turn_l += c.search_hz * max(0.0, osc)
            turn_r += c.search_hz * max(0.0, -osc)
        inj["dna01_left"] = turn_l
        inj["dna01_right"] = turn_r
        inj["dna02_left"] = turn_l
        inj["dna02_right"] = turn_r
        # 梳理 aDN1：灰尘达阈值
        dust = max(msg.dust_level_left, msg.dust_level_right)
        groom = c.groom_hz if dust >= c.dust_threshold else 0.0
        inj["adn1_left"] = groom
        inj["adn1_right"] = groom
        return inj

    def handle(self, msg: SensoryMessage) -> MotorMessage:
        self.request_count += 1
        readout = self.brain.step(self._injection(msg))
        return MotorMessage(
            request_id=msg.request_id,
            readout_rates_hz=readout.readout_rates_hz,
            behavior_state="",  # 行为仲裁由身体侧 MotorController 负责
            active_neuron_count=readout.active_neuron_count,
            total_neuron_count=readout.total_neuron_count,
            neuron_activity=readout.neuron_activity,
            brain_wall_time_ms=readout.wall_time_ms,
            window_s=readout.window_s,
            extra={"request_count": self.request_count},
        )

    def startup_info(self) -> dict:
        return self.brain.startup_info()
