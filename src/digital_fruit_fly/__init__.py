"""Local implementation for the minimal embodied fruit fly demo."""

from .brain_bridge import BrainBridge, RuleBrainBridge, readout_to_descending_signal
from .l1_demo import run_l1_body_demo
from .l2_demo import run_l2_embodied_demo
from .state import BehaviorState, BrainReadout, SensoryState
from .virtual_environment import VirtualEnvironment

__all__ = [
    "BehaviorState",
    "BrainBridge",
    "BrainReadout",
    "RuleBrainBridge",
    "SensoryState",
    "VirtualEnvironment",
    "run_l1_body_demo",
    "run_l2_embodied_demo",
    "readout_to_descending_signal",
]
