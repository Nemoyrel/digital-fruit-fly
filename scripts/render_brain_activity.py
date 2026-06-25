#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
# ─── How to run ───
# python3 scripts/render_brain_activity.py --input outputs/smoke/brain_server --output outputs/smoke/brain_server/video/brain_activity.mp4

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from digital_fruit_fly.observability.brain_video import (  # noqa: E402
    BrainActivityInputError,
    RenderRequest,
    render_brain_activity,
)


def main() -> int:
    args = _parse_args()
    try:
        result = render_brain_activity(RenderRequest(input_path=args.input, output_path=args.output))
    except BrainActivityInputError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "artifact_path": str(result.artifact_path),
                "fallback_reason": result.fallback_reason,
                "frame_count": result.frame_count,
                "metadata_path": str(result.metadata_path),
                "mode": result.mode,
                "readouts": list(result.readouts),
                "row_count": result.row_count,
                "summary_csv_path": str(result.summary_csv_path),
            },
            sort_keys=True,
        )
    )
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render brain activity from Todo 13 rates.csv.")
    parser.add_argument("--input", type=Path, required=True, help="Run directory or rates.csv path.")
    parser.add_argument("--output", type=Path, required=True, help="Requested MP4 output path.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
