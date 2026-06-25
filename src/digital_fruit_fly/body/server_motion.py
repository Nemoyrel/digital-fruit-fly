from __future__ import annotations

import math
import time
from typing import assert_never

from digital_fruit_fly.arena.dust import DustState, build_dust_config_from_runtime
from digital_fruit_fly.arena.model import FlyPose2D, Vector2D, build_arena_geometry_from_runtime
from digital_fruit_fly.body.controllers import (
    ArenaControllerSignals,
    BodyCommand,
    BodyControllerContract,
    BodyControllerFeedback,
    BodyControllerRequest,
    ControllerMode,
    DecodedControl,
    FoodDirection,
    LocomotionTarget,
    decoded_control_from_frame,
    select_body_command,
)
from digital_fruit_fly.bridge.messages import (
    SCHEMA_VERSION,
    BrainFrame,
    ControlFrame,
    SensoryFrame,
    payload_checksum,
)
from digital_fruit_fly.runtime.timeouts import JsonObject, JsonValue

from digital_fruit_fly.body.server_types import (
    BodyRunContext,
    BodyState,
    BrainReply,
    BodyServerRuntimeError,
    TickInputs,
    TickRecord,
)


def fixture_contract() -> BodyControllerContract:
    dofs = (
        "c_thorax-c_head-pitch",
        "c_thorax-c_head-yaw",
        "c_head-c_rostrum-pitch",
        "c_head-c_rostrum-yaw",
        "c_rostrum-c_haustellum-pitch",
        "c_rostrum-c_haustellum-yaw",
        "c_head-c_l_antenna-pedicel-yaw",
        "c_head-c_r_antenna-pedicel-yaw",
        "c_thorax-c_head-lf_coxa",
        "c_thorax-c_head-rf_coxa",
    )
    return BodyControllerContract(
        dofs,
        dofs[2:6],
        dofs[6:8],
        dofs[8:10],
        dofs[0:2],
        "fixture.HybridTurningController",
    )


def initial_state(context: BodyRunContext) -> BodyState:
    arena = build_arena_geometry_from_runtime(context.simulation.runtime.arena)
    return BodyState(
        pose=FlyPose2D(
            x_mm=arena.dimensions.width_mm * 0.18,
            y_mm=arena.dimensions.height_mm * 0.5,
            heading_rad=0.0,
        ),
        dust=DustState.clean(),
    )


def sensory_frame(context: BodyRunContext, state: BodyState, tick_index: int) -> SensoryFrame:
    arena = build_arena_geometry_from_runtime(context.simulation.runtime.arena)
    cue = arena.sample_sugar_cue(state.pose)
    food = food_direction(arena.vector_to_food(state.pose), state.pose)
    payload: JsonObject = {
        "sugar_grn": max(cue.left, cue.right),
        "left_mechanosensory": cue.left,
        "right_mechanosensory": cue.right,
        "dust_load": state.dust.dust_load,
        "food_contact": arena.is_food_contact(state.pose),
        "food_bearing_rad": food.bearing_rad,
        "food_elevation_rad": food.elevation_rad,
        "food_distance_mm": food.distance_mm,
        "pose_x_mm": state.pose.x_mm,
        "pose_y_mm": state.pose.y_mm,
        "pose_heading_rad": state.pose.heading_rad,
    }
    return SensoryFrame(
        SCHEMA_VERSION,
        context.config.output_dir.name,
        tick_index,
        tick_index * context.tick_seconds,
        time.monotonic(),
        payload,
        payload_checksum(payload),
    )


def control_frame(context: BodyRunContext, sensory: SensoryFrame, brain: BrainReply) -> ControlFrame:
    match brain:
        case ControlFrame():
            return brain
        case BrainFrame():
            payload = decode_brain_payload(context, sensory, brain)
            return ControlFrame(
                SCHEMA_VERSION,
                sensory.run_id,
                sensory.frame_index,
                sensory.simulation_time_s,
                time.monotonic(),
                payload,
                payload_checksum(payload),
            )
        case unreachable:
            assert_never(unreachable)


def apply_tick(context: BodyRunContext, inputs: TickInputs) -> TickRecord:
    runtime = context.simulation.runtime
    arena = build_arena_geometry_from_runtime(runtime.arena)
    control = decoded_control_from_frame(inputs.control)
    command = select_body_command(
        BodyControllerRequest(
            control=control,
            contract=context.simulation.contract,
            arena=ArenaControllerSignals(
                arena.is_food_contact(inputs.state.pose),
                inputs.state.dust.dust_load,
                control.food_direction,
            ),
            feedback=BodyControllerFeedback(face_distance_mm=0.5, antenna_distance_mm=0.4),
        )
    )
    clamped = arena.clamp_pose(step_pose(inputs.state.pose, command, context.tick_seconds))
    dust = inputs.state.dust.advance(
        build_dust_config_from_runtime(runtime.arena.dust),
        context.tick_seconds,
        command.mode == ControllerMode.GROOMING,
    )
    return TickRecord(
        BodyState(clamped.pose, dust.state),
        inputs.sensory,
        inputs.brain,
        inputs.control,
        command,
        clamped.collided,
        tuple(event.to_json_data() for event in dust.events),
    )


