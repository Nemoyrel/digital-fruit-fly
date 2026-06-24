# 数字果蝇 (Digital Fruit Fly)

一个尝试复现 Eon 的具身果蝇的项目。主要使用 FlyGym2/NeuroMechFly 的果蝇**身体**与Shiu et al. 公开的 Brian2 全连接组**脑模型**。

本项目整合**公开**组件，并开发必要的连接模块。

## 双进程 / 双环境架构

身体与脑需要**两个相互依赖冲突的 conda 环境**，无法共享同一进程：

- `flygym_env` —— FlyGym/NeuroMechFly + numpy/matplotlib/imageio，运行身体模型。
- `brain_env` —— Brian2 + Cython + C 编译器，运行脑模型。


### 运行

```bash
# 终端 1 —— 在 brain_env 启动脑模型
/opt/miniconda3/envs/brain_env/bin/python scripts/run_brain.py
# 终端 2 —— 在 flygym_env 运行身体模型
/opt/miniconda3/envs/flygym_env/bin/python scripts/run_body.py
```

### 上游模型
Shiu 仓库与连接组文件已克隆至本地external/drosophila_brain_model/。

## 目录结构
- `scripts/` —— 存储最终运行脚本，解析用户配置的参数。
- `src/` —— 存储全部模块。
- `data` —— 如有运行所需的静态原始数据，存储在此（例如脑模型的原始输出数据）。
- `configs/` —— 存储用户可配置参数的配置文件。
- `external/drosophila_brain_model/` —— 上游 Shiu 克隆（gitignore，大型 parquet/csv）。
- `outputs/` —— 生成的产物（gitignore）。
- `tests/` —— 测试代码，开发时如有必要，只进行最关键的测试。

## 参考

- Eon Systems —— *The First Multi-Behavior Brain Upload*：https://eon.systems/updates/first-multi-behavior-brain-upload
- Eon Systems —— *We've Uploaded a Fruit Fly*：https://eon.systems/updates/weve-uploaded-a-fruit-fly
- Eon Systems —— *How the Eon Team Produced a Virtual Embodied Fly*：https://eon.systems/updates/embodied-brain-emulation
- Shiu et al.（Nature 2024）：https://www.nature.com/articles/s41586-024-07763-9
- philshiu/Drosophila_brain_model：https://github.com/philshiu/Drosophila_brain_model
- FlyGym/NeuroMechFly：https://github.com/NeLy-EPFL/flygym

