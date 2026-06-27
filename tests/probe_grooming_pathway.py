"""独立验证：触角梳理回路在 783 连接组中的静态通路。

回答的问题（独立于旧 docs 结论）：Shiu et al. figures.ipynb Figure 5 的梳理回路
——JON(机械感受 CE/F/D_m 亚型) → aBN1 → aDN1/aDN2——在 v783 连接组里是否真实存在、
突触强度与符号如何；并与旧实现误用的 JO-B(听觉亚型) 输入做反事实对照。

纯静态：只查 Connectivity_783.parquet / annotations，不跑仿真。
运行：/opt/miniconda3/envs/brain_env/bin/python tests/probe_grooming_pathway.py
"""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SHIU = ROOT / "external" / "drosophila_brain_model"
COMP = SHIU / "Completeness_783.csv"
CON = SHIU / "Connectivity_783.parquet"
ANN = ROOT / "data" / "flywire_783_annotations.parquet"
FIG5 = ROOT / "data" / "shiu_fig5_grooming_ids.json"
NIDS = ROOT / "data" / "neuron_ids.json"


def hdr(s):
    print("\n" + "=" * 78 + f"\n{s}\n" + "=" * 78)


def main():
    fig5 = json.loads(FIG5.read_text())
    nids = json.loads(NIDS.read_text())
    JON_CE = [int(x) for x in fig5["input"]["neu_JON_CE"]]
    JON_F = [int(x) for x in fig5["input"]["neu_JON_F"]]
    JON_Dm = [int(x) for x in fig5["input"]["neu_JON_D_m"]]
    JON_all = JON_CE + JON_F + JON_Dm
    aBN1 = [int(x) for x in fig5["readout"]["aBN1"]]
    aDN1 = [int(x) for x in fig5["readout"]["aDN1"]]
    aDN2 = [int(x) for x in fig5["readout"]["aDN2_left"]]
    # 旧实现误用的 JON 输入（JO-B 听觉亚型）
    old_jon = [int(x) for x in nids["sensory"]["jon_left"]] + [int(x) for x in nids["sensory"]["jon_right"]]

    hdr("0) 数据加载")
    comp = pd.read_csv(COMP, index_col=0)
    present = set(int(x) for x in comp.index)
    print(f"Completeness_783: {len(present)} 神经元")

    def cov(name, ids):
        ok = [i for i in ids if i in present]
        print(f"  {name:14s}: {len(ok)}/{len(ids)} 在 783 中存在 ({100*len(ok)/max(1,len(ids)):.0f}%)")
        return ok

    hdr("1) ID 存在性校验（figures.ipynb 为 v630，校验是否仍在 v783）")
    JON_CE = cov("JON_CE", JON_CE); JON_F = cov("JON_F", JON_F); JON_Dm = cov("JON_D_m", JON_Dm)
    JON_all = JON_CE + JON_F + JON_Dm
    print(f"  -> JON_all 有效: {len(JON_all)}")
    aBN1 = cov("aBN1", aBN1); aDN1 = cov("aDN1", aDN1); aDN2 = cov("aDN2_left", aDN2)
    old_jon = cov("old_jon(JO-B)", old_jon)

    hdr("2) 读出神经元 + 输入样例的 annotation 身份核对")
    ann = pd.read_parquet(ANN, columns=["root_id", "super_class", "cell_class", "cell_type", "hemibrain_type", "side", "top_nt"])
    ann = ann.set_index("root_id")

    def show(label, ids, n=6):
        print(f"\n[{label}] ({len(ids)} 个，显示前 {min(n,len(ids))})")
        sub = ann.reindex(ids)
        cols = ["super_class", "cell_class", "cell_type", "hemibrain_type", "side", "top_nt"]
        print(sub[cols].head(n).to_string())
        # cell_type 分布
        vc = sub["cell_type"].value_counts(dropna=False)
        print("  cell_type 计数:", dict(list(vc.items())[:8]))

    show("aBN1 (读出)", aBN1)
    show("aDN1 (读出)", aDN1)
    show("aDN2 (读出)", aDN2)
    show("JON_CE (Fig5 输入)", JON_CE)
    show("JON_F (Fig5 输入)", JON_F)
    show("old_jon = JO-B (旧实现误用输入)", old_jon)

    hdr("3) 静态连接追踪（Connectivity_783：syn=Connectivity, 带符号权重=Excitatory x Connectivity）")
    con = pd.read_parquet(CON, columns=["Presynaptic_ID", "Postsynaptic_ID", "Connectivity", "Excitatory", "Excitatory x Connectivity"])
    print(f"加载连接表: {len(con):,} 行")

    def path(pre_ids, post_ids, label):
        m = con[con["Presynaptic_ID"].isin(pre_ids) & con["Postsynaptic_ID"].isin(post_ids)]
        if m.empty:
            print(f"  {label:34s}: 无连接")
            return
        syn = int(m["Connectivity"].sum())
        signed = float(m["Excitatory x Connectivity"].sum())
        npairs = len(m)
        nexc = int((m["Excitatory"] > 0).sum()); ninh = int((m["Excitatory"] < 0).sum())
        print(f"  {label:34s}: {npairs:4d} 对, Σsyn={syn:5d}, Σ带符号={signed:+8.0f}  (兴奋对 {nexc} / 抑制对 {ninh})")

    print("\n-- 输入 → aBN1（new_report1 称 v630 为 103/78 突触；下为 v783 实测，应≈77/69）--")
    path(JON_CE, aBN1, "JON_CE  -> aBN1")
    path(JON_F, aBN1, "JON_F   -> aBN1")
    path(JON_Dm, aBN1, "JON_D_m -> aBN1")
    path(JON_all, aBN1, "JON_all -> aBN1")

    print("\n-- aBN1 → 下行神经元 aDN1/aDN2 --")
    path(aBN1, aDN1, "aBN1 -> aDN1")
    path(aBN1, aDN2, "aBN1 -> aDN2")

    print("\n-- 输入 → aDN1/aDN2（直接，预期弱：回路应经 aBN1 间接）--")
    path(JON_all, aDN1, "JON_all -> aDN1 (直接)")
    path(JON_all, aDN2, "JON_all -> aDN2 (直接)")

    print("\n-- 反事实对照：旧实现误用的 JO-B → 梳理回路（预期≈无）--")
    path(old_jon, aBN1, "old_jon(JO-B) -> aBN1")
    path(old_jon, aDN1, "old_jon(JO-B) -> aDN1")
    path(old_jon, aDN2, "old_jon(JO-B) -> aDN2")

    print("\n-- JON_all 的总下游广度（看是否会引发全脑泛激活）--")
    m = con[con["Presynaptic_ID"].isin(JON_all)]
    print(f"  JON_all 直接下游神经元数: {m['Postsynaptic_ID'].nunique()}  (总突触 {int(m['Connectivity'].sum()):,})")
    mb = con[con["Presynaptic_ID"].isin(old_jon)]
    print(f"  JO-B   直接下游神经元数: {mb['Postsynaptic_ID'].nunique()}  (总突触 {int(mb['Connectivity'].sum()):,})")


if __name__ == "__main__":
    main()
