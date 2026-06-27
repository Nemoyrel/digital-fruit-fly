# `simulation.json` 参数说明

数字果蝇**身体进程**（`scripts/run_body.py`，在 `flygym_env` 运行）的唯一配置文件，逐参数注释见下。

> **为什么是独立文档而不是行内注释？** 配置以标准 `json.loads` 读取，JSON 不支持 `//` 注释；且 `motor` 组以 `MotorConfig(**config["motor"])` 解包加载，在该组里添加任何多余键会启动即 `TypeError`。因此把注释单独放在本文件，原 `.json` 保持纯净。

**加载链路**：`run_body.py` 读入 → 透传给 `run_embodied_loop(config=...)` → 各模块（`sensing.py` / `arena.py` / `fly_body.py` / `motor_controller.py` / `brain_panel.py` / `ipc.py`）按分组取用。

**命令行覆盖**（`run_body.py` 的参数优先于文件）：

| 命令行参数 | 覆盖的配置项 / 作用 |
| --- | --- |
| `--config <路径>` | 改用别的配置文件（默认 `configs/simulation.json`） |
| `--duration-s <秒>` | 覆盖 `run.duration_s` |
| `--port <端口>` | 覆盖 `ipc.port` |
| `--output-dir <目录>` | 产物输出目录（不在本文件中，默认 `outputs/`） |
| `--no-video` | 跳过渲染，只跑物理 + 写遥测 |
| `--start-worker` | 由身体进程用 `ipc.brain_env_python` 自动拉起脑进程（透传 `--config`，脑侧据此读 `brain` 组） |

---

## `run` —— 运行控制

| 参数 | 当前值 | 说明 |
| --- | --- | --- |
| `duration_s` | `15.0` | 仿真总时长（秒）。决定主循环物理步数 `n_steps = duration_s ÷ 仿真步长`。可被 `--duration-s` 覆盖。 |
| `seed` | `1` | 全局随机种子。传入身体：控制器 `reset(seed)`、灰尘布点用 `seed+3`。固定它保证可复现。 |
| `warmup_s` | `0.05` | 正式循环前的物理预热时长（秒）。让果蝇落地、姿态稳定后再开始决策与记录。 |
| `log_every_steps` | `300` | 每隔多少个物理步写一行遥测（`*_telemetry.json` 的 `rows`）。仅影响日志密度，不影响仿真本身。 |

## `scene` —— 场景几何 + 虚拟感觉编码

既用于在 MuJoCo 世界里摆放围墙/食物/灰尘（`arena.py`），也用于由果蝇位姿**合成**喂给脑的双侧感觉（`sensing.py`）。`flygym 2.0.2` 无气味物理，感觉信号是几何合成的。

| 参数 | 当前值 | 说明 |
| --- | --- | --- |
| `arena_half_size_mm` | `50.0` | 方形场地半边长（mm）。决定四面围墙位置、灰尘撒布范围与地面大小。 |
| `food_position_mm` | `[25.0, 0.0]` | 食物源中心坐标 `(x, y)`（mm）。果蝇出生在原点 `(0,0)`，食物在 +x 方向 25 mm 处。 |
| `food_cue_radius_mm` | `18.0` | 气味/味觉羽流半径（mm）。距食物 ≤ 此半径才有 cue，内部按高斯衰减（σ = 半径 ÷ 1.5）；同时是可视黄色气味斑的半径。决定果蝇"多远能闻到糖"。**从 10 增大到 18 以提高搜索命中容错**（实测 10 时果蝇常擦肩 2–3mm 而错过）。 |
| `food_contact_radius_mm` | `2.5` | 接触/进食判定半径（mm）。果蝇到食物中心距离 ≤ 此值即 `food_contact=True`，是进食行为的门控之一；也决定食物块/接触环的可视大小。 |
| `dust_accumulation_rate_per_s` | `0.22` | 灰尘每秒累积速率（无量纲/秒）。非梳理状态下身上灰尘按此速率线性累积（按当前值约需 `1.0 ÷ 0.22 ≈ 4.5` 秒到阈值）。 |
| `dust_threshold` | `1.0` | 灰尘累积阈值（同时是累积上限）。达到即触发梳理行为；梳理结束后清零。 |
| `bilateral_gain` | `0.7` | 左右感觉不对称增益。依据食物在航向左/右侧，把基线 cue 拆成 `cue_left/right = base·(1 ± g·lateral)`。**这是脑内 DNa01/DNa02 差分放电（→ 转向）的唯一来源**——转向决策在脑里做，这里只提供不对称刺激。越大越"急转向"。 |
| `dust_count` | `200` | 全场撒布的灰尘斑点数量（仅可视、不参与碰撞）。纯视觉效果，不改变灰尘累积逻辑。 |
| `scenery` | *（未列，默认 `true`）* | **远景贴图开关**（仿 Eon 演示视频）：开启时 `arena.py` 把 FlyGym 默认的纯白天空盒改为淡雾蓝白渐变、灰棋盘地面改为沙地，并在场地外围加一圈绿草地 + 低多边形绿丘陵 + 奶白树冠的树（全部 `contype=0` 仅可视、不参与物理）。写 `false` 可关闭、回到素净场景。 |
| `boundary_margin_mm` | `12.0` | **边界回弹**触发距离（mm）：果蝇到最近围墙 < 此值即转向场地中心并减速。由 [`loop.py`](../src/digital_fruit_fly/body/loop.py) 的 `_boundary_steer` 实现（仅 foraging 态生效），防止搜索阶段（无 cue 约束）冲出场地。 |
| `boundary_turn_gain` | `0.5` | 边界回弹的转向强度。越大转回中心越急。 |
| `boundary_slowdown` | `0.6` | 边界回弹的减速比例。贴墙（strength→1）时前进压低到 `1−0.6 = 40%`。 |

