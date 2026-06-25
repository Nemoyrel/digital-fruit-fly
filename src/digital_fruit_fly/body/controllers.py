from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Final, assert_never

from digital_fruit_fly.bridge.messages import ControlFrame
from digital_fruit_fly.runtime.timeouts import JsonObject, JsonValue


MAX_PROBOSCIS_YAW_RAD: Final = 0.75; MAX_PROBOSCIS_PITCH_RAD: Final = 0.55
TARGET_FACE_DISTANCE_MM: Final = 0.25; TARGET_ANTENNA_DISTANCE_MM: Final = 0.2


@unique
class ControllerMode(StrEnum):
    STOP = "stop"
    LOCOMOTION = "locomotion"
    FEEDING = "feeding"
    GROOMING = "grooming"


@dataclass(frozen=True, slots=True)
class FoodDirection:
    bearing_rad: float; elevation_rad: float; distance_mm: float


@dataclass(frozen=True, slots=True)
class DecodedControl:
    forward: float = 0.0; turn_bias: float = 0.0; feeding: float = 0.0; grooming: float = 0.0
    stop: float = 0.0; proboscis_extension: float = 0.0; sweep_phase: float = 0.0
    food_direction: FoodDirection | None = None


@dataclass(frozen=True, slots=True)
class ArenaControllerSignals:
    food_contact: bool = False; dust_load: float = 0.0; food_direction: FoodDirection | None = None


@dataclass(frozen=True, slots=True)
class BodyControllerFeedback:
    proboscis_yaw_rad: float | None = None; proboscis_pitch_rad: float | None = None
    face_distance_mm: float | None = None; antenna_distance_mm: float | None = None


@dataclass(frozen=True, slots=True)
class ControllerPriority:
    mode_order: tuple[ControllerMode, ...] = (ControllerMode.STOP, ControllerMode.GROOMING, ControllerMode.FEEDING, ControllerMode.LOCOMOTION)
    threshold: float = 0.5


@dataclass(frozen=True, slots=True)
class BodyControllerContract:
    actuator_dofs: tuple[str, ...]; proboscis_dofs: tuple[str, ...]; antenna_dofs: tuple[str, ...]
    front_leg_dofs: tuple[str, ...]; head_dofs: tuple[str, ...]; locomotion_controller_import_path: str


@dataclass(frozen=True, slots=True)
class BodyControllerRequest:
    control: DecodedControl; contract: BodyControllerContract; config: ControllerPriority = ControllerPriority()
    arena: ArenaControllerSignals = ArenaControllerSignals(); feedback: BodyControllerFeedback = BodyControllerFeedback()


@dataclass(frozen=True, slots=True)
class LocomotionTarget:
    forward_intensity: float; turn_bias: float; brake: bool; controller_import_path: str


@dataclass(frozen=True, slots=True)
class BodyCommand:
    mode: ControllerMode; actuator_targets: Mapping[str, float]; locomotion: LocomotionTarget; audit: JsonObject


@dataclass(frozen=True, slots=True)
class MissingFoodDirection(RuntimeError):
    feeding_intensity: float

    def __str__(self) -> str:
        return f"directional feeding requires food_relative direction at intensity {self.feeding_intensity}"


@dataclass(frozen=True, slots=True)
class MalformedControlFrame(ValueError):
    field: str; reason: str

    def __str__(self) -> str:
        return f"control frame {self.field}: {self.reason}"


def build_controller_contract(api_report: Mapping[str, JsonValue]) -> BodyControllerContract:
    fine_action = _json_mapping(api_report, "fine_action_support")
    actuators = _json_mapping(api_report, "actuators")
    locomotion = _json_mapping(api_report, "locomotion_controller")
    actuator_dofs = _string_tuple(actuators, "position_actuator_order")
    return BodyControllerContract(
        actuator_dofs=actuator_dofs,
        proboscis_dofs=_string_tuple(fine_action, "proboscis_dofs"),
        antenna_dofs=_string_tuple(fine_action, "antenna_dofs"),
        front_leg_dofs=_string_tuple(fine_action, "front_leg_face_grooming_dofs"),
        head_dofs=tuple(name for name in actuator_dofs if name.startswith("c_thorax-c_head-")),
        locomotion_controller_import_path=_turning_controller_import(_string_tuple(locomotion, "controller_imports")),
    )


def decoded_control_from_frame(frame: ControlFrame) -> DecodedControl:
    return decoded_control_from_payload(frame.payload)


