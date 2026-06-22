"""Shiu 全连接组脑后端：Brian2 引擎 + 行为状态机 + 逐神经元活动读出。

设计要点
--------
- ``Brian2ShiuEngine``  封装 Shiu ``model.py`` 的网络构建、可复用 Poisson 输入、
  单窗口仿真与 ``spk_mon.count`` 逐神经元脉冲计数读出。brian2 仅在方法内部惰性导入，
  因此在没有 brian2 的环境（如 flygym_env / 测试）中也能导入本模块。
- ``ShiuFullBackend``   与引擎无关的行为逻辑：FORAGING/GROOMING/FEEDING 状态机、
  feeding/grooming 评分、运动驱动映射、以及把全脑活动下采样成可视化向量。
  测试可注入一个 numpy-only 的假引擎来覆盖这些逻辑，无需 Brian2 / 连接组数据。

边界：神经动力学来自 Shiu et al. 公开 Brian2 模型；感觉编码、readout->行为/驱动 的映射
是本项目自己的工程桥接。
"""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
from pathlib import Path
import shutil
from time import perf_counter
from typing import Any, Protocol

import numpy as np

from .brain_neurons import (
    GROOMING_READOUT_IDS,
    JON_GRN_IDS,
    MN9_FLYWIRE_ID,
    SUGAR_GRN_IDS,
)
from .messages import BrainReadoutMessage, SensoryStateMessage
from .state import BehaviorState


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class BrainBackendUnavailable(RuntimeError):
    """所需的全 Shiu 后端无法启动或运行时抛出（绝不静默兜底）。"""

    def __init__(self, stage: str, reason: str, metadata: dict[str, Any] | None = None):
        super().__init__(f"{stage}: {reason}")
        self.stage = stage
        self.reason = reason
        self.metadata = metadata or {}


@dataclass(frozen=True)
class BrainWorkerConfig:
    """全 Shiu 脑 worker 的运行配置。"""

    brain_window_s: float = 0.05          # 每次请求仿真的脑时间窗（秒）；50ms 才够食物→MN9 信号传导
    grooming_duration_s: float = 1.2      # 一次梳理持续时间
    feeding_hold_s: float = 1.0           # 进入进食后的最短保持时间
    max_turn_drive: float = 0.6
    search_turn_gain: float = 0.85
    min_forward_drive: float = 0.1
    max_forward_drive: float = 1.4
    max_startup_s: float = 0.0            # >0 时对启动设时间上限
    viz_neuron_count: int = 4000          # 送往可视化的下采样神经元数量
    # 感觉量 -> Poisson 输入 rate 的标定
    food_max_rate_hz: float = 160.0
    dust_max_rate_hz: float = 220.0
    feeding_rate_norm_hz: float = 100.0
    grooming_rate_norm_hz: float = 100.0
    # 神经元 ID
    sugar_grn_ids: tuple[int, ...] = SUGAR_GRN_IDS
    jon_grn_ids: tuple[int, ...] = JON_GRN_IDS
    mn9_flywire_id: int = MN9_FLYWIRE_ID
    grooming_readout_ids: tuple[int, ...] = GROOMING_READOUT_IDS
    # 数据路径
    project_root: Path = field(
        default_factory=lambda: Path(__file__).resolve().parents[2]
    )
    shiu_repo_path: Path | None = None
    shiu_completeness_csv: Path | None = None
    shiu_connectivity_parquet: Path | None = None


class BrainEngine(Protocol):
    """脑引擎接口：把感觉输入 rate 转成逐神经元脉冲计数向量。"""

    n_neurons: int
    flywire_to_index: dict[int, int]
    startup_metadata: dict[str, Any]

    def run_window(self, *, food_rate_hz: float, dust_rate_hz: float) -> np.ndarray:
        """运行一个脑时间窗，返回长度 n_neurons 的逐神经元脉冲计数（int）。"""


def _brian2_environment_metadata() -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "compiler_available": any(
            shutil.which(name) for name in ("clang", "gcc", "g++")
        ),
    }
    try:
        import brian2
        from brian2 import prefs

        metadata["brian2_version"] = brian2.__version__
        if metadata["compiler_available"]:
            try:
                prefs.codegen.target = "cython"
            except Exception:
                prefs.codegen.target = "numpy"
        metadata["codegen_target"] = str(prefs.codegen.target)
    except Exception as exc:  # pragma: no cover - 仅在缺 brian2 时触发
        metadata["brian2_version"] = None
        metadata["codegen_target"] = "unavailable"
        metadata["brian2_error"] = repr(exc)
    return metadata


