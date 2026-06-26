# 数字果蝇复现开发计划

> 目标：复现 Eon Systems「具身果蝇」的工程成果——Foraging / Feeding / Grooming 三种行为在 FlyGym 身体 + Shiu Brian2 脑的实时闭环中运行。

---

## 技术基线（据技术报告锁定）

| 组件 | 参数 | 来源 |
|---|---|---|
| 脑神经元 | ~138,640 LIF 点神经元（FlyWire v783） | 本地 `Completeness_783.csv` |
| 突触 | ~1468 万神经元对连接 | 本地 `Connectivity_783.parquet` |
| 脑积分步长 | **0.1 ms**（Brian2 dt） | Eon fly-brain 仓库 |
| 脑-体同步步长 | **15 ms** | Eon 博客原文 |
| LIF 参数 | `v_0=-52mV, v_th=-45mV, t_mbr=20ms, tau=5ms, w_syn=0.275mV` | `external/model.py` default_params |
| 身体 | NeuroMechFly v2 / FlyGym，87 关节，MuJoCo | Eon 博客原文 |
| 行走生成 | FlyGym 既有步态控制器（+ 可选模仿学习微调），DN 调制方向/速度 | Eon 博客 §8.3 |
| 行为-DN 映射 | 转向=DNa01/DNa02，前进=oDN1，进食=MN9，触角梳理=触角DN | Eon 博客 §4.2 |

---

## 模块划分

```
src/
  brain/          # brain_env：脑模型包装 + 在线激活接口
  body/           # flygym_env：场地 + 感觉 + 行为控制器
  bridge/         # 共享：IPC 协议定义（两端各自 import）
  viz/            # flygym_env：相机渲染 + 脑活动记录/可视化
configs/
  simulation.yaml # 全局参数（步长、行为触发阈值、场地尺寸等）
scripts/
  run_brain.py    # brain_env 入口
  run_body.py     # flygym_env 入口
```

---

## Phase 1：环境与单组件验证（约 2–3 天）

**目标**：确认双环境可运行，两端单独跑通，建立复现基准。

### 1.1 环境检查
- [ ] 验证 `brain_env` 可导入 Brian2 + pandas + pyarrow，并加载 `Connectivity_783.parquet`（~14万行读取无报错）
- [ ] 验证 `flygym_env` 可导入 FlyGym，能创建最小 MuJoCo 场景并执行 step

### 1.2 脑侧 ground-truth 验证
- [ ] 在 `brain_env` 中用 `model.py` 的 `default_params` 跑通 Shiu 原始实验：
  - 激活**糖 GRN** 神经元 → 检验 **MN9（喙运动）** 是否放电（参照 ruiluohub 的 exp1 模板）
  - 目标：与 Shiu 论文 r ≥ 0.90 的激活率对齐
- [ ] 启用 Brian2 C++ codegen（`set_device('cpp_standalone')`），记录 138k 神经元规模的实际运行速度（ms/step）
- [ ] 输出：`tests/test_brain_sugar_grn.py`，作为后续回归基准

### 1.3 身体侧验证
- [ ] 在 `flygym_env` 中创建平坦地形 + FlyGym 步态控制器，确认果蝇能直线行走 5 秒
- [ ] 验证 FlyGym 的感觉读取接口：腿接触力、触角位置、嗅觉浓度
- [ ] 输出：`tests/test_body_walk.py`

### 1.4 性能基线
- [ ] 记录：脑 1 秒仿真耗时（含/不含 C++ codegen）；身体 1 秒仿真耗时
- [ ] 判断是否需要优化才能达到接近实时（目标：1s 仿真 ≤ 5s 挂钟时间）

---

## Phase 2：场地模型（约 1–2 天）

**目标**：构建有界 MuJoCo 场景，包含食物源和灰尘机制。

### 2.1 场地设计（`src/body/arena.py`）
- [ ] 有界矩形地形（例如 30cm × 30cm），四周透明边界碰撞体（无贴图）
- [ ] **糖食物源**：MuJoCo geom（圆柱体），附加自定义属性 `sugar=True`，关联化学信号场（嗅觉浓度随距离衰减，FlyGym olfaction 接口）
- [ ] **灰尘机制**：不做物理粒子仿真，而用一个轻量状态：
  - 每步按概率在果蝇触角位置累积「灰尘计数」
  - 触角 DN 激活阈值：`dust_count >= DUST_THRESHOLD`（可配置）
  - Grooming 行为执行后重置计数