def decoded_control_from_payload(payload: Mapping[str, JsonValue]) -> DecodedControl:
    return DecodedControl(
        forward=_number_field(payload, "forward"),
        turn_bias=_number_field(payload, "turn_bias"),
        feeding=_number_field(payload, "feeding"),
        grooming=_number_field(payload, "grooming"),
        stop=_number_field(payload, "stop"),
        proboscis_extension=_number_field(payload, "proboscis_extension"),
        sweep_phase=_number_field(payload, "sweep_phase"),
        food_direction=_optional_food_direction(payload),
    )


def select_body_command(request: BodyControllerRequest) -> BodyCommand:
    selected, active = _select_mode(request.control, request.config)
    audit = {"selection": _selection_audit(selected, active, request)}  # type: JsonObject
    match selected:
        case ControllerMode.STOP:
            return _stop_command(request, audit)
        case ControllerMode.LOCOMOTION:
            return _locomotion_command(request, audit)
        case ControllerMode.FEEDING:
            return _feeding_command(request, audit)
        case ControllerMode.GROOMING:
            return _grooming_command(request, audit)
        case unreachable:
            assert_never(unreachable)


def _stop_command(request: BodyControllerRequest, audit: JsonObject) -> BodyCommand:
    audit["stop"] = {"zeroed_actuator_count": len(request.contract.actuator_dofs), "brake": True}
    return BodyCommand(
        mode=ControllerMode.STOP,
        actuator_targets={name: 0.0 for name in request.contract.actuator_dofs},
        locomotion=LocomotionTarget(0.0, 0.0, True, request.contract.locomotion_controller_import_path),
        audit=audit,
    )


def _locomotion_command(request: BodyControllerRequest, audit: JsonObject) -> BodyCommand:
    forward = _clamp(request.control.forward, 0.0, 1.0)
    turn_bias = _clamp(request.control.turn_bias, -1.0, 1.0)
    audit["locomotion"] = {"forward_intensity": forward, "turn_bias": turn_bias}
    return BodyCommand(
        mode=ControllerMode.LOCOMOTION,
        actuator_targets={},
        locomotion=LocomotionTarget(forward, turn_bias, False, request.contract.locomotion_controller_import_path),
        audit=audit,
    )


def _feeding_command(request: BodyControllerRequest, audit: JsonObject) -> BodyCommand:
    direction = request.control.food_direction
    if direction is None:
        raise MissingFoodDirection(request.control.feeding)
    intensity = _clamp(request.control.feeding, 0.0, 1.0)
    extension = _clamp(request.control.proboscis_extension, 0.0, 1.0) * intensity
    yaw = _clamp(direction.bearing_rad, -MAX_PROBOSCIS_YAW_RAD, MAX_PROBOSCIS_YAW_RAD) * intensity
    pitch = _clamp(direction.elevation_rad, -MAX_PROBOSCIS_PITCH_RAD, MAX_PROBOSCIS_PITCH_RAD) * intensity
    supported = frozenset(request.contract.actuator_dofs)
    candidates = (
        ("c_thorax-c_head-pitch", pitch * 0.25),
        ("c_thorax-c_head-yaw", yaw * 0.25),
        ("c_head-c_rostrum-pitch", pitch + 0.35 * extension),
        ("c_head-c_rostrum-yaw", yaw),
        ("c_rostrum-c_haustellum-pitch", pitch * 0.5 + 0.55 * extension),
        ("c_rostrum-c_haustellum-yaw", yaw * 0.55),
    )
    targets = {name: value for name, value in candidates if name in supported}
    audit["feeding"] = {
        "food_direction": {
            "bearing_rad": direction.bearing_rad,
            "elevation_rad": direction.elevation_rad,
            "distance_mm": direction.distance_mm,
        },
        "target_proboscis_direction": {
            "yaw_rad": yaw,
            "pitch_rad": pitch,
            "yaw_sign": _sign_label(yaw),
            "extension": extension,
        },
        "measured_proboscis_direction": {
            "yaw_rad": request.feedback.proboscis_yaw_rad,
            "pitch_rad": request.feedback.proboscis_pitch_rad,
        },
    }
    return BodyCommand(
        mode=ControllerMode.FEEDING,
        actuator_targets=targets,
        locomotion=LocomotionTarget(0.0, 0.0, False, request.contract.locomotion_controller_import_path),
        audit=audit,
    )