def trajectory_row(record: TickRecord) -> JsonObject:
    pose = record.state.pose
    return {
        "tick_index": record.sensory.frame_index,
        "simulation_time_s": record.sensory.simulation_time_s,
        "pose": {"x_mm": pose.x_mm, "y_mm": pose.y_mm, "heading_rad": pose.heading_rad},
        "collided": record.collided,
    }


def control_row(record: TickRecord) -> JsonObject:
    command = record.command
    return {
        "tick_index": record.sensory.frame_index,
        "mode": command.mode.value,
        "decoded_control": record.control.payload,
        "locomotion": {
            "forward_intensity": command.locomotion.forward_intensity,
            "turn_bias": command.locomotion.turn_bias,
            "brake": command.locomotion.brake,
        },
        "actuator_targets": dict(command.actuator_targets),
        "audit": command.audit,
    }


def arena_row(record: TickRecord) -> JsonObject:
    return {
        "tick_index": record.sensory.frame_index,
        "sensory": record.sensory.payload,
        "dust_events": list(record.dust_events),
    }


def decode_brain_payload(
    context: BodyRunContext, sensory: SensoryFrame, brain: BrainFrame
) -> JsonObject:
    rates = json_object(brain.payload, "rates_hz")
    forward = unit((rate(rates, "forward") - 8.0) / 40.0)
    feeding = unit((rate(rates, "feed") - 3.0) / 25.0)
    payload: JsonObject = {
        "forward": forward,
        "turn_bias": clamp(rate(rates, "turn") / 12.0, -1.0, 1.0),
        "feeding": feeding,
        "grooming": unit((rate(rates, "groom") - 1.0) / 30.0),
        "stop": unit((rate(rates, "stop") - 1.0) / 5.0),
        "proboscis_extension": feeding,
        "sweep_phase": (sensory.frame_index % 20) / 20.0,
    }
    if feeding >= context.simulation.runtime.decoder.feeding_threshold:
        payload["food_direction"] = {
            "bearing_rad": number(sensory.payload["food_bearing_rad"]),
            "elevation_rad": number(sensory.payload["food_elevation_rad"]),
            "distance_mm": number(sensory.payload["food_distance_mm"]),
        }
    return payload


def step_pose(pose: FlyPose2D, command: BodyCommand, tick_seconds: float) -> FlyPose2D:
    turn = command.locomotion.turn_bias * 2.0 * tick_seconds
    heading = math.atan2(math.sin(pose.heading_rad + turn), math.cos(pose.heading_rad + turn))
    distance = 1.2 * command.locomotion.forward_intensity * tick_seconds
    if command.locomotion.brake:
        return FlyPose2D(pose.x_mm, pose.y_mm, heading)
    return FlyPose2D(
        pose.x_mm + math.cos(heading) * distance,
        pose.y_mm + math.sin(heading) * distance,
        heading,
    )


def food_direction(vector: Vector2D, pose: FlyPose2D) -> FoodDirection:
    heading_error = math.atan2(vector.dy_mm, vector.dx_mm) - pose.heading_rad
    return FoodDirection(
        math.atan2(math.sin(heading_error), math.cos(heading_error)),
        0.0,
        math.hypot(vector.dx_mm, vector.dy_mm),
    )


def json_object(payload: JsonObject, key: str) -> JsonObject:
    value = payload.get(key)
    if isinstance(value, dict):
        return value
    raise BodyServerRuntimeError("malformed_brain_frame", f"{key} must be an object")


def rate(rates: JsonObject, key: str) -> float:
    return number(rates.get(key, 0.0))


def number(value: JsonValue) -> float:
    if isinstance(value, bool) or value is None or isinstance(value, (str, list, dict)):
        raise BodyServerRuntimeError("malformed_numeric_value", "expected numeric JSON value")
    return float(value)


def unit(value: JsonValue) -> float:
    return clamp(number(value), 0.0, 1.0)


def unit_rate(value: JsonValue) -> float:
    return max(0.0, number(value))


def stop_locomotion() -> LocomotionTarget:
    return LocomotionTarget(0.0, 0.0, True, "fixture.HybridTurningController")


def clamp(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)
