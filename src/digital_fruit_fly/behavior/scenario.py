from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from digital_fruit_fly.bridge.messages import (
    BrainFrame,
    BridgeFrame,
    ControlFrame,
    ErrorFrame,
    JsonObject,
    JsonValue,
    SensoryFrame,
    decode_message,
)
from digital_fruit_fly.runtime.config import ConfigError, RuntimeConfig, load_config
from digital_fruit_fly.runtime.timeouts import write_json_evidence

BEHAVIOR_SUMMARY: Final = "behavior_summary.json"
TASK_EVIDENCE: Final = Path(".omo/evidence/task-22-eon-embodied-fly.json")
ORDERED_EVENTS: Final = (
    "search_started",
    "sugar_cue_acquired",
    "food_contact",
    "feeding_started",
    "proboscis_extended",
    "dust_threshold_crossed",
    "grooming_started",
    "face_grooming_sweep_detected",
    "dust_clean",
    "locomotion_resumed",
)

@dataclass(frozen=True, slots=True)
class BehaviorFailure:
    code: str
    message: str
    details: JsonObject


@dataclass(frozen=True, slots=True)
class BehaviorVerificationError(Exception):
    failure: BehaviorFailure

    def __str__(self) -> str:
        return self.failure.message


@dataclass(frozen=True, slots=True)
class BehaviorVerifyRequest:
    input_dir: Path
    config_path: Path
    evidence_path: Path = TASK_EVIDENCE


@dataclass(frozen=True, slots=True)
class ScenarioEvent:
    name: str
    frame_index: int
    brain_frame_id: str
    control_frame_id: str
    selected_action: str
    details: JsonObject

    def evidence(self) -> JsonObject:
        return {
            "name": self.name,
            "frame_index": self.frame_index,
            "brain_frame_id": self.brain_frame_id,
            "control_frame_id": self.control_frame_id,
            "selected_action": self.selected_action,
            "details": self.details,
        }


@dataclass(frozen=True, slots=True)
class BehaviorResult:
    input_dir: Path
    config_path: Path
    events: tuple[ScenarioEvent, ...]
    metrics: JsonObject
    summary_path: Path
    evidence_path: Path

    def evidence(self) -> JsonObject:
        return {
            "script": "replay_run",
            "status": "ok",
            "mode": "verify_behavior",
            "input": str(self.input_dir),
            "config": str(self.config_path),
            "ordered_events": [event.evidence() for event in self.events],
            "metrics": dict(self.metrics),
            "artifacts": [str(self.summary_path), str(self.evidence_path)],
        }


@dataclass(frozen=True, slots=True)
class FrameTriplet:
    sensory: SensoryFrame
    brain: BrainFrame
    control: ControlFrame


@dataclass(frozen=True, slots=True)
class MetricState:
    proboscis_target: float | None
    food_bearing: float | None
    angular_error: float | None
    sweep_min: float | None
    sweep_max: float | None


def verify_behavior(request: BehaviorVerifyRequest) -> BehaviorResult:
    summary_path = request.input_dir / BEHAVIOR_SUMMARY
    summary_path.unlink(missing_ok=True)
    config = _load_config(request.config_path)
    triplets = _load_triplets(request.input_dir / "frames.jsonl")
    events, metrics = _scan_ordered_events(triplets, config)
    result = BehaviorResult(request.input_dir, request.config_path, events, metrics, summary_path, request.evidence_path)
    payload = result.evidence()
    write_json_evidence(summary_path, payload)
    write_json_evidence(request.evidence_path, payload)
    return result


def write_behavior_failure(request: BehaviorVerifyRequest, failure: BehaviorFailure) -> None:
    payload: JsonObject = {
        "script": "replay_run",
        "status": "failed",
        "mode": "verify_behavior",
        "input": str(request.input_dir),
        "config": str(request.config_path),
        "error_code": failure.code,
        "error": failure.message,
        "failure": failure.details,
    }
    write_json_evidence(request.input_dir / "replay_evidence.json", payload)
    write_json_evidence(request.evidence_path, payload)


