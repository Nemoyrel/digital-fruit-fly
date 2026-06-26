"""在线运行时模式的 Shiu 全连接组脑（Brian2 runtime + 连续积分 + 分窗读出）。

与上游 ``model.py`` 的批处理设计（每 trial 重建网络、一次性 ``net.run``、落盘）不同，
本模块**建一次网络、长期持有、按同步窗（默认 15ms）分步推进**，并在每个窗口：
  1. 按身体侧感觉量设置各感觉通道的 Poisson 注入频率（运行时可变）；
  2. ``net.run(window)`` 增量推进（**不重置状态**——连续积分，保留跨窗的信号传导潜伏期）；
  3. 用 ``SpikeMonitor.count`` 的窗口差分读出 MN9 / 各下行神经元(DN) 的放电率。

为什么连续积分而非每窗 restore：实测糖 GRN→MN9 的信号潜伏期约 30ms，任何单个 15ms
窗内下游运动神经元都来不及放电。连续积分让感觉刺激的效应跨窗累积，符合生物学，也是
闭环能产生运动信号的前提。

关键工程点（复刻自已验证实现并升级）：
- 用 ``NeuronGroup(threshold='rand()<rate*dt')`` 作可运行时改频率的 Poisson 源，
  经 ``Synapses(on_pre='v_post += w')`` 注入目标神经元，权重 = ``w_syn * f_poi``，
  与上游 ``PoissonInput`` 等价但频率可在线修改。
- ``SpikeMonitor(neu, record=False)``：只累计每神经元 spike 数（``.count``），不存时间戳，
  省内存且大幅降低长跑开销。

Brian2 仅在 ``__init__`` 内惰性导入，故在无 brian2 的环境中也能 import 本模块（便于测试桩）。

边界：神经动力学与 LIF 参数来自 Shiu et al. 公开 Brian2 模型；感觉→Poisson 频率的标定、
DN 放电率→行为的解码是本项目自己的工程桥接。
"""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

from .neuron_ids import ResolvedNeurons, resolve_neurons

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SHIU_REPO = PROJECT_ROOT / "external" / "drosophila_brain_model"


@dataclass
class OnlineBrainConfig:
    """OnlineBrain 的构建与运行配置。"""

    comp_path: Path = SHIU_REPO / "Completeness_783.csv"
    con_path: Path = SHIU_REPO / "Connectivity_783.parquet"
    model_path: Path = SHIU_REPO / "model.py"
    ids_path: Path | None = None              # None=用 data/neuron_ids.json
    window_ms: float = 15.0                    # 脑-体同步窗（忠于 Eon 15ms）
    codegen_target: str = "cython"             # 'cython'(快, 需编译器) / 'numpy'(纯py兜底)
    record_spikes: bool = False                # False=只用 .count（推荐, 省内存）
    viz_neuron_count: int = 4000               # 送可视化的下采样分箱数
    continuous: bool = True                    # True=跨窗连续积分; False=每窗 restore baseline
    # 「直驱 DN 控制句柄」：除感觉神经元外，这些 readout 组也可被注入 Poisson（作控制句柄）。
    # 身体侧由感觉算出意图 → 注入这些 DN → 全脑传播 → 读 DN 放电 → 运动解码。
    handle_channels: tuple[str, ...] = (
        "dna01_left", "dna01_right", "dna02_left", "dna02_right",
        "odn1_left", "odn1_right", "adn1_left", "adn1_right",
    )


@dataclass
class WindowReadout:
    """单个同步窗推进后的读出。``readout_rates_hz`` 键 = neuron_ids.json 的 readout 组名。"""

    readout_rates_hz: dict[str, float] = field(default_factory=dict)
    active_neuron_count: int = 0
    total_neuron_count: int = 0
    neuron_activity: list[int] = field(default_factory=list)   # 下采样分箱脉冲数（viz）
    window_s: float = 0.0
    wall_time_ms: float = 0.0


