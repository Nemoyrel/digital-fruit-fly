from __future__ import annotations

import math
from dataclasses import dataclass, field

from digital_fruit_fly.arena.model import ArenaGeometry, FlyPose2D, build_arena_geometry_from_runtime
from digital_fruit_fly.body.observations import BodyObservation, BodyPose, FineJointAngles, FoodRelative
from digital_fruit_fly.bridge.messages import SCHEMA_VERSION, BrainFrame, ControlFrame, JsonObject, JsonValue, SensoryFrame, payload_checksum
from digital_fruit_fly.bridge.motor_decoder import FoodDirectionContext, MotorDecoderConfig, MotorDecoderState, SensoryDecoderContext
from digital_fruit_fly.bridge.sensory_encoder import SensoryEncoder, SensoryEncodingConfig, SensoryNormalizationConfig
from digital_fruit_fly.runtime.config import RuntimeConfig


@dataclass(frozen=True, slots=True)
class BridgeSmokeError(Exception):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class FixtureState:
    x_mm: float
    y_mm: float
    z_mm: float
    yaw_rad: float
    dust_load: float = 0.0
    dust_threshold_crossed: bool = False
    action_feedback: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FixtureLoop:
    run_id: str
    arena: ArenaGeometry
    config: RuntimeConfig
    decoder_config: MotorDecoderConfig
    encoder: SensoryEncoder
    body_state: FixtureState
    decoder_state: MotorDecoderState | None = None


@dataclass(frozen=True, slots=True)
class FixtureBrainDrive:
    tick: int
    sugar_left: float
    sugar_right: float
    food_contact: float
    dust_threshold: float
    food_bearing_rad: float
    grooming_feedback: float


def initial_loop(run_id: str, config: RuntimeConfig) -> FixtureLoop:
    arena = build_arena_geometry_from_runtime(config.arena)
    decoder_config = MotorDecoderConfig.from_runtime_thresholds(config.decoder)
    body = FixtureState(4.0, config.arena.height_mm / 2.0, 0.3, 0.0)
    encoder = SensoryEncoder(
        SensoryEncodingConfig(
            normalization=SensoryNormalizationConfig(dust_threshold=config.arena.dust.threshold),
            action_feedback_channels=(
                "forward",
                "turn_bias",
                "feeding",
                "grooming",
                "stop",
                "proboscis_extension",
                "sweep_phase",
            )
        )
    )
    return FixtureLoop(run_id, arena, config, decoder_config, encoder, body)


def fixture_observation(state: FixtureState, arena: ArenaGeometry, dust_threshold: float) -> BodyObservation:
    pose = BodyPose(state.x_mm, state.y_mm, state.z_mm, state.yaw_rad)
    food = _food_relative(pose, arena)
    fly_pose = FlyPose2D(state.x_mm, state.y_mm, state.yaw_rad)
    return BodyObservation(
        pose=pose,
        food_contact=arena.is_food_contact(fly_pose),
        food_relative=food,
        ground_contact={"active_fraction": 0.5},
        contact_forces={},
        proprioception={"joint_angle_mean_abs": 0.2, "joint_velocity_mean_abs": 0.3},
        dust={"dust_load": state.dust_load, "threshold_crossed": state.dust_threshold_crossed or state.dust_load >= dust_threshold},
        joint_angles=FineJointAngles(proboscis={}, antenna={}, front_leg={}, head={}),
        site_positions={},
    )


def sensory_payload(tick: int, observation: BodyObservation, rates: dict[str, float], audit: JsonObject) -> JsonObject:
    food = observation.food_relative
    payload: JsonObject = {
        "tick_index": tick,
        "rates_hz": dict(rates),
        "encoder_audit": audit,
        "food_direction": {"bearing_rad": food.bearing_rad, "elevation_rad": food.elevation_rad, "distance_mm": food.distance_mm},
    }
    payload["payload_checksum_source"] = payload_checksum(payload)
    return payload


def build_fixture_brain_frame(sensory: SensoryFrame) -> BrainFrame:
    drive = _brain_drive(sensory)
    rates = _brain_rates(drive)
    payload: JsonObject = {"rates_hz": rates, "spike_deltas": {}, "tick_index": drive.tick, "fixture_mode": _fixture_mode(drive)}
    return BrainFrame(
        SCHEMA_VERSION,
        sensory.run_id,
        sensory.frame_index,
        sensory.simulation_time_s,
        sensory.sent_monotonic_s,
        payload,
        payload_checksum(payload),
    )


def decoder_context_from_sensory(sensory: SensoryFrame) -> SensoryDecoderContext:
    direction = _object_payload(sensory.payload, "food_direction")
    return SensoryDecoderContext(
        FoodDirectionContext(
            _number(direction.get("bearing_rad", 0.0), "food_direction.bearing_rad"),
            _number(direction.get("elevation_rad", 0.0), "food_direction.elevation_rad"),
            _number(direction.get("distance_mm", 0.0), "food_direction.distance_mm"),
            f"sensory_frame:{sensory.frame_index}/food_direction",
        )
    )


