#!/usr/bin/env python3
"""CLI wrapper for the L2 rule-based embodied loop demo."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the L2 embodied-loop demo.")
    parser.add_argument("--duration", type=float, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--log-every-steps", type=int, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--no-video", action="store_true")
    parser.add_argument("--no-plot", action="store_true")
    return parser.parse_args()


def main() -> None:
    from digital_fruit_fly import run_l2_embodied_demo

    args = parse_args()
    outputs = run_l2_embodied_demo(
        duration_s=args.duration,
        seed=args.seed,
        log_every_steps=args.log_every_steps,
        output_dir=args.output_dir,
        no_video=args.no_video,
        no_plot=args.no_plot,
    )
    print(f"telemetry: {outputs['telemetry_csv']}")
    if outputs["video_mp4"] is not None:
        print(f"video: {outputs['video_mp4']}")
    if outputs["telemetry_plot_png"] is not None:
        print(f"plot: {outputs['telemetry_plot_png']}")
    print(f"metadata: {outputs['metadata_json']}")
    print(f"events: {outputs['events']}")


if __name__ == "__main__":
    main()
