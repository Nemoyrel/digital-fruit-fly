# 数字果蝇

一个最小 **Eon 式具身果蝇模型**复现项目。项目只复用公开论文、公开代码和本项目自己的工程桥接逻辑，不声称完成“果蝇脑上传”，也不声称复现 Eon Systems 未公开的内部代码。

## 当前状态

当前已完成 **L3 最小可运行链路**：

- L1：FlyGym/NeuroMechFly 身体基线可运行；
- L2：规则版 `sensory_state -> brain_readout -> behavior_state -> action` 闭环可运行；
- L3：离线脑读出查表已生成，并通过 `LookupBrainBridge` 接入 FlyGym 身体仿真；
- L4：`level4-branch` 上新增了小型在线 LIF proxy 尝试、脑状态动画和实时 telemetry/benchmark 输出。
- L4 IPC：`codex/l4-ipc-brain-worker` 上新增 `brain_env` Brian2 worker + `flygym_env` FlyGym 主循环的 TCP JSON-lines IPC 尝试。

L3 的关键边界：

- sugar/MN9 行来自 `philshiu/Drosophila_brain_model` 上游示例 spike parquet；
- dust/grooming 行当前是小型 Brian2 LIF proxy，使用 Shiu 模型同风格的 LIF 常量，不是完整 connectome 运行；
- 行为门控、turn/forward 映射和 FlyGym 控制是本项目自己的工程桥接。
- L4 在线部分是小型 LIF-style proxy 和 timing benchmark，不是完整 Shiu connectome 在线运行。
- L4 IPC 使用本项目自己的 TCP JSON-lines 协议；Eon 公开文章没有披露具体脑-身 IPC 协议。
- L4/L2/L3 的场景感知现在不会在气味场外泄漏食物方向；`food_cue == 0` 时使用 seeded random search，进入 cue radius 后才使用趋化 `turn_bias`；L4 额外用 `search_turn_gain` 放大气味外搜索转向，避免视频里随机搜索过弱。

## 目录结构

```text
configs/                 L1/L2/L3 默认配置，不使用 --config 任意路径参数
data/                    小型派生数据，例如 L3 lookup table
docs/                    说明、文献笔记和里程碑文档
external/                可选本地上游仓库克隆，不提交大型上游数据
outputs/                 本地生成的视频、日志、图表和 metadata，默认忽略
scripts/                 CLI 入口，只解析参数并调用 src 中 runner
src/digital_fruit_fly/   本项目自己的可复用 Python 实现
```

## 快速运行

先准备两个 conda 环境：

```bash
conda activate flygym_env
python scripts/run_l1_flygym_body_demo.py --duration 3 --pattern sweep
python scripts/run_l2_embodied_demo.py --duration 10
```

生成 L3 lookup table：

```bash
conda activate brain_env
python scripts/generate_l3_brain_lookup.py
```

运行 L3 embodied demo：

```bash
conda activate flygym_env
python scripts/run_l3_embodied_demo.py --duration 6.5 --log-every-steps 50
```

运行 L4 online LIF 尝试：

```bash
conda activate flygym_env
python scripts/run_l4_embodied_demo.py --duration 8 --log-every-steps 50
```

运行 L4 IPC brain worker 尝试：

```bash
# Terminal 1
/opt/miniconda3/envs/brain_env/bin/python scripts/run_l4_brain_worker.py --backend auto --host 127.0.0.1 --port 8765

# Terminal 2
/opt/miniconda3/envs/flygym_env/bin/python scripts/run_l4_ipc_embodied_demo.py --duration 8 --combine-video
```

无视频快速检查：

```bash
conda activate flygym_env
python scripts/run_l3_embodied_demo.py --duration 5 --no-video --no-plot
```

## L3 产物

生成的 L3 lookup 文件：

- `data/l3_brain_readout_lookup.csv`
- `data/l3_brain_readout_lookup_metadata.json`
- `outputs/l3_brain/l3_brain_readout_lookup_report.json`

L3 demo 运行后会在 `outputs/l3_embodied_loop/` 下生成：

- `*.mp4`：FlyGym 渲染视频；
- `*.csv`：逐帧 telemetry，含 sensory、readout、behavior、action 和 pose；
- `*_telemetry.png`：紧凑读出图；
- `*_metadata.json`：配置、事件时间、输出路径和边界说明。

最近一次本地验证中，dust 在约 `4.5655s` 达到阈值并进入 grooming，在约 `5.5656s` 清零后回到 foraging。

## L4 产物

L4 demo 运行后会在 `outputs/l4_embodied_loop/` 下生成：

- `*.mp4`：FlyGym 身体运动视频；
- `*_brain_state.mp4`：脑模型 proxy 实时状态动画，如果本机 ffmpeg 可用；
- `*_brain_state.gif`：ffmpeg 不可用时的脑状态动画 fallback；
- `*_l4_telemetry.png`：包含 `dust_level`、`food_cue`、readout、behavior 和在线更新时间的图；
- `*_brain_benchmark.json`：在线脑更新耗时、缓存步数、目标同步频率和是否达标；
- `*.csv` / `*_metadata.json`：逐帧 telemetry 和复现实验 metadata。

详见 `docs/l4_online_lif.md`。

## L4 IPC 产物

L4 IPC demo 运行后会在 `outputs/l4_ipc_embodied_loop/` 下生成：

- FlyGym 身体视频；
- 脑状态 MP4 或 GIF fallback；
- 左侧身体、右侧脑状态的 combined video，如果本机视频工具可用；
- IPC telemetry plot，包含 worker latency、backend、timeout/cache 状态；
- CSV 和 metadata JSON。

详见 `docs/l4_ipc_brain_worker.md`。

## 上游依赖

L3 查表生成需要本地存在上游仓库：

```bash
git clone https://github.com/philshiu/Drosophila_brain_model external/drosophila_brain_model
```

`external/drosophila_brain_model/` 包含大型连接组 parquet，已被 `.gitignore` 忽略。项目应提交本项目生成的小型 lookup，而不是提交上游大型原始输出。

## 参考

- Eon Systems: [How the Eon Team Produced a Virtual Embodied Fly](https://eon.systems/updates/embodied-brain-emulation)
- Shiu et al.: [A Drosophila computational brain model reveals sensorimotor processing](https://www.nature.com/articles/s41586-024-07763-9)
- GitHub: [philshiu/Drosophila_brain_model](https://github.com/philshiu/Drosophila_brain_model)
- FlyGym/NeuroMechFly: [flygym](https://github.com/NeLy-EPFL/flygym)
