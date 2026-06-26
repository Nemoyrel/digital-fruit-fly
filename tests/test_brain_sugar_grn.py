"""M1 回归：糖 GRN 持续激活 → MN9（喙运动神经元）放电。

对应里程碑 M1（糖 GRN→MN9 激活），并验证 OnlineBrain 的连续积分能跨窗累积出
下游运动信号。需在 brain_env 运行（依赖 brian2 + 783 连接组）：

    /opt/miniconda3/envs/brain_env/bin/python tests/test_brain_sugar_grn.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def run(n_windows: int = 8, window_ms: float = 15.0, sugar_hz: float = 150.0):
    from digital_fruit_fly.brain.online_brain import OnlineBrain, OnlineBrainConfig

    brain = OnlineBrain(OnlineBrainConfig(window_ms=window_ms, continuous=True))
    info = brain.startup_info()
    print(">>> startup:", info)

    # 1) 基线：无输入，跑几窗，MN9 应基本静默
    brain.reset()
    base_mn9 = []
    for _ in range(4):
        r = brain.step({})
        base_mn9.append(r.readout_rates_hz.get("mn9", 0.0))
    print(f">>> baseline MN9 rates(Hz): {[round(x,1) for x in base_mn9]}")

    # 2) 持续糖输入：MN9 应在累积若干窗后放电
    brain.reset()
    print(f">>> 持续 sugar={sugar_hz}Hz, {n_windows} 窗 × {window_ms}ms:")
    mn9_rates, walls, actives = [], [], []
    cum_t = 0.0
    for k in range(n_windows):
        r = brain.step({"sugar_grn": sugar_hz})
        cum_t += window_ms
        mn9 = r.readout_rates_hz.get("mn9", 0.0)
        mn9_rates.append(mn9); walls.append(r.wall_time_ms); actives.append(r.active_neuron_count)
        print(f"    t={cum_t:5.0f}ms  MN9={mn9:6.1f}Hz  active={r.active_neuron_count:4d}  wall={r.wall_time_ms:6.0f}ms")

    peak = max(mn9_rates)
    mean_wall = sum(walls[1:]) / max(1, len(walls) - 1)  # 跳过首窗(编译)
    print(f">>> 结果: MN9 峰值={peak:.1f}Hz  稳态窗均挂钟={mean_wall:.0f}ms  实时比≈{mean_wall/window_ms:.1f}x")

    assert max(base_mn9) < peak, "基线 MN9 不应高于糖激活峰值"
    assert peak > 0.0, "M1 失败：持续糖输入未能让 MN9 放电"
    print(">>> ✅ M1 PASS: 糖 GRN 持续激活 → MN9 放电（连续积分跨窗累积）")
    return {"peak_mn9_hz": peak, "mean_wall_ms": mean_wall, "baseline_max": max(base_mn9)}


if __name__ == "__main__":
    run()