class OnlineBrain:
    """在线运行时 Shiu 脑：建一次网, 分窗连续推进, 读出 DN/MN9 放电率。"""

    def __init__(self, config: OnlineBrainConfig | None = None) -> None:
        self.config = config or OnlineBrainConfig()
        self._build()

    # ------------------------------------------------------------------ build
    def _import_model(self):
        spec = importlib.util.spec_from_file_location("shiu_model", self.config.model_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _build(self) -> None:
        cfg = self.config
        t0 = perf_counter()

        from brian2 import prefs, NeuronGroup, Synapses, SpikeMonitor, Network, Hz, ms
        import pandas as pd

        try:
            prefs.codegen.target = cfg.codegen_target
        except Exception:
            prefs.codegen.target = "numpy"
        self._Hz, self._ms = Hz, ms

        model = self._import_model()
        self.params = dict(model.default_params)

        # flyid2i：completeness 行序 = brian 索引（与 create_model 内 NeuronGroup 编号一致）
        df_comp = pd.read_csv(cfg.comp_path, index_col=0)
        self.flyid2i = {int(f): i for i, f in enumerate(df_comp.index)}
        self.n_neurons = len(self.flyid2i)

        # 复用上游 create_model 建 neu + 全连接组 syn；丢弃其 record=True 的 SpikeMonitor
        self.neu, self.syn, _ = model.create_model(
            str(cfg.comp_path), str(cfg.con_path), self.params
        )
        self.spk_mon = SpikeMonitor(self.neu, record=cfg.record_spikes, name="online_spkmon")

        # 解析感觉/读出神经元 -> brian 索引（按 783 校验）
        self.resolved: ResolvedNeurons = resolve_neurons(
            self.flyid2i, ids_path=cfg.ids_path
        )

        # 可注入通道 = 感觉通道 + DN 控制句柄通道（后者来自 readout 组）。
        # 全部拼到一个可运行时改频率的 Poisson 源；按通道名记录切片以便分别设频率。
        inject: list[tuple[str, list[int]]] = [
            (c, idx) for c, idx in self.resolved.sensory.items() if idx
        ]
        for name in cfg.handle_channels:
            idx = self.resolved.readout.get(name, [])
            if idx:
                inject.append((name, idx))

        self._chan_order: list[str] = [c for c, _ in inject]
        target_idx: list[int] = []
        self._chan_slice: dict[str, slice] = {}
        for chan, idx in inject:
            self._chan_slice[chan] = slice(len(target_idx), len(target_idx) + len(idx))
            target_idx.extend(idx)
        self._n_inp = len(target_idx)

        if self._n_inp:
            self._pois = NeuronGroup(
                self._n_inp, "rate : Hz",
                threshold="rand() < rate * dt", name="online_poisson",
            )
            self._rates = np.zeros(self._n_inp, dtype=float)
            self._pois.rate = self._rates * Hz
            self._pois_syn = Synapses(
                self._pois, self.neu, "w : volt",
                on_pre="v_post += w", name="online_drive",
            )
            self._pois_syn.connect(i=list(range(self._n_inp)), j=target_idx)
            self._pois_syn.w = self.params["w_syn"] * self.params["f_poi"]
            for j in target_idx:
                self.neu[j].rfc = 0 * ms       # 复刻 poi() 副作用：注入点无不应期
            net_objs = [self.neu, self.syn, self.spk_mon, self._pois, self._pois_syn]
        else:
            self._pois = None
            net_objs = [self.neu, self.syn, self.spk_mon]

        self.net = Network(*net_objs)
        if not cfg.continuous:
            self.net.store("baseline")

        # 可视化下采样分箱起点
        self._viz_bins = self._make_viz_bins(self.n_neurons, cfg.viz_neuron_count)
        self._prev_count = np.zeros(self.n_neurons, dtype=np.int64)
        self.build_time_s = perf_counter() - t0

    @staticmethod
    def _make_viz_bins(n: int, k: int) -> np.ndarray:
        if n <= 0:
            return np.zeros(0, dtype=np.int64)
        k = max(1, min(k, n))
        return np.linspace(0, n, k + 1, dtype=np.int64)[:-1]

    # ------------------------------------------------------------------- run
    def reset(self) -> None:
        """重置膜状态（新 episode）。连续模式下重置 v/g 与读出基线。"""
        self.neu.v = self.params["v_0"]
        self.neu.g = 0
        if not self.config.continuous:
            self.net.restore("baseline")
        self._prev_count = np.asarray(self.spk_mon.count, dtype=np.int64).copy()

    def set_channel_rates(self, rates_hz: dict[str, float]) -> None:
        """设置各感觉通道的 Poisson 注入频率（Hz）。未给的通道置 0。"""
        if self._pois is None:
            return
        self._rates[:] = 0.0
        for chan, hz in rates_hz.items():
            sl = self._chan_slice.get(chan)
            if sl is not None:
                self._rates[sl] = float(hz)
        self._pois.rate = self._rates * self._Hz

    def step(self, rates_hz: dict[str, float] | None = None, window_ms: float | None = None) -> WindowReadout:
        """推进一个同步窗，返回读出。``rates_hz`` 为各感觉通道频率(Hz)。"""
        if rates_hz is not None:
            self.set_channel_rates(rates_hz)
        win = float(window_ms if window_ms is not None else self.config.window_ms)
        win_s = win / 1000.0

        t0 = perf_counter()
        prev = np.asarray(self.spk_mon.count, dtype=np.int64)
        self.net.run(win * self._ms)
        count = np.asarray(self.spk_mon.count, dtype=np.int64)
        delta = count - prev
        wall_ms = (perf_counter() - t0) * 1000.0

        readout = {}
        for name, idxs in self.resolved.readout.items():
            if idxs:
                readout[name] = float(delta[idxs].mean() / max(1e-9, win_s))
            else:
                readout[name] = 0.0

        activity = (
            np.add.reduceat(delta, self._viz_bins).astype(int).tolist()
            if self._viz_bins.size else []
        )
        return WindowReadout(
            readout_rates_hz=readout,
            active_neuron_count=int((delta > 0).sum()),
            total_neuron_count=self.n_neurons,
            neuron_activity=activity,
            window_s=win_s,
            wall_time_ms=wall_ms,
        )

    # --------------------------------------------------------------- helpers
    def startup_info(self) -> dict[str, Any]:
        return {
            "n_neurons": self.n_neurons,
            "n_inject_neurons": self._n_inp,
            "inject_channels": {c: (sl.stop - sl.start) for c, sl in self._chan_slice.items()},
            "readout_groups": {k: len(v) for k, v in self.resolved.readout.items()},
            "empty_groups": self.resolved.empty_groups,
            "build_time_s": round(self.build_time_s, 2),
            "window_ms": self.config.window_ms,
            "continuous": self.config.continuous,
            "codegen": self.config.codegen_target,
        }
