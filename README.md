# 数字果蝇

复现一个**Eon 式具身果蝇模型**。

项目基于公开论文和开源工具，做一个可解释、可降级、可演示的工程原型。

## 项目目标

最终至少完成 **L3：脑模型实证接入**：

- 使用或复用 Shiu et al. 的果蝇全脑 LIF 模型；
- 为关键感觉输入生成离线神经读出表；
- 将这些读出接入具身仿真；
- 输出可用于汇报的视频、日志和图表。

同时尝试 **L4：实时在线 LIF**：

- 尝试在身体仿真循环中在线调用 LIF 模型；
- 记录运行时间、内存和同步问题；
- 如果计算资源不足，则降级为缓存窗口、低频更新、代理模型或离线查表；
- 明确说明降级原因，不让 L4 影响 L3 交付。

## 最小系统架构

```text
虚拟环境
  -> 感觉状态
  -> 脑模型读出
       L3：离线 LIF 查表
       L4：在线 LIF 尝试或降级
  -> BrainBridge
  -> FlyGym/NeuroMechFly 虚拟身体
  -> 日志、图表、视频
```

演示内容：

1. 果蝇从起点进入觅食状态；
2. 食物线索影响前进和转向；
3. 虚拟尘埃触发梳理行为；
4. 接触食物后触发 MN9/feeding 读出；
5. 输出一段 30-60 秒演示视频，并同步展示传感状态、脑读出和行为状态。

## 目录结构

```text
configs/                 小型 YAML/JSON 配置，例如脑模型、身体和演示场景
data/                    小型派生数据，尤其是 LIF 脑读出查表
docs/                    文献笔记、报告、图表和汇报材料
external/                可选的上游仓库克隆，例如 drosophila_brain_model 或 flygym
outputs/                 运行日志、截图、视频和 benchmark 结果
scripts/                 演示入口脚本
src/                     本项目自己的实现代码
```

可复用逻辑都放在 `src/digital_fruit_fly/`；`scripts/` 存放演示入口脚本。默认运行参数放在 `configs/l1_body.json` 和 `configs/l2_embodied_loop.json`。

根目录存有两份项目调研阶段的报告：

- `digital-fruit-fly-research-report.html`：技术脉络调研报告；
- `minimal-eon-embodied-fly-report.html`：任务清单。

## 里程碑

| 等级 | 目标 | 产物 |
| --- | --- | --- |
| L1 | 跑通 FlyGym/NeuroMechFly 身体基线 | 身体运动截图或视频 |
| L2 | 建立最小具身闭环 | 规则版 `brain_bridge`、传感日志、演示视频 |
| L3 | 接入实证脑模型读出 | LIF 查表驱动的演示、读出曲线和日志 |
| L4 | 尝试在线 LIF 耦合 | benchmark、成功记录或降级说明 |

## 关键参考

- Shiu et al., 2024, *Nature*：成年果蝇全脑 LIF 计算模型；
- `philshiu/Drosophila_brain_model`：公开 Brian2 代码仓库；
- FlyWire：成年果蝇全脑连接组；
- FlyGym/NeuroMechFly：基于 MuJoCo 的具身果蝇仿真；
- Eon Systems 公开文章：虚拟具身果蝇的系统集成思路。

## 当前状态

L1 和 L2 基线已经可以运行：

```bash
conda activate flygym_env
python scripts/run_l1_flygym_body_demo.py --duration 3 --pattern sweep
python scripts/run_l2_embodied_demo.py --duration 10
```

L2 已输出规则版 `sensory_state -> brain_readout -> behavior_state -> action`
闭环，结果包含视频、telemetry CSV、metadata 和简要图表，默认保存在
`outputs/l2_embodied_loop/`。L2 的 dust 规则参考 Eon 公开说明：全局 fictive
dust 会在果蝇身上累积，达到阈值后停止并进入 grooming，grooming 完成后清零并继续行动
（<https://eon.systems/updates/embodied-brain-emulation>）。当前 grooming/feeding
只是状态输出，还没有自定义头部、前腿或 proboscis actuator 的可视化动作；这些等 L3 后再考虑。当前 L2 读出是明确的工程占位实现；L3 需要把关键读出来源替换为 LIF 查表输出。