def _grooming_command(request: BodyControllerRequest, audit: JsonObject) -> BodyCommand:
    intensity = _clamp(request.control.grooming, 0.0, 1.0)
    sweep = math.sin((request.control.sweep_phase % 1.0) * math.tau)
    targets = {
        name: _grooming_target(name, intensity, sweep)
        for name in request.contract.front_leg_dofs + request.contract.antenna_dofs + request.contract.head_dofs
    }
    audit["grooming"] = {
        "target_face_distance_mm": TARGET_FACE_DISTANCE_MM,
        "target_antenna_distance_mm": TARGET_ANTENNA_DISTANCE_MM,
        "measured_face_distance_mm": request.feedback.face_distance_mm,
        "measured_antenna_distance_mm": request.feedback.antenna_distance_mm,
        "sweep_phase": request.control.sweep_phase,
    }
    return BodyCommand(
        mode=ControllerMode.GROOMING,
        actuator_targets=targets,
        locomotion=LocomotionTarget(0.0, 0.0, False, request.contract.locomotion_controller_import_path),
        audit=audit,
    )


def _select_mode(control: DecodedControl, config: ControllerPriority) -> tuple[ControllerMode, tuple[ControllerMode, ...]]:
    active = tuple(mode for mode in config.mode_order if _mode_intensity(mode, control) >= config.threshold)
    return (ControllerMode.STOP, active) if len(active) == 0 else (active[0], active)


def _mode_intensity(mode: ControllerMode, control: DecodedControl) -> float:
    match mode:
        case ControllerMode.STOP:
            return control.stop
        case ControllerMode.GROOMING:
            return control.grooming
        case ControllerMode.FEEDING:
            return control.feeding
        case ControllerMode.LOCOMOTION:
            return max(control.forward, abs(control.turn_bias))
        case unreachable:
            assert_never(unreachable)


def _selection_audit(selected: ControllerMode, active: tuple[ControllerMode, ...], request: BodyControllerRequest) -> JsonObject:
    return {
        "selected_mode": selected.value,
        "active_modes": [mode.value for mode in active],
        "conflict_modes": [mode.value for mode in active] if len(active) > 1 else [],
        "priority_order": [mode.value for mode in request.config.mode_order],
        "tie_break": "configured_priority" if len(active) > 1 else "none",
        "arena_state_used_for_mode": False,
        "arena": {
            "food_contact": request.arena.food_contact,
            "dust_load": request.arena.dust_load,
            "food_direction_available": request.arena.food_direction is not None,
        },
    }


def _grooming_target(name: str, intensity: float, sweep: float) -> float:
    side = 1.0 if "-lf_" in name or "-l_" in name else -1.0 if "-rf_" in name or "-r_" in name else 0.0
    if name.endswith("-yaw"):
        return side * 0.35 * intensity * sweep
    if name.endswith("-roll"):
        return side * 0.2 * intensity
    if name.endswith("-pitch"):
        return 0.35 * intensity + 0.12 * intensity * abs(sweep)
    return 0.0
def _turning_controller_import(imports: tuple[str, ...]) -> str:
    turning = tuple(path for path in imports if "TurningController" in path)
    if len(turning) > 0:
        return turning[0]
    return imports[0] if len(imports) > 0 else ""


def _optional_food_direction(payload: Mapping[str, JsonValue]) -> FoodDirection | None:
    value = payload.get("food_relative")
    if value is None:
        return None
    if not isinstance(value, dict):
        raise MalformedControlFrame("food_relative", "must be an object")
    return FoodDirection(_number_field(value, "bearing_rad"), _number_field(value, "elevation_rad"), _number_field(value, "distance_mm"))


def _number_field(payload: Mapping[str, JsonValue], field: str) -> float:
    value = payload.get(field, 0.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise MalformedControlFrame(field, "must be a finite number")
    return float(value)


def _json_mapping(raw: Mapping[str, JsonValue], key: str) -> Mapping[str, JsonValue]:
    value = raw.get(key)
    if isinstance(value, dict):
        return value
    raise MalformedControlFrame(key, "must be an object")


def _string_tuple(raw: Mapping[str, JsonValue], key: str) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise MalformedControlFrame(key, "must be a list of strings")
    return tuple(value)


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))


def _sign_label(value: float) -> str:
    return "positive" if value > 0.0 else "negative" if value < 0.0 else "zero"
