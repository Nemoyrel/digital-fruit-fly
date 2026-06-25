from __future__ import annotations

import csv
import queue
import socket
import struct
import tempfile
import threading
import time
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol
from unittest.mock import patch

from digital_fruit_fly.brain.server import (
    BoundAddress,
    BrainServerConfig,
    BrainServerResult,
    BrainTick,
    serve_brain,
)
from digital_fruit_fly.bridge.messages import (
    SCHEMA_VERSION,
    BrainFrame,
    ErrorFrame,
    Hello,
    SensoryFrame,
    Shutdown,
    payload_checksum,
)
from digital_fruit_fly.bridge.transport import FramedJsonSocket
from digital_fruit_fly.runtime.logging import read_jsonl


@dataclass(frozen=True)
class RunningServer:
    address: BoundAddress
    result_queue: queue.Queue[BrainServerResult | BaseException]
    thread: threading.Thread


class BrainRuntimeStub(Protocol):
    sensory_channel_names: tuple[str, ...]

    def tick(self, channel_values: Mapping[str, float]) -> BrainTick:
        ...


class TestBrainServer(unittest.TestCase):
    def test_fixture_server_returns_brain_frame_and_writes_rates_when_tick_received(self) -> None:
        # Given: a fixture brain server listening on a loopback TCP socket.
        with tempfile.TemporaryDirectory() as temp_root:
            output_dir = Path(temp_root) / "outputs" / "brain_server"
            running = self._start_fixture_server(output_dir, max_ticks=3)

            # When: a body client completes the hello exchange and sends one sensory frame.
            with socket.create_connection(running.address.as_tuple(), timeout=1.0) as raw_sock:
                client = FramedJsonSocket(raw_sock, timeout_s=1.0)
                hello = client.recv_frame()
                self.assertIsInstance(hello, Hello)
                client.send_frame(Hello(SCHEMA_VERSION, hello.run_id, 0, 0.0, time.monotonic(), "body"))
                sensory_payload = {"sugar_grn": 0.8, "dust_load": 0.1}
                client.send_frame(
                    SensoryFrame(
                        SCHEMA_VERSION,
                        hello.run_id,
                        0,
                        0.0,
                        time.monotonic(),
                        sensory_payload,
                        payload_checksum(sensory_payload),
                    )
                )
                response = client.recv_frame()
                client.send_frame(Shutdown(SCHEMA_VERSION, hello.run_id, 1, 0.015, time.monotonic(), "done"))

            result = self._wait_for_result(running)

            # Then: the response is a brain frame and the run writes rate rows under brain/.
            self.assertIsInstance(response, BrainFrame)
            self.assertEqual(response.frame_index, 0)
            self.assertIn("rates_hz", response.payload)
            self.assertEqual(result.exit_reason, "shutdown")
            self.assertTrue(result.rates_path.is_file())
            with result.rates_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertGreaterEqual(len(rows), 1)
            self.assertEqual(rows[0]["frame_index"], "0")

    def test_channel_values_drop_body_context_before_brian2_tick(self) -> None:
        # Given: a Brian2-shaped runtime that only accepts configured sensory channels.
        with tempfile.TemporaryDirectory() as temp_root:
            output_dir = Path(temp_root) / "outputs" / "brain_server"
            received_channel_values: list[dict[str, float]] = []

            class RecordingRuntime:
                sensory_channel_names = (
                    "sugar_grn",
                    "dust_load",
                    "left_mechanosensory",
                    "right_mechanosensory",
                )

                def tick(self, channel_values: Mapping[str, float]) -> BrainTick:
                    received_channel_values.append(dict(channel_values))
                    return BrainTick(1, {"fixture_output": 9.0}, {"fixture_output": 1}, 0.0)

            running = self._start_fixture_server(
                output_dir,
                max_ticks=3,
                mode="brian2",
                runtime=RecordingRuntime(),
            )

            # When: the body sends configured channels plus body-only context fields.
            with socket.create_connection(running.address.as_tuple(), timeout=1.0) as raw_sock:
                client = FramedJsonSocket(raw_sock, timeout_s=1.0)
                hello = client.recv_frame()
                self.assertIsInstance(hello, Hello)
                client.send_frame(Hello(SCHEMA_VERSION, hello.run_id, 0, 0.0, time.monotonic(), "body"))
                sensory_payload = {
                    "sugar_grn": 1.0,
                    "dust_load": 0.2,
                    "left_mechanosensory": 0.3,
                    "right_mechanosensory": 0.1,
                    "food_bearing_rad": 0.4,
                    "food_elevation_rad": 0.0,
                    "food_distance_mm": 4.2,
                }
                client.send_frame(
                    SensoryFrame(
                        SCHEMA_VERSION,
                        hello.run_id,
                        0,
                        0.0,
                        time.monotonic(),
                        sensory_payload,
                        payload_checksum(sensory_payload),
                    )
                )
                response = client.recv_frame()
                client.send_frame(Shutdown(SCHEMA_VERSION, hello.run_id, 1, 0.015, time.monotonic(), "done"))

            result = self._wait_for_result(running)

            # Then: only configured Brian2 sensory channels reach the runtime tick boundary.
            self.assertIsInstance(response, BrainFrame)
            self.assertEqual(
                received_channel_values,
                [
                    {
                        "sugar_grn": 1.0,
                        "dust_load": 0.2,
                        "left_mechanosensory": 0.3,
                        "right_mechanosensory": 0.1,
                    }
                ],
            )
            self.assertEqual(result.exit_reason, "shutdown")

    def test_fixture_server_logs_protocol_error_when_frame_index_is_skipped(self) -> None:
        # Given: a fixture brain server waiting for frame index 0.
        with tempfile.TemporaryDirectory() as temp_root:
            output_dir = Path(temp_root) / "outputs" / "brain_server"
            running = self._start_fixture_server(output_dir, max_ticks=3)

            # When: the body skips directly to frame index 1.
            with socket.create_connection(running.address.as_tuple(), timeout=1.0) as raw_sock:
                client = FramedJsonSocket(raw_sock, timeout_s=1.0)
                hello = client.recv_frame()
                self.assertIsInstance(hello, Hello)
                client.send_frame(Hello(SCHEMA_VERSION, hello.run_id, 0, 0.0, time.monotonic(), "body"))
                payload = {"sugar_grn": 0.5}
                client.send_frame(
                    SensoryFrame(
                        SCHEMA_VERSION,
                        hello.run_id,
                        1,
                        0.015,
                        time.monotonic(),
                        payload,
                        payload_checksum(payload),
                    )
                )
                response = client.recv_frame()

            result = self._wait_for_result(running)

            # Then: the server reports and persists the protocol error.
            self.assertIsInstance(response, ErrorFrame)
            self.assertEqual(response.code, "frame_index_skipped")
            records = read_jsonl(result.events_path)
            self.assertIn("protocol_error", {record["kind"] for record in records})

    def test_fixture_server_logs_protocol_error_when_handshake_message_is_malformed(self) -> None:
        # Given: a fixture brain server waiting for a body hello.
        with tempfile.TemporaryDirectory() as temp_root:
            output_dir = Path(temp_root) / "outputs" / "brain_server"
            running = self._start_fixture_server(output_dir, max_ticks=3)

            # When: the body sends malformed framed JSON instead of a hello.
            with socket.create_connection(running.address.as_tuple(), timeout=1.0) as raw_sock:
                client = FramedJsonSocket(raw_sock, timeout_s=1.0)
                self.assertIsInstance(client.recv_frame(), Hello)
                malformed = b'{"type":'
                raw_sock.sendall(struct.pack(">I", len(malformed)) + malformed)

            result = self._wait_for_result(running)

            # Then: the server records a protocol error and exits the handshake.
            self.assertEqual(result.exit_reason, "handshake_failed")
            records = read_jsonl(result.events_path)
            self.assertIn("protocol_error", {record["kind"] for record in records})

    def _start_fixture_server(
        self,
        output_dir: Path,
        max_ticks: int,
        mode: str = "fixture",
        runtime: BrainRuntimeStub | None = None,
    ) -> RunningServer:
        config = BrainServerConfig(
            host="127.0.0.1",
            port=0,
            run_id="brain_server",
            mode=mode,
            max_ticks=max_ticks,
            output_dir=output_dir,
            tick_ms=15,
            timeout_s=1.0,
            mapping_path=Path("configs/brain_mapping.yaml"),
            shiu_repo_path=Path("external/drosophila_brain_model"),
            completeness_path=Path("external/drosophila_brain_model/Completeness_783.csv"),
            connectivity_path=Path("external/drosophila_brain_model/Connectivity_783.parquet"),
        )
        ready_queue: queue.Queue[BoundAddress] = queue.Queue()
        result_queue: queue.Queue[BrainServerResult | BaseException] = queue.Queue()

        def target() -> None:
            try:
                if runtime is None:
                    result_queue.put(serve_brain(config, ready_queue.put))
                    return
                with patch("digital_fruit_fly.brain.server._build_runtime", return_value=runtime):
                    result_queue.put(serve_brain(config, ready_queue.put))
            except BaseException as exc:
                result_queue.put(exc)

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        address = ready_queue.get(timeout=2.0)
        return RunningServer(address=address, result_queue=result_queue, thread=thread)

    def _wait_for_result(self, running: RunningServer) -> BrainServerResult:
        result = running.result_queue.get(timeout=2.0)
        running.thread.join(timeout=1.0)
        if isinstance(result, BaseException):
            raise result
        return result


if __name__ == "__main__":
    unittest.main()
