from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

from digital_fruit_fly.arena.model import SugarCueSample
from digital_fruit_fly.body.observations import BodyObservation
from digital_fruit_fly.runtime.timeouts import JsonObject, JsonValue

RateAdder = Callable[[str, float, JsonValue], None]


FORBIDDEN_SENSORY_KEYS: Final = frozenset(
    ("behavior", "behavior_label", "action", "action_label", "mode", "controller_mode", "groom_now", "feed_now")
)


@dataclass(frozen=True, slots=True)
class SensoryEncodingConfigError(Exception):
    field: str
    reason: str

    def __str__(self) -> str:
        return f"{self.field}: {self.reason}"


@dataclass(frozen=True, slots=True)
class SensoryEncodingValueError(Exception):
    field: str
    reason: str

    def __str__(self) -> str:
        return f"{self.field}: {self.reason}"


@dataclass(frozen=True, slots=True)
class ForbiddenSensoryField(Exception):
    field_path: str

    def __str__(self) -> str:
        return f"forbidden sensory behavior-label field: {self.field_path}"


@dataclass(frozen=True, slots=True)
class ChannelRateLimit:
    channel_name: str
    max_rate_hz: float

    def __post_init__(self) -> None:
        if self.channel_name == "":
            raise SensoryEncodingConfigError("channel_name", "must not be empty")
        if self.max_rate_hz < 0.0:
            raise SensoryEncodingConfigError(self.channel_name, "max_rate_hz must be non-negative")


@dataclass(frozen=True, slots=True)
class SensoryChannelRateConfig:
    default_max_rate_hz: float = 250.0
    channel_limits: tuple[ChannelRateLimit, ...] = ()

    def __post_init__(self) -> None:
        if self.default_max_rate_hz < 0.0:
            raise SensoryEncodingConfigError("default_max_rate_hz", "must be non-negative")

    def max_rate_for(self, channel_name: str) -> float:
        for limit in self.channel_limits:
            if limit.channel_name == channel_name:
                return limit.max_rate_hz
        return self.default_max_rate_hz


@dataclass(frozen=True, slots=True)
class SensoryNormalizationConfig:
    max_dust_load: float = 1.0
    dust_threshold: float = 0.5
    max_food_distance_mm: float = 25.0
    max_joint_abs: float = 1.0
    max_velocity_abs: float = 5.0
    max_feedback_abs: float = 1.0
    max_bearing_rad: float = math.pi
    max_elevation_rad: float = math.pi / 2.0

    def __post_init__(self) -> None:
        for field_name, value in (
            ("max_dust_load", self.max_dust_load),
            ("dust_threshold", self.dust_threshold),
            ("max_food_distance_mm", self.max_food_distance_mm),
            ("max_joint_abs", self.max_joint_abs),
            ("max_velocity_abs", self.max_velocity_abs),
            ("max_feedback_abs", self.max_feedback_abs),
            ("max_bearing_rad", self.max_bearing_rad),
            ("max_elevation_rad", self.max_elevation_rad),
        ):
            if value <= 0.0:
                raise SensoryEncodingConfigError(field_name, "must be positive")


@dataclass(frozen=True, slots=True)
class FineJointDofConfig:
    proboscis: tuple[str, ...] = ()
    antenna: tuple[str, ...] = ()
    front_leg: tuple[str, ...] = ()
    head: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SensoryEncodingConfig:
    channel_rates: SensoryChannelRateConfig = field(default_factory=SensoryChannelRateConfig)
    normalization: SensoryNormalizationConfig = field(default_factory=SensoryNormalizationConfig)
    fine_joint_dofs: FineJointDofConfig = field(default_factory=FineJointDofConfig)
    action_feedback_channels: tuple[str, ...] = ()
    latency_ticks: int = 0

    def __post_init__(self) -> None:
        if self.latency_ticks < 0:
            raise SensoryEncodingConfigError("latency_ticks", "must be non-negative")
        for channel in self.action_feedback_channels:
            _reject_forbidden_name(channel, "action_feedback_channels")


