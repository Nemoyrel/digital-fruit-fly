"""数字果蝇：FlyGym 身体 + Shiu 全连接组脑（双进程 IPC）具身演示。

注意：本 ``__init__`` 刻意保持轻量，只导入纯标准库 / numpy-light 的共享类型。
重型子模块（loop/demo/fly_body/arena/brain_viz 依赖 flygym/matplotlib/imageio；
brain_backend/brain_server 依赖 brian2）请按需显式导入，以免在缺少对应依赖的环境
（如 brain_env 没有 matplotlib）里导入子模块时连带失败。
"""

from __future__ import annotations

from .drive import readout_to_descending_signal
from .messages import BrainReadoutMessage, SensoryStateMessage
from .sensing import SceneConfig, VirtualEnvironment
from .state import BehaviorState, BrainReadout, SensoryState

__all__ = [
    "BehaviorState",
    "BrainReadout",
    "BrainReadoutMessage",
    "SceneConfig",
    "SensoryState",
    "SensoryStateMessage",
    "VirtualEnvironment",
    "readout_to_descending_signal",
]
