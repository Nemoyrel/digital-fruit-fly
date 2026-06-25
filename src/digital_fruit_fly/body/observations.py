from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from digital_fruit_fly.arena.model import ArenaGeometry, FlyPose2D
from digital_fruit_fly.body.observation_values import (
    MissingObservationField,
    ObservationValueError,
    RawObservationValue,
    json_bool,
    json_mapping,
    json_scalar,
    json_string_tuple,
    mean_abs,
    number,
    optional_scalars,
    optional_vectors,
    raw_mapping,
    read_named,
    required_raw,
    scalars,
    vector3,
)
from digital_fruit_fly.runtime.timeouts import JsonObject, JsonValue
HEAD_DOF_PREFIX: Final = "c_thorax-c_head-"
PROBOSCIS_SITE_LINKS: Final = frozenset(("rostrum", "haustellum"))
ANTENNA_SITE_LINKS: Final = frozenset(("pedicel", "funiculus", "arista"))
FRONT_LEG_PREFIXES: Final = ("lf_", "rf_")


@dataclass(frozen=True, slots=True)
class BodyObservationContract:
    joint_dof_order: tuple[str, ...]; site_order: tuple[str, ...]; proboscis_dofs: tuple[str, ...]; antenna_dofs: tuple[str, ...]; front_leg_dofs: tuple[str, ...]; head_dofs: tuple[str, ...]; verification_site_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BodyObservationRequest:
    raw: Mapping[str, RawObservationValue]; contract: BodyObservationContract; arena: ArenaGeometry


@dataclass(frozen=True, slots=True)
class BodyPose:
    x_mm: float; y_mm: float; z_mm: float; yaw_rad: float


@dataclass(frozen=True, slots=True)
class FoodRelative:
    bearing_rad: float; elevation_rad: float; distance_mm: float


@dataclass(frozen=True, slots=True)
class FineJointAngles:
    proboscis: JsonObject; antenna: JsonObject; front_leg: JsonObject; head: JsonObject


@dataclass(frozen=True, slots=True)
class BodyObservation:
    pose: BodyPose; food_contact: bool; food_relative: FoodRelative; ground_contact: JsonObject; contact_forces: JsonObject; proprioception: JsonObject; dust: JsonObject; joint_angles: FineJointAngles; site_positions: JsonObject


def build_observation_contract(api_report: Mapping[str, JsonValue]) -> BodyObservationContract:
    fine_action = json_mapping(api_report, "fine_action_support")
    joint_order = json_string_tuple(json_mapping(api_report, "joint_readout"), "joint_dof_order")
    site_order = json_string_tuple(json_mapping(api_report, "site_positions"), "site_order")
    return BodyObservationContract(
        joint_dof_order=joint_order,
        site_order=site_order,
        proboscis_dofs=_supported_names(fine_action, "supports_proboscis_control", "proboscis_dofs"),
        antenna_dofs=_supported_names(fine_action, "supports_antenna_control", "antenna_dofs"),
        front_leg_dofs=_supported_names(fine_action, "supports_front_leg_face_grooming", "front_leg_face_grooming_dofs"),
        head_dofs=tuple(name for name in joint_order if name.startswith(HEAD_DOF_PREFIX)),
        verification_site_names=tuple(name for name in site_order if _site_required(name)),
    )


def normalize_body_observation(request: BodyObservationRequest) -> BodyObservation:
    pose = _pose(raw_mapping(request.raw, "pose"))
    joints = required_raw(request.raw, "joint_angles", "joint_angles")
    sites = required_raw(request.raw, "site_positions", "site_positions")
    fly_pose = FlyPose2D(x_mm=pose.x_mm, y_mm=pose.y_mm, heading_rad=pose.yaw_rad)
    return BodyObservation(
        pose=pose,
        food_contact=request.arena.is_food_contact(fly_pose),
        food_relative=_food_relative(pose, request.arena),
        ground_contact=_ground_contact(request.raw.get("ground_contact")),
        contact_forces=_contact_forces(request.raw.get("bodysegment_contact_forces")),
        proprioception=_proprioception(request.raw, joints),
        dust=_dust(request.raw.get("dust")),
        joint_angles=_fine_angles(joints, request.contract),
        site_positions=_named_vectors(sites, request.contract.verification_site_names, request.contract.site_order, "site_positions"),
    )


