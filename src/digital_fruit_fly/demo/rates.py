from __future__ import annotations

import csv
import math
from pathlib import Path

from digital_fruit_fly.bridge.messages import BrainFrame, BridgeFrame, ErrorFrame, JsonObject, JsonValue, decode_message


class RatesSynthesisError(Exception):
    """Raised when bridge frames cannot be converted to brain rates."""


def synthesize_rates_csv(run_dir: Path, frame_cap: int) -> Path:
    frames_path = run_dir / "frames.jsonl"
    rates_path = run_dir / "brain" / "rates.csv"
    rates_path.parent.mkdir(parents=True, exist_ok=True)
    rows = tuple(_brain_rows(_load_frames(frames_path), frame_cap))
    if len(rows) == 0:
        raise RatesSynthesisError(f"no brain frames in {frames_path}")
    with rates_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("frame_index", "simulation_time_s", "readout", "rate_hz", "spike_delta"))
        writer.writerows(rows)
    return rates_path


def _load_frames(path: Path) -> tuple[BridgeFrame, ...]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RatesSynthesisError(f"unable to read bridge frames: {path}: {exc}") from exc
    return tuple(_decode_line(line) for line in lines)


def _decode_line(line: str) -> BridgeFrame:
    frame = decode_message(line.encode("utf-8"))
    match frame:
        case ErrorFrame(message=message):
            raise RatesSynthesisError(message)
        case _:
            return frame


def _brain_rows(frames: tuple[BridgeFrame, ...], frame_cap: int) -> tuple[tuple[int, float, str, float, int], ...]:
    rows: list[tuple[int, float, str, float, int]] = []
    brain_frames = 0
    for frame in frames:
        match frame:
            case BrainFrame(payload=payload):
                if brain_frames >= frame_cap:
                    break
                brain_frames += 1
                rates = _object_field(payload, "rates_hz")
                for readout, value in sorted(rates.items()):
                    rate = _number(value, readout)
                    rows.append((frame.frame_index, frame.simulation_time_s, readout, rate, int(rate > 0.0)))
            case _:
                continue
    return tuple(rows)


def _object_field(payload: JsonObject, field: str) -> JsonObject:
    value = payload.get(field)
    if isinstance(value, dict):
        return value
    raise RatesSynthesisError(f"brain payload {field} must be an object")


def _number(value: JsonValue, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise RatesSynthesisError(f"brain rate {field} must be finite")
    return float(value)
