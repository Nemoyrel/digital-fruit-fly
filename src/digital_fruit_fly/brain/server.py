from __future__ import annotations

import csv
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Literal, Mapping

from digital_fruit_fly.bridge.messages import (
    SCHEMA_VERSION,
    BrainFrame,
    BridgeFrame,
    ErrorFrame,
    Hello,
    JsonObject,
    JsonValue,
    SensoryFrame,
    Shutdown,
    payload_checksum,
)
from digital_fruit_fly.bridge.transport import (
    FramedJsonSocket,
    TransportError,
    TransportTimeoutError,
    TruncatedFrameError,
)
from digital_fruit_fly.runtime.logging import append_jsonl
from digital_fruit_fly.runtime.run_manifest import RunLayout, create_run_layout


BrainServerMode = Literal["fixture", "brian2"]
ReadyCallback = Callable[["BoundAddress"], None]


@dataclass(frozen=True)
class BoundAddress:
    host: str; port: int

    def as_tuple(self) -> tuple[str, int]:
        return (self.host, self.port)


@dataclass(frozen=True)
class BrainServerConfig:
    host: str; port: int; run_id: str; mode: BrainServerMode
    max_ticks: int; output_dir: Path; tick_ms: int; timeout_s: float
    mapping_path: Path; shiu_repo_path: Path; completeness_path: Path; connectivity_path: Path


@dataclass(frozen=True)
class BrainServerResult:
    exit_reason: str; ticks: int; run_dir: Path
    rates_path: Path; events_path: Path; server_log_path: Path


@dataclass(frozen=True)
class BrainTick:
    tick_index: int; rate_hz: Dict[str, float]; spike_deltas: Dict[str, int]; wall_time_sec: float


class FixtureBrain:
    """Deterministic in-process brain used for bridge and process tests."""

    def __init__(self, tick_ms: int) -> None:
        self._tick_ms = tick_ms
        self._tick_index = 0

    def tick(self, channel_values: Mapping[str, float]) -> BrainTick:
        started = time.monotonic()
        self._tick_index += 1
        drive = _mean_channel_drive(channel_values)
        rates = {
            "forward": 8.0 + 40.0 * drive,
            "turn": 2.0 + 10.0 * (channel_values.get("left_mechanosensory", 0.0) - channel_values.get("right_mechanosensory", 0.0)),
            "feed": 3.0 + 25.0 * channel_values.get("sugar_grn", 0.0),
            "groom": 1.0 + 30.0 * channel_values.get("dust_load", 0.0),
            "stop": 1.0 + 5.0 * (1.0 - drive),
        }
        spikes = {name: max(0, int(rate * self._tick_ms / 1000.0)) for name, rate in rates.items()}
        return BrainTick(
            tick_index=self._tick_index,
            rate_hz=rates,
            spike_deltas=spikes,
            wall_time_sec=time.monotonic() - started,
        )


class Brian2Brain:
    """Brian2-backed brain runtime; only construct inside brain_env."""

    def __init__(self, config: BrainServerConfig) -> None:
        from digital_fruit_fly.brain.mapping import (
            load_brian_index_map,
            load_neural_mapping,
            validate_neural_mapping,
        )
        from digital_fruit_fly.brain.tickable_network import (
            ChannelConfig,
            ReadoutConfig,
            ShiuModelPaths,
            TickableBrainConfig,
            TickableBrainNetwork,
        )

        mapping = load_neural_mapping(config.mapping_path)
        validation = validate_neural_mapping(mapping, load_brian_index_map(config.completeness_path))
        sensory = tuple(
            ChannelConfig(channel.channel_name, channel.brian_indices, 250.0)
            for channel in validation.channels
            if channel.kind == "sensory" and channel.usable
        )
        readouts = tuple(
            ReadoutConfig(channel.channel_name, channel.brian_indices)
            for channel in validation.channels
            if channel.kind == "motor" and channel.usable
        )
        tick_config = TickableBrainConfig(float(config.tick_ms), sensory, readouts)
        self.sensory_channel_names = tuple(channel.name for channel in sensory)
        self._network = TickableBrainNetwork.shiu(
            tick_config,
            ShiuModelPaths(config.shiu_repo_path, config.completeness_path, config.connectivity_path),
        )

    def tick(self, channel_values: Mapping[str, float]) -> BrainTick:
        result = self._network.tick(channel_values)
        return BrainTick(result.tick_index, result.rate_hz, result.spike_deltas, result.wall_time_sec)


def serve_brain(config: BrainServerConfig, on_ready: ReadyCallback | None = None) -> BrainServerResult:
    layout = create_run_layout(config.output_dir, config.run_id)
    rates_path = layout.brain_dir / "rates.csv"
    server_log_path = layout.logs_dir / "brain_server.jsonl"
    _write_rates_header(rates_path)
    append_jsonl(layout.events_path, {"kind": "brain_server_start", "mode": config.mode})
    brain = _build_runtime(config)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((config.host, config.port))
        listener.listen(1)
        listener.settimeout(config.timeout_s)
        bound = BoundAddress(config.host, listener.getsockname()[1])
        if on_ready is not None:
            on_ready(bound)
        exit_reason, ticks = _accept_and_serve(listener, config, layout, rates_path, server_log_path, brain)

    append_jsonl(layout.events_path, {"kind": "brain_server_stop", "reason": exit_reason, "ticks": ticks})
    return BrainServerResult(exit_reason, ticks, layout.run_dir, rates_path, layout.events_path, server_log_path)