def next_loop(loop: FixtureLoop, control: ControlFrame, decoder_state: MotorDecoderState) -> FixtureLoop:
    return FixtureLoop(loop.run_id, loop.arena, loop.config, loop.decoder_config, loop.encoder, _next_state(loop, control), decoder_state)


def feedback_numbers(payload: JsonObject) -> dict[str, float]:
    return {key: _number(value, f"feedback.{key}") for key, value in payload.items() if isinstance(value, (int, float)) and not isinstance(value, bool)}


def _brain_drive(sensory: SensoryFrame) -> FixtureBrainDrive:
    tick = _int_payload(sensory.payload, "tick_index")
    source_rates = _object_payload(sensory.payload, "rates_hz")
    direction = _object_payload(sensory.payload, "food_direction")
    return FixtureBrainDrive(
        tick,
        _number(source_rates.get("sugar_left", 0.0), "rates_hz.sugar_left"),
        _number(source_rates.get("sugar_right", 0.0), "rates_hz.sugar_right"),
        _number(source_rates.get("food_contact", 0.0), "rates_hz.food_contact"),
        _number(source_rates.get("dust_threshold", 0.0), "rates_hz.dust_threshold"),
        _number(direction.get("bearing_rad", 0.0), "food_direction.bearing_rad"),
        _number(source_rates.get("action_feedback_grooming", 0.0), "rates_hz.action_feedback_grooming"),
    )


def _brain_rates(drive: FixtureBrainDrive) -> JsonObject:
    match _fixture_mode(drive):
        case "grooming":
            return {"forward": 8.0, "turn": 2.0, "feed": 3.0, "groom": 44.0, "stop": 3.0}
        case "feeding":
            return {"forward": 8.0, "turn": 2.0, "feed": 42.0, "groom": 1.0, "stop": 1.0}
        case "locomotion":
            return {"forward": 48.0, "turn": 2.0 + (_turn_drive(drive) * 12.0), "feed": 3.0, "groom": 1.0, "stop": 1.0}
        case _:
            raise BridgeSmokeError("unsupported fixture brain mode")


def _fixture_mode(drive: FixtureBrainDrive) -> str:
    if drive.dust_threshold >= 125.0:
        return "grooming"
    if drive.grooming_feedback >= 1.0:
        return "locomotion"
    if drive.food_contact >= 125.0:
        return "feeding"
    return "locomotion"


def _turn_drive(drive: FixtureBrainDrive) -> float:
    sugar_total = drive.sugar_left + drive.sugar_right
    if sugar_total > 1.0:
        return _clamp(drive.food_bearing_rad, -1.0, 1.0)
    return 0.0


def _next_state(loop: FixtureLoop, control: ControlFrame) -> FixtureState:
    forward = _number(control.payload.get("forward", 0.0), "control.forward")
    turn = _number(control.payload.get("turn_bias", 0.0), "control.turn_bias")
    grooming = _number(control.payload.get("grooming", 0.0), "control.grooming")
    yaw = loop.body_state.yaw_rad + (turn * 0.08)
    distance = forward * 0.2
    raw_pose = FlyPose2D(loop.body_state.x_mm + math.cos(yaw) * distance, loop.body_state.y_mm + math.sin(yaw) * distance, yaw)
    pose = loop.arena.clamp_pose(raw_pose).pose
    dust = max(
        0.0,
        loop.body_state.dust_load
        + loop.config.arena.dust.accumulation_rate_per_sec * loop.config.tick_ms / 1000.0
        - grooming * loop.config.arena.dust.cleaning_rate_per_sec * loop.config.tick_ms / 1000.0,
    )
    threshold_crossed = False if dust == 0.0 else loop.body_state.dust_threshold_crossed or dust >= loop.config.arena.dust.threshold
    return FixtureState(pose.x_mm, pose.y_mm, loop.body_state.z_mm, pose.heading_rad, dust, threshold_crossed, dict(control.payload))


def _food_relative(pose: BodyPose, arena: ArenaGeometry) -> FoodRelative:
    dx = arena.food.center.x_mm - pose.x_mm
    dy = arena.food.center.y_mm - pose.y_mm
    heading_error = math.atan2(dy, dx) - pose.yaw_rad
    horizontal = math.hypot(dx, dy)
    return FoodRelative(
        math.atan2(math.sin(heading_error), math.cos(heading_error)),
        math.atan2(-pose.z_mm, horizontal),
        math.hypot(horizontal, pose.z_mm),
    )


def _object_payload(payload: JsonObject, field: str) -> JsonObject:
    value = payload.get(field)
    if isinstance(value, dict):
        return value
    raise BridgeSmokeError(f"{field} must be an object")


def _int_payload(payload: JsonObject, field: str) -> int:
    value = payload.get(field)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise BridgeSmokeError(f"{field} must be an integer")


def _number(value: JsonValue, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise BridgeSmokeError(f"{field} must be a finite number")
    return float(value)


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))