def _scan_ordered_events(triplets: tuple[FrameTriplet, ...], config: RuntimeConfig) -> tuple[tuple[ScenarioEvent, ...], JsonObject]:
    events: list[ScenarioEvent] = []
    metrics = MetricState(None, None, None, None, None)
    for triplet in triplets:
        metrics = _update_sweep(metrics, triplet)
        if len(events) == len(ORDERED_EVENTS):
            break
        expected = ORDERED_EVENTS[len(events)]
        if _matches_event(expected, triplet, config, metrics):
            event, metrics = _record_event(expected, triplet, metrics)
            events.append(event)
    if len(events) != len(ORDERED_EVENTS):
        missing = ORDERED_EVENTS[len(events)]
        raise BehaviorVerificationError(
            BehaviorFailure(
                "missing_behavior_event",
                f"missing ordered behavior event: {missing}",
                {"missing_event": missing, "observed_events": [event.name for event in events], "required_order": list(ORDERED_EVENTS)},
            )
        )
    return tuple(events), _metrics_json(metrics)


def _matches_event(name: str, triplet: FrameTriplet, config: RuntimeConfig, metrics: MetricState) -> bool:
    action = _selected_action(triplet.control)
    rates = _object(triplet.sensory.payload, "rates_hz")
    match name:
        case "search_started":
            return action == "locomotion" and _rate(rates, "sugar_left") + _rate(rates, "sugar_right") <= 1.0
        case "sugar_cue_acquired":
            return _rate(rates, "sugar_left") + _rate(rates, "sugar_right") > 1.0
        case "food_contact":
            return _rate(rates, "food_contact") >= 125.0
        case "feeding_started":
            return action == "feeding"
        case "proboscis_extended":
            return action == "feeding" and _number(triplet.control.payload.get("proboscis_extension", 0.0), "proboscis_extension") > 0.1
        case "dust_threshold_crossed":
            return _rate(rates, "dust_threshold") >= 125.0 and _dust_load(triplet.sensory) >= config.arena.dust.threshold
        case "grooming_started":
            return action == "grooming"
        case "face_grooming_sweep_detected":
            return action == "grooming" and _sweep_amplitude(metrics) >= 0.30
        case "dust_clean":
            return _dust_load(triplet.sensory) <= 1e-9
        case "locomotion_resumed":
            return action == "locomotion"
        case _:
            return False


def _record_event(name: str, triplet: FrameTriplet, metrics: MetricState) -> tuple[ScenarioEvent, MetricState]:
    next_metrics = _update_proboscis(metrics, triplet) if name == "proboscis_extended" else metrics
    event = ScenarioEvent(
        name=name,
        frame_index=triplet.control.frame_index,
        brain_frame_id=f"{triplet.brain.run_id}:{triplet.brain.frame_index}",
        control_frame_id=f"{triplet.control.run_id}:{triplet.control.frame_index}",
        selected_action=_selected_action(triplet.control),
        details={"action_event": name not in ("sugar_cue_acquired", "food_contact", "dust_threshold_crossed", "dust_clean"), "brain_rates_hz": _object(triplet.brain.payload, "rates_hz")},
    )
    return event, next_metrics


def _update_proboscis(metrics: MetricState, triplet: FrameTriplet) -> MetricState:
    target = _number(triplet.control.payload.get("proboscis_yaw", 0.0), "proboscis_yaw")
    food = _object(triplet.control.payload, "food_relative")
    bearing = _number(food.get("bearing_rad", 0.0), "food_relative.bearing_rad")
    return MetricState(target, bearing, math.atan2(math.sin(target - bearing), math.cos(target - bearing)), metrics.sweep_min, metrics.sweep_max)


