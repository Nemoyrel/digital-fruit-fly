"""低活动态下重测「感觉→DN 转向/前进/梳理 涌现」(I1 核心发现复核)。

背景：原探针 /tmp/dn_validation.py 用 ORN/JON 150Hz 注入，会触发全脑「锁死」
(active~5500、去刺激不回落)。本探针要在**低活动态**下重测 DN 差分是否跟随刺激侧。

诊断中发现的两个关键事实（决定了本探针的设计）：
1. OnlineBrain.reset() **无法清除锁死**：一旦点燃自持活动，reset 只重置 v/g，
   网络仍停在 active~5500（实测锁死后 30 窗空输入也不衰减）。
   => 故每个条件必须 **fresh 重建整张网络**，否则前一条件的锁死会污染后续所有条件
      （这正是原探针 13 条件全报 active~5500、turn_diff 恒左偏的根因）。
2. 低频注入下存在**点燃潜伏期**：ORN仅左 2Hz 时网络前 ~7 窗(~105ms)真低活动
   (active 0~4)，之后才点燃(→3613→锁死)；5Hz 约 2~3 窗点燃。即「低活动态」是
   **瞬态**（点燃前），非稳态。

因此本探针对每个条件：fresh 重建 → 从 window0 起逐窗 step，记录每窗 active 与各 DN 的
spike 增量。点燃定义为某窗 active 首次 ≥ IGNITE_TH(500)。分两段汇总：
  - **低活动段**(点燃前的窗)：在此段累计 DN spike，看转向差分是否跟随刺激侧。
    DN→刺激的潜伏 ~30ms(~2 窗)，2Hz 点燃在 ~7 窗，故低活动段足够让 DN 先响应。
  - **锁死段**(点燃后)：作对照，看是否仍恒左偏。

只写 tests/ 探针 + reports/_build/probe_dn_emergence.json，不碰任何报告文件。
"""
import sys
import json
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, "/Users/lins/Code/digital-fruit-fly/src")
from digital_fruit_fly.brain.online_brain import OnlineBrain, OnlineBrainConfig

OUT_PATH = Path("/Users/lins/Code/digital-fruit-fly/reports/_build/probe_dn_emergence.json")

DN_KEYS = [
    "dna01_left", "dna01_right",
    "dna02_left", "dna02_right",
    "odn1_left", "odn1_right",
    "adn1_left", "adn1_right",
    "mn9",
]

N_WINDOWS = 14          # 每条件 14 窗(210ms 连续积分)
WIN_MS = 15.0
IGNITE_TH = 500         # active ≥ 此值视为已点燃(锁死段)；低活动段 = 点燃前的窗


def build_brain():
    return OnlineBrain(OnlineBrainConfig(window_ms=WIN_MS, continuous=True))


