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
        choices=["auto", "shiu_full"],
        default="shiu_full",
    )
    parser.add_argument("--once-smoke", action="store_true")
    parser.add_argument("--max-startup-s", type=float, default=0.0)
    parser.add_argument("--brain-window-s", type=float, default=0.015)
    return parser.parse_args()


def main() -> None:
    from digital_fruit_fly.brain_worker import (
        BrainBackendUnavailable,
        BrainWorkerConfig,
        L4BrainWorkerServer,
        select_backend,
        smoke_response,
    )

    args = parse_args()
    config = BrainWorkerConfig(
        max_startup_s=args.max_startup_s,
        brain_window_s=args.brain_window_s,
    )
    if args.once_smoke:
        try:
            print(json.dumps(smoke_response(args.backend, config), indent=2))
        except BrainBackendUnavailable as exc:
            print(
                json.dumps(
                    {
                        "event": "brain_worker_failed",
                        "backend": args.backend,
                        "stage": exc.stage,
                        "reason": exc.reason,
                        "metadata": exc.metadata,
                    },
                    indent=2,
                ),
                file=sys.stderr,
            )
            raise SystemExit(2)
        return

    try:
        selection = select_backend(args.backend, config)
    except BrainBackendUnavailable as exc:
        print(
            json.dumps(
                {
                    "event": "brain_worker_failed",
                    "backend": args.backend,
                    "stage": exc.stage,
                    "reason": exc.reason,
                    "metadata": exc.metadata,
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        raise SystemExit(2)
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
