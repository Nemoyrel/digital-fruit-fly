"""脑模型神经元 FlyWire ID 注册表的加载与解析。

职责：把 ``data/neuron_ids.json`` 里按生物名字组织的 FlyWire id，解析成
Brian2 网络里的整数索引（brian index），并在解析时按当前连接组
（``Completeness_*.csv`` 的 index）再次校验，自动剔除不存在的 id 并告警。

只依赖标准库（json / pathlib），可在 brain_env（无 pyyaml）中使用。

设计边界：感觉编码（哪些神经元算"糖味"）与运动读出（哪些 DN 控制转向）的
**选择**是本项目的工程桥接；神经动力学本身来自 Shiu et al. 公开模型。
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_IDS_PATH = PROJECT_ROOT / "data" / "neuron_ids.json"


@dataclass
class ResolvedNeurons:
    """解析后的神经元索引（已按连接组校验）。

    ``sensory`` / ``readout`` 的值都是 **brian 整数索引**（0..N-1），可直接用于
    PoissonGroup 连接与 ``spk_mon.count[indices]`` 读出。
    ``missing`` 记录每个组里被剔除（不在当前连接组）的 flywire id，便于诊断。
    """

    sensory: dict[str, list[int]] = field(default_factory=dict)
    readout: dict[str, list[int]] = field(default_factory=dict)
    sensory_flyids: dict[str, list[int]] = field(default_factory=dict)
    readout_flyids: dict[str, list[int]] = field(default_factory=dict)
    missing: dict[str, list[int]] = field(default_factory=dict)
    empty_groups: list[str] = field(default_factory=list)

    def report(self) -> str:
        lines = ["神经元解析报告:"]
        for kind, groups in (("sensory", self.sensory), ("readout", self.readout)):
            for name, idxs in groups.items():
                miss = self.missing.get(f"{kind}.{name}", [])
                flag = "  ⚠空" if not idxs else ""
                miss_s = f"  (剔除 {len(miss)} 个不在连接组的 id)" if miss else ""
                lines.append(f"  [{kind}] {name}: {len(idxs)} 个{flag}{miss_s}")
        if self.empty_groups:
            lines.append(f"  ⚠ 空组（id 待回填）: {', '.join(self.empty_groups)}")
        return "\n".join(lines)


def load_neuron_ids(path: str | Path | None = None) -> dict:
    """读取 neuron_ids.json（含 sensory / readout 两段）。"""
    path = Path(path) if path else DEFAULT_IDS_PATH
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def resolve_neurons(
    flyid2i: dict[int, int],
    neuron_ids: dict | None = None,
    *,
    ids_path: str | Path | None = None,
) -> ResolvedNeurons:
    """把 name→[flywire_id] 注册表解析成 name→[brian_index]，并按 ``flyid2i`` 校验。

    Parameters
    ----------
    flyid2i : dict[int, int]
        当前连接组的 flywire_id → brian_index 映射（来自 completeness 表行序）。
    neuron_ids : dict, optional
        已加载的注册表；为 None 时按 ``ids_path`` / 默认路径加载。
    """
    raw = neuron_ids if neuron_ids is not None else load_neuron_ids(ids_path)
    out = ResolvedNeurons()

    for kind in ("sensory", "readout"):
        groups = raw.get(kind, {})
        target_idx = out.sensory if kind == "sensory" else out.readout
        target_fly = out.sensory_flyids if kind == "sensory" else out.readout_flyids
        for name, ids in groups.items():
            present, missing = [], []
            for fid in ids:
                fid = int(fid)
                if fid in flyid2i:
                    present.append(fid)
                else:
                    missing.append(fid)
            target_fly[name] = present
            target_idx[name] = [flyid2i[f] for f in present]
            if missing:
                out.missing[f"{kind}.{name}"] = missing
            if not present:
                out.empty_groups.append(f"{kind}.{name}")
    return out
