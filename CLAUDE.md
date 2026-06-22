# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目是什么

数字果蝇 —— 一个参考 Eon 的具身果蝇复现演示项目。它把 FlyGym/NeuroMechFly 的果蝇**身体**与
Shiu et al. 公开的 Brian2 全连接组**脑模型**耦合起来，作为两个进程运行，彼此通过 TCP JSON-lines IPC 桥
交换 `感觉状态 → 脑读出`，并产出**左身体、右脑活动**并排的实时汇报视频，以及 telemetry / benchmark / metadata。

本项目只整合**公开**组件。它**不是**果蝇脑上传，也**不是**对 Eon Systems 的完全复现 —— 见
[边界](#边界在任何汇报文档中都要声明)。

## 双进程 / 双环境架构（最核心的设计事实）

身体与脑运行在**两个相互依赖冲突的 conda 环境**中，无法共享同一进程：

- `flygym_env` —— FlyGym/NeuroMechFly + numpy/matplotlib/imageio，运行身体 loop 与视频合成。
- `brain_env` —— Brian2 + Cython + C 编译器，运行脑 worker。

两者通过 TCP JSON-lines 在 `127.0.0.1:8765`（默认）通信。该传输是**本项目自行实现的**，并非 Eon 披露过的协议。

```
flygym_env                                          brain_env
scripts/run_demo.py                                 scripts/run_brain_worker.py
 └ demo.run_demo                                      └ BrainWorkerServer (TCP)
    └ loop.run_embodied_loop                             └ ShiuFullBackend.handle()
        VirtualEnvironment.observe() ─SensoryState─▶        Brian2ShiuEngine.run_window():
                                                             net.restore("baseline"); 设 Poisson rate;
        IpcBrainBridge.step()        ◀─BrainReadout──        net.run(window); spk_mon.count 逐神经元计数
        readout_to_descending_signal()                       + MN9/grooming 读出 + 下采样活动向量
        FlyGymBody.apply_behavior()  (运动/梳理/进食 → MuJoCo step + 渲染)
        BrainPanelRenderer.render()  (右侧脑活动面板)
        compositor.hstack_frame()    (左身体 | 右脑 → 合成 mp4)
```

关键：脑读出消息里带一个**下采样的逐神经元脉冲计数向量**（`neuron_activity`，默认 4000 个），
身体侧据此逐帧渲染右侧脑活动面板。

## 常用命令

### 测试
测试使用标准库 `unittest`；脑后端通过**依赖注入的假引擎（FakeEngine）**替换，因此**不需要 Brian2 / FlyGym / 连接组数据**
（只需 numpy + matplotlib，`flygym_env` 中均有）：

```bash
# 整个测试套件（注意 -t tests，用于加载 tests/_bootstrap.py）
/opt/miniconda3/envs/flygym_env/bin/python -m unittest discover -s tests -t tests
# 单个模块 / 用例
/opt/miniconda3/envs/flygym_env/bin/python -m unittest tests.test_brain_backend
```

没有 pytest、requirements 文件或构建步骤。`tests/_bootstrap.py` 负责把 `src/` 加入 `sys.path`，
每个测试文件 `import _bootstrap`。

### 运行演示（两个终端）
```bash
# 终端 1 —— 在 brain_env 启动脑 worker
/opt/miniconda3/envs/brain_env/bin/python scripts/run_brain_worker.py --backend shiu_full --host 127.0.0.1 --port 8765
# 终端 2 —— 在 flygym_env 运行身体 loop 并合成视频
/opt/miniconda3/envs/flygym_env/bin/python scripts/run_demo.py --host 127.0.0.1 --port 8765
```
也可让 demo 自行拉起 worker：加 `--start-worker`（用 config 里的 `ipc.brain_env_python` 启动子进程）。
合成视频用 imageio + libx264（imageio-ffmpeg 自带），不依赖系统 ffmpeg。

### worker 冒烟检查（不开 socket）
```bash
/opt/miniconda3/envs/brain_env/bin/python scripts/run_brain_worker.py --backend shiu_full --once-smoke
```
任何失败时 worker 会打印 `brain_worker_failed` JSON 并以非零码退出（绝不用兜底输出包装成成功）。

### 首次准备上游模型
Shiu 仓库与连接组文件已被 gitignore，需在本地克隆：
```bash
git clone https://github.com/philshiu/Drosophila_brain_model external/drosophila_brain_model
```

## 当前目录结构与逻辑归属
- `scripts/` —— **只能**是 thin CLI wrapper：解析参数、把 `src/` 加入 `sys.path`、调用包内函数。
  仿真 / 渲染 / IPC 逻辑不得写在这里。`run_brain_worker.py`（brain_env）、`run_demo.py`（flygym_env）。
- `src/digital_fruit_fly/` —— 全部真实逻辑。**`__init__.py` 刻意保持轻量**（只导入纯标准库/numpy-light
  的共享类型），因为导入任一子模块都会先执行 `__init__`，而 brain_env 没有 matplotlib/imageio、
  flygym_env 没有 brian2。重型子模块按需显式导入。各模块职责：
  - 共享（两端都用，纯 stdlib/numpy-light）：`state.py`（BehaviorState/SensoryState/BrainReadout）、
    `messages.py`（IPC 消息 + encode/decode）、`ipc_client.py`、`brain_neurons.py`（硬编码 FlyWire ID）、
    `drive.py`（readout→左右驱动）、`sensing.py`（VirtualEnvironment 感觉编码）、`config.py`。
  - 脑侧（brain_env，惰性 import brian2/pandas）：`brain_backend.py`（`Brian2ShiuEngine` 真实引擎 +
    `ShiuFullBackend` 行为状态机/评分/下采样，**引擎可注入假实现以便测试**）、`brain_server.py`（TCP 服务 +
    `select_backend` + `smoke_response`）。
  - 身体侧（flygym_env，惰性 import flygym/matplotlib/imageio）：`arena.py`（围墙/食物/气味斑/落灰）、
    `fly_body.py`（`FlyGymBody`：运动/梳理/进食 + 位姿 + 渲染，legs-only 果蝇）、
    `brain_link.py`（`IpcBrainBridge`：节流 + 读出缓存 + 携带最新神经元活动）、
    `brain_viz.py`（确定性脑形点云布局 + 逐帧活动面板渲染）、`compositor.py`（左右帧拼接 + 写 mp4）、
    `loop.py`（具身 loop 编排）、`telemetry.py`、`demo.py`（编排入口）。
- `configs/demo.json` —— 唯一的 demo 配置（`run`/`scene`/`ipc`/`render`/`camera`/`brain_viz`）。
- `external/drosophila_brain_model/` —— 上游 Shiu 克隆（gitignore，大型 parquet/csv）。不要修改它；
  worker 在运行时通过 `importlib` 导入 `model.py` 并调用 `create_model()`。
- `outputs/` —— 生成的产物（gitignore）。

## 行为模型
worker 运行一个 `FORAGING / GROOMING / FEEDING / HALTED` 状态机（`brain_backend.py: ShiuFullBackend.handle`），
受感觉量与神经元读出门控。感觉量 `food_cue` / `dust_level` 驱动 Brian2 Poisson 输入 rate（落到 sugar GRN /
JON GRN）；MN9（`MN9_FLYWIRE_ID`）与梳理读出神经元的脉冲速率转成 `feeding_score` / `grooming_score`。
灰尘超过阈值触发一段定时 grooming，结束时给出一次性 `dust_clearance`，身体侧据此 `scene.clear_dust()`。
每个脑窗用 `spk_mon.count` 读出**全部神经元**（127400）的脉冲计数，再把相邻神经元**分箱求和**（`np.add.reduceat`，
默认 4000 箱）下采样成 `neuron_activity` 送回身体侧渲染脑面板——分箱求和保留全部脉冲，使稀疏的真实活动（约 0.5% 神经元/窗）在面板上可见。
脑窗默认 **0.05s**（实测：20ms 太短，糖味觉→MN9 的进食信号来不及传导，50ms 才能让 MN9/grooming 读出对感觉输入特异响应）。

## 关键运行事实（来自源码核对，便于不重复踩坑）
- 这套 `flygym` 是**定制构建**（`flygym.compose.Fly/FlatGroundWorld`、`flygym.Simulation`、
  `flygym_demo.complex_terrain.*`），不是 PyPI 上的 stock flygym2。装在 `…/flygym_env/lib/python3.12/site-packages/`。
- `make_locomotion_fly` 用 **LEGS_ONLY** 骨架：只有腿部 DoF 被驱动，**没有喙/触角 DoF**。
  因此“梳理/进食”靠**前腿动作 + 停步**表现（前腿 = `JointDOF.child.pos in {"lf","rf"}`，与 `action.joint_angles` 同序）。
- 渲染：`sim.renderer.frames[cam_name]` 是逐帧 RGB ndarray 列表；`save_video` 用 imageio+libx264。
  合成视频靠**逐帧抓取**这些帧与 matplotlib 脑面板帧 hstack，得到真正的“同屏”双面板，无需系统 ffmpeg。
- 连接组 completeness 表只有 `[FlyWire ID, Completed]` 两列 —— **没有坐标/类型/半球标签**，
  故脑面板布局必须确定性合成（示意性脑形），亮度才用真实脉冲。

## 边界（在任何汇报/文档中都要声明）
- 神经动力学来自 **Shiu et al. 公开 Brian2 模型**。感觉编码、readout→身体的映射、TCP IPC、脑面板布局都是
  **本项目自己的工程桥接**。
- 不要声称「果蝇脑上传」或复现 Eon 未公开的内部实现；Eon 的文章没有披露其 IPC 协议。
- 如果 `shiu_full` 失败，应展示失败阶段 + benchmark —— 绝不用兜底输出包装成成功。
- 新增关于 Eon / FlyWire / Nature / Shiu / FlyGym 的事实性描述时，请附上来源。

## 参考
- Eon Systems —— *How the Eon Team Produced a Virtual Embodied Fly*：https://eon.systems/updates/embodied-brain-emulation
- Shiu et al.（Nature 2024）：https://www.nature.com/articles/s41586-024-07763-9
- philshiu/Drosophila_brain_model：https://github.com/philshiu/Drosophila_brain_model
- FlyGym/NeuroMechFly：https://github.com/NeLy-EPFL/flygym