def _accept_and_serve(
    listener: socket.socket,
    config: BrainServerConfig,
    layout: RunLayout,
    rates_path: Path,
    server_log_path: Path,
    brain: FixtureBrain | Brian2Brain,
) -> tuple[str, int]:
    try:
        conn, peer = listener.accept()
    except socket.timeout:
        append_jsonl(layout.events_path, {"kind": "accept_timeout"})
        return ("accept_timeout", 0)
    append_jsonl(server_log_path, {"kind": "client_connected", "peer": str(peer)})
    with conn:
        transport = FramedJsonSocket(conn, timeout_s=config.timeout_s)
        transport.send_frame(Hello(SCHEMA_VERSION, config.run_id, 0, 0.0, time.monotonic(), "brain"))
        if not _receive_body_hello(transport, config, layout):
            return ("handshake_failed", 0)
        return _serve_frames(transport, config, layout, rates_path, brain)


def _serve_frames(
    transport: FramedJsonSocket,
    config: BrainServerConfig,
    layout: RunLayout,
    rates_path: Path,
    brain: FixtureBrain | Brian2Brain,
) -> tuple[str, int]:
    expected_frame = 0
    ticks = 0
    while True:
        try:
            frame = transport.recv_frame()
        except TransportTimeoutError:
            return ("transport_timeout", ticks)
        except TruncatedFrameError:
            return ("client_closed", ticks)
        except TransportError:
            return ("transport_error", ticks)
        if isinstance(frame, Shutdown):
            append_jsonl(layout.events_path, {"kind": "shutdown", "reason": frame.reason})
            return ("shutdown", ticks)
        if isinstance(frame, SensoryFrame):
            if ticks >= config.max_ticks:
                _send_protocol_error(transport, config, layout, frame, "max_ticks_reached", "maximum ticks reached")
                return ("max_ticks_reached", ticks)
            if frame.frame_index != expected_frame:
                _send_protocol_error(transport, config, layout, frame, "frame_index_skipped", f"expected {expected_frame}")
                return ("protocol_error", ticks)
            tick = brain.tick(_channel_values(frame.payload, getattr(brain, "sensory_channel_names", None)))
            response = _brain_frame(config.run_id, frame, tick)
            transport.send_frame(response)
            _append_rate_rows(rates_path, frame, tick)
            expected_frame += 1
            ticks += 1
            continue
        _send_protocol_error(transport, config, layout, frame, "unexpected_frame", "expected sensory_frame or shutdown")
        return ("protocol_error", ticks)


def _receive_body_hello(transport: FramedJsonSocket, config: BrainServerConfig, layout: RunLayout) -> bool:
    frame = transport.recv_frame()
    if isinstance(frame, Hello) and frame.run_id == config.run_id:
        append_jsonl(layout.events_path, {"kind": "handshake", "peer_role": frame.role})
        return True
    _send_protocol_error(transport, config, layout, frame, "handshake_failed", "expected matching body hello")
    return False


def _build_runtime(config: BrainServerConfig) -> FixtureBrain | Brian2Brain:
    if config.mode == "fixture":
        return FixtureBrain(config.tick_ms)
    return Brian2Brain(config)


def _brain_frame(run_id: str, source: SensoryFrame, tick: BrainTick) -> BrainFrame:
    payload: JsonObject = {
        "rates_hz": tick.rate_hz,
        "spike_deltas": tick.spike_deltas,
        "tick_index": tick.tick_index,
        "wall_time_sec": tick.wall_time_sec,
    }
    return BrainFrame(
        SCHEMA_VERSION,
        run_id,
        source.frame_index,
        source.simulation_time_s,
        time.monotonic(),
        payload,
        payload_checksum(payload),
    )


def _send_protocol_error(
    transport: FramedJsonSocket,
    config: BrainServerConfig,
    layout: RunLayout,
    frame: BridgeFrame,
    code: str,
    message: str,
) -> None:
    details: JsonObject = {"received_frame_index": frame.frame_index}
    append_jsonl(layout.events_path, {"kind": "protocol_error", "code": code, "message": message, "details": details})
    if transport.closed:
        return
    try:
        transport.send_frame(ErrorFrame(SCHEMA_VERSION, config.run_id, frame.frame_index, frame.simulation_time_s, time.monotonic(), code, message, details))
    except OSError:
        return


def _channel_values(payload: JsonObject, allowed_names: tuple[str, ...] | None = None) -> Dict[str, float]:
    allowed = set(allowed_names) if allowed_names is not None else None
    return {
        key: parsed
        for key, value in payload.items()
        if (allowed is None or key in allowed) and (parsed := _unit_float(value)) is not None
    }


def _unit_float(value: JsonValue) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return min(1.0, max(0.0, float(value)))
    return None


def _mean_channel_drive(values: Mapping[str, float]) -> float:
    if len(values) == 0:
        return 0.0
    return sum(values.values()) / len(values)


def _write_rates_header(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow(("frame_index", "simulation_time_s", "readout", "rate_hz", "spike_delta"))


def _append_rate_rows(path: Path, frame: SensoryFrame, tick: BrainTick) -> None:
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        for readout, rate in tick.rate_hz.items():
            writer.writerow((frame.frame_index, frame.simulation_time_s, readout, rate, tick.spike_deltas.get(readout, 0)))
