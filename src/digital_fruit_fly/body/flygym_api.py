from __future__ import annotations

import importlib
import importlib.metadata
import platform
from dataclasses import dataclass
from datetime import UTC, datetime
from types import ModuleType
from typing import Final, Sequence

from digital_fruit_fly.runtime.timeouts import JsonObject


UNSUPPORTED_FINE_ACTION_API: Final = "unsupported installed FlyGym fine-action API"
SCHEMA_VERSION: Final = 1
PROBOSCIS_LINKS: Final = frozenset(("rostrum", "haustellum"))
ANTENNA_LINKS: Final = frozenset(("pedicel", "funiculus", "arista"))
FRONT_LEG_PREFIXES: Final = frozenset(("lf_", "rf_"))


@dataclass(frozen=True, slots=True)
class ApiReportInputs:
    joint_dofs: tuple[str, ...]
    site_names: tuple[str, ...]
    controller_imports: tuple[str, ...]
    flygym_version: str
    mujoco_version: str
    python_version: str


@dataclass(frozen=True, slots=True)
class UnsupportedFineActionAPI(RuntimeError):
    missing: tuple[str, ...]

    def __str__(self) -> str:
        return f"{UNSUPPORTED_FINE_ACTION_API}: missing {', '.join(self.missing)}"


def build_installed_api_report(
    flygym_module: ModuleType, mujoco_module: ModuleType
) -> JsonObject:
    inputs = ApiReportInputs(
        joint_dofs=_installed_joint_dof_names(),
        site_names=_installed_site_names(),
        controller_imports=_available_controller_imports(),
        flygym_version=_package_version("flygym", flygym_module),
        mujoco_version=_package_version("mujoco", mujoco_module),
        python_version=platform.python_version(),
    )
    return build_report_from_names(inputs)


def build_report_from_names(inputs: ApiReportInputs) -> JsonObject:
    fine_action = _fine_action_support(inputs.joint_dofs, inputs.site_names)
    _raise_if_unsupported(fine_action)
    actuator_order = list(inputs.joint_dofs)
    site_order = list(inputs.site_names)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "environment": {
            "python": inputs.python_version,
            "platform": platform.platform(),
            "flygym": inputs.flygym_version,
            "mujoco": inputs.mujoco_version,
        },
        "imports": _imports_payload(inputs.controller_imports),
        "simulation": _simulation_payload(),
        "locomotion_controller": _controller_payload(inputs.controller_imports),
        "observation": _observation_payload(),
        "camera": _camera_payload(),
        "video": _video_payload(),
        "skeleton": {
            "skeleton_class": "flygym.anatomy.Skeleton",
            "joint_preset": "ALL_BIOLOGICAL",
            "axis_order": "PITCH_ROLL_YAW",
            "joint_dof_order": actuator_order,
            "site_order": site_order,
        },
        "actuators": {
            "actuator_type": "position",
            "actuator_type_import": "flygym.compose.fly.ActuatorType.POSITION",
            "order_source": "Skeleton(ALL_BIOLOGICAL).iter_jointdofs(c_thorax)",
            "position_actuator_order": actuator_order,
        },
        "joint_readout": {
            "method": "flygym.simulation.Simulation.get_joint_angles",
            "order_source": "fly.get_jointdofs_order()",
            "joint_dof_order": actuator_order,
        },
        "site_positions": {
            "supports_site_positions": fine_action["supports_site_positions"],
            "method": "flygym.simulation.Simulation.get_site_positions",
            "order_source": "fly.get_sites_order()",
            "site_order": site_order,
        },
        "fine_action_support": fine_action,
    }


def _installed_joint_dof_names() -> tuple[str, ...]:
    anatomy = importlib.import_module("flygym.anatomy")
    skeleton = anatomy.Skeleton(
        joint_preset=anatomy.JointPreset.ALL_BIOLOGICAL,
        axis_order=anatomy.AxisOrder.PITCH_ROLL_YAW,
    )
    return tuple(dof.name for dof in skeleton.iter_jointdofs("c_thorax"))


def _installed_site_names() -> tuple[str, ...]:
    anatomy = importlib.import_module("flygym.anatomy")
    skeleton = anatomy.Skeleton(
        joint_preset=anatomy.JointPreset.ALL_BIOLOGICAL,
        axis_order=anatomy.AxisOrder.PITCH_ROLL_YAW,
    )
    return tuple(joint.name for joint in skeleton.anatomical_joints)


def _available_controller_imports() -> tuple[str, ...]:
    candidates = (
        "flygym_demo.complex_terrain.cpg_controller.CPGController",
        "flygym_demo.complex_terrain.rule_based_controller.RuleBasedController",
        "flygym_demo.complex_terrain.hybrid_controller.HybridController",
        "flygym_demo.complex_terrain.turning_controller.HybridTurningController",
    )
    return tuple(path for path in candidates if _import_path_exists(path))


