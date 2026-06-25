from __future__ import annotations

import math
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum, unique
from typing import Final, Protocol, assert_never

from digital_fruit_fly.bridge.messages import SCHEMA_VERSION, BrainFrame, ControlFrame, JsonObject, JsonValue, payload_checksum

DEFAULT_WINDOW_MS: Final = 15.0


@unique
class MotorAction(StrEnum):
    STOP = "stop"
    GROOMING = "grooming"
    FEEDING = "feeding"
    LOCOMOTION = "locomotion"


class DecoderThresholdSource(Protocol):
    locomotion_threshold: float
    turn_threshold: float
    feeding_threshold: float
    grooming_threshold: float
    stop_threshold: float


@dataclass(frozen=True, slots=True)
class ReadoutRule:
    group: str; baseline_hz: float; gain_hz: float


@dataclass(frozen=True, slots=True)
class MotorReadoutRules:
    forward: ReadoutRule; turn: ReadoutRule; feeding: ReadoutRule; grooming: ReadoutRule; stop: ReadoutRule

    @classmethod
    def default(cls) -> MotorReadoutRules:
        return cls(ReadoutRule("forward", 8.0, 40.0), ReadoutRule("turn", 2.0, 12.0), ReadoutRule("feed", 3.0, 25.0), ReadoutRule("groom", 1.0, 30.0), ReadoutRule("stop", 1.0, 5.0))

    @property
    def groups(self) -> tuple[str, ...]:
        return (self.forward.group, self.turn.group, self.feeding.group, self.grooming.group, self.stop.group)


@dataclass(frozen=True, slots=True)
class MotorThresholds:
    locomotion: float; turn: float; feeding: float; grooming: float; stop: float

    @classmethod
    def default(cls) -> MotorThresholds:
        return cls(0.2, 0.15, 0.4, 0.35, 0.6)


@dataclass(frozen=True, slots=True)
class MotorDecoderConfig:
    readouts: MotorReadoutRules = field(default_factory=MotorReadoutRules.default)
    thresholds: MotorThresholds = field(default_factory=MotorThresholds.default)
    priority: tuple[MotorAction, ...] = (MotorAction.STOP, MotorAction.GROOMING, MotorAction.FEEDING, MotorAction.LOCOMOTION)
    smoothing_alpha: float = 0.45
    readout_window_ms: float = DEFAULT_WINDOW_MS
    sweep_period_ticks: int = 20
    idle_stop_intensity: float = 1.0

    @classmethod
    def default(cls) -> MotorDecoderConfig:
        return cls()

    @classmethod
    def from_runtime_thresholds(cls, source: DecoderThresholdSource) -> MotorDecoderConfig:
        return cls(thresholds=MotorThresholds(source.locomotion_threshold, source.turn_threshold, source.feeding_threshold, source.grooming_threshold, source.stop_threshold))

    def with_priority(self, priority: tuple[MotorAction, ...]) -> MotorDecoderConfig:
        return MotorDecoderConfig(self.readouts, self.thresholds, priority, self.smoothing_alpha, self.readout_window_ms, self.sweep_period_ticks, self.idle_stop_intensity)


@dataclass(frozen=True, slots=True)
class FoodDirectionContext:
    bearing_rad: float; elevation_rad: float; distance_mm: float; provenance: str


@dataclass(frozen=True, slots=True)
class SensoryDecoderContext:
    food_direction: FoodDirectionContext | None = None


@dataclass(frozen=True, slots=True)
class BrainFrameReadout:
    frame: BrainFrame


@dataclass(frozen=True, slots=True)
class RateReadout:
    rates_hz: Mapping[str, JsonValue]; spike_deltas: Mapping[str, JsonValue] = field(default_factory=dict)
    run_id: str = "rate-readout"; frame_index: int = 0; simulation_time_s: float = 0.0


MotorReadout = BrainFrameReadout | RateReadout


@dataclass(frozen=True, slots=True)
class MotorDecoderState:
    forward: float = 0.0; turn: float = 0.0; feeding: float = 0.0; grooming: float = 0.0; stop: float = 0.0
    sweep_phase: float = 0.0; last_frame_index: int | None = None


@dataclass(frozen=True, slots=True)
class MotorDecoderRequest:
    readout: MotorReadout
    config: MotorDecoderConfig = field(default_factory=MotorDecoderConfig.default)
    sensory: SensoryDecoderContext = field(default_factory=SensoryDecoderContext)
    previous_state: MotorDecoderState | None = None


@dataclass(frozen=True, slots=True)
class MotorDecodeResult:
    payload: JsonObject; control_frame: ControlFrame; state: MotorDecoderState; audit: JsonObject


@dataclass(frozen=True, slots=True)
class MissingReadoutGroup(ValueError):
    group: str; available: tuple[str, ...]

    def __str__(self) -> str:
        return f"missing motor readout group {self.group!r}; available={self.available}"


@dataclass(frozen=True, slots=True)
class MalformedBrainReadout(ValueError):
    field: str; reason: str

    def __str__(self) -> str:
        return f"brain readout {self.field}: {self.reason}"


