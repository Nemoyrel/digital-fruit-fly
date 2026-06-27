"""脑后端：把身体侧 ``SensoryMessage`` 映射成脑内 Poisson 注入，推进一个同步窗，
读出 MN9 与各下行神经元(DN)放电率，返回 ``MotorMessage``。

注入分三类（依据实测，见 docs/GROOMING_PATHWAY_VERIFICATION.md 与记忆 dn-emergence-does-not-work）：
1. **真涌现通路·进食**：味觉(接触)→ 糖 GRN → 下游 → MN9 放电（进食由连接组真正算出）；
   嗅觉(气味)→ ORN（双侧，主要点亮嗅觉区供可视化）。
2. **真涌现通路·梳理**：灰尘 → JON_groom(Shiu Fig5 机械感受梳理 JON) → 全脑传播
   JON→aBN1→aDN1/aDN2 → 身体侧读 grooming_readout 过阈触发（2026-06 独立验证证实，非直驱）。
3. **直驱 DN 控制句柄**（Eon「人工指定的控制句柄」做法）：前进 oDN1 / 转向 DNa01·DNa02
   由身体侧算出意图后直接注入，经全脑传播读出放电率交身体侧解码（转向/前进的感觉涌现不成立，故直驱）。

后端**无状态**：行为仲裁(grooming>feeding>foraging 的时序状态机)放在身体侧 MotorController。
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
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
    jon_max_hz: float = 0.0           # JO-B(听觉)注入；与梳理无关(梳理走 jon_groom)，>0 会锁死，默认关
    # DN 控制句柄驱动频率
    forward_hz: float = 150.0         # oDN1 前进
    forward_base: float = 0.6         # 觅食基线前进占比（无气味也前行以便搜索）
    turn_hz: float = 150.0            # DNa01/02 转向(按同侧气味)
    search_hz: float = 90.0           # 无气味时的搜索摆动幅度
    search_freq_hz: float = 0.3       # 搜索摆动频率
    groom_jon_hz: float = 160.0       # 灰尘→注入 JON_groom→脑通路 JON→aBN1→aDN(真涌现, 非直驱)
    dust_threshold: float = 1.0
    cue_eps: float = 0.05

    @classmethod
    def from_dict(cls, d: dict | None) -> "BackendConfig":
        """从配置 dict（simulation.json 的 brain 组）构造。

        忽略未知键（避免 ``**`` 解包炸），未给的字段用默认值。故 orn_max_hz/jon_max_hz
        若不写即保持默认 0（不触发全脑锁死，见上方警告）。
        """
        if not d:
            return cls()
        names = {f.name for f in fields(cls)}
        return replace(cls(), **{k: float(v) for k, v in d.items() if k in names})


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
        # 梳理：灰尘达阈值 → 注入 JON_groom(Shiu Fig5 机械感受梳理 JON)，经全脑连接组
        # 传播 JON→aBN1→aDN1/aDN2（真脑通路，非直驱 aDN 句柄）。行为触发由身体侧
        # MotorController 读 grooming_readout(aBN1/aDN1/aDN2) 过阈决定（含通路潜伏期）。
        dust = max(msg.dust_level_left, msg.dust_level_right)
        inj["jon_groom"] = c.groom_jon_hz if dust >= c.dust_threshold else 0.0
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
