#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
# ─── How to run ───
# python3 scripts/replay_run.py --input outputs/smoke/bridge --verify
# python3 scripts/replay_run.py --input outputs/smoke/bridge --verify-behavior configs/eon_demo.yaml

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from digital_fruit_fly.bridge.replay import (  # noqa: E402
    ReplayVerificationError,
    summarize_replay,
    verify_replay,
    write_replay_failure,
    write_replay_success,
)
from digital_fruit_fly.behavior.scenario import (  # noqa: E402
    BehaviorVerificationError,
    BehaviorVerifyRequest,
    verify_behavior,
    write_behavior_failure,
)


def main() -> int:
    args = _parse_args()
    if args.verify_behavior is not None:
        request = BehaviorVerifyRequest(args.input, args.verify_behavior)
        try:
            result = verify_behavior(request)
        except BehaviorVerificationError as exc:
            write_behavior_failure(request, exc.failure)
            print(json.dumps({"status": "failed", "error": str(exc), "error_code": exc.failure.code}, sort_keys=True), file=sys.stderr)
            return 1
        print(json.dumps(result.evidence(), sort_keys=True))
        return 0
    if args.verify:
        try:
            result = verify_replay(args.input)
        except ReplayVerificationError as exc:
            write_replay_failure(args.input, exc.failure)
            print(json.dumps({"status": "failed", "error": str(exc), "error_code": exc.failure.code}, sort_keys=True), file=sys.stderr)
            return 1
        write_replay_success(args.input, result)
        print(json.dumps(result.evidence(), sort_keys=True))
        return 0
    try:
        payload = summarize_replay(args.input)
    except ReplayVerificationError as exc:
        write_replay_failure(args.input, exc.failure)
        print(json.dumps({"status": "failed", "error": str(exc), "error_code": exc.failure.code}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(payload, sort_keys=True))
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay and verify bridge smoke JSONL artifacts.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--verify-behavior", type=Path, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
