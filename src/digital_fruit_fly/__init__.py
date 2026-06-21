"""L4-only embodied fruit fly demo package."""

from .brain_bridge import readout_to_descending_signal
from .l4_ipc_bridge import IpcBrainBridge
from .l4_ipc_demo import run_l4_ipc_embodied_demo
from .state import BehaviorState, BrainReadout, SensoryState
from .virtual_environment import VirtualEnvironment

__all__ = [
    "BehaviorState",
    "BrainReadout",
    "IpcBrainBridge",
    "SensoryState",
    "VirtualEnvironment",
    "run_l4_ipc_embodied_demo",
    "readout_to_descending_signal",
]
