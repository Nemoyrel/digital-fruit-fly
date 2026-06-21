"""Brain worker backends and TCP server for L4 IPC demos."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import shutil
import socket
import threading
from time import perf_counter
from typing import Any

from .brain_bridge import _clip
from .ipc_protocol import (
    BrainReadoutMessage,
    SensoryStateMessage,
    decode_message,
    encode_message,
)
from .state import BehaviorState


@dataclass(frozen=True)
class BrainWorkerConfig:
    """Runtime configuration for the L4 brain worker."""

    brain_window_s: float = 0.015
    grooming_duration_s: float = 1.0
    feeding_hold_s: float = 0.8
    max_turn_drive: float = 0.55
    max_startup_s: float = 10.0
    project_root: Path = field(
        default_factory=lambda: Path(__file__).resolve().parents[2]
    )


@dataclass(frozen=True)
class BackendSelection:
    """Selected backend and performance/environment metadata."""

    backend_name: str
    backend: Any
    metadata: dict[str, Any]


def _brain2_environment_metadata() -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "compiler_available": any(
            shutil.which(name) for name in ("clang", "gcc", "g++")
        ),
    }
    try:
        import brian2
        from brian2 import prefs

        metadata["brian2_version"] = brian2.__version__
        if metadata["compiler_available"]:
            try:
                prefs.codegen.target = "cython"
            except Exception:
                prefs.codegen.target = "numpy"
        metadata["codegen_target"] = str(prefs.codegen.target)
    except Exception as exc:
        metadata["brian2_version"] = None
        metadata["codegen_target"] = "unavailable"
        metadata["brian2_error"] = repr(exc)
    return metadata


class Brian2ProxyBackend:
    """Small online Brian2-style worker backend used for stable IPC demos."""

    backend_name = "brian2_proxy"

    def __init__(self, config: BrainWorkerConfig) -> None:
        self.config = config
        self.behavior_state = BehaviorState.FORAGING
        self.state_until_s = 0.0
        self.mn9_voltage_mV = -52.0
        self.grooming_voltage_mV = -52.0
        self.request_count = 0
        self.metadata = _brain2_environment_metadata()

    def _advance_voltage(self, current: float, stimulus: float) -> float:
        target = -52.0 + _clip(stimulus, 0.0, 1.0) * 9.0
        updated = current + 0.75 * (target - current)
        return -52.0 if updated >= -45.0 else updated

    def handle(self, message: SensoryStateMessage) -> BrainReadoutMessage:
        start = perf_counter()
        self.request_count += 1

        self.mn9_voltage_mV = self._advance_voltage(
            self.mn9_voltage_mV,
            message.food_cue,
        )
        self.grooming_voltage_mV = self._advance_voltage(
            self.grooming_voltage_mV,
            message.dust_level,
        )
        feeding_score = _clip(message.food_cue, 0.0, 1.0)
        grooming_score = _clip(message.dust_level, 0.0, 1.0)
        mn9_rate_hz = 5.0 + 85.0 * feeding_score
        grooming_rate_hz = 4.0 + 70.0 * grooming_score

        dust_clearance = 0.0
        if (
            self.behavior_state == BehaviorState.GROOMING
            and message.time_s >= self.state_until_s
        ):
            self.behavior_state = BehaviorState.FORAGING
            self.state_until_s = 0.0
            dust_clearance = 1.0
        elif self.behavior_state == BehaviorState.GROOMING:
            pass
        elif message.dust_threshold_reached:
            self.behavior_state = BehaviorState.GROOMING
            self.state_until_s = message.time_s + self.config.grooming_duration_s
        elif message.food_contact:
            self.behavior_state = BehaviorState.FEEDING
            self.state_until_s = max(
                self.state_until_s,
                message.time_s + self.config.feeding_hold_s,
            )
        elif message.time_s >= self.state_until_s:
            self.behavior_state = BehaviorState.FORAGING

        if self.behavior_state == BehaviorState.GROOMING:
            forward_drive = 0.0
            turn_bias = 0.0
        elif self.behavior_state == BehaviorState.FEEDING:
            forward_drive = 0.0
            turn_bias = 0.0
        else:
            forward_drive = _clip(0.72 + 0.4 * feeding_score - 0.12 * grooming_score, 0.12, 1.35)
            turn_bias = _clip(
                message.turn_bias * (0.25 + 0.75 * feeding_score),
                -self.config.max_turn_drive,
                self.config.max_turn_drive,
            )

        wall_ms = (perf_counter() - start) * 1000.0
        return BrainReadoutMessage(
            request_id=message.request_id,
            behavior_state=self.behavior_state.value,
            forward_drive=forward_drive,
            turn_bias=turn_bias,
            grooming_score=0.0 if dust_clearance else grooming_score,
            feeding_score=feeding_score,
            mn9_rate_hz=mn9_rate_hz,
            dust_clearance=dust_clearance,
            source="brain_worker:brian2_proxy",
            backend=self.backend_name,
            brain_wall_time_ms=wall_ms,
            brain_simulated_window_s=self.config.brain_window_s,
            cache_hit=False,
            extra={
                "mn9_voltage_mV": self.mn9_voltage_mV,
                "grooming_voltage_mV": self.grooming_voltage_mV,
                "grooming_rate_hz": grooming_rate_hz,
                "request_count": self.request_count,
                **self.metadata,
            },
        )


class ShiuFullBackend:
    """Fast-failing wrapper for a full Shiu Brian2 model attempt."""

    backend_name = "shiu_full"

    def __init__(self, config: BrainWorkerConfig) -> None:
        self.config = config
        self.available = False
        self.fallback_reason = ""
        self.metadata = _brain2_environment_metadata()
        self._attempt_startup()

    def _attempt_startup(self) -> None:
        if self.config.max_startup_s <= 0:
            self.fallback_reason = "startup budget was 0s; full Shiu load skipped"
            return
        started = perf_counter()
        repo = self.config.project_root / "external" / "drosophila_brain_model"
        required = [
            repo / "model.py",
            repo / "2023_03_23_completeness_630_final.csv",
            repo / "2023_03_23_connectivity_630_final.parquet",
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            self.fallback_reason = f"missing Shiu model files: {missing}"
            return
        if perf_counter() - started > self.config.max_startup_s:
            self.fallback_reason = "full Shiu startup exceeded budget"
            return
        self.fallback_reason = (
            "full Shiu online backend is available only as a benchmark attempt; "
            "using proxy unless explicitly benchmarked"
        )

    def handle(self, message: SensoryStateMessage) -> BrainReadoutMessage:
        proxy = Brian2ProxyBackend(self.config)
        response = proxy.handle(message)
        return BrainReadoutMessage(
            **{
                **response.__dict__,
                "source": "brain_worker:shiu_full_unavailable",
                "backend": "brian2_proxy",
                "extra": {
                    **response.extra,
                    "shiu_full_attempted": True,
                    "fallback_reason": self.fallback_reason,
                },
            }
        )


def select_backend(name: str, config: BrainWorkerConfig) -> BackendSelection:
    """Select a backend while recording environment and fallback metadata."""
    metadata = _brain2_environment_metadata()
    if name == "brian2_proxy":
        backend = Brian2ProxyBackend(config)
        return BackendSelection("brian2_proxy", backend, {**metadata, "fallback_reason": ""})
    if name == "shiu_full":
        backend = ShiuFullBackend(config)
        return BackendSelection(
            "shiu_full" if backend.available else "brian2_proxy",
            backend if backend.available else Brian2ProxyBackend(config),
            {**metadata, "fallback_reason": backend.fallback_reason},
        )
    if name == "auto":
        shiu = ShiuFullBackend(config)
        if shiu.available:
            return BackendSelection("shiu_full", shiu, {**metadata, "fallback_reason": ""})
        return BackendSelection(
            "brian2_proxy",
            Brian2ProxyBackend(config),
            {**metadata, "fallback_reason": shiu.fallback_reason},
        )
    raise ValueError(f"Unknown brain worker backend: {name}")


class L4BrainWorkerServer:
    """Minimal blocking TCP JSON-lines server for brain worker requests."""

    def __init__(self, *, host: str, port: int, backend: Any) -> None:
        self.host = host
        self.port = port
        self.backend = backend
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def bound_port(self) -> int:
        if self._sock is None:
            return self.port
        return int(self._sock.getsockname()[1])

    def serve_forever(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))
            sock.listen()
            sock.settimeout(0.1)
            self._sock = sock
            while not self._stop.is_set():
                try:
                    conn, _addr = sock.accept()
                except TimeoutError:
                    continue
                with conn:
                    raw = conn.makefile("rb").readline()
                    if not raw:
                        continue
                    request = decode_message(raw)
                    if not isinstance(request, SensoryStateMessage):
                        continue
                    conn.sendall(encode_message(self.backend.handle(request)))

    def serve_background(self) -> threading.Thread:
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()
        return self._thread

    def shutdown(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                with socket.create_connection((self.host, self.bound_port), timeout=0.1):
                    pass
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1.0)


def smoke_response(backend_name: str, config: BrainWorkerConfig) -> dict[str, Any]:
    """Return one synthetic backend response as plain JSON-compatible data."""
    selection = select_backend(backend_name, config)
    message = SensoryStateMessage(
        request_id=1,
        time_s=0.0,
        food_cue=1.0,
        turn_bias=0.0,
        dust_level=0.0,
        dust_threshold_reached=False,
        food_contact=True,
        food_distance_mm=0.5,
    )
    response = selection.backend.handle(message)
    return {
        "selection": {
            "backend_name": selection.backend_name,
            "metadata": selection.metadata,
        },
        "response": json.loads(encode_message(response).decode("utf-8")),
    }