@dataclass(frozen=True, slots=True)
class SensoryEncodingRequest:
    observation: BodyObservation
    sugar_cue: SugarCueSample
    action_feedback: Mapping[str, float] = field(default_factory=dict)
    source_metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "action_feedback", MappingProxyType(dict(self.action_feedback)))
        object.__setattr__(self, "source_metadata", MappingProxyType(dict(self.source_metadata)))


@dataclass(frozen=True, slots=True)
class SensoryEncodingResult:
    rates_hz: dict[str, float]
    audit: JsonObject


class SensoryEncoder:
    def __init__(self, config: SensoryEncodingConfig) -> None:
        self._config = config
        self._pending: list[SensoryEncodingResult] = []

    def encode(self, request: SensoryEncodingRequest) -> SensoryEncodingResult:
        current = _encode_current(self._config, request)
        if self._config.latency_ticks == 0:
            return current
        self._pending.append(current)
        if len(self._pending) <= self._config.latency_ticks:
            return _silence_like(current, self._config.latency_ticks)
        return self._pending.pop(0)


def encode_sensory_observation(
    config: SensoryEncodingConfig, request: SensoryEncodingRequest
) -> SensoryEncodingResult:
    return SensoryEncoder(config).encode(request)


def _encode_current(config: SensoryEncodingConfig, request: SensoryEncodingRequest) -> SensoryEncodingResult:
    _reject_forbidden_json(request.source_metadata, "source_metadata")
    for channel_name in request.action_feedback:
        _reject_forbidden_name(channel_name, "action_feedback")
    rates: dict[str, float] = {}
    raw: JsonObject = {}
    normalized: JsonObject = {}

    def add(channel_name: str, unit_value: float, raw_value: JsonValue) -> None:
        unit = _clip_unit(unit_value)
        rates[channel_name] = unit * config.channel_rates.max_rate_for(channel_name)
        raw[channel_name] = raw_value
        normalized[channel_name] = unit

    observation = request.observation
    norm = config.normalization
    add("sugar_left", request.sugar_cue.left, request.sugar_cue.left)
    add("sugar_right", request.sugar_cue.right, request.sugar_cue.right)
    add("food_contact", 1.0 if observation.food_contact else 0.0, observation.food_contact)
    _encode_dust(add, observation, norm)
    add("ground_contact", _number(observation.ground_contact, "active_fraction", "ground_contact"), observation.ground_contact)
    _encode_proprioception(add, observation, norm)
    _encode_food_direction(add, observation, norm)
    _encode_fine_joints(add, observation, config.fine_joint_dofs, norm)
    _encode_action_feedback(add, request, config)
    return SensoryEncodingResult(
        rates_hz=rates,
        audit={"latency_ticks": config.latency_ticks, "raw": raw, "normalized": normalized, "rates_hz": dict(rates)},
    )


def _encode_dust(add: RateAdder, observation: BodyObservation, norm: SensoryNormalizationConfig) -> None:
    dust_load = _number(observation.dust, "dust_load", "dust")
    threshold = _bool(observation.dust, "threshold_crossed") or dust_load >= norm.dust_threshold
    add("dust_load", dust_load / norm.max_dust_load, dust_load)
    add("dust_threshold", 1.0 if threshold else 0.0, threshold)


def _encode_proprioception(add: RateAdder, observation: BodyObservation, norm: SensoryNormalizationConfig) -> None:
    angle = _number(observation.proprioception, "joint_angle_mean_abs", "proprioception")
    velocity = _number(observation.proprioception, "joint_velocity_mean_abs", "proprioception")
    angle_unit = abs(angle) / norm.max_joint_abs
    velocity_unit = abs(velocity) / norm.max_velocity_abs
    add("proprioception_summary", (angle_unit + velocity_unit) / 2.0, observation.proprioception)
    add("proprioception_joint_angle", angle_unit, angle)
    add("proprioception_joint_velocity", velocity_unit, velocity)