def run_condition(label, inject_side, freq, rates_hz):
    """fresh 重建网络，逐窗记录 active 与 DN spike 增量，分低活动/锁死两段汇总。"""
    brain = build_brain()
    # 直接读 spk_mon.count 做 DN spike 增量（绕开 15ms 量化的 rate，用整数 spike 数累计）
    dn_idx = {k: brain.resolved.readout.get(k, []) for k in DN_KEYS}
    win_s = WIN_MS / 1000.0

    actives, dn_spikes_per_win = [], []
    prev = np.asarray(brain.spk_mon.count, dtype=np.int64).copy()
    for _ in range(N_WINDOWS):
        brain.step(rates_hz)
        cur = np.asarray(brain.spk_mon.count, dtype=np.int64)
        delta = cur - prev
        prev = cur
        actives.append(int((delta > 0).sum()))
        dn_spikes_per_win.append({k: int(delta[idx].sum()) for k, idx in dn_idx.items()})

    # 点燃窗 = active 首次 ≥ 阈值的窗号(None=全程未点燃)
    ignite_w = next((i for i, a in enumerate(actives) if a >= IGNITE_TH), None)
    low_range = range(0, ignite_w if ignite_w is not None else N_WINDOWS)
    lock_range = range(ignite_w, N_WINDOWS) if ignite_w is not None else range(0, 0)

    def phase_summary(rng):
        n = len(rng)
        if n == 0:
            return {"n_windows": 0, "ms": 0, "active_mean": None, "dn_hz": {}}
        # 该段累计 DN spike → 段内平均放电率(Hz) = 总 spike /(神经元数 * 段总时长)
        dn_hz = {}
        for k, idx in dn_idx.items():
            tot = sum(dn_spikes_per_win[i][k] for i in rng)
            denom = max(1, len(idx)) * n * win_s
            dn_hz[k] = round(tot / denom, 1)
        return {
            "n_windows": n,
            "ms": int(n * WIN_MS),
            "active_mean": round(sum(actives[i] for i in rng) / n, 1),
            "dn_hz": dn_hz,
        }

    low = phase_summary(low_range)
    lock = phase_summary(lock_range)

    def turn_diff(dn_hz):
        if not dn_hz:
            return None, None, None
        tl = dn_hz["dna01_left"] + dn_hz["dna02_left"]
        tr = dn_hz["dna01_right"] + dn_hz["dna02_right"]
        return round(tl, 1), round(tr, 1), round(tr - tl, 1)

    low_tl, low_tr, low_td = turn_diff(low["dn_hz"])
    lock_tl, lock_tr, lock_td = turn_diff(lock["dn_hz"])

    rec = {
        "label": label,
        "inject_side": inject_side,
        "freq_hz": freq,
        "ignite_window": ignite_w,                # None=全程未点燃
        "ignite_ms": None if ignite_w is None else int(ignite_w * WIN_MS),
        "actives_per_window": actives,
        "low_activity_phase": {
            **low,
            "turn_left_sum": low_tl, "turn_right_sum": low_tr,
            "turn_diff_R_minus_L": low_td,
        },
        "locked_phase": {
            **lock,
            "turn_left_sum": lock_tl, "turn_right_sum": lock_tr,
            "turn_diff_R_minus_L": lock_td,
        },
    }
    # 控制台速览：重点看低活动段
    ldn = low["dn_hz"]
    ig = "未点燃" if ignite_w is None else f"点燃@w{ignite_w}({int(ignite_w*WIN_MS)}ms)"
    if ldn:
        print(
            f"[{label:14s}] {ig:14s} 低活段{low['ms']:>3d}ms active≈{low['active_mean']:>5.1f} | "
            f"DNa01 L/R={ldn['dna01_left']:>4.0f}/{ldn['dna01_right']:<4.0f} "
            f"DNa02 L/R={ldn['dna02_left']:>4.0f}/{ldn['dna02_right']:<4.0f} "
            f"turnΔ={low_td:+5.0f} | oDN1={ldn['odn1_left']:.0f}/{ldn['odn1_right']:.0f} "
            f"aDN1={ldn['adn1_left']:.0f}/{ldn['adn1_right']:.0f} MN9={ldn['mn9']:.0f}",
            flush=True,
        )
    else:
        print(f"[{label:14s}] {ig:14s} 低活段0ms(即刻点燃) | 锁死段 turnΔ={lock_td:+.0f}", flush=True)
    del brain
    return rec


def main():
    t0 = time.perf_counter()
    b0 = build_brain()
    info = b0.startup_info()
    build_s = round(b0.build_time_s, 2)
    del b0
    print(f">>> 单次 build {build_s}s  n_neurons={info['n_neurons']}  "
          f"window={WIN_MS}ms  每条件 {N_WINDOWS} 窗(fresh 重建)\n", flush=True)

    freqs = [2.0, 5.0, 10.0]
    side_specs = [
        ("orn_left", "ORN仅左"),
        ("orn_right", "ORN仅右"),
        ("jon_left", "JON仅左"),
        ("jon_right", "JON仅右"),
    ]

    results = [run_condition("基线(无输入)", "none", 0.0, {})]
    for chan, prefix in side_specs:
        for f in freqs:
            results.append(run_condition(f"{prefix}{f:g}Hz", chan, f, {chan: f}))
        print("", flush=True)

    out = {
        "_doc": (
            "低活动态(2/5/10Hz单侧 ORN/JON)重测 感觉→DN 涌现。每条件 fresh 重建网络"
            "(因 reset 无法清除锁死)。low_activity_phase=点燃前的低活窗(在此看 DN 是否跟随刺激侧)，"
            "locked_phase=点燃后(active≥500)。turn_diff_R_minus_L>0=右主导, <0=左主导。"
            "dn_hz 由该段累计 spike / (神经元数 * 段时长) 得到。"
        ),
        "meta": {
            "build_time_s": build_s,
            "n_neurons": info["n_neurons"],
            "window_ms": WIN_MS,
            "n_windows_per_condition": N_WINDOWS,
            "ignite_threshold_active": IGNITE_TH,
            "fresh_rebuild_per_condition": True,
            "continuous": True,
            "codegen": info["codegen"],
            "inject_channel_sizes": info["inject_channels"],
        },
        "conditions": results,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n>>> 写出 {OUT_PATH}", flush=True)
    print(f">>> 总耗时 {time.perf_counter() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
