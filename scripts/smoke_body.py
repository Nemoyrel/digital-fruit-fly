#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
# ─── How to run ───
# /opt/miniconda3/envs/flygym_env/bin/python scripts/smoke_body.py --config configs/body_smoke.yaml --output outputs/smoke/body --headless --steps 20 --timeout-sec 60

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from digital_fruit_fly.body.camera import (  # noqa: E402
    CameraRecordingRequest,
    RecordingResult,
    deterministic_probe_frames,
    resolve_viewer_status,
    write_camera_recording,
)
from digital_fruit_fly.body.flygym_probe import (  # noqa: E402
    BodyProbeRequest,
    run_body_probe,
)
from digital_fruit_fly.runtime.config import ConfigError, RuntimeConfig, load_config  # noqa: E402
from digital_fruit_fly.runtime.timeouts import JsonObject, write_json_evidence  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        payload = _config_failure_payload(str(exc), args)
        _write_failure(args.output, args.evidence, payload)
        print(json.dumps(payload, sort_keys=True), file=sys.stderr)
        return 2

    outcome = run_body_probe(
        BodyProbeRequest(
            config_path=args.config,
            output_dir=args.output,
            steps=args.steps,
            timeout_sec=args.timeout_sec,
            headless=args.headless,
            renderer=args.renderer,
            evidence_path=args.evidence,
            api_report=args.api_report,
            fixture_sleep_sec=args.fixture_sleep_sec,
        )
    )
    outcome.payload["body_python"] = config.body.python
    outcome.payload["camera_enabled"] = config.camera.enabled
    if args.record and outcome.exit_code == 0:
        recording = _record_camera_smoke(args, config, outcome.payload)
        outcome.payload["camera_recording"] = recording.to_json()
    if outcome.exit_code == 0:
        write_json_evidence(args.output / "body_env.json", outcome.payload)
        write_json_evidence(args.evidence, outcome.payload)
        print(json.dumps(outcome.payload, sort_keys=True))
    else:
        write_json_evidence(args.output / "body_env_error.json", outcome.payload)
        write_json_evidence(args.evidence, outcome.payload)
        print(json.dumps(outcome.payload, sort_keys=True), file=sys.stderr)
    return outcome.exit_code


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate FlyGym/MuJoCo body runtime.")
    parser.add_argument("--config", type=Path, default=Path("configs/body_smoke.yaml"))
    parser.add_argument("--output", type=Path, default=Path("outputs/smoke/body"))
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--timeout-sec", type=float, default=60.0)
    parser.add_argument("--renderer", default="auto")
    parser.add_argument("--api-report", action="store_true")
    parser.add_argument("--evidence", type=Path, default=Path(".omo/evidence/smoke_body_latest.json"))
    parser.add_argument("--fixture-sleep-sec", type=float, default=0.0)
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--record-codec", default="libx264")
    parser.add_argument("--viewer", action="store_true")
    return parser.parse_args(argv)


def _record_camera_smoke(
    args: argparse.Namespace, config: RuntimeConfig, payload: JsonObject
) -> RecordingResult:
    camera_mode = "tracking" if config.camera.follow_fly else "fixed"
    request = CameraRecordingRequest(
        output_dir=args.output / "camera",
        stem="body_smoke",
        fps=config.camera.fps,
        codec=args.record_codec,
        mode=camera_mode,
        source="deterministic_probe_frames",
        viewer_status=resolve_viewer_status(args.headless, args.viewer),
        fallback_reason=_recording_fallback_reason(payload),
    )
    frames = deterministic_probe_frames(
        config.camera.width_px, config.camera.height_px, args.steps
    )
    return write_camera_recording(request, frames)


def _recording_fallback_reason(payload: JsonObject) -> str | None:
    renderer = payload.get("renderer")
    if isinstance(renderer, dict) and renderer.get("status") != "ok":
        return "renderer skipped or unavailable; wrote deterministic probe frames instead of FlyGym rendered video"
    return None


def _config_failure_payload(message: str, args: argparse.Namespace) -> JsonObject:
    return {
        "script": "smoke_body",
        "status": "failed",
        "exit_code": 2,
        "error": message,
        "probe_stage": "config",
        "config": str(args.config),
    }


def _write_failure(output_dir: Path, evidence_path: Path, payload: JsonObject) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json_evidence(output_dir / "body_env_error.json", payload)
    write_json_evidence(evidence_path, payload)


if __name__ == "__main__":
    raise SystemExit(main())
