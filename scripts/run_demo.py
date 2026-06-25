#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
# ─── How to run ───
# python3 scripts/run_demo.py --config configs/eon_demo.yaml --output outputs/runs/eon_demo_smoke --duration-sec 60 --seed 1

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from digital_fruit_fly.demo.runner import DemoRequest, ProcessMode, run_demo  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    request = DemoRequest(
        config_path=args.config,
        output_dir=args.output,
        evidence_path=args.evidence,
        duration_sec=args.duration_sec,
        seed=args.seed,
        process_mode=args.process_mode,
        timeout_sec=args.timeout_sec,
        video_frame_cap=args.video_frame_cap,
        brain_frame_cap=args.brain_frame_cap,
        video_width_px=args.video_width_px,
        video_height_px=args.video_height_px,
        record_codec=args.record_codec,
        failure_qa_delay_sec=args.failure_qa_delay_sec,
    )
    return run_demo(request)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the final digital fruit fly demo.")
    parser.add_argument("--config", type=Path, default=Path("configs/eon_demo.yaml"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration-sec", type=float, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument(
        "--process-mode",
        choices=("separate_processes", "fixture_demo", "failure_qa_kill_brain"),
        default="separate_processes",
    )
    parser.add_argument("--timeout-sec", type=float, default=60.0)
    parser.add_argument("--video-frame-cap", type=int, default=6)
    parser.add_argument("--brain-frame-cap", type=int, default=60)
    parser.add_argument("--video-width-px", type=int, default=None)
    parser.add_argument("--video-height-px", type=int, default=None)
    parser.add_argument("--record-codec", default="libx264")
    parser.add_argument("--failure-qa-delay-sec", type=float, default=0.5)
    parser.add_argument("--evidence", type=Path, default=Path(".omo/evidence/task-23-eon-embodied-fly.json"))
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