class Brian2ShiuEngine:
    """封装 Shiu Brian2 模型的真实引擎（brian2 惰性导入）。"""

    def __init__(self, config: BrainWorkerConfig) -> None:
        self.config = config
        self.repo_path = config.shiu_repo_path or (
            config.project_root / "external" / "drosophila_brain_model"
        )
        self.path_comp = config.shiu_completeness_csv or (
            self.repo_path / "2023_03_23_completeness_630_final.csv"
        )
        self.path_con = config.shiu_connectivity_parquet or (
            self.repo_path / "2023_03_23_connectivity_630_final.parquet"
        )
        self.n_neurons = 0
        self.flywire_to_index: dict[int, int] = {}
        self.startup_metadata: dict[str, Any] = _brian2_environment_metadata()
        self.startup_wall_time_s = 0.0
        self._sugar_indices: list[int] = []
        self._jon_indices: list[int] = []
        self._input_group: Any | None = None

    def _fail(self, stage: str, reason: str) -> None:
        metadata = {
            **self.startup_metadata,
            "stage": stage,
            "reason": reason,
            "shiu_full_attempted": True,
            "shiu_full_used": False,
            "shiu_repo_path": str(self.repo_path),
            "shiu_completeness_csv": str(self.path_comp),
            "shiu_connectivity_parquet": str(self.path_con),
            "startup_wall_time_s": self.startup_wall_time_s,
        }
        raise BrainBackendUnavailable(stage, reason, metadata)

    def startup(self) -> dict[str, Any]:
        started = perf_counter()
        try:
            self._check_required_files()
            module = self._import_shiu_module()
            from brian2 import Hz, NeuronGroup, Network, Synapses, ms

            self.params = dict(module.default_params)
            self.params["n_run"] = 1
            self.params["t_run"] = self.config.brain_window_s * 1000.0 * ms

            self.flywire_to_index = self._load_flywire_to_index()
            self.n_neurons = len(self.flywire_to_index)

            self.neu, self.syn, self.spk_mon = module.create_model(
                self.path_comp, self.path_con, self.params
            )
            self._sugar_indices = self._indices(self.config.sugar_grn_ids)
            self._jon_indices = self._indices(self.config.jon_grn_ids)

            target_indices = self._sugar_indices + self._jon_indices
            source_indices = list(range(len(target_indices)))
            input_group = NeuronGroup(
                len(target_indices),
                "rate : Hz",
                threshold="rand() < rate * dt",
                name="reusable_poisson_input*",
            )
            input_group.rate = [0.0 for _ in target_indices] * Hz
            input_syn = Synapses(
                input_group,
                self.neu,
                "w : volt",
                on_pre="v_post += w",
                name="reusable_poisson_synapses*",
            )
            input_syn.connect(i=source_indices, j=target_indices)
            input_syn.w = self.params["w_syn"] * self.params["f_poi"]
            for j in target_indices:
                self.neu[j].rfc = 0 * ms
            self._input_group = input_group
            self._Hz = Hz

            self.net = Network(self.neu, self.syn, self.spk_mon, input_group, input_syn)
            self.net.store("baseline")
        except BrainBackendUnavailable:
            raise
        except Exception as exc:
            self.startup_wall_time_s = perf_counter() - started
            self._fail("startup", repr(exc))

        self.startup_wall_time_s = perf_counter() - started
        if (
            self.config.max_startup_s > 0
            and self.startup_wall_time_s > self.config.max_startup_s
        ):
            self._fail("startup_budget", f"startup took {self.startup_wall_time_s:.3f}s")

        self.startup_metadata.update(
            {
                "shiu_full_attempted": True,
                "shiu_full_used": True,
                "startup_wall_time_s": self.startup_wall_time_s,
                "n_neurons": self.n_neurons,
                "shiu_repo_path": str(self.repo_path),
                "shiu_completeness_csv": str(self.path_comp),
                "shiu_connectivity_parquet": str(self.path_con),
            }
        )
        return self.startup_metadata

    def _check_required_files(self) -> None:
        missing = [
            str(p)
            for p in (self.repo_path / "model.py", self.path_comp, self.path_con)
            if not p.exists()
        ]
        if missing:
            self._fail("file_check", f"missing Shiu model files: {missing}")

    def _import_shiu_module(self) -> Any:
        model_path = self.repo_path / "model.py"
        spec = importlib.util.spec_from_file_location("shiu_brain_model", model_path)
        if spec is None or spec.loader is None:
            self._fail("import_shiu", f"cannot import {model_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _load_flywire_to_index(self) -> dict[int, int]:
        try:
            import pandas as pd

            df_comp = pd.read_csv(self.path_comp, index_col=0)
        except Exception as exc:
            self._fail("load_completeness", repr(exc))
        return {int(fid): idx for idx, fid in enumerate(df_comp.index)}

    def _indices(self, flywire_ids: tuple[int, ...]) -> list[int]:
        indices = [
            self.flywire_to_index[fid]
            for fid in flywire_ids
            if fid in self.flywire_to_index
        ]
        if not indices:
            self._fail("flywire_mapping", f"no configured IDs found in model: {flywire_ids}")
        return indices

    def run_window(self, *, food_rate_hz: float, dust_rate_hz: float) -> np.ndarray:
        self.net.restore("baseline")
        rates = (
            [food_rate_hz for _ in self._sugar_indices]
            + [dust_rate_hz for _ in self._jon_indices]
        )
        self._input_group.rate = rates * self._Hz
        self.net.run(self.params["t_run"])
        return np.asarray(self.spk_mon.count, dtype=np.int64).copy()


class ShiuFullBackend:
    """与引擎无关的行为后端：FSM + 评分 + 运动驱动 + 可视化下采样。"""

    backend_name = "shiu_full"

    def __init__(self, config: BrainWorkerConfig, *, engine: BrainEngine | None = None) -> None:
        self.config = config
        self.engine: BrainEngine = engine or Brian2ShiuEngine(config)
        if not getattr(self.engine, "startup_metadata", None):
            self.engine.startup_metadata = {}
        # 若是真实引擎需启动；假引擎应已自带 n_neurons / flywire_to_index。
        startup = getattr(self.engine, "startup", None)
        if callable(startup):
            startup()
        self.metadata = dict(self.engine.startup_metadata)

        self.behavior_state = BehaviorState.FORAGING
        self.state_until_s = 0.0
        self.request_count = 0
        self._last_msg_time_s = -1.0  # 用于检测新 episode（时间回退）
        self._mn9_index = self.engine.flywire_to_index.get(config.mn9_flywire_id)
        self._grooming_indices = [
            self.engine.flywire_to_index[fid]
            for fid in config.grooming_readout_ids
            if fid in self.engine.flywire_to_index
        ]
        self._viz_bin_starts = self._make_viz_bins(
            self.engine.n_neurons, config.viz_neuron_count
        )

    @staticmethod
    def _make_viz_bins(n_neurons: int, k: int) -> np.ndarray:
        """把全部神经元切成 k 个连续分箱，返回各分箱起点索引（供 np.add.reduceat 求和）。

        每个可视化点 = 一组相邻神经元在本窗内的脉冲总数。相比“每隔 step 取一个”，
        分箱求和保留了全部脉冲，使稀疏的真实活动（~0.5% 神经元激活）在面板上更可见。
        """
        if n_neurons <= 0:
            return np.zeros(0, dtype=np.int64)
        k = max(1, min(k, n_neurons))
        return np.linspace(0, n_neurons, k + 1, dtype=np.int64)[:-1]

    def _rate_from_counts(self, counts: np.ndarray, indices: list[int] | None) -> float:
        if not indices:
            return 0.0
        window = max(1e-9, self.config.brain_window_s)
        sub = counts[indices]
        return float(sub.mean() / window)

    def _state_readout(
        self,
        message: SensoryStateMessage,
        *,
        feeding_score: float,
        grooming_score: float,
        dust_clearance: float,
    ) -> tuple[str, float, float]:
        if self.behavior_state == BehaviorState.GROOMING:
            return BehaviorState.GROOMING.value, 0.0, 0.0
        if self.behavior_state == BehaviorState.FEEDING:
            return BehaviorState.FEEDING.value, 0.0, 0.0

        forward_drive = 0.75 + 0.4 * feeding_score - 0.12 * grooming_score
        if message.food_cue <= 0.0:
            turn_drive = message.turn_bias * self.config.search_turn_gain
        else:
            turn_drive = message.turn_bias * (0.3 + 0.7 * feeding_score)
        if dust_clearance:
            turn_drive = 0.0
        return (
            BehaviorState.FORAGING.value,
            _clip(forward_drive, self.config.min_forward_drive, self.config.max_forward_drive),
            _clip(turn_drive, -self.config.max_turn_drive, self.config.max_turn_drive),
        )

    def handle(self, message: SensoryStateMessage) -> BrainReadoutMessage:
        start = perf_counter()
        self.request_count += 1
        # 新 episode 检测：body loop 重启后 time_s 回退，重置行为状态机，
        # 避免长驻 worker 把上一段 demo 的 FEEDING/state_until 带进新一段。
        if message.time_s + 1e-6 < self._last_msg_time_s:
            self.behavior_state = BehaviorState.FORAGING
            self.state_until_s = 0.0
        self._last_msg_time_s = message.time_s
        try:
            counts = self.engine.run_window(
                food_rate_hz=self.config.food_max_rate_hz * message.food_cue,
                dust_rate_hz=self.config.dust_max_rate_hz * message.dust_level,
            )
        except BrainBackendUnavailable:
            raise
        except Exception as exc:
            raise BrainBackendUnavailable("network_run", repr(exc), dict(self.metadata))

        mn9_rate = self._rate_from_counts(
            counts, [self._mn9_index] if self._mn9_index is not None else None
        )
        grooming_rate = self._rate_from_counts(counts, self._grooming_indices)
        feeding_score = _clip(mn9_rate / self.config.feeding_rate_norm_hz, 0.0, 1.0)
        grooming_score = _clip(grooming_rate / self.config.grooming_rate_norm_hz, 0.0, 1.0)

        # 行为状态机（受感觉量与神经元读出门控）
        dust_clearance = 0.0
        if (
            self.behavior_state == BehaviorState.GROOMING
            and message.time_s >= self.state_until_s
        ):
            self.behavior_state = BehaviorState.FORAGING
            self.state_until_s = 0.0
            dust_clearance = 1.0
            grooming_score = 0.0
        elif self.behavior_state == BehaviorState.GROOMING:
            pass
        elif message.dust_threshold_reached:
            self.behavior_state = BehaviorState.GROOMING
            self.state_until_s = message.time_s + self.config.grooming_duration_s
        elif message.food_contact:
            self.behavior_state = BehaviorState.FEEDING
            self.state_until_s = max(
                self.state_until_s, message.time_s + self.config.feeding_hold_s
            )
        elif message.time_s >= self.state_until_s:
            self.behavior_state = BehaviorState.FORAGING

        behavior, forward_drive, turn_bias = self._state_readout(
            message,
            feeding_score=feeding_score,
            grooming_score=grooming_score,
            dust_clearance=dust_clearance,
        )

        activity = (
            np.add.reduceat(counts, self._viz_bin_starts).astype(int).tolist()
            if self._viz_bin_starts.size
            else []
        )
        active_neuron_count = int((counts > 0).sum())
        wall_ms = (perf_counter() - start) * 1000.0
        return BrainReadoutMessage(
            request_id=message.request_id,
            behavior_state=behavior,
            forward_drive=forward_drive,
            turn_bias=turn_bias,
            grooming_score=grooming_score,
            feeding_score=feeding_score,
            mn9_rate_hz=mn9_rate,
            dust_clearance=dust_clearance,
            source="brain_worker:shiu_full",
            backend=self.backend_name,
            brain_wall_time_ms=wall_ms,
            brain_simulated_window_s=self.config.brain_window_s,
            neuron_activity=activity,
            active_neuron_count=active_neuron_count,
            total_neuron_count=int(self.engine.n_neurons),
            extra={
                "grooming_rate_hz": grooming_rate,
                "request_count": self.request_count,
                "brain_window_s": self.config.brain_window_s,
                "viz_neuron_count": int(self._viz_bin_starts.size),
                "shiu_full_used": bool(self.metadata.get("shiu_full_used", True)),
                **self.metadata,
            },
        )
