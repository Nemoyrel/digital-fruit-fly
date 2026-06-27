"""在线模式验证：15ms 窗连续积分下，灰尘→JON_groom 注入能否驱动脑通路 JON→aBN1→aDN，
使 grooming_readout 过阈触发梳理，并确认 (1)不锁死 (2)去刺激后回落。

对应升级后的闭环：backend 灰尘→注入 jon_groom；motor 读 grooming_readout 的 EMA 过阈触发。
本脚本直接驱动 OnlineBrain，复刻 motor 的 EMA 触发逻辑，隔离验证脑侧行为。

运行：/opt/miniconda3/envs/brain_env/bin/python tests/probe_grooming_online.py
"""
from __future__ import annotations
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from digital_fruit_fly.brain.online_brain import OnlineBrain, OnlineBrainConfig  # noqa: E402

GROOM_HZ = 160.0     # backend.groom_jon_hz
THRESH = 8.0         # motor.grooming_readout_threshold_hz
ALPHA = 0.35         # motor.ema_alpha
N_INJECT = 40        # 注入窗数 (600ms，模拟灰尘累积期持续注入)
N_RELAX = 20         # 回落窗数 (300ms，梳理后清零灰尘→停注入)


def main():
    brain = OnlineBrain(OnlineBrainConfig(window_ms=15.0, continuous=True))
    info = brain.startup_info()
    print("startup:", {k: info[k] for k in
                       ("n_neurons", "n_inject_neurons", "inject_channels", "readout_groups", "empty_groups")})
    assert "jon_groom" in info["inject_channels"], "jon_groom 未进入注入通道！检查 neuron_ids.json / online_brain"
    print(f"  jon_groom 注入神经元数 = {info['inject_channels']['jon_groom']}")

    brain.reset()
    groom_ema = 0.0
    fired = None
    hdr = f"{'win':>4} {'t_ms':>6} {'gr_read':>8} {'aDN1_l':>7} {'aDN1_r':>7} {'ema':>6} {'active':>7}"

    print(f"\n阶段1: 注入 jon_groom @{GROOM_HZ}Hz × {N_INJECT} 窗（模拟灰尘）\n{hdr}")
    for w in range(N_INJECT):
        ro = brain.step({"jon_groom": GROOM_HZ})
        r = ro.readout_rates_hz
        gr = r.get("grooming_readout", 0.0)
        groom_ema = (1 - ALPHA) * groom_ema + ALPHA * gr
        if fired is None and groom_ema >= THRESH:
            fired = w
        if w < 10 or w % 5 == 0:
            print(f"{w:4d} {(w+1)*15:6d} {gr:8.1f} {r.get('adn1_left',0):7.1f} {r.get('adn1_right',0):7.1f} "
                  f"{groom_ema:6.1f} {ro.active_neuron_count:7d}")
    lat = f"{(fired+1)*15}ms" if fired is not None else "未过阈"
    print(f"  -> grooming_readout EMA 首次过阈({THRESH}Hz) @ 窗 {fired}（潜伏 ~{lat}）")

    print(f"\n阶段2: 停注入 × {N_RELAX} 窗（梳理后清零灰尘→回落）\n{hdr}")
    last_active = 0
    for w in range(N_RELAX):
        ro = brain.step({})
        r = ro.readout_rates_hz
        gr = r.get("grooming_readout", 0.0)
        groom_ema = (1 - ALPHA) * groom_ema + ALPHA * gr
        last_active = ro.active_neuron_count
        if w < 6 or w % 5 == 0:
            print(f"{w:4d} {'-':>6} {gr:8.1f} {r.get('adn1_left',0):7.1f} {r.get('adn1_right',0):7.1f} "
                  f"{groom_ema:6.1f} {ro.active_neuron_count:7d}")

    print("\n================= 判定 =================")
    print(f"  触发梳理(EMA过阈): {'✅ 可行' if fired is not None else '❌ 未过阈'}（潜伏 {lat}）")
    print(f"  锁死检查: 回落末窗 active={last_active} → {'⚠ 疑似锁死' if last_active > 2000 else '✅ 未锁死(已回落)'}")


if __name__ == "__main__":
    main()
