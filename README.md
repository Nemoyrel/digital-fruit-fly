# 数字果蝇 L4

这是一个 **L4-only Eon 式具身果蝇演示分支**。当前目标是预先生成汇报视频：左侧为 FlyGym/NeuroMechFly 果蝇身体状态，右侧为 Shiu et al. 公开 Brian2 全量脑模型的读出状态。

本项目只复用公开论文、公开代码和本项目自己的工程桥接逻辑，不声称完成“果蝇脑上传”，也不声称复现 Eon Systems 未公开的内部代码。Eon 公开文章没有披露脑-身 IPC 协议；本项目的 TCP JSON-lines IPC 是自行实现。

## 当前范围

- 仅保留 L4 IPC 工作流。
- 正式 brain backend 只有 `shiu_full`。
- `shiu_full` 必须调用 `external/drosophila_brain_model/model.py:create_model()` 并运行 Brian2 `Network` window。
- 不再保留旧阶段脚本、lookup 表、规则桥或替代 backend 作为演示路径。
- 汇报前可以长时间预跑；如果全量脑模型失败，输出失败 metadata，而不是 fallback 成功。

## 目录结构

```text
configs/                 L4 IPC 默认配置
docs/                    L4 说明和执行计划
external/                本地上游仓库克隆，不提交大型连接组数据
outputs/                 本地生成的视频、日志、图表和 metadata，默认忽略
scripts/                 CLI 入口，只解析参数并调用 src 中 runner/worker
src/digital_fruit_fly/   本项目自己的 L4 Python 实现
tests/                   不依赖 FlyGym/全量 connectome 的单元测试
```

## 准备上游模型

本地需要存在 Shiu et al. 的公开仓库和连接组文件：

```bash
git clone https://github.com/philshiu/Drosophila_brain_model external/drosophila_brain_model
```

`external/drosophila_brain_model/` 包含大型 parquet/csv 数据，已被 `.gitignore` 忽略。

## 运行

Terminal 1，在 `brain_env` 中启动全量脑模型 worker：

```bash
/opt/miniconda3/envs/brain_env/bin/python scripts/run_l4_brain_worker.py --backend shiu_full --host 127.0.0.1 --port 8765
```

Terminal 2，在 `flygym_env` 中运行身体仿真并合成视频：

```bash
/opt/miniconda3/envs/flygym_env/bin/python scripts/run_l4_ipc_embodied_demo.py --host 127.0.0.1 --port 8765 --combine-video
```

无 socket smoke check：

```bash
/opt/miniconda3/envs/brain_env/bin/python scripts/run_l4_brain_worker.py --backend shiu_full --once-smoke --max-startup-s 0
```

`--max-startup-s 0` 表示不设启动时间上限，适合汇报前预计算。失败时脚本会输出 `brain_worker_failed` JSON 并非零退出。

## 输出

L4 IPC demo 写入 `outputs/l4_ipc_embodied_loop/`：

- FlyGym body MP4；
- 黑底脑活动 MP4，或 ffmpeg 不可用时的 GIF fallback；
- body-left / brain-right combined MP4；
- telemetry CSV；
- telemetry plot 和 IPC plot；
- benchmark JSON，记录 worker latency、backend、timeout 和 combined-video metadata；
- metadata JSON，记录配置、输出路径、事件时间和边界说明。

## 边界

- 神经动力学来自 Shiu et al. 公开 Brian2 模型。
- 感觉编码、低维 readout 到身体控制的映射、TCP IPC 和视频面板是本项目自己的工程实现。
- 汇报时应说明这不是 Eon 私有系统复现，也不是完整生物学上传。
- 如果 `shiu_full` 运行失败，应展示失败阶段和 benchmark，而不是用替代输出包装成成功。

## 参考

- Eon Systems: [How the Eon Team Produced a Virtual Embodied Fly](https://eon.systems/updates/embodied-brain-emulation)
- Shiu et al.: [A Drosophila computational brain model reveals sensorimotor processing](https://www.nature.com/articles/s41586-024-07763-9)
- GitHub: [philshiu/Drosophila_brain_model](https://github.com/philshiu/Drosophila_brain_model)
- FlyGym/NeuroMechFly: [flygym](https://github.com/NeLy-EPFL/flygym)
