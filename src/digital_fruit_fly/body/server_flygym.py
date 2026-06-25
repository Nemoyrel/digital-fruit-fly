from __future__ import annotations

import importlib.metadata
import os
from dataclasses import dataclass
from types import ModuleType
from typing import TYPE_CHECKING

from digital_fruit_fly.body.controllers import BodyCommand, BodyControllerContract
from digital_fruit_fly.body.server_types import BodyServerRuntimeError
from digital_fruit_fly.runtime.timeouts import JsonObject

if TYPE_CHECKING:
    from flygym import Simulation
    from flygym.compose.fly import ActuatorType, Fly

FLY_NAME = "nmf"
BACKEND_NAME = "FlyGym/NeuroMechFly live Simulation position-actuator stepping"


@dataclass(slots=True)
class FlyGymBodyRuntime:
    """Mutable wrapper around a live FlyGym simulation step counter."""

    fly: Fly
    simulation: Simulation
    actuator_type: ActuatorType
    actuator_order: tuple[str, ...]
    site_count: int
    body_count: int
    flygym_version: str
    mujoco_version: str
    step_count: int = 0

    @property
    def contract(self) -> BodyControllerContract:
        return BodyControllerContract(
            actuator_dofs=self.actuator_order,
            proboscis_dofs=_matching_dofs(self.actuator_order, ("rostrum", "haustellum")),
            antenna_dofs=_matching_dofs(self.actuator_order, ("pedicel", "funiculus", "arista")),
            front_leg_dofs=tuple(
                name
                for name in self.actuator_order
                if _child_segment(name).startswith(("lf_", "rf_"))
            ),
            head_dofs=tuple(name for name in self.actuator_order if name.startswith("c_thorax-c_head-")),
            locomotion_controller_import_path="flygym.simulation.Simulation.set_actuator_inputs",
        )

    def reset(self) -> None:
        self.simulation.reset()
        self.step_count = 0

    def step(self, command: BodyCommand) -> JsonObject:
        numpy = _numpy()
        targets = numpy.zeros(len(self.actuator_order), dtype=float)
        for index, name in enumerate(self.actuator_order):
            value = command.actuator_targets.get(name)
            if value is not None:
                targets[index] = float(value)
        self.simulation.set_actuator_inputs(FLY_NAME, self.actuator_type, targets)
        self.simulation.step()
        self.step_count += 1
        return self._observation(command)

    def summary(self) -> JsonObject:
        return {
            "live": True,
            "backend": BACKEND_NAME,
            "fly_name": FLY_NAME,
            "flygym_version": self.flygym_version,
            "mujoco_version": self.mujoco_version,
            "simulation_class": "flygym.simulation.Simulation",
            "world_class": "flygym.compose.world.FlatGroundWorld",
            "fly_class": "flygym.compose.fly.Fly",
            "joint_preset": "ALL_BIOLOGICAL",
            "axis_order": "PITCH_ROLL_YAW",
            "actuator_type": "POSITION",
            "actuator_count": len(self.actuator_order),
            "site_count": self.site_count,
            "body_count": self.body_count,
            "model_nq": int(self.simulation.mj_model.nq),
            "model_nv": int(self.simulation.mj_model.nv),
            "model_nu": int(self.simulation.mj_model.nu),
            "live_step_count": self.step_count,
            "model_time_s": float(self.simulation.mj_data.time),
            "timestep_s": float(self.simulation.timestep),
        }

    def close(self) -> None:
        self.simulation.close()

    def _observation(self, command: BodyCommand) -> JsonObject:
        joint_angles = self.simulation.get_joint_angles(FLY_NAME)
        site_positions = self.simulation.get_site_positions(FLY_NAME)
        body_positions = self.simulation.get_body_positions(FLY_NAME)
        thorax = body_positions[0]
        return {
            "backend": BACKEND_NAME,
            "step_index": self.step_count - 1,
            "live_step_count": self.step_count,
            "model_time_s": float(self.simulation.mj_data.time),
            "model_nq": int(self.simulation.mj_model.nq),
            "model_nv": int(self.simulation.mj_model.nv),
            "model_nu": int(self.simulation.mj_model.nu),
            "actuator_count": len(self.actuator_order),
            "commanded_actuator_count": len(command.actuator_targets),
            "joint_angles_shape": [int(size) for size in joint_angles.shape],
            "site_positions_shape": [int(size) for size in site_positions.shape],
            "body_positions_shape": [int(size) for size in body_positions.shape],
            "thorax_position_mm": [float(value) for value in thorax],
        }


def open_flygym_runtime() -> FlyGymBodyRuntime:
    try:
        _set_headless_env()
        runtime = _build_runtime()
    except Exception as exc:  # noqa: BLE001 - external FlyGym init failures must become artifacts.
        message = f"{type(exc).__name__}: {exc}"
        raise BodyServerRuntimeError("flygym_initialization_failed", message) from exc
    runtime.reset()
    return runtime


def _build_runtime() -> FlyGymBodyRuntime:
    from flygym import Simulation
    from flygym.anatomy import AxisOrder, JointPreset, Skeleton
    from flygym.compose.fly import ActuatorType, Fly
    from flygym.compose.world import FlatGroundWorld
    from flygym.utils.math import Rotation3D

    fly = Fly(name=FLY_NAME)
    skeleton = Skeleton(
        joint_preset=JointPreset.ALL_BIOLOGICAL,
        axis_order=AxisOrder.PITCH_ROLL_YAW,
    )
    fly.add_joints(skeleton)
    fly.add_joint_sites(skeleton.anatomical_joints)
    fly.add_actuators(fly.get_jointdofs_order(), ActuatorType.POSITION)
    world = FlatGroundWorld()
    world.add_fly(
        fly,
        spawn_position=(0, 0, 0.2),
        spawn_rotation=Rotation3D("quat", (1, 0, 0, 0)),
    )
    simulation = Simulation(world)
    return FlyGymBodyRuntime(
        fly=fly,
        simulation=simulation,
        actuator_type=ActuatorType.POSITION,
        actuator_order=tuple(dof.name for dof in fly.get_actuated_jointdofs_order(ActuatorType.POSITION)),
        site_count=len(fly.get_sites_order()),
        body_count=len(fly.get_bodysegs_order()),
        flygym_version=_package_version("flygym"),
        mujoco_version=_package_version("mujoco"),
    )


def _set_headless_env() -> None:
    cache_root = os.environ.get("DIGITAL_FRUIT_FLY_CACHE_DIR", "/private/tmp/digital_fruit_fly_body_server")
    os.makedirs(cache_root, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", os.path.join(cache_root, "matplotlib"))
    os.environ.setdefault("XDG_CACHE_HOME", os.path.join(cache_root, "xdg"))
    os.environ.setdefault("NUMBA_CACHE_DIR", os.path.join(cache_root, "numba"))
    for key in ("MPLCONFIGDIR", "XDG_CACHE_HOME", "NUMBA_CACHE_DIR"):
        os.makedirs(os.environ[key], exist_ok=True)
    os.environ["GLFW_PLATFORM"] = "null"
    os.environ["MUJOCO_GL"] = "glfw"
    import glfw

    glfw.init_hint(glfw.PLATFORM, glfw.PLATFORM_NULL)


def _numpy() -> ModuleType:
    import numpy

    return numpy


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _matching_dofs(joint_dofs: tuple[str, ...], links: tuple[str, ...]) -> tuple[str, ...]:
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