def _import_path_exists(path: str) -> bool:
    module_name, _, attr_name = path.rpartition(".")
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return False
    return hasattr(module, attr_name)


def _package_version(name: str, module: ModuleType) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return getattr(module, "__version__", "unknown")


def _fine_action_support(joint_dofs: Sequence[str], site_names: Sequence[str]) -> JsonObject:
    proboscis_dofs = _matching_dofs(joint_dofs, PROBOSCIS_LINKS)
    antenna_dofs = _matching_dofs(joint_dofs, ANTENNA_LINKS)
    front_leg_dofs = tuple(name for name in joint_dofs if _child_segment(name).startswith(tuple(FRONT_LEG_PREFIXES)))
    site_supported = len(site_names) > 0
    proboscis_links = {_child_link(name) for name in proboscis_dofs}
    return {
        "supports_proboscis_control": PROBOSCIS_LINKS.issubset(proboscis_links),
        "proboscis_dofs": list(proboscis_dofs),
        "supports_antenna_control": len(antenna_dofs) > 0,
        "antenna_dofs": list(antenna_dofs),
        "supports_front_leg_face_grooming": len(front_leg_dofs) > 0 and site_supported,
        "front_leg_face_grooming_dofs": list(front_leg_dofs),
        "supports_site_positions": site_supported,
    }


def _matching_dofs(joint_dofs: Sequence[str], links: frozenset[str]) -> tuple[str, ...]:
    return tuple(name for name in joint_dofs if _child_link(name) in links)


def _child_segment(joint_dof_name: str) -> str:
    parts = joint_dof_name.split("-")
    if len(parts) != 3:
        return ""
    return parts[1]


def _child_link(joint_dof_name: str) -> str:
    child = _child_segment(joint_dof_name)
    parts = child.split("_", maxsplit=1)
    if len(parts) != 2:
        return ""
    return parts[1]


def _raise_if_unsupported(fine_action: JsonObject) -> None:
    missing: list[str] = []
    for field in (
        "supports_proboscis_control",
        "supports_antenna_control",
        "supports_front_leg_face_grooming",
        "supports_site_positions",
    ):
        if fine_action[field] is not True:
            missing.append(field)
    if missing:
        raise UnsupportedFineActionAPI(tuple(missing))


def _imports_payload(controller_imports: Sequence[str]) -> JsonObject:
    return {
        "flygym": "flygym",
        "mujoco": "mujoco",
        "simulation_class": "flygym.simulation.Simulation",
        "fly_class": "flygym.compose.fly.Fly",
        "world_class": "flygym.compose.world.FlatGroundWorld",
        "skeleton_class": "flygym.anatomy.Skeleton",
        "renderer_class": "flygym.rendering.Renderer",
        "controller_imports": list(controller_imports),
    }


def _simulation_payload() -> JsonObject:
    return {
        "class": "flygym.simulation.Simulation",
        "step_method": "flygym.simulation.Simulation.step",
        "reset_method": "flygym.simulation.Simulation.reset",
        "actuator_input_method": "flygym.simulation.Simulation.set_actuator_inputs",
    }


def _controller_payload(controller_imports: Sequence[str]) -> JsonObject:
    return {
        "status": "demo_controllers_available" if controller_imports else "low_level_actuators_only",
        "controller_imports": list(controller_imports),
        "selected_control_surface": "flygym.simulation.Simulation.set_actuator_inputs",
    }


def _observation_payload() -> JsonObject:
    return {
        "joint_angles": "flygym.simulation.Simulation.get_joint_angles",
        "joint_velocities": "flygym.simulation.Simulation.get_joint_velocities",
        "body_positions": "flygym.simulation.Simulation.get_body_positions",
        "body_rotations": "flygym.simulation.Simulation.get_body_rotations",
        "ground_contact": "flygym.simulation.Simulation.get_ground_contact_info",
        "bodysegment_contact_forces": "flygym.simulation.Simulation.get_bodysegment_contact_forces",
        "site_positions": "flygym.simulation.Simulation.get_site_positions",
    }


def _camera_payload() -> JsonObject:
    return {
        "tracking_camera": "flygym.compose.fly.Fly.add_tracking_camera",
        "eye_camera": "flygym.compose.fly.Fly.add_vision",
        "renderer_attach": "flygym.simulation.Simulation.set_renderer",
        "frame_capture": "flygym.rendering.Renderer.render_as_needed",
        "interactive_viewer": "flygym.rendering.launch_interactive_viewer",
    }


def _video_payload() -> JsonObject:
    return {
        "buffer": "flygym.rendering.Renderer.frames",
        "save_video": "flygym.rendering.Renderer.save_video",
        "frame_writer": "flygym.utils.video.write_video_from_frames",
        "backend": "imageio.v3.imwrite",
    }
