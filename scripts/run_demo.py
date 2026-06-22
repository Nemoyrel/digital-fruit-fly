#!/usr/bin/env python3
"""在 flygym_env 中运行数字果蝇具身演示（thin CLI）。"""

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
    parser = argparse.ArgumentParser(description="运行数字果蝇具身演示。")
    parser.add_argument("--duration-s", type=float, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--timeout-s", type=float, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--no-video", action="store_true")
    parser.add_argument("--no-plot", action="store_true")
    parser.add_argument("--start-worker", action="store_true",
                        help="用 config 里的 ipc.brain_env_python 自行拉起脑 worker 子进程。")
    return parser.parse_args()


def main() -> None:
    from digital_fruit_fly.demo import run_demo

    args = parse_args()
    result = run_demo(
        duration_s=args.duration_s,
        seed=args.seed,
        output_dir=args.output_dir,
        no_video=args.no_video,
        no_plot=args.no_plot,
        host=args.host,
        port=args.port,
        timeout_s=args.timeout_s,
        start_worker=True if args.start_worker else None,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
