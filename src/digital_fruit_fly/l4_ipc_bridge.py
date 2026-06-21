"""FlyGym-side bridge that talks to the L4 brain worker over IPC."""

from __future__ import annotations

from dataclasses import dataclass
import socket
from typing import Any

from .ipc_client import TcpJsonlClient
from .ipc_protocol import BrainReadoutMessage, SensoryStateMessage
from .state import BehaviorState, BrainReadout, SensoryState


@dataclass
class IpcBrainBridge:
    """BrainBridge implementation backed by a TCP brain worker."""

    client: Any

    def __post_init__(self) -> None:
        self.request_count = 0
        self.timeout_count = 0
        self.just_completed_grooming = False
        self.last_backend = "not_connected"
        self.last_brain_wall_time_ms = 0.0
        self.last_error = ""
        self.last_readout = BrainReadout(
            behavior_state=BehaviorState.FORAGING,
            forward_drive=0.65,
            turn_bias=0.0,
            grooming_score=0.0,
            feeding_score=0.0,
            mn9_rate_hz=5.0,
            source="ipc_initial_cache",
        )

    @classmethod
    def from_config(cls, ipc_config: dict[str, Any]) -> "IpcBrainBridge":
        client = TcpJsonlClient(
            host=ipc_config.get("host", "127.0.0.1"),
            port=int(ipc_config.get("port", 8765)),
            timeout_s=float(ipc_config.get("timeout_s", 0.05)),
        )
        return cls(client=client)

    def _make_message(self, sensory_state: SensoryState) -> SensoryStateMessage:
        return SensoryStateMessage(
            request_id=self.request_count + 1,
            time_s=sensory_state.time_s,
            food_cue=sensory_state.food_cue,
            turn_bias=sensory_state.turn_bias,
            dust_level=sensory_state.dust_level,
            dust_threshold_reached=sensory_state.dust_threshold_reached,
            food_contact=sensory_state.food_contact,
            food_distance_mm=sensory_state.food_distance_mm,
        )

    def _to_readout(self, response: BrainReadoutMessage) -> BrainReadout:
        return BrainReadout(
            behavior_state=BehaviorState(response.behavior_state),
            forward_drive=response.forward_drive,
            turn_bias=response.turn_bias,
            grooming_score=response.grooming_score,
            feeding_score=response.feeding_score,
            mn9_rate_hz=response.mn9_rate_hz,
            dust_clearance=response.dust_clearance,
            source=response.source,
        )

    def step(self, sensory_state: SensoryState) -> BrainReadout:
        self.request_count += 1
        self.just_completed_grooming = False
        try:
            response = self.client.request(self._make_message(sensory_state))
        except (OSError, TimeoutError, socket.timeout) as exc:
            self.timeout_count += 1
            self.last_backend = "timeout_cache"
            self.last_error = repr(exc)
            self.last_brain_wall_time_ms = 0.0
            return self.last_readout

        self.last_backend = response.backend
        self.last_error = ""
        self.last_brain_wall_time_ms = response.brain_wall_time_ms
        self.just_completed_grooming = bool(response.dust_clearance)
        self.last_readout = self._to_readout(response)
        return self.last_readout

    def telemetry_fields(self) -> dict[str, float | int | str]:
        return {
            "ipc_request_count": self.request_count,
            "ipc_timeout_count": self.timeout_count,
            "ipc_backend": self.last_backend,
            "ipc_brain_wall_time_ms": self.last_brain_wall_time_ms,
            "ipc_last_error": self.last_error,
        }