def observation_to_json(observation: BodyObservation) -> str:
    try:
        return json.dumps(_observation_data(observation), allow_nan=False, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ObservationValueError("serialization", "json", str(exc)) from exc


def _observation_data(observation: BodyObservation) -> JsonObject:
    pose = observation.pose
    food = observation.food_relative
    angles = observation.joint_angles
    return {
        "pose": {"x_mm": pose.x_mm, "y_mm": pose.y_mm, "z_mm": pose.z_mm, "yaw_rad": pose.yaw_rad},
        "food_contact": observation.food_contact,
        "food_relative": {"bearing_rad": food.bearing_rad, "elevation_rad": food.elevation_rad, "distance_mm": food.distance_mm},
        "ground_contact": observation.ground_contact,
        "contact_forces": observation.contact_forces,
        "proprioception": observation.proprioception,
        "dust": observation.dust,
        "joint_angles": {"proboscis": angles.proboscis, "antenna": angles.antenna, "front_leg": angles.front_leg, "head": angles.head},
        "site_positions": observation.site_positions,
    }


def _fine_angles(readout: RawObservationValue, contract: BodyObservationContract) -> FineJointAngles:
    order = contract.joint_dof_order
    return FineJointAngles(
        proboscis=_named_scalars(readout, contract.proboscis_dofs, order, "proboscis_joint_angles"),
        antenna=_named_scalars(readout, contract.antenna_dofs, order, "antenna_joint_angles"),
        front_leg=_named_scalars(readout, contract.front_leg_dofs, order, "front_leg_joint_angles"),
        head=_named_scalars(readout, contract.head_dofs, order, "head_joint_angles"),
    )


def _supported_names(fine_action: Mapping[str, JsonValue], support_key: str, names_key: str) -> tuple[str, ...]:
    return json_string_tuple(fine_action, names_key) if json_bool(fine_action, support_key) else ()


def _site_required(name: str) -> bool:
    child = name.split("-")[-1]
    return (
        name == "c_thorax-c_head"
        or any(link in name for link in PROBOSCIS_SITE_LINKS | ANTENNA_SITE_LINKS)
        or child.startswith(FRONT_LEG_PREFIXES)
    )


def _pose(raw_pose: Mapping[str, RawObservationValue]) -> BodyPose:
    return BodyPose(
        x_mm=number(required_raw(raw_pose, "x_mm", "pose"), "pose", "x_mm"),
        y_mm=number(required_raw(raw_pose, "y_mm", "pose"), "pose", "y_mm"),
        z_mm=number(required_raw(raw_pose, "z_mm", "pose"), "pose", "z_mm"),
        yaw_rad=number(required_raw(raw_pose, "yaw_rad", "pose"), "pose", "yaw_rad"),
    )


def _food_relative(pose: BodyPose, arena: ArenaGeometry) -> FoodRelative:
    dx_mm = arena.food.center.x_mm - pose.x_mm
    dy_mm = arena.food.center.y_mm - pose.y_mm
    heading_error = math.atan2(dy_mm, dx_mm) - pose.yaw_rad
    horizontal = math.hypot(dx_mm, dy_mm)
    return FoodRelative(
        bearing_rad=math.atan2(math.sin(heading_error), math.cos(heading_error)),
        elevation_rad=math.atan2(-pose.z_mm, horizontal),
        distance_mm=math.hypot(horizontal, pose.z_mm),
    )


def _named_scalars(readout: RawObservationValue, names: tuple[str, ...], order: tuple[str, ...], category: str) -> JsonObject:
    missing: list[str] = []
    values: JsonObject = {}
    for name in names:
        item = read_named(readout, order, name)
        missing.append(name) if item is None else values.update({name: number(item, category, name)})
    if missing:
        raise MissingObservationField(category, tuple(missing))
    return values


def _named_vectors(readout: RawObservationValue, names: tuple[str, ...], order: tuple[str, ...], category: str) -> JsonObject:
    missing: list[str] = []
    values: JsonObject = {}
    for name in names:
        item = read_named(readout, order, name)
        missing.append(name) if item is None else values.update({name: vector3(name, item, category)})
    if missing:
        raise MissingObservationField(category, tuple(missing))
    return values


def _ground_contact(readout: RawObservationValue | None) -> JsonObject:
    values = optional_scalars(readout, "ground_contact")
    if len(values) == 0:
        return {}
    active = sum(1 for value in values if value > 0.0)
    return {"sample_count": float(len(values)), "active_count": float(active), "active_fraction": active / len(values)}


def _contact_forces(readout: RawObservationValue | None) -> JsonObject:
    vectors = optional_vectors(readout, "bodysegment_contact_forces")
    if len(vectors) == 0:
        return {}
    magnitudes = tuple(math.sqrt(sum(component * component for component in vector)) for vector in vectors)
    return {"sample_count": float(len(magnitudes)), "total_magnitude": sum(magnitudes), "max_magnitude": max(magnitudes)}


def _proprioception(raw: Mapping[str, RawObservationValue], joints: RawObservationValue) -> JsonObject:
    values: JsonObject = {"joint_angle_mean_abs": mean_abs(scalars(joints, "joint_angles"))}
    velocities = optional_scalars(raw.get("joint_velocities"), "joint_velocities")
    if velocities:
        values.update({"joint_velocity_mean_abs": mean_abs(velocities), "joint_velocity_max_abs": max(abs(value) for value in velocities)})
    return values


def _dust(readout: RawObservationValue | None) -> JsonObject:
    if readout is None:
        return {}
    if not isinstance(readout, Mapping):
        raise ObservationValueError("dust", "dust", "must be a mapping")
    return {name: json_scalar(value, "dust", name) for name, value in readout.items()}
