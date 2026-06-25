#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
# ─── How to run ───
# python3 scripts/smoke_bridge.py --config configs/bridge_smoke.yaml --ticks 3 --output outputs/smoke/bridge_unit

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from pathlib import Path
from typing import List, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from digital_fruit_fly.bridge.messages import (  # noqa: E402
    BrainFrame,
    ErrorFrame,
    Hello,
    SCHEMA_VERSION,
    SensoryFrame,
    Shutdown,
    decode_message,
    encode_message,
    payload_checksum,
)
from digital_fruit_fly.bridge.fixture_run import (  # noqa: E402
    BridgeSmokeError,
    BridgeSmokeRequest,
    write_fixture_smoke,
)
from digital_fruit_fly.bridge.transport import FramedJsonSocket  # noqa: E402
from digital_fruit_fly.runtime.config import ConfigError, RuntimeConfig, load_config  # noqa: E402
from digital_fruit_fly.runtime.timeouts import (  # noqa: E402
    TIMEOUT_EXIT_CODE,
    JsonObject,
    run_subprocess,
    write_json_evidence,
)


def main() -> int:
    args, unknown_args = _parse_args()
    evidence_path = args.evidence
    output_dir = args.output
    if args.ticks <= 0:
        return _fail("ticks must be positive", 2, evidence_path, output_dir, unknown_args)
    if args.timeout_sec <= 0.0:
        return _fail("timeout-sec must be positive", 2, evidence_path, output_dir, unknown_args)
    if args.fixture_sleep_sec > 0.0:
        return _run_sleep_fixture(args.fixture_sleep_sec, args.timeout_sec, evidence_path, output_dir)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        return _fail(str(exc), 2, evidence_path, output_dir, unknown_args)
    if args.brain_client:
        return _run_brain_client(args, config, evidence_path, output_dir, unknown_args)
    started = time.monotonic()
    try:
        result = write_fixture_smoke(BridgeSmokeRequest(args.config, config, args.ticks, output_dir))
    except BridgeSmokeError as exc:
        return _fail(str(exc), 1, evidence_path, output_dir, unknown_args)
    payload = result.evidence()
    payload["duration_sec"] = time.monotonic() - started
    payload["unknown_args"] = list(unknown_args)
    write_json_evidence(evidence_path, payload)
    print(json.dumps(payload, sort_keys=True))
    return 0


def _parse_args() -> Tuple[argparse.Namespace, List[str]]:
    parser = argparse.ArgumentParser(description="Run a fixture-only bridge smoke probe.")
    parser.add_argument("--config", type=Path, default=Path("configs/bridge_smoke.yaml"))
    parser.add_argument("--ticks", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("outputs/smoke/bridge"))
    parser.add_argument("--timeout-sec", type=float, default=10.0)
    parser.add_argument("--evidence", type=Path, default=Path(".omo/evidence/smoke_bridge_latest.json"))
    parser.add_argument("--fixture-sleep-sec", type=float, default=0.0)
    parser.add_argument("--brain-client", action="store_true")
    parser.add_argument("--host", type=str, default=None)
    parser.add_argument("--port", type=int, default=None)
    return parser.parse_known_args()


def _run_sleep_fixture(
    sleep_sec: float,
    timeout_sec: float,
    evidence_path: Path,
    output_dir: Path,
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    result = run_subprocess(
        (
            sys.executable,
            "-c",
            f"import time; print('fixture-start', flush=True); time.sleep({sleep_sec!r})",
        ),
        timeout_sec=timeout_sec,
        evidence_path=output_dir / "fixture_timeout.json",
    )
    payload = result.to_json()
    payload["script"] = "smoke_bridge"
    payload["fixture"] = "sleep"
    payload["artifacts"] = [str(output_dir / "fixture_timeout.json")]
    write_json_evidence(evidence_path, payload)
    print(json.dumps(payload, sort_keys=True))
    if result.timed_out:
        return TIMEOUT_EXIT_CODE
    return result.exit_code


def _run_brain_client(
    args: argparse.Namespace,
    config: RuntimeConfig,
    evidence_path: Path,
    output_dir: Path,
    unknown_args: List[str],
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    frames_path = output_dir / "brain_frames.jsonl"
    host = args.host or config.process.host
    port = args.port if args.port is not None else config.process.brain_port
    started = time.monotonic()
    with socket.create_connection((host, port), timeout=args.timeout_sec) as raw_sock:
        client = FramedJsonSocket(raw_sock, timeout_s=args.timeout_sec)
        hello = client.recv_frame()
        if not isinstance(hello, Hello):
            return _fail("brain server did not send hello", 1, evidence_path, output_dir, unknown_args)
        client.send_frame(Hello(SCHEMA_VERSION, hello.run_id, 0, 0.0, time.monotonic(), "body"))
        with frames_path.open("w", encoding="utf-8") as frames_file:
            for frame_index in range(args.ticks):
                payload = {
                    "sugar_grn": min(1.0, 0.2 + 0.1 * frame_index),
                    "dust_load": 0.05 * frame_index,
                    "left_mechanosensory": 0.1,
                    "right_mechanosensory": 0.0,
                }
                client.send_frame(
                    SensoryFrame(
                        SCHEMA_VERSION,
                        hello.run_id,
                        frame_index,
                        frame_index * config.tick_ms / 1000.0,
                        time.monotonic(),
                        payload,
                        payload_checksum(payload),
                    )
                )
                response = client.recv_frame()
                frames_file.write(encode_message(response).decode("utf-8") + "\n")
                if isinstance(response, ErrorFrame):
                    return _fail(response.message, 1, evidence_path, output_dir, unknown_args)
                if not isinstance(response, BrainFrame):
                    return _fail("brain server sent unexpected frame", 1, evidence_path, output_dir, unknown_args)
        client.send_frame(Shutdown(SCHEMA_VERSION, hello.run_id, args.ticks, args.ticks * config.tick_ms / 1000.0, time.monotonic(), "smoke_bridge_done"))
    payload = {
        "script": "smoke_bridge",
        "status": "ok",
        "mode": "brain_client",
        "ticks": args.ticks,
        "duration_sec": time.monotonic() - started,
        "artifacts": [str(frames_path)],
        "unknown_args": list(unknown_args),
    }
    write_json_evidence(evidence_path, payload)
    print(json.dumps(payload, sort_keys=True))
    return 0


def _fail(
    message: str,
    exit_code: int,
    evidence_path: Path,
    output_dir: Path,
    unknown_args: List[str],
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload: JsonObject = {
        "script": "smoke_bridge",
        "status": "failed",
        "exit_code": exit_code,
        "error": message,
        "unknown_args": list(unknown_args),
    }
    write_json_evidence(output_dir / "error.json", payload)
    write_json_evidence(evidence_path, payload)
    print(json.dumps(payload, sort_keys=True), file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