## `ipc` —— 身体 ↔ 脑 进程间通信

身体在 `flygym_env`、脑在 `brain_env`，两进程经 TCP + JSON-line 通信。

| 参数 | 当前值 | 说明 |
| --- | --- | --- |
| `host` | `"127.0.0.1"` | 脑进程 TCP 监听/连接地址（本机回环）。 |
| `port` | `8765` | TCP 端口。可被 `--port` 覆盖；`--start-worker` 时一并传给脑进程。 |
| `window_ms` | `15.0` | 身体 → 脑同步窗口（毫秒）：每 15 ms 物理时间向脑查询一次决策，窗内物理步复用上次决策；同时作为脑侧的积分窗长（`--window-ms`）。实测一个 15 ms 窗脑约需 ≈140 ms 计算（≈9.4× 慢于实时）。 |
| `timeout_s` | `600.0` | 单次 IPC 请求的 socket 超时（秒）。 |
| `brain_env_python` | `"/opt/miniconda3/envs/brain_env/bin/python"` | `brain_env` 的 Python 解释器绝对路径。仅在 `--start-worker` 自动拉起脑进程时使用。换机器需改这里。 |
| `worker_ready_timeout_s` | `120.0` | 等待脑进程就绪（完成 Brian2 / 连接组加载）的最长等待（秒），超时则放弃启动。 |

## `render` —— 渲染与视频输出

| 参数 | 当前值 | 说明 |
| --- | --- | --- |
| `camera_res` | `[368, 480]` | 身体相机渲染分辨率（像素），项目语义为 `[帧高, 帧宽]`。`loop.py` 取第 0 项作右侧脑面板高度以对齐左右拼接；改分辨率时保持第 0 项 = 帧高。 |
| `output_fps` | `30` | 输出合成视频的帧率（fps）。 |
| `playback_speed` | `1.0` | 回放速度倍率。`1.0` = 实时；>1 加快、<1 放慢（影响渲染采样）。 |

## `camera` —— 跟踪相机

跟随果蝇的第三人称相机（`fly.add_tracking_camera`，`mode="track"`：随果蝇平移、**朝向固定**由 `rotation_xyaxes` 决定）。当前机位为**低俯角贴地视角**，目的是把果蝇压在前景、让身后的远景（天空 / 丘陵 / 树）露在画面上半部，复刻 Eon 演示视频的取景。

| 参数 | 当前值 | 说明 |
| --- | --- | --- |
| `pos_offset` | `[0, -9, 3.2]` | 相机相对果蝇的位置偏移 `(x, y, z)`（mm）。`y=-9` 在身后、`z=3.2` 略高于果蝇，构成贴地的低机位。 |
| `fovy` | `55.0` | 相机垂直视场角（度）。越大视野越广、果蝇看着越小。 |
| `rotation_xyaxes` | `[1, 0, 0, 0, 0.225, 0.974]` | 相机朝向（MuJoCo `xyaxes`：前 3 个是像面 x 轴、后 3 个是像面 y 轴）。当前 ≈ 向下 13° 的近水平视角，让地平线落在画面上半、露出远景。**留空则用 FlyGym 默认的 ≈37° 大俯角**（看不到天空/远景）。 |

## `brain_viz` —— 右侧脑活动面板可视化

把脑模型逐神经元脉冲计数渲染成"脑形点云"面板，与身体帧并排（`brain_panel.py`）。注意点云**空间坐标是确定性合成的、示意性的**（公开数据无神经元坐标），而每点**亮度来自真实脉冲计数**。

| 参数 | 当前值 | 说明 |
| --- | --- | --- |
| `panel_width` | `520` | 脑面板宽度（像素）；高度取 `camera_res[0]`。 |
| `n_points` | `4000` | 脑形点云初始点数。运行时若与脑回传的逐神经元活动维度不一致，会按后者重建布局（实际点数 = 脑回传的采样神经元数）。 |
| `activity_norm` | `2.0` | 活动归一化分母：`norm = clip(activity ÷ activity_norm, 0, 1)` 再着色。值越小越易饱和（画面越亮）。 |
| `activity_decay` | `0.9` | 帧间活动衰减系数。两次脑查询之间，活动每渲染帧 ×0.9，形成余晖/淡出效果。 |