> 选择此简化实现而非完整粒子系统的原因：Eon 视频中灰尘为"虚构"道具，目的是触发机械感受梳理通路，不需要真实物理模拟。

### 2.2 场地配置（`configs/simulation.yaml`）
```yaml
arena:
  width: 0.30       # m
  height: 0.30      # m
  food_sources:
    - pos: [0.20, 0.15]
      radius: 0.01
      odor_strength: 1.0
  dust:
    accumulation_rate: 0.02   # per step probability
    grooming_threshold: 50
```

---

## Phase 3：IPC 通信协议（约 1–2 天）

**目标**：设计两进程间每 15 ms 的握手协议，保证同步。

### 3.1 协议设计（`src/bridge/protocol.py`）

选用 **ZeroMQ（pyzmq）**：两环境均可 pip 安装，低延迟，无需共享内存权限。

```
脑进程（PUSH）  ──────────────►  体进程（PULL）
  DN 放电率向量（5个DN × float32）

体进程（PUSH）  ──────────────►  脑进程（PULL）
  感觉事件列表（神经元 FlyWire ID + 激活强度 float32）
```

同步流程（每 15 ms 循环）：
1. **体进程**完成 MuJoCo step → 收集感觉事件 → PUSH 到脑
2. **脑进程**收到事件 → 更新 Poisson 注入 → Brian2 推进 15ms（150步@0.1ms）→ 读出 DN 放电率 → PUSH 到体
3. **体进程**收到 DN 指令 → 映射为步态参数 → 下一 MuJoCo step

> 注意：脑的 C++ standalone 模式与在线 IPC 不兼容（codegen 模式生成独立 binary）。闭环运行须使用 Brian2 **运行时模式**（runtime mode，无 `set_device`）。性能不足时再考虑用多步缓冲或 NEST 后端。

### 3.2 消息格式（`src/bridge/messages.py`）
```python
# 体 → 脑
SensoryMessage:
  sugar_grn_left:  float  # 糖 GRN 左侧激活强度 0..1
  sugar_grn_right: float
  odor_intensity:  float  # ORN 激活强度
  dust_mechanical: float  # Johnston 器官激活强度（0 或 1）

# 脑 → 体
MotorMessage:
  dna01: float   # DNa01 放电率（归一化 0..1）
  dna02: float   # DNa02 放电率
  odn1:  float   # oDN1 前进指令
  mn9:   float   # MN9 进食指令
  ant_dn: float  # 触角梳理 DN
```

---

## Phase 4：感觉编码层（约 2 天）

**目标**：把 FlyGym 感觉事件映射为脑内特定神经元的 Poisson 激活。

### 4.1 神经元 ID 查找（`src/brain/sensory_neurons.py`）

从 `Completeness_783.csv` 中按 cell_type / annotation 字段查找：
- 糖 GRN：`cell_type` 包含 "GRN" + 兴奋性 sugar 标注
- 苦 GRN：同上苦味标注
- ORN：嗅觉受体神经元
- Johnston 器官机械感受：触角 mechanosensory 标注

> 若 v783 标注不足以精确定位，参考 Shiu et al. 论文 Supplementary 中的 FlyWire ID 列表作为 fallback。

### 4.2 动态 Poisson 注入接口（`src/brain/online_brain.py`）

Shiu 原始 `poi()` 函数在创建网络时静态绑定。闭环需要**运行时动态调整激活频率**：

```python
# 实现方案：用 PoissonGroup 替代 PoissonInput，可在运行中修改 .rates
class OnlineBrain:
    def step(self, sensory: SensoryMessage, dt_ms=15):
        # 1. 根据感觉消息更新 Poisson rates
        self.sugar_grn_group.rates = sensory.sugar_grn_left * 150 * Hz
        # 2. Brian2 推进 dt_ms
        self.net.run(dt_ms * ms)
        # 3. 读出 DN 放电率
        return self._read_dn_rates()
```

