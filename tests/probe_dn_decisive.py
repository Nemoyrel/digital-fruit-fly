"""存档两个「决定性条件」的精确数值，供报告 §9.3 与 I1 取证可复算。

补 probe_dn_emergence.json 缺的字段：报告引用的 363/40 spike、450ms、峰值 active、
单窗挂钟耗时此前来自一次性命令、不在任何存档里（踩了「可复算」标尺）。本脚本用与
probe_dn_emergence.py 同一套读法，把两条件重跑并落盘。

条件 1：JON 仅左 5Hz，跑满 450ms(30 窗)，fresh 网络。验证「低频感觉点亮自身却不传播到 DN」：
  记录 总 spike / JON 自身 spike / 下游非 JON spike / 各 DN spike / 峰值 active / 逐窗挂钟 ms。
条件 2：糖 sugar_grn 150Hz，跑满 450ms，fresh 网络。读法健全性对照(MN9 应 >0)：
  记录 MN9 总 spike / 糖自身 spike / 峰值 active / 逐窗挂钟 ms。

只写 tests/ 探针 + reports/_build/probe_dn_decisive.json，不碰报告文件。
"""
import sys
import json
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, "/Users/lins/Code/digital-fruit-fly/src")
from digital_fruit_fly.brain.online_brain import OnlineBrain, OnlineBrainConfig

OUT_PATH = Path("/Users/lins/Code/digital-fruit-fly/reports/_build/probe_dn_decisive.json")

WIN_MS = 15.0
N_WINDOWS = 30          # 450ms

DN_KEYS = [
    "dna01_left", "dna01_right",
    "dna02_left", "dna02_right",
    "odn1_left", "odn1_right",
    "adn1_left", "adn1_right",
]


def build_brain():
    return OnlineBrain(OnlineBrainConfig(window_ms=WIN_MS, continuous=True))


def run(label, rates_hz, self_channel, self_kind):
    """fresh 网络跑 N_WINDOWS 窗，逐窗记录 spike 增量分解 + 挂钟耗时。

    self_channel/self_kind: 被注入群（统计其「自身 spike」），如 ('jon_left','sensory')。
    """
    brain = build_brain()
    res = brain.resolved
    self_idx = np.array((res.sensory if self_kind == "sensory" else res.readout).get(self_channel, []))
    dn_idx = {k: np.array(res.readout.get(k, [])) for k in DN_KEYS}
    mn9_idx = np.array(res.readout.get("mn9", []))

    actives, wall_ms = [], []
    tot_spk = 0
    self_spk = 0
    mn9_spk = 0
    dn_spk = {k: 0 for k in DN_KEYS}

    prev = np.asarray(brain.spk_mon.count, dtype=np.int64).copy()
    for _ in range(N_WINDOWS):
        t0 = time.perf_counter()
        brain.step(rates_hz)
        wall_ms.append(round((time.perf_counter() - t0) * 1000.0, 1))
        cur = np.asarray(brain.spk_mon.count, dtype=np.int64)
        d = cur - prev
        prev = cur
        actives.append(int((d > 0).sum()))
        tot_spk += int(d.sum())
        if self_idx.size:
            self_spk += int(d[self_idx].sum())
        if mn9_idx.size:
            mn9_spk += int(d[mn9_idx].sum())
        for k, idx in dn_idx.items():
            if idx.size:
                dn_spk[k] += int(d[idx].sum())

    dn_total = sum(dn_spk.values())
    downstream_non_self = tot_spk - self_spk     # 下游(注入群之外)的所有 spike
    # 单窗稳态耗时区间：剔除首窗(含 cython 预热)后的 min/max/median
    steady = sorted(wall_ms[1:]) if len(wall_ms) > 1 else wall_ms
    rec = {
        "label": label,
        "inject": rates_hz,
        "n_windows": N_WINDOWS,
        "window_ms": WIN_MS,
        "duration_ms": int(N_WINDOWS * WIN_MS),
        "total_spikes": tot_spk,
        "self_channel": self_channel,
        "self_population_spikes": self_spk,
        "downstream_non_self_spikes": downstream_non_self,
        "dn_spikes": dn_spk,
        "dn_spikes_total": dn_total,
        "mn9_spikes": mn9_spk,
        "active_peak": max(actives),
        "active_mean": round(sum(actives) / len(actives), 1),
        "actives_per_window": actives,
        "wall_ms_per_window": wall_ms,
        "wall_ms_first_window": wall_ms[0],
        "wall_ms_steady_min": steady[0],
        "wall_ms_steady_max": steady[-1],
        "wall_ms_steady_median": steady[len(steady) // 2],
    }
    print(f"=== {label} ===", flush=True)
    print(f"  总spk={tot_spk}  {self_channel}自身spk={self_spk}  下游非自身spk={downstream_non_self}  "
          f"DN_spk总={dn_total}  MN9_spk={mn9_spk}", flush=True)
    print(f"  DN分解: " + " ".join(f"{k}={v}" for k, v in dn_spk.items()), flush=True)
    print(f"  峰值active={rec['active_peak']}  均active={rec['active_mean']}", flush=True)
    print(f"  单窗挂钟: 首窗={wall_ms[0]}ms  稳态 min/med/max={steady[0]}/{steady[len(steady)//2]}/{steady[-1]}ms", flush=True)
    del brain
    return rec


def main():
    t0 = time.perf_counter()
    info = build_brain().startup_info()
    c1 = run("JON仅左 5Hz / 450ms", {"jon_left": 5.0}, "jon_left", "sensory")
    print("", flush=True)
    c2 = run("糖 sugar_grn 150Hz / 450ms (读法对照)", {"sugar_grn": 150.0}, "sugar_grn", "sensory")

    out = {
        "_doc": (
            "两个决定性条件的精确存档(supersedes 报告里此前一次性命令的口述数字)。"
            "条件1(JON_L 5Hz/450ms)证：低频感觉点亮自身、向 DN 零传播且不锁死。"
            "条件2(糖 150Hz/450ms)证：同套 spike-count 读法能抓真涌现(MN9>0)，故 DN=0 非测量伪影。"
            "downstream_non_self_spikes = total_spikes - self_population_spikes。"
            "wall_ms_steady_* 已剔除含 cython 预热的首窗。"
        ),
        "meta": {
            "n_neurons": info["n_neurons"],
            "window_ms": WIN_MS,
            "n_windows": N_WINDOWS,
            "fresh_rebuild_per_condition": True,
            "continuous": True,
            "codegen": info["codegen"],
            "python": sys.version.split()[0],
        },
        "conditions": [c1, c2],
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n>>> 写出 {OUT_PATH}", flush=True)
    print(f">>> 总耗时 {time.perf_counter() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
