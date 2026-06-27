"""独立验证（动态）：在 Shiu 783 LIF 全脑模型上实跑触角梳理回路。

复现 Shiu figures.ipynb Figure 5 的核心可证伪声明：激活 JON 机械感受梳理亚型
(JON-CE / JON-F) → 下游 aBN1 / aDN1 / aDN2 是否显著放电。

设计：建一次 783 网络（model.create_model），把多组候选输入并接到一个可调频率
Poisson 源；逐个实验 restore→设频率→run(1s)→读 aBN1/aDN1/aDN2 发放率。含两个对照：
  - JO-B（旧实现误用的听觉亚型）→ 预期梳理读出≈0（反事实）
  - 直驱 aDN1（旧实现的 Option A 句柄）→ 自身当然放电（说明读出探针没坏）

运行：/opt/miniconda3/envs/brain_env/bin/python tests/probe_grooming_dynamic.py
"""
from __future__ import annotations
import json
from pathlib import Path
import importlib.util
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SHIU = ROOT / "external" / "drosophila_brain_model"
COMP = SHIU / "Completeness_783.csv"
CON = SHIU / "Connectivity_783.parquet"
MODEL = SHIU / "model.py"
FIG5 = ROOT / "data" / "shiu_fig5_grooming_ids.json"
NIDS = ROOT / "data" / "neuron_ids.json"

N_RUN = 5              # 每实验重复次数（Poisson 随机，取均值±std）
T_RUN_MS = 1000.0      # 单 trial 时长


