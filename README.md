# 数字果蝇 (Digital Fruit Fly)

一个参考 [Eon](https://eon.systems/updates/embodied-brain-emulation) 的**具身果蝇**复现演示：
把 [FlyGym/NeuroMechFly](https://github.com/NeLy-EPFL/flygym) 的果蝇**身体**与
[Shiu et al.（Nature 2024）](https://www.nature.com/articles/s41586-024-07763-9) 公开的
[Brian2 全连接组**脑模型**](https://github.com/philshiu/Drosophila_brain_model) 耦合起来，
作为两个进程运行，通过 TCP JSON-lines 交换 `感觉状态 → 脑读出`，
最终产出**左身体、右脑活动**并排的实时视频。

## 行为叙事

果蝇的动作由脑模型的神经元激活状态读出驱动：

1. **觅食 FORAGING**：默认无味觉线索时随机搜索；进入糖食物源的气味羽流后趋向食物。
2. **进食 FEEDING**：接触食物后停步取食（进食运动神经元 MN9 的脉冲速率 → `feeding_score`）。
3. **梳理 GROOMING**：身体持续累积灰尘，达阈值时停步、抬前腿对搓清理，清零后继续
   （梳理下行神经元脉冲速率 → `grooming_score`）。

## 双进程 / 双环境架构（核心设计）

身体与脑运行在两个相互依赖冲突的 conda 环境，无法共享同一进程：

- `flygym_env` —— FlyGym/NeuroMechFly + numpy/matplotlib/imageio，运行身体 loop 与视频合成。
- `brain_env` —— Brian2 + C 编译器，运行脑 worker。

二者通过 TCP JSON-lines 在 `127.0.0.1:8765`（默认）通信。该传输是**本项目自行实现的**，
并非 Eon 披露过的协议。

```
flygym_env                                          brain_env
scripts/run_demo.py                                 scripts/run_brain_worker.py
 └ demo.run_demo                                      └ BrainWorkerServer (TCP)
    └ loop.run_embodied_loop                             └ ShiuFullBackend.handle()
        VirtualEnvironment.observe() ─SensoryState─▶        Brian2ShiuEngine.run_window():
                                                             restore baseline → 设 Poisson rate →
        IpcBrainBridge.step()        ◀─BrainReadout──        net.run(window) → spk_mon.count
        readout_to_descending_signal()                       逐神经元计数 + MN9/grooming 读出
        FlyGymBody.apply_behavior()  (运动/梳理/进食 → MuJoCo step + 渲染)
        BrainPanelRenderer.render()  (右侧脑活动面板)
        compositor.hstack_frame()    (左身体 | 右脑 → 合成视频)
```

## 准备上游模型（首次）

Shiu 仓库与连接组数据已被 gitignore，需在本地克隆：

```bash
git clone https://github.com/philshiu/Drosophila_brain_model external/drosophila_brain_model
```

## 运行（两个终端）

```bash
# 终端 1 —— 在 brain_env 启动脑 worker
/opt/miniconda3/envs/brain_env/bin/python scripts/run_brain_worker.py \
    --backend shiu_full --host 127.0.0.1 --port 8765

# 终端 2 —— 在 flygym_env 运行身体 loop 并合成视频
/opt/miniconda3/envs/flygym_env/bin/python scripts/run_demo.py \
    --host 127.0.0.1 --port 8765
```

也可让 demo 自行拉起 worker（用 config 里的 `ipc.brain_env_python` 启动子进程）：

```bash
/opt/miniconda3/envs/flygym_env/bin/python scripts/run_demo.py --start-worker
```

合成视频用 imageio + libx264（imageio-ffmpeg 自带编码器），不依赖系统 ffmpeg。

### worker 冒烟检查（不开 socket）

```bash
/opt/miniconda3/envs/brain_env/bin/python scripts/run_brain_worker.py \
    --backend shiu_full --once-smoke
```

构建后端、对一条合成请求返回一次响应后退出。任何失败时打印 `brain_worker_failed` JSON 并以非零码退出。

## 测试

测试使用标准库 `unittest`；脑后端通过**依赖注入的假引擎**替换，因此**不需要 Brian2 / FlyGym / 连接组数据**
（只需 numpy + matplotlib，`flygym_env` 中均有）：

```bash
/opt/miniconda3/envs/flygym_env/bin/python -m unittest discover -s tests -t tests
```

## 输出产物（`outputs/digital_fruit_fly/`）

- `*_combined.mp4` —— 左身体、右脑并排的合成视频（主产物）。
- `*_body.mp4` —— 仅身体画面。
- `*_summary.png` —— 感觉量 / 神经读出 / 行为的汇总图。
- `*.csv` —— 逐步遥测。
- `*_benchmark.json` —— IPC 请求数、超时数、脑窗 wall-time 统计。
- `*_metadata.json` —— 完整配置、事件时间、行为计数、边界声明、来源。

## 边界

- 神经动力学来自 **Shiu et al. 公开 Brian2 模型**。
- 感觉编码、readout→身体/驱动的映射、TCP IPC、脑活动面板的**点云布局**都是**本项目自己的工程桥接**。
- 脑面板的神经元**空间坐标在公开数据中并不可得**（completeness 表只有 FlyWire ID 与 Completed 两列），
  因此布局是**确定性合成、示意性的**脑形；但每个点的**亮度来自脑模型真实计算出的脉冲计数**（127400 神经元按相邻分箱求和成 4000 个可视化点）。

## 参考

- Eon Systems —— *How the Eon Team Produced a Virtual Embodied Fly*：https://eon.systems/updates/embodied-brain-emulation
- Shiu et al.（Nature 2024）：https://www.nature.com/articles/s41586-024-07763-9
- philshiu/Drosophila_brain_model：https://github.com/philshiu/Drosophila_brain_model
- FlyGym/NeuroMechFly：https://github.com/NeLy-EPFL/flygym
