# 数字果蝇 (Digital Fruit Fly)

一个尝试复现 Eon 的具身果蝇的项目。主要使用 FlyGym2/NeuroMechFly 的果蝇**身体**与Shiu et al. 公开的 Brian2 全连接组**脑模型**。

本项目整合**公开**组件，并开发必要的连接模块。

## 双进程 / 双环境架构

身体与脑需要**两个相互依赖冲突的 conda 环境**，无法共享同一进程：

- `flygym_env` —— FlyGym2/NeuroMechFly + numpy/matplotlib/imageio，运行身体模型。
- `brain_env` —— Brian2 + Cython + C 编译器，运行脑模型。


### 运行

```bash
# 方式 A（推荐，单命令）：身体进程自行拉起脑子进程
/opt/miniconda3/envs/flygym_env/bin/python scripts/run_body.py --start-worker

# 方式 B（分终端）
/opt/miniconda3/envs/brain_env/bin/python scripts/run_brain.py     # 终端 1：脑
/opt/miniconda3/envs/flygym_env/bin/python scripts/run_body.py     # 终端 2：身体
```

配置见 `configs/simulation.json`；运行后在outputs/目录下输出果蝇运动视频 + 遥测 JSON）。

### 当前状态

具身闭环已端到端跑通：FlyGym 身体 + Shiu 783 全连接组脑（在线连续积分）+ **直驱 DN 控制句柄**，
果蝇经脑路由的 DN 转向趋食、接触触发 MN9 进食、灰尘触发 aDN1 梳理，三行为循环并输出左身体右脑的并排视频。

里程碑：M1 脑·糖→MN9 ✅ / M2 体·行走 ✅ / M3 IPC 握手 ✅ / M4 趋糖前进 ✅ / M5 多行为 + M6 视频 ✅
（测试：`tests/test_brain_sugar_grn.py`、`test_body_walk.py`、`test_bridge_ipc.py`）

### 上游模型
Shiu 仓库与连接组文件已克隆至本地external/drosophila_brain_model/。

## 目录结构
- `scripts/` —— 存储最终运行脚本，解析用户配置的参数。
- `src/` —— 存储全部模块。
- `data` —— 运行所需的静态原始数据存储在此（例如脑连接组的.csv和.parquet）。
- `configs/` —— 存储用户可配置参数的配置文件。
- `external/drosophila_brain_model/` —— 上游 Shiu 克隆（gitignore，大型 parquet/csv）。
- `outputs/` —— 生成的产物（gitignore）。
- `tests/` —— 测试代码。

## 参考

- Eon Systems —— *The First Multi-Behavior Brain Upload*：https://eon.systems/updates/first-multi-behavior-brain-upload
- Eon Systems —— *We've Uploaded a Fruit Fly*：https://eon.systems/updates/weve-uploaded-a-fruit-fly
- Eon Systems —— *How the Eon Team Produced a Virtual Embodied Fly*：https://eon.systems/updates/embodied-brain-emulation
- Shiu et al.（Nature 2024）：https://www.nature.com/articles/s41586-024-07763-9
- philshiu/Drosophila_brain_model：https://github.com/philshiu/Drosophila_brain_model
- FlyGym/NeuroMechFly：https://github.com/NeLy-EPFL/flygym

