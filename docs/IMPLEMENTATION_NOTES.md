# 实现说明与关键实测发现

> 本文记录「数字果蝇」实际落地的架构、相对 `DEVELOPMENT_PLAN.md` 的调整，以及调研/实测得到的关键事实。计划是出发点，本文是经实测校正后的真实实现。

## 1. 架构总览

双进程双环境，TCP JSON-lines 每 15ms 同步窗握手一次（先算脑、再仿真身体）：

```
flygym_env (身体)                          brain_env (脑)
SensoryEncoder ──SensoryMessage(双侧)──►  BrainBackend
  (双侧嗅觉/灰尘/接触)    TCP:8765          ├ 感觉→Poisson 注入
MotorController ◄──MotorMessage(逐DN读出)─┤ ├ OnlineBrain.step(15ms 连续积分)
  (DN→[left,right]+FSM)                    └ 读 MN9 + DN 放电率
FlyGymBody (HybridTurningController)
Viz: 脑活动面板 + 身体相机 → 并排 MP4
```

模块：`src/digital_fruit_fly/{brain,body,bridge,viz}`。

## 2. 相对计划的关键调整（均有实测依据）

| 项 | 计划 | 实际 | 原因 |
|---|---|---|---|
| 连接组 | 783 | **783** ✓ | 138,639 神经元 / 15,091,983 连接 |
| 脑积分模式 | runtime | **runtime + 跨窗连续积分** | 糖→MN9 潜伏 ~30ms，单 15ms 窗看不到运动信号，必须连续积分 |
| 实时性 | 接近实时 | **非实时录制**(15ms 窗≈140ms 挂钟, ~9.4x) | 783 全脑 runtime 跑不到实时；15ms 是同步步长(忠于 Eon)非实时保证 |
| IPC | ZeroMQ | **TCP JSON-lines** | 零依赖、已验证；两 conda 环境无需装 pyzmq |
| 转向 | 纯 DNa01/DNa02 涌现差分 | **直驱 DN 控制句柄** | 见 §3：感觉→DN 转向/前进/梳理不会从连接组涌现 |
| 感觉激活频率 | 「Eon 150Hz」 | 本项目工程设定 | 博客把激活频率列为开放问题，非 Eon 既定值 |
| FlyGym | 1.x(HybridTurningController/OdorArena) | **2.0.2 + flygym_demo** | 本机版本；flygym_demo 提供走路控制器；无原生气味，自建感觉场 |

## 3. 核心实测发现：DN 行为「涌现 vs 直驱」

在 Shiu LIF 点神经元模型上实测感觉→DN 通路（见记忆 `dn-emergence-does-not-work`、脚本 `/tmp/dn_validation.py`）：

- ✅ **糖 GRN → MN9 进食**：唯一干净涌现的运动通路（持续糖→MN9≈80Hz，潜伏 ~30ms）。
- ❌ **oDN1(DNg97) 前进、aDN1(DNg62) 梳理**：任何感觉输入下读出恒为 0（它们由中枢态驱动，不在感觉下游）。
- ❌ **DNa01/DNa02 转向**：会放电，但左右差分**恒定左偏、不跟随刺激侧**（ORN 给左/给右甚至 JON 都左偏），无法用于趋向转向。

这与 Eon 自述吻合：「整合而非涌现」「DN 是**人工指定**的稀疏控制句柄」。故采用 **Option A 直驱 DN 句柄**：身体侧由感觉算出意图 → 注入对应 DN(DNa01/02 左右=转向、oDN1=前进、aDN1=梳理) → 全脑连接组传播 → 读 DN 放电率 → 运动解码。实测直驱使读出干净跟随意图（左强→左主导→左转）。

**连续积分「锁死」陷阱**：强驱大群感觉神经元(ORN/JON，低至 ~8Hz)会点燃全脑自持递归活动(active~5500 且去刺激回不来)。故 ORN/JON 注入默认关闭，只注入 糖(接触) + DN 句柄(单神经元)——全程低活动、稳定。

## 4. 神经元 ID 来源

- 糖 GRN(20)/MN9/grooming readout：上游 Shiu example/figures.ipynb 硬编码，按 783 过滤。
- **DNa01/DNa02/oDN1=DNg97/aDN1=DNg62 的 L/R id**、双侧 ORN(Or42b)/JON/bitter：取自 `flyconnectome/flywire_annotations`(Schlegel et al. 2024)，逐一核对 IN_783。完整注释表存 `data/flywire_783_annotations.parquet`（13.9 万行，可查任意神经元 cell_type/super_class/side）。
- 注册表：`data/neuron_ids.json`（加载时再按 783 校验，缺失自动剔除）。

## 5. 运行

```bash
# 单命令（身体进程自行拉起脑子进程）：
/opt/miniconda3/envs/flygym_env/bin/python scripts/run_body.py --start-worker

# 或分终端：
/opt/miniconda3/envs/brain_env/bin/python scripts/run_brain.py
/opt/miniconda3/envs/flygym_env/bin/python scripts/run_body.py
```

配置见 `configs/simulation.json`。产物（MP4 + 遥测 JSON）写到 `outputs/`。

## 6. 里程碑状态

- M1 脑·糖→MN9：✅ `tests/test_brain_sugar_grn.py`
- M2 体·行走：✅ `tests/test_body_walk.py`
- M3 IPC 握手：✅ `tests/test_bridge_ipc.py`（RTT 0.55ms）
- M4 趋糖前进：✅ 端到端闭环经脑路由 DN 转向 homing 趋食
- M5 多行为序列 / M6 视频：进行中（调参 + 出双画面 MP4）
