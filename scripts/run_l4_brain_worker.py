#!/usr/bin/env python3
"""Run the L4 brain worker in brain_env."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the L4 IPC brain worker.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--backend",
        choices=["auto", "brian2_proxy", "shiu_full"],
        default="auto",
    )
    parser.add_argument("--once-smoke", action="store_true")
    parser.add_argument("--max-startup-s", type=float, default=10.0)
    return parser.parse_args()


def main() -> None:
    from digital_fruit_fly.brain_worker import (
        BrainWorkerConfig,
        L4BrainWorkerServer,
        select_backend,
        smoke_response,
    )

    args = parse_args()
    config = BrainWorkerConfig(max_startup_s=args.max_startup_s)
    if args.once_smoke:
        print(json.dumps(smoke_response(args.backend, config), indent=2))
        return

    selection = select_backend(args.backend, config)
    print(
        json.dumps(
            {
                "event": "brain_worker_started",
                "host": args.host,
                "port": args.port,
                "backend": selection.backend_name,
                "metadata": selection.metadata,
            },
            indent=2,
        ),
        flush=True,
    )
    server = L4BrainWorkerServer(
        host=args.host,
        port=args.port,
        backend=selection.backend,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
