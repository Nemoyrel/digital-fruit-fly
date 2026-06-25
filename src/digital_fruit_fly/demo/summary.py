from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from digital_fruit_fly.runtime.timeouts import JsonObject, write_json_evidence


class RunSummaryError(Exception):
    """Raised when a demo summary cannot be validated."""


def validate_and_rewrite_summary(input_dir: Path, verify: bool) -> JsonObject:
    summary_path = input_dir / "summary.json"
    payload = _load_json(summary_path)
    if verify:
        _verify_summary(input_dir, payload)
    payload["summary_validated_at_utc"] = _utc_now()
    write_json_evidence(summary_path, payload)
    return payload


def _verify_summary(input_dir: Path, payload: JsonObject) -> None:
    status = payload.get("status")
    if status != "ok":
        raise RunSummaryError(f"summary status is not ok: {status}")
    mode = payload.get("mode")
    match mode:
        case "separate_processes":
            _verify_live_replay_marker(payload)
        case "fixture_demo":
            raise RunSummaryError("fixture_demo summary is not valid final acceptance evidence")
        case _:
            raise RunSummaryError(f"unsupported demo mode: {mode}")
    for field in ("body_recording", "brain_activity"):
        artifact = _artifact_path(payload, field)
        if not artifact.is_file() or artifact.stat().st_size == 0:
            raise RunSummaryError(f"{field} artifact is missing or empty: {artifact}")


def _verify_live_replay_marker(payload: JsonObject) -> None:
    replay_path = payload.get("replay_evidence_path")
    if not isinstance(replay_path, str) or replay_path == "":
        raise RunSummaryError("replay_evidence_path must be a non-empty string")
    replay = _load_json(Path(replay_path))
    if replay.get("status") != "ok":
        raise RunSummaryError(f"live replay/log evidence is not ok: {replay_path}")


def _artifact_path(payload: JsonObject, field: str) -> Path:
    value = payload.get(field)
    if not isinstance(value, dict):
        raise RunSummaryError(f"{field} must be an object")
    path = value.get("artifact_path")
    if isinstance(path, str) and path != "":
        return Path(path)
    raise RunSummaryError(f"{field}.artifact_path must be a non-empty string")


def _load_json(path: Path) -> JsonObject:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RunSummaryError(f"unable to read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RunSummaryError(f"malformed JSON in {path}: {exc}") from exc
    if isinstance(raw, dict):
        return raw
    raise RunSummaryError(f"{path} must contain a JSON object")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