激活强度编码方式（参照 Eon §4.1）：
- 接触 sugar = 完全激活：`r_poi = 150 Hz`
- 无接触：`r_poi = 0 Hz`
- 气味浓度：线性映射到 `0..150 Hz`
- 灰尘机械激活：阈值触发，`r_poi = 150 Hz` 持续 ~100ms

---

## Phase 5：运动解码层（约 2 天）

**目标**：把 DN 放电率映射为 FlyGym 步态参数，实现转向/前进/进食/梳理。

### 5.1 DN 放电率读出（`src/brain/online_brain.py`）

```python
def _read_dn_rates(self) -> MotorMessage:
    # 取 DN 神经元在上一个 15ms 窗口内的平均放电率
    # 归一化为 0..1（基于经验最大值，调参时确定）
    ...
```

### 5.2 运动控制器（`src/body/motor_controller.py`）

行为优先级：`Grooming > Feeding > Foraging`（同 Eon 视频逻辑顺序）

```python
class MotorController:
    def get_action(self, motor: MotorMessage, sensory_state) -> FlyGymAction:
        if motor.ant_dn > GROOMING_THRESHOLD:
            return self._grooming_action()
        if motor.mn9 > FEEDING_THRESHOLD and sensory_state.on_food:
            return self._feeding_action()
        # Foraging：DN 调制 FlyGym 步态控制器
        forward_speed = motor.odn1 * MAX_SPEED
        turn_bias = (motor.dna01 - motor.dna02)  # 正=右转，负=左转
        return self._walking_action(forward_speed, turn_bias)
```

行为具体实现：
- **Foraging（觅食行走）**：FlyGym HybridTurningController，`forward_drive` 由 oDN1 调制，转向由 DNa01-DNa02 不对称差值调制
- **Feeding（进食）**：锁定位置，触发 FlyGym 喙伸展执行器（proboscis extension）持续 ~500ms
- **Grooming（梳理）**：锁定位置，触发前腿触角擦拭动作序列（FlyGym 关节目标角预设姿态），持续 ~300ms，结束后重置灰尘计数

### 5.3 调参项（写入 `configs/simulation.yaml`）
```yaml
motor:
  grooming_threshold: 0.3
  feeding_threshold: 0.4
  max_forward_speed: 0.01   # m/step
  turn_gain: 2.0
  feeding_duration_ms: 500
  grooming_duration_ms: 300
```

---

## Phase 6：闭环联调（约 3 天）

**目标**：两进程 + 三种行为端到端跑通。

### 6.1 单行为验证
- [ ] 趋糖前进：放置食物源 → 果蝇是否通过嗅觉梯度向食物源移动
- [ ] 接触食物 → MN9 激活 → 进食动作触发
- [ ] 灰尘积累到阈值 → 触角 DN 激活 → 梳理动作 → 灰尘清零

### 6.2 多行为切换验证（复现 Eon Demo 序列）
完整行为序列：
1. 嗅觉引导 Foraging → 逼近食物
2. 途中灰尘积累 → 中断行走 → Grooming → 恢复行走
3. 到达食物源 → Feeding

### 6.3 性能调优
若 15ms 窗口内脑推进（runtime 模式）耗时超 15ms 实际时间：
- 优先：减少 SpikeMonitor 监控范围（仅监控 DN + 关键感觉神经元，而非全脑）
- 其次：考虑只对部分神经元子网做在线步进（感觉→DN 通路），全脑仍离线批量运行

---

## Phase 7：可视化系统（约 2–3 天）

**目标**：实时相机 + 脑活动记录，运行结束生成视频。

### 7.1 场地相机（`src/viz/camera.py`）

**最优目标（交互式）**：

使用 MuJoCo 内置的 `mujoco.viewer` (`mjpython` passive viewer)，在独立线程里渲染，主循环每 15ms 刷新：
- 用户可用鼠标调整摄像机视角（MuJoCo viewer 原生支持）
- 同时后台写帧缓冲到内存队列
- 运行结束后用 `imageio` 写成 MP4

若 viewer 线程与仿真线程冲突，降级方案：每 N 步 offscreen render 一帧，运行结束后合并为视频（静默录制）。