def load_model():
    spec = importlib.util.spec_from_file_location("shiu_model", MODEL)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def main():
    from brian2 import prefs, NeuronGroup, Synapses, Network, Hz, ms, seed as b2seed
    try:
        prefs.codegen.target = "cython"
    except Exception:
        prefs.codegen.target = "numpy"

    model = load_model()
    params = dict(model.default_params)

    fig5 = json.loads(FIG5.read_text()); nids = json.loads(NIDS.read_text())
    comp = pd.read_csv(COMP, index_col=0)
    flyid2i = {int(f): i for i, f in enumerate(comp.index)}

    def idx(ids):
        return [flyid2i[int(x)] for x in ids if int(x) in flyid2i]

    JON_CE = idx(fig5["input"]["neu_JON_CE"])
    JON_F = idx(fig5["input"]["neu_JON_F"])
    JON_Dm = idx(fig5["input"]["neu_JON_D_m"])
    JON_all = JON_CE + JON_F + JON_Dm
    JO_B = idx(nids["sensory"]["jon_left"] + nids["sensory"]["jon_right"])
    aBN1 = idx(fig5["readout"]["aBN1"])
    aDN1 = idx(fig5["readout"]["aDN1"])
    aDN2 = idx(fig5["readout"]["aDN2_left"])
    readouts = {"aBN1": aBN1, "aDN1": aDN1, "aDN2": aDN2}
    print(f"输入规模  JON_CE={len(JON_CE)} JON_F={len(JON_F)} JON_Dm={len(JON_Dm)} JON_all={len(JON_all)} JO_B={len(JO_B)}")
    print(f"读出规模  aBN1={len(aBN1)} aDN1={len(aDN1)} aDN2={len(aDN2)}")

    # ---- 建一次网络 ----
    print("建网中 ...", flush=True)
    from brian2 import SpikeMonitor
    neu, syn, _ = model.create_model(str(COMP), str(CON), params)
    spk = SpikeMonitor(neu, record=False, name="probe_spk")

    # 并接可调 Poisson：把所有候选输入神经元合并，按通道记 slice
    channels = {"JON_CE": JON_CE, "JON_F": JON_F, "JON_all": JON_all, "JO_B": JO_B, "aDN1_direct": aDN1}
    # 注意 JON_all 与 JON_CE/JON_F 索引重叠：各通道单独建一份注入边，互不干扰
    tgt_idx, ch_slice = [], {}
    cursor = 0
    for ch, ids in channels.items():
        ch_slice[ch] = slice(cursor, cursor + len(ids))
        tgt_idx.extend(ids)
        cursor += len(ids)
    n_inp = len(tgt_idx)
    src_idx = list(range(n_inp))

    pois = NeuronGroup(n_inp, "rate : Hz", threshold="rand() < rate * dt", name="probe_poi")
    rates = np.zeros(n_inp)
    pois.rate = rates * Hz
    psyn = Synapses(pois, neu, "w : volt", on_pre="v_post += w", name="probe_drive")
    psyn.connect(i=src_idx, j=tgt_idx)
    psyn.w = params["w_syn"] * params["f_poi"]
    for j in tgt_idx:
        neu[j].rfc = 0 * ms

    net = Network(neu, syn, spk, pois, psyn)
    net.store("base")
    print("建网完成。", flush=True)

    def run_exp(active_channels: dict, label: str):
        """active_channels: {channel_name: rate_hz}。返回各 readout 平均发放率(Hz)。"""
        agg = {k: [] for k in readouts}
        agg["_active_total"] = []
        for r in range(N_RUN):
            net.restore("base")
            b2seed(1234 + r)  # 固定每 trial 种子，使结果可复现
            rates[:] = 0.0
            for ch, hz in active_channels.items():
                rates[ch_slice[ch]] = hz
            pois.rate = rates * Hz
            prev = np.asarray(spk.count, dtype=np.int64).copy()
            net.run(T_RUN_MS * ms)
            delta = np.asarray(spk.count, dtype=np.int64) - prev
            for name, ix in readouts.items():
                agg[name].append(float(delta[ix].mean() / (T_RUN_MS / 1000.0)) if ix else 0.0)
            agg["_active_total"].append(int((delta > 0).sum()))
        res = {k: float(np.mean(v)) for k, v in agg.items()}
        rstd = {k: float(np.std(agg[k])) for k in readouts}
        print(f"  [{label:28s}] " + "  ".join(f"{k}={res[k]:5.1f}±{rstd[k]:4.1f}" for k in readouts)
              + f"  | active={res['_active_total']:.0f}")
        res["_std"] = rstd
        return res

    print(f"\n开始实验（每个 {N_RUN} trial × {T_RUN_MS:.0f}ms）：")
    out = {}
    out["baseline"] = run_exp({}, "baseline 无输入")
    out["JON_CE_140"] = run_exp({"JON_CE": 140}, "JON_CE @140Hz (Fig5)")
    out["JON_F_140"] = run_exp({"JON_F": 140}, "JON_F  @140Hz (Fig5)")
    out["JON_all_140"] = run_exp({"JON_all": 140}, "JON_all @140Hz (Fig5)")
    out["JON_all_200"] = run_exp({"JON_all": 200}, "JON_all @200Hz (Fig5)")
    out["JO_B_140"] = run_exp({"JO_B": 140}, "JO-B @140Hz (旧误用/反事实)")
    out["aDN1_direct_150"] = run_exp({"aDN1_direct": 150}, "直驱 aDN1 @150Hz (旧句柄)")

    print("\n================= 结论判定 =================")
    # 三档：完整前馈通路需下行 aDN 真被驱动(>1Hz) 且 aBN1 显著(>5Hz)；
    # 仅 aBN1 微升(>1Hz) 而 aDN≈0 记为「仅触及中间神经元」；其余未激活。
    for key in ["JON_CE_140", "JON_F_140", "JON_all_140", "JON_all_200"]:
        adn1 = out[key]["aDN1"]; abn1 = out[key]["aBN1"]; adn2 = out[key]["aDN2"]
        down = max(adn1, adn2)
        if down > 1.0 and abn1 > 5.0:
            verdict = "✅ 完整前馈通路打通 (JON→aBN1→aDN1/aDN2)"
        elif abn1 > 1.0:
            verdict = "◐ 仅微弱触及 aBN1, 未驱动下行 aDN"
        else:
            verdict = "❌ 未激活"
        print(f"  {key:14s}: aBN1={abn1:5.1f} aDN1={adn1:5.1f} aDN2={adn2:5.1f}  {verdict}")
    jb = out["JO_B_140"]
    print(f"  反事实 JO-B    : aBN1={jb['aBN1']:.1f} aDN1={jb['aDN1']:.1f} aDN2={jb['aDN2']:.1f}  (应≈baseline {out['baseline']['aDN1']:.1f})")

    (ROOT / "outputs").mkdir(exist_ok=True)
    res_path = ROOT / "outputs" / "grooming_dynamic_result.json"
    res_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\n结果写入 {res_path}")


if __name__ == "__main__":
    main()
