#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
# ─── How to run ───
# /opt/miniconda3/envs/flygym_env/bin/python scripts/run_body.py --config configs/bridge_smoke.yaml --brain-mode fixture --max-ticks 20 --output outputs/smoke/body_server

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from digital_fruit_fly.body.server import (  # noqa: E402
    BodyServerConfig,
    BodyServerConfigError,
    serve_body,
)
from digital_fruit_fly.runtime.config import ConfigError, load_config  # noqa: E402
from digital_fruit_fly.runtime.timeouts import JsonObject, write_json_evidence  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        config = _server_config(args)
        result = serve_body(config)
    except (BodyServerConfigError, ConfigError) as exc:
        payload = _error_payload(args.output, "configuration_error", str(exc), 2)
        _write_cli_error(args.output, payload)
        print(json.dumps(payload, sort_keys=True), file=sys.stderr)
        return 2
    payload: JsonObject = {
        "status": result.status,
        "exit_code": result.exit_code,
        "ticks": result.ticks,
        "run_dir": str(result.run_dir),
        "manifest_path": str(result.manifest_path),
        "trajectory_path": str(result.trajectory_path),
        "control_path": str(result.control_path),
        "arena_path": str(result.arena_path),
        "recording_metadata_path": str(result.recording_metadata_path),
    }
    print(json.dumps(payload, sort_keys=True))
    return result.exit_code


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the digital fruit fly body server.")
    parser.add_argument("--config", type=Path, default=Path("configs/eon_demo.yaml"))
    parser.add_argument("--brain-mode", default="connect")
    parser.add_argument("--max-ticks", type=int, default=None)
    parser.add_argument("--output", type=Path, default=Path("outputs/smoke/body_server"))
    parser.add_argument("--host", type=str, default=None)
    parser.add_argument("--brain-port", type=int, default=None)
    parser.add_argument("--timeout-sec", type=float, default=10.0)
    parser.add_argument("--record-codec", default="libx264")
    parser.add_argument("--viewer", action="store_true")
    return parser.parse_args(argv)


def _server_config(args: argparse.Namespace) -> BodyServerConfig:
    runtime = load_config(args.config)
    max_ticks = args.max_ticks if args.max_ticks is not None else max(1, int(runtime.duration_sec * 1000.0 / runtime.tick_ms))
    return BodyServerConfig(
        config_path=args.config,
        output_dir=args.output,
        brain_mode=args.brain_mode,
        max_ticks=max_ticks,
        timeout_s=args.timeout_sec,
        host=args.host or runtime.process.host,
        brain_port=args.brain_port if args.brain_port is not None else runtime.process.brain_port,
        record_codec=args.record_codec,
        viewer_requested=args.viewer,
    )


def _error_payload(output_dir: Path, code: str, message: str, exit_code: int) -> JsonObject:
    return {
        "status": "error",
        "exit_code": exit_code,
        "run_dir": str(output_dir),
        "manifest_path": str(output_dir / "manifest.json"),
        "error": {"code": code, "message": message},
    }


def _write_cli_error(output_dir: Path, payload: JsonObject) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json_evidence(output_dir / "manifest.json", payload)


if __name__ == "__main__":
    raise SystemExit(main())