```python
# 推荐结构
class ArenaCamera:
    def __init__(self, fly_sim, interactive=True):
        ...
    def on_step(self, frame_data):
        # 将帧写入队列（非阻塞）
        ...
    def save_video(self, path):
        # 从队列合成 MP4
        ...
```

**配置项**（`configs/simulation.yaml`）：
```yaml
camera:
  interactive: true
  fps: 30
  resolution: [1280, 720]
  default_view: "side"   # side / top / follow
  output: "outputs/run_{timestamp}.mp4"
```

### 7.2 脑活动可视化（`src/viz/brain_monitor.py`）

**运行时记录**（brain_env 侧）：
- 每个 15ms 窗口记录所有放电的神经元 ID + 时间戳（稀疏存储）
- 只记录关键子集（DN + 感觉神经元 + 可选全脑下采样），避免爆内存
- 同时记录 DN 放电率时间序列（用于行为对照）

**事后生成视频**（运行结束触发）：
- 在连接组 3D 坐标（若可从 `Completeness_783.csv` 获取）上绘制放电点亮效果
- 或退而求其次：用栅格图（神经元 ID × 时间轴）展示放电密度热力图
- 最终合并脑活动视频 + 场地相机视频为并排输出（参考 Eon Demo 视频左右布局）

```yaml
# configs/simulation.yaml
brain_monitor:
  record_all: false        # true=全脑（内存密集），false=仅 DN + 感觉层
  output: "outputs/brain_{timestamp}.mp4"
  colormap: "hot"
```

---

## 目录结构（完成后）

```
src/
  brain/
    online_brain.py      # OnlineBrain：运行时 Brian2 包装
    sensory_neurons.py   # 从 CSV 查找感觉/DN 神经元 FlyWire ID
  body/
    arena.py             # MuJoCo 场地（食物源 + 灰尘状态）
    motor_controller.py  # DN → 行为 → FlyGym action
  bridge/
    protocol.py          # ZeroMQ 连接管理
    messages.py          # SensoryMessage / MotorMessage dataclass
  viz/
    camera.py            # 场地相机 + MP4 录制
    brain_monitor.py     # 脑活动记录 + 事后视频
scripts/
  run_brain.py           # brain_env 入口（OnlineBrain + ZMQ）
  run_body.py            # flygym_env 入口（Arena + MotorController + Camera + ZMQ）
configs/
  simulation.yaml
tests/
  test_brain_sugar_grn.py
  test_body_walk.py
```

---

## 里程碑与验收标准

| 里程碑 | 验收标准 |
|---|---|
| M1 脑单跑 | 糖 GRN → MN9 激活率 r ≥ 0.90，对应 Shiu 论文基准 |
| M2 体单跑 | 果蝇在有界场地平稳行走 10 秒，无穿墙 |
| M3 IPC 握手 | 空载 15ms 心跳，两端延迟 < 5ms |
| M4 单行为 | 趋糖前进：从随机初始位出发 30s 内到达食物源 |
| M5 多行为 | 完整复现：Foraging → Grooming（灰尘触发）→ Foraging → Feeding |
| M6 视频 | 输出可播放的 MP4，含果蝇视角 + 脑活动并排画面 |

---

## 关键风险与缓解

| 风险 | 可能性 | 缓解策略 |
|---|---|---|
| Brian2 runtime 模式在 15ms 内跑不完 138k 神经元 | 中高 | 仅在线步进感觉→DN 子网；全脑离线记录；或改用 Eon 的 fly-brain 多后端（PyTorch/CUDA） |
| DN FlyWire ID 无法从 v783 标注确定 | 中 | 参照 Shiu 论文 Supplementary；参考 ruiluohub 的 MN9 ID 确认方法 |
| MuJoCo viewer 线程与仿真冲突 | 低中 | 降级到 offscreen render + 事后生成视频 |
| 灰尘→梳理行为 DN 路径不激活 | 中 | 先用直接 Poisson 注入 Johnston 器官 ID 验证；再反查通路 |
| FlyGym 喙伸展执行器 API 不熟悉 | 低 | FlyGym 有 proboscis extension 示例，参照 |