def _encode_food_direction(add: RateAdder, observation: BodyObservation, norm: SensoryNormalizationConfig) -> None:
    food = observation.food_relative
    add("food_bearing_left", max(food.bearing_rad, 0.0) / norm.max_bearing_rad, food.bearing_rad)
    add("food_bearing_right", max(-food.bearing_rad, 0.0) / norm.max_bearing_rad, food.bearing_rad)
    add("food_elevation_up", max(food.elevation_rad, 0.0) / norm.max_elevation_rad, food.elevation_rad)
    add("food_elevation_down", max(-food.elevation_rad, 0.0) / norm.max_elevation_rad, food.elevation_rad)
    add("food_distance", food.distance_mm / norm.max_food_distance_mm, food.distance_mm)


def _encode_fine_joints(
    add: RateAdder, observation: BodyObservation, config: FineJointDofConfig, norm: SensoryNormalizationConfig
) -> None:
    for group, names, values in (
        ("proboscis", config.proboscis, observation.joint_angles.proboscis),
        ("antenna", config.antenna, observation.joint_angles.antenna),
        ("front_leg", config.front_leg, observation.joint_angles.front_leg),
        ("head", config.head, observation.joint_angles.head),
    ):
        for name in names:
            angle = _required_number(values, name, group)
            add(f"{group}_{_channel_token(name)}", abs(angle) / norm.max_joint_abs, angle)


def _encode_action_feedback(
    add: RateAdder, request: SensoryEncodingRequest, config: SensoryEncodingConfig
) -> None:
    for channel in config.action_feedback_channels:
        value = request.action_feedback.get(channel, 0.0)
        add(f"action_feedback_{_channel_token(channel)}", value / config.normalization.max_feedback_abs, value)


def _silence_like(result: SensoryEncodingResult, latency_ticks: int) -> SensoryEncodingResult:
    rates = {channel: 0.0 for channel in result.rates_hz}
    return SensoryEncodingResult(
        rates_hz=rates,
        audit={"latency_ticks": latency_ticks, "latency_priming": True, "rates_hz": rates},
    )


def _number(source: Mapping[str, JsonValue], key: str, category: str) -> float:
    value = source.get(key, 0.0)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    raise SensoryEncodingValueError(f"{category}.{key}", "must be a finite number")


def _required_number(source: Mapping[str, JsonValue], key: str, category: str) -> float:
    if key not in source:
        raise SensoryEncodingValueError(f"{category}.{key}", "is required by fine_joint_dofs")
    return _number(source, key, category)


def _bool(source: Mapping[str, JsonValue], key: str) -> bool:
    value = source.get(key, False)
    if isinstance(value, bool):
        return value
    raise SensoryEncodingValueError(key, "must be a boolean")


def _reject_forbidden_json(value: Mapping[str, JsonValue], path: str) -> None:
    for key, item in value.items():
        child_path = f"{path}.{key}"
        _reject_forbidden_name(key, child_path)
        if isinstance(item, dict):
            _reject_forbidden_json(item, child_path)
        if isinstance(item, list):
            _reject_forbidden_list(item, child_path)


def _reject_forbidden_list(values: list[JsonValue], path: str) -> None:
    for index, item in enumerate(values):
        child_path = f"{path}[{index}]"
        if isinstance(item, dict):
            _reject_forbidden_json(item, child_path)
        if isinstance(item, list):
            _reject_forbidden_list(item, child_path)


def _reject_forbidden_name(name: str, path: str) -> None:
    if name in FORBIDDEN_SENSORY_KEYS:
        raise ForbiddenSensoryField(path)


def _channel_token(name: str) -> str:
    token = "".join(character if character.isalnum() else "_" for character in name.lower()).strip("_")
    return token or "unnamed"


def _clip_unit(value: float) -> float:
    if value <= 0.0:
        return 0.0
    if value >= 1.0:
        return 1.0
    return value