## `motor` —— 运动解码 + 行为状态机

把脑回传的 DN 放电率解码成 `[left, right]` 下行驱动，并按 **梳理 > 进食 > 觅食** 优先级做时序仲裁（`motor_controller.py`）。

> ⚠️ 该组以 `MotorConfig(**motor)` 解包加载，**不要在此组添加 `MotorConfig` 没有的键**，否则启动即 `TypeError`。

| 参数 | 当前值 | 说明 |
| --- | --- | --- |
| `grooming_duration_s` | `1.0` | 一次梳理持续时长（秒）；结束后清零灰尘。 |
| `feeding_hold_s` | `1.6` | 一次进食保持时长（秒）。 |
| `feeding_mn9_threshold_hz` | `25.0` | 进食触发的 MN9 放电率阈值（Hz）。须"接触食物 **且** MN9 真实放电 ≥ 此值"才进食。MN9 是糖 → 连接组真实涌现的运动神经元（项目中唯一真正涌现的运动信号）。 |
| `turn_gain` | `1.2` | 转向增益。把（左 DN − 右 DN）差分放大成转向量 `turn`（>0 左转）。**调小可缓解盲搜打转**（曾为 2.2，偏大）。 |
| `forward_gain` | `1.15` | 前进增益。把 oDN1 归一化前进量放大成 `forward`。调大让盲搜走得更直；过大会冲出场地，故从 1.4 回收到 1.15。 |
| `max_turn` | `0.35` | 转向量硬上限。钳住急转，杜绝"一侧腿停住"式原地打转（代码默认 `0.6`）。 |
| `min_forward` | `0.3` | 前进量下限。保证始终有净前进，避免净位移≈0 的原地转（代码默认 `0.2`）。 |
| `arrive_slowdown` | `0.85` | **接近食物驻留**：foraging 时 `forward ×= (1 − arrive_slowdown·cue)`。`cue→1`（到达食物）时前进压到 ~15%，停在食物附近取食/徘徊，避免进食后高速冲出场地；`cue=0`（搜索阶段）不减速。 |
| `feeding_refractory_s` | `2.0` | 进食不应期（秒）。一次进食结束后此时长内不再触发进食，促使果蝇离开食物再返回。 |

**该组其余可选键**（`MotorConfig` 的合法字段，JSON 未列时用代码默认值，需要时可补进本组）：
`forward_norm_hz`（前进归一化分母，默认 `150.0`）、`turn_norm_hz`（转向归一化分母，默认 `150.0`）、`max_forward`（前进上限，默认 `1.3`）、`ema_alpha`（前进/转向 EMA 平滑系数，默认 `0.35`）、`dust_threshold`（与 `scene` 同名，梳理触发阈值，默认 `1.0`）。

## `brain` —— 脑后端驱动标定（搜索 / 趋化 / 进食 / 梳理）

由**脑进程** [`run_brain.py`](../scripts/run_brain.py) 读取（`--config`，默认同此配置文件），映射成 [`backend.py`](../src/digital_fruit_fly/brain/backend.py) 的 `BackendConfig`，把身体侧感觉标定成脑内各通道的 Poisson 注入频率（Hz）。`run_body.py --start-worker` 拉起脑进程时会自动透传同一份 `--config`。

> ⚠️ `BackendConfig.from_dict` 只认合法字段、忽略未知键；未列字段一律用代码默认值。

| 参数 | 当前值 | 说明 |
| --- | --- | --- |
| `forward_hz` | `150.0` | oDN1（前进 DN）满量程注入频率（Hz）。 |
| `forward_base` | `0.7` | 无气味时前进基线占比：`odn1 = forward_hz·(forward_base + (1−forward_base)·cue)`。调大让盲搜走得更快更直；与 `forward_gain` 一起从 0.8 回收到 0.7 以免冲出场地（代码默认 `0.6`）。 |
| `turn_hz` | `150.0` | 趋化转向 DN（DNa01/02）满量程注入频率（Hz）；有气味时按同侧 cue 强度注入。 |
| `search_hz` | `55.0` | **无气味搜索摆动**幅度（Hz）。`cue < cue_eps` 时叠加到转向 DN，让扫掠更平缓（代码默认 `90`）。 |
| `search_freq_hz` | `0.7` | **无气味搜索摆动**频率（Hz）。摆动周期 = 1 ÷ 此值。调大缩短单向转时长，把"画圈"变"蛇形扫掠"前进（代码默认 `0.3`，即周期 3.33 s、前后各 1.67 s 单向转 → 易打转）。 |
| `sugar_max_hz` | `150.0` | 接触食物时糖 GRN 注入频率（Hz）。这是**唯一保留的真涌现通路**（糖 → MN9 进食）。 |
| `groom_hz` | `150.0` | 灰尘达阈值时 aDN1（梳理 DN）注入频率（Hz）。 |
| `cue_eps` | `0.05` | "有/无气味"判定阈值。`max(cue_left, cue_right) < cue_eps` 即进入搜索摆动模式。 |