@dataclass(frozen=True, slots=True)
class MissingFoodDirection(RuntimeError):
    selected_action: str

    def __str__(self) -> str:
        return f"{self.selected_action} requires explicit food-relative direction"


@dataclass(frozen=True, slots=True)
class StaleDecoderState(ValueError):
    previous_frame_index: int; current_frame_index: int

    def __str__(self) -> str:
        return f"decoder state is stale: previous={self.previous_frame_index}, current={self.current_frame_index}"


@dataclass(frozen=True, slots=True)
class _Signals:
    forward: float; turn: float; feeding: float; grooming: float; stop: float


@dataclass(frozen=True, slots=True)
class _Source:
    rates_hz: Mapping[str, JsonValue]; spike_deltas: Mapping[str, JsonValue]
    run_id: str; frame_index: int; simulation_time_s: float


@dataclass(frozen=True, slots=True)
class _AuditInput:
    action: MotorAction; raw: _Signals; state: MotorDecoderState; source: _Source; request: MotorDecoderRequest


def validate_motor_decoder_readouts(config: MotorDecoderConfig, available_groups: Iterable[str]) -> None:
    available = tuple(available_groups); available_set = frozenset(available)
    for group in config.readouts.groups:
        if group not in available_set:
            raise MissingReadoutGroup(group, available)


def decode_motor_payload(request: MotorDecoderRequest) -> MotorDecodeResult:
    _validate_config(request.config)
    source = _source(request.readout)
    if request.previous_state is not None and request.previous_state.last_frame_index is not None and source.frame_index <= request.previous_state.last_frame_index:
        raise StaleDecoderState(request.previous_state.last_frame_index, source.frame_index)
    raw = _signals(source, request.config)
    smoothed = raw if request.previous_state is None else _Signals(
        _smooth(raw.forward, request.previous_state.forward, request.config.smoothing_alpha),
        _smooth(raw.turn, request.previous_state.turn, request.config.smoothing_alpha),
        _smooth(raw.feeding, request.previous_state.feeding, request.config.smoothing_alpha),
        _smooth(raw.grooming, request.previous_state.grooming, request.config.smoothing_alpha),
        _smooth(raw.stop, request.previous_state.stop, request.config.smoothing_alpha),
    )
    state = _state(smoothed, source, request)
    action = _select_action(smoothed, request.config)
    payload = _payload(action, state, request)
    audit = _audit(_AuditInput(action, raw, state, source, request))
    payload["decoder_audit"] = audit
    frame = ControlFrame(SCHEMA_VERSION, source.run_id, source.frame_index, source.simulation_time_s, time.monotonic(), payload, payload_checksum(payload))
    return MotorDecodeResult(payload, frame, state, audit)


def decode_motor_control(request: MotorDecoderRequest) -> MotorDecodeResult:
    return decode_motor_payload(request)


def _source(readout: MotorReadout) -> _Source:
    match readout:
        case BrainFrameReadout(frame=frame):
            return _Source(_object_field(frame.payload, "rates_hz"), _optional_object_field(frame.payload, "spike_deltas"), frame.run_id, frame.frame_index, frame.simulation_time_s)
        case RateReadout(rates_hz=rates, spike_deltas=spikes, run_id=run_id, frame_index=index, simulation_time_s=sim_time):
            return _Source(rates, spikes, run_id, index, sim_time)
        case unreachable:
            assert_never(unreachable)


def _signals(source: _Source, config: MotorDecoderConfig) -> _Signals:
    rules = config.readouts
    return _Signals(_unit(source, rules.forward, config), _signed(source, rules.turn, config), _unit(source, rules.feeding, config), _unit(source, rules.grooming, config), _unit(source, rules.stop, config))


def _unit(source: _Source, rule: ReadoutRule, config: MotorDecoderConfig) -> float:
    return _clamp((_rate(source, rule.group, config) - rule.baseline_hz) / rule.gain_hz, 0.0, 1.0)


def _signed(source: _Source, rule: ReadoutRule, config: MotorDecoderConfig) -> float:
    return _clamp((_rate(source, rule.group, config) - rule.baseline_hz) / rule.gain_hz, -1.0, 1.0)


def _rate(source: _Source, group: str, config: MotorDecoderConfig) -> float:
    if group in source.rates_hz:
        return _number(source.rates_hz[group], f"rates_hz.{group}")
    if group in source.spike_deltas:
        return _nonnegative_int(source.spike_deltas[group], f"spike_deltas.{group}") * 1000.0 / config.readout_window_ms
    raise MissingReadoutGroup(group, tuple(source.rates_hz.keys()) + tuple(source.spike_deltas.keys()))


def _select_action(signals: _Signals, config: MotorDecoderConfig) -> MotorAction:
    if signals.stop >= config.thresholds.stop:
        return MotorAction.STOP
    active = _active(signals, config)
    for action in config.priority:
        if action in active:
            return action
    return MotorAction.STOP


