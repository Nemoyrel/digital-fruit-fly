from __future__ import annotations

import socket
import time
from typing import assert_never

from digital_fruit_fly.body.server_motion import unit, unit_rate
from digital_fruit_fly.body.server_types import (
    BodyRunContext,
    BodyServerRuntimeError,
    BrainReply,
)
from digital_fruit_fly.bridge.messages import (
    SCHEMA_VERSION,
    BrainFrame,
    BridgeFrame,
    ControlFrame,
    ErrorFrame,
    Heartbeat,
    Hello,
    SensoryFrame,
    Shutdown,
    payload_checksum,
)
from digital_fruit_fly.bridge.transport import FramedJsonSocket, TransportError
from digital_fruit_fly.runtime.timeouts import JsonObject


class FixtureBrainPeer:
    def __init__(self, run_id: str, tick_ms: int) -> None:
        self._run_id = run_id
        self._tick_ms = tick_ms

    def next_frame(self, source: SensoryFrame) -> BrainReply:
        drive = unit(source.payload["sugar_grn"])
        dust = unit(source.payload["dust_load"])
        turn = unit(source.payload["left_mechanosensory"]) - unit(
            source.payload["right_mechanosensory"]
        )
        rates: JsonObject = {
            "forward": 8.0 + 40.0 * drive,
            "turn": 2.0 + 10.0 * turn,
            "feed": 3.0 + 25.0 * drive,
            "groom": 1.0 + 30.0 * dust,
            "stop": 1.0 + 5.0 * (1.0 - drive),
        }
        spikes: JsonObject = {
            name: int(unit_rate(rate) * self._tick_ms / 1000.0)
            for name, rate in rates.items()
        }
        payload: JsonObject = {
            "rates_hz": rates,
            "spike_deltas": spikes,
            "tick_index": source.frame_index + 1,
            "wall_time_sec": 0.0,
        }
        return BrainFrame(
            SCHEMA_VERSION,
            self._run_id,
            source.frame_index,
            source.simulation_time_s,
            time.monotonic(),
            payload,
            payload_checksum(payload),
        )

    def shutdown(self, frame_index: int, simulation_time_s: float) -> None:
        return None


class SocketBrainPeer:
    def __init__(self, context: BodyRunContext, raw_sock: socket.socket) -> None:
        self._context = context
        self._transport = FramedJsonSocket(raw_sock, timeout_s=context.config.timeout_s)

    def handshake(self) -> None:
        try:
            frame = self._transport.recv_frame()
            self._expect_hello(frame)
            self._transport.send_frame(
                Hello(
                    SCHEMA_VERSION,
                    self._context.config.output_dir.name,
                    0,
                    0.0,
                    time.monotonic(),
                    "body",
                )
            )
        except BodyServerRuntimeError:
            self._transport.close()
            raise
        except TransportError as exc:
            self._transport.close()
            raise BodyServerRuntimeError("brain_handshake_failed", str(exc)) from exc

    def next_frame(self, source: SensoryFrame) -> BrainReply:
        try:
            self._transport.send_frame(source)
            return self._expect_reply(self._transport.recv_frame())
        except TransportError as exc:
            raise BodyServerRuntimeError("brain_transport_error", str(exc)) from exc

    def shutdown(self, frame_index: int, simulation_time_s: float) -> None:
        if self._transport.closed:
            return
        try:
            self._transport.send_frame(
                Shutdown(
                    SCHEMA_VERSION,
                    self._context.config.output_dir.name,
                    frame_index,
                    simulation_time_s,
                    time.monotonic(),
                    "body_complete",
                )
            )
        except OSError:
            return
        finally:
            self._transport.close()

    def _expect_hello(self, frame: BridgeFrame) -> None:
        match frame:
            case Hello(run_id=run_id) if run_id == self._context.config.output_dir.name:
                return
            case Hello():
                raise BodyServerRuntimeError(
                    "brain_handshake_failed", "brain hello run_id did not match body run"
                )
            case BrainFrame() | ControlFrame() | SensoryFrame() | Heartbeat() | ErrorFrame() | Shutdown():
                raise BodyServerRuntimeError("brain_handshake_failed", "expected brain hello")
            case unreachable:
                assert_never(unreachable)

    def _expect_reply(self, frame: BridgeFrame) -> BrainReply:
        match frame:
            case BrainFrame() | ControlFrame():
                return frame
            case ErrorFrame(code=code, message=message):
                raise BodyServerRuntimeError(code, message)
            case Hello() | SensoryFrame() | Heartbeat() | Shutdown():
                raise BodyServerRuntimeError(
                    "unexpected_brain_frame", "expected brain or control frame"
                )
            case unreachable:
                assert_never(unreachable)


def connect_brain_peer(context: BodyRunContext) -> SocketBrainPeer:
    try:
        raw_sock = socket.create_connection(
            (context.config.host, context.config.brain_port),
            timeout=context.config.timeout_s,
        )
    except OSError as exc:
        message = (
            f"could not connect to brain at {context.config.host}:"
            f"{context.config.brain_port}: {exc}"
        )
        raise BodyServerRuntimeError("brain_unreachable", message) from exc
    peer = SocketBrainPeer(context, raw_sock)
    peer.handshake()
    return peer
