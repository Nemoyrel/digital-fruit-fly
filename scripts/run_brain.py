#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
# ─── How to run ───
# python3 scripts/run_brain.py --config configs/bridge_smoke.yaml --mode fixture --max-ticks 5 --output outputs/smoke/brain_server

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from digital_fruit_fly.brain.server import BrainServerConfig, serve_brain  # noqa: E402
from digital_fruit_fly.brain.server import BoundAddress  # noqa: E402
from digital_fruit_fly.runtime.config import ConfigError, RuntimeConfig, load_config  # noqa: E402


def main() -> int:
    args = _parse_args()
    try:
        runtime_config = load_config(args.config)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    max_ticks = args.max_ticks if args.max_ticks is not None else _ticks_from_config(runtime_config)
    result = serve_brain(_server_config(args, runtime_config, max_ticks), _print_ready)
    print(
        json.dumps(
            {
                "status": result.exit_reason,
                "ticks": result.ticks,
                "run_dir": str(result.run_dir),
                "rates_path": str(result.rates_path),
                "events_path": str(result.events_path),
                "server_log_path": str(result.server_log_path),
            },
            sort_keys=True,
        )
    )
    return 0 if result.exit_reason in ("shutdown", "client_closed") else 1


def _print_ready(address: BoundAddress) -> None:
    print(
        json.dumps(
            {
                "status": "ready",
                "role": "brain",
                "host": address.host,
                "port": address.port,
            },
            sort_keys=True,
        ),
        flush=True,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the digital fruit fly brain server.")
    parser.add_argument("--config", type=Path, default=Path("configs/eon_demo.yaml"))
    parser.add_argument("--mode", choices=("fixture", "brian2"), default="brian2")
    parser.add_argument("--max-ticks", type=int, default=None)
    parser.add_argument("--output", type=Path, default=Path("outputs/smoke/brain_server"))
    parser.add_argument("--host", type=str, default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--timeout-sec", type=float, default=60.0)
    return parser.parse_args()


def _server_config(args: argparse.Namespace, runtime_config: RuntimeConfig, max_ticks: int) -> BrainServerConfig:
    return BrainServerConfig(
        host=args.host or runtime_config.process.host,
        port=args.port if args.port is not None else runtime_config.process.brain_port,
        run_id=args.output.name,
        mode=args.mode,
        max_ticks=max_ticks,
        output_dir=args.output,
        tick_ms=runtime_config.tick_ms,
        timeout_s=args.timeout_sec,
        mapping_path=Path(runtime_config.brain.mapping_path),
        shiu_repo_path=Path(runtime_config.brain.shiu_repo_path),
        completeness_path=Path(runtime_config.brain.completeness_path),
        connectivity_path=Path(runtime_config.brain.connectivity_path),
    )


def _ticks_from_config(runtime_config: RuntimeConfig) -> int:
    return max(1, int(runtime_config.duration_sec * 1000.0 / runtime_config.tick_ms))


if __name__ == "__main__":
    raise SystemExit(main())