def _active(signals: _Signals, config: MotorDecoderConfig) -> frozenset[MotorAction]:
    active: set[MotorAction] = set()
    if signals.feeding >= config.thresholds.feeding:
        active.add(MotorAction.FEEDING)
    if signals.grooming >= config.thresholds.grooming:
        active.add(MotorAction.GROOMING)
    if signals.forward >= config.thresholds.locomotion or abs(signals.turn) >= config.thresholds.turn:
        active.add(MotorAction.LOCOMOTION)
    return frozenset(active)


def _state(signals: _Signals, source: _Source, request: MotorDecoderRequest) -> MotorDecoderState:
    phase = (source.frame_index % request.config.sweep_period_ticks) / request.config.sweep_period_ticks
    if request.previous_state is not None:
        phase = (request.previous_state.sweep_phase + 1.0 / request.config.sweep_period_ticks) % 1.0
    return MotorDecoderState(signals.forward, signals.turn, signals.feeding, signals.grooming, signals.stop, phase, source.frame_index)


def _payload(action: MotorAction, state: MotorDecoderState, request: MotorDecoderRequest) -> JsonObject:
    payload: JsonObject = {"forward": 0.0, "turn_bias": 0.0, "feeding": 0.0, "grooming": 0.0, "stop": 0.0, "proboscis_extension": 0.0, "sweep_phase": state.sweep_phase}
    match action:
        case MotorAction.STOP:
            payload["stop"] = max(state.stop, request.config.idle_stop_intensity)
        case MotorAction.LOCOMOTION:
            payload["forward"] = state.forward; payload["turn_bias"] = state.turn
        case MotorAction.FEEDING:
            direction = request.sensory.food_direction
            if direction is None:
                raise MissingFoodDirection(action.value)
            payload.update({"feeding": state.feeding, "proboscis_extension": state.feeding, "proboscis_yaw": _clamp(direction.bearing_rad, -1.0, 1.0), "proboscis_pitch": _clamp(direction.elevation_rad, -1.0, 1.0), "food_relative": {"bearing_rad": direction.bearing_rad, "elevation_rad": direction.elevation_rad, "distance_mm": direction.distance_mm}})
        case MotorAction.GROOMING:
            payload["grooming"] = state.grooming; payload["grooming_sweep_intensity"] = state.grooming
        case unreachable:
            assert_never(unreachable)
    return payload


def _audit(data: _AuditInput) -> JsonObject:
    direction = data.request.sensory.food_direction
    return {
        "selected_action": data.action.value, "arena_state_used_for_mode": False,
        "source": {"run_id": data.source.run_id, "frame_index": data.source.frame_index, "simulation_time_s": data.source.simulation_time_s},
        "readout_groups": list(data.request.config.readouts.groups), "thresholds": _thresholds(data.request.config.thresholds),
        "priority": [item.value for item in data.request.config.priority], "raw": _signals_json(data.raw),
        "smoothed": _signals_json(_Signals(data.state.forward, data.state.turn, data.state.feeding, data.state.grooming, data.state.stop)),
        "sensory_provenance": {"food_direction": None} if direction is None else {"food_direction": direction.provenance, "distance_mm": direction.distance_mm},
    }


def _signals_json(signals: _Signals) -> JsonObject:
    return {"forward": signals.forward, "turn": signals.turn, "feeding": signals.feeding, "grooming": signals.grooming, "stop": signals.stop}


def _thresholds(thresholds: MotorThresholds) -> JsonObject:
    return {"locomotion": thresholds.locomotion, "turn": thresholds.turn, "feeding": thresholds.feeding, "grooming": thresholds.grooming, "stop": thresholds.stop}


def _validate_config(config: MotorDecoderConfig) -> None:
    if not 0.0 <= config.smoothing_alpha <= 1.0:
        raise MalformedBrainReadout("smoothing_alpha", "must be between 0 and 1")
    if config.readout_window_ms <= 0.0 or config.sweep_period_ticks <= 0:
        raise MalformedBrainReadout("decoder_timing", "window and sweep period must be positive")
    for rule in (config.readouts.forward, config.readouts.turn, config.readouts.feeding, config.readouts.grooming, config.readouts.stop):
        if rule.gain_hz <= 0.0:
            raise MalformedBrainReadout(rule.group, "gain_hz must be positive")


def _object_field(payload: Mapping[str, JsonValue], field_name: str) -> JsonObject:
    value = payload.get(field_name)
    if isinstance(value, dict):
        return value
    raise MalformedBrainReadout(field_name, "must be an object")


def _optional_object_field(payload: Mapping[str, JsonValue], field_name: str) -> JsonObject:
    value = payload.get(field_name, {})
    if isinstance(value, dict):
        return value
    raise MalformedBrainReadout(field_name, "must be an object")


def _number(value: JsonValue, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise MalformedBrainReadout(field_name, "must be a finite number")
    return float(value)


def _nonnegative_int(value: JsonValue, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MalformedBrainReadout(field_name, "must be a non-negative integer")
    return value


def _smooth(current: float, previous: float, alpha: float) -> float:
    return alpha * current + (1.0 - alpha) * previous


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))
