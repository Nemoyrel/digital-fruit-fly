"""FlyGym-side bridge that talks to the L4 brain worker over IPC."""

from __future__ import annotations

from dataclasses import dataclass, replace
import socket
from typing import Any

from .ipc_client import TcpJsonlClient
from .ipc_protocol import BrainReadoutMessage, SensoryStateMessage
from .state import BehaviorState, BrainReadout, SensoryState


@dataclass
class IpcBrainBridge:
    """BrainBridge implementation backed by a TCP brain worker."""

    client: Any
    brain_sync_interval_s: float = 0.5

    def __post_init__(self) -> None:
        self.step_count = 0
        self.request_count = 0
        self.timeout_count = 0
        self.cached_step_count = 0
        self.last_cache_hit = False
        self.last_request_time_s: float | None = None
        self.behavior_state = BehaviorState.FORAGING
        self.just_completed_grooming = False
        self.last_backend = "not_connected"
        self.last_brain_wall_time_ms = 0.0
        self.last_error = ""
        self.last_extra: dict[str, Any] = {}
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
            timeout_s=float(ipc_config.get("timeout_s", 600.0)),
        )
        return cls(
            client=client,
            brain_sync_interval_s=float(ipc_config.get("brain_sync_interval_s", 0.5)),
        )

    def _make_message(self, sensory_state: SensoryState) -> SensoryStateMessage:
        return SensoryStateMessage(
            request_id=self.request_count,
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

    def _should_use_cached_readout(self, sensory_state: SensoryState) -> bool:
        if self.brain_sync_interval_s <= 0.0:
            return False
        if self.last_request_time_s is None:
            return False
        return (
            sensory_state.time_s - self.last_request_time_s
        ) < self.brain_sync_interval_s

    def _cached_readout(self) -> BrainReadout:
        self.cached_step_count += 1
        self.last_cache_hit = True
        self.just_completed_grooming = False
        self.last_brain_wall_time_ms = 0.0
        self.behavior_state = self.last_readout.behavior_state
        if self.last_readout.dust_clearance:
            return replace(self.last_readout, dust_clearance=0.0)
        return self.last_readout

    def step(self, sensory_state: SensoryState) -> BrainReadout:
        self.step_count += 1
        self.just_completed_grooming = False
        if self._should_use_cached_readout(sensory_state):
            return self._cached_readout()

        self.request_count += 1
        self.last_request_time_s = sensory_state.time_s
        self.last_cache_hit = False
        self.just_completed_grooming = False
        try:
            response = self.client.request(self._make_message(sensory_state))
        except (OSError, TimeoutError, socket.timeout) as exc:
            self.timeout_count += 1
            self.last_backend = "timeout_cache"
            self.last_error = repr(exc)
            self.last_brain_wall_time_ms = 0.0
            self.last_extra = {}
            return self.last_readout

        self.last_backend = response.backend
        self.last_error = ""
        self.last_brain_wall_time_ms = response.brain_wall_time_ms
        self.last_extra = dict(response.extra)
        self.just_completed_grooming = bool(response.dust_clearance)
        self.last_readout = self._to_readout(response)
        self.behavior_state = self.last_readout.behavior_state
        return self.last_readout

    def telemetry_fields(self) -> dict[str, float | int | str]:
        return {
            "ipc_step_count": self.step_count,
            "ipc_request_count": self.request_count,
            "ipc_timeout_count": self.timeout_count,
            "ipc_cached_step_count": self.cached_step_count,
            "ipc_cache_hit": int(self.last_cache_hit),
            "ipc_brain_sync_interval_s": self.brain_sync_interval_s,
            "ipc_last_request_time_s": (
                -1.0
                if self.last_request_time_s is None
                else self.last_request_time_s
            ),
            "ipc_backend": self.last_backend,
            "ipc_brain_wall_time_ms": self.last_brain_wall_time_ms,
            "ipc_last_error": self.last_error,
            "ipc_grooming_rate_hz": float(
                self.last_extra.get("grooming_rate_hz", 0.0)
            ),
            "ipc_shiu_full_used": int(
                bool(self.last_extra.get("shiu_full_used", False))
            ),
            "ipc_brain_window_s": float(self.last_extra.get("brain_window_s", 0.0)),
        }
