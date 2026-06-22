#!/usr/bin/env python3
"""在 brain_env 中启动 Shiu 全连接组脑 worker（thin CLI）。

仅做参数解析、把 src/ 加入 sys.path、调用包内函数。
"""

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
    parser = argparse.ArgumentParser(description="运行 Shiu 全连接组脑 worker。")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--backend", choices=["auto", "shiu_full"], default="shiu_full")
    parser.add_argument("--brain-window-s", type=float, default=0.05)
    parser.add_argument("--viz-neuron-count", type=int, default=4000)
    parser.add_argument("--max-startup-s", type=float, default=0.0)
    parser.add_argument("--once-smoke", action="store_true",
                        help="构建后端、对一条合成请求返回一次响应后退出（不开 socket）。")
    return parser.parse_args()


def _fail_json(backend: str, exc) -> None:
    print(
        json.dumps(
            {
                "event": "brain_worker_failed",
                "backend": backend,
                "stage": exc.stage,
                "reason": exc.reason,
                "metadata": exc.metadata,
            },
            indent=2,
        ),
        file=sys.stderr,
    )


def main() -> None:
    from digital_fruit_fly.brain_backend import BrainBackendUnavailable, BrainWorkerConfig
    from digital_fruit_fly.brain_server import (
        BrainWorkerServer,
        select_backend,
        smoke_response,
    )

    args = parse_args()
    config = BrainWorkerConfig(
        brain_window_s=args.brain_window_s,
        viz_neuron_count=args.viz_neuron_count,
        max_startup_s=args.max_startup_s,
    )

    if args.once_smoke:
        try:
            print(json.dumps(smoke_response(args.backend, config), indent=2))
        except BrainBackendUnavailable as exc:
            _fail_json(args.backend, exc)
            raise SystemExit(2)
        return

    try:
        backend = select_backend(args.backend, config)
    except BrainBackendUnavailable as exc:
        _fail_json(args.backend, exc)
        raise SystemExit(2)

    print(
        json.dumps(
            {
                "event": "brain_worker_started",
                "host": args.host,
                "port": args.port,
                "backend": backend.backend_name,
                "metadata": backend.metadata,
            },
            indent=2,
        ),
        flush=True,
    )
    server = BrainWorkerServer(host=args.host, port=args.port, backend=backend)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