def _update_sweep(metrics: MetricState, triplet: FrameTriplet) -> MetricState:
    if _selected_action(triplet.control) != "grooming":
        return metrics
    phase = _number(triplet.control.payload.get("sweep_phase", 0.0), "sweep_phase")
    low = phase if metrics.sweep_min is None else min(metrics.sweep_min, phase)
    high = phase if metrics.sweep_max is None else max(metrics.sweep_max, phase)
    return MetricState(metrics.proboscis_target, metrics.food_bearing, metrics.angular_error, low, high)


def _metrics_json(metrics: MetricState) -> JsonObject:
    if metrics.proboscis_target is None or metrics.food_bearing is None or metrics.angular_error is None:
        raise BehaviorVerificationError(BehaviorFailure("missing_metric", "proboscis metrics were not recorded", {}))
    return {
        "proboscis_target_bearing_rad": metrics.proboscis_target,
        "food_bearing_at_extension_rad": metrics.food_bearing,
        "proboscis_angular_error_rad": metrics.angular_error,
        "proboscis_abs_angular_error_rad": abs(metrics.angular_error),
        "grooming_sweep_amplitude": _sweep_amplitude(metrics),
    }


def _load_triplets(path: Path) -> tuple[FrameTriplet, ...]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise BehaviorVerificationError(BehaviorFailure("missing_artifact", f"missing {path}", {"path": str(path)})) from exc
    frames = tuple(_decode_line(line, index + 1) for index, line in enumerate(lines))
    if len(frames) % 3 != 0:
        raise BehaviorVerificationError(BehaviorFailure("malformed_artifact", "frames.jsonl must contain complete sensory/brain/control triplets", {"frame_count": len(frames)}))
    return tuple(_triplet(frames[index : index + 3], index) for index in range(0, len(frames), 3))


def _decode_line(line: str, line_number: int) -> BridgeFrame:
    frame = decode_message(line.encode("utf-8"))
    match frame:
        case ErrorFrame(code=code, message=message):
            raise BehaviorVerificationError(BehaviorFailure("malformed_frame", message, {"line_number": line_number, "decode_code": code}))
        case _:
            return frame


def _triplet(frames: tuple[BridgeFrame, ...], offset: int) -> FrameTriplet:
    match frames:
        case (SensoryFrame() as sensory, BrainFrame() as brain, ControlFrame() as control):
            return FrameTriplet(sensory, brain, control)
        case _:
            raise BehaviorVerificationError(BehaviorFailure("malformed_artifact", "expected sensory/brain/control triplet", {"sequence": offset}))


def _load_config(path: Path) -> RuntimeConfig:
    try:
        return load_config(path)
    except ConfigError as exc:
        raise BehaviorVerificationError(BehaviorFailure("config_error", str(exc), {"config": str(path)})) from exc


def _selected_action(control: ControlFrame) -> str:
    audit = _object(control.payload, "decoder_audit")
    value = audit.get("selected_action")
    if isinstance(value, str):
        return value
    raise BehaviorVerificationError(BehaviorFailure("malformed_artifact", "control decoder_audit.selected_action must be a string", {"frame_index": control.frame_index}))


def _dust_load(sensory: SensoryFrame) -> float:
    audit = _object(sensory.payload, "encoder_audit")
    raw = _object(audit, "raw")
    return _number(raw.get("dust_load", 0.0), "encoder_audit.raw.dust_load")


def _rate(rates: JsonObject, name: str) -> float:
    return _number(rates.get(name, 0.0), f"rates_hz.{name}")


def _sweep_amplitude(metrics: MetricState) -> float:
    if metrics.sweep_min is None or metrics.sweep_max is None:
        return 0.0
    return metrics.sweep_max - metrics.sweep_min


def _object(payload: JsonObject, field: str) -> JsonObject:
    value = payload.get(field)
    if isinstance(value, dict):
        return value
    raise BehaviorVerificationError(BehaviorFailure("malformed_artifact", f"{field} must be an object", {"field": field}))


def _number(value: JsonValue, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise BehaviorVerificationError(BehaviorFailure("malformed_artifact", f"{field} must be a finite number", {"field": field}))
    return float(value)
