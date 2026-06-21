"""Reusable FlyGym body simulation wrapper for the L4 demo."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SceneMarker:
    name: str
    geom_type: str
    size: tuple[float, ...]
    pos: tuple[float, float, float]
    rgba: tuple[float, float, float, float]


@dataclass(frozen=True)
class BodyPose:
    time_s: float
    thorax_xyz_mm: tuple[float, float, float]
    heading_xy: tuple[float, float]


class FlyGymLocomotionBody:
    """Thin wrapper around FlyGym's locomotion controller and renderer."""

    def __init__(
        self,
        *,
        arena_half_size_mm: float,
        seed: int,
        scene_markers: list[SceneMarker] | None = None,
        camera_config: dict[str, Any] | None = None,
        colorize: bool = True,
    ) -> None:
        import numpy as np
        from flygym.anatomy import BodySegment
        from flygym.compose import FlatGroundWorld
        from flygym.simulation import Simulation
        from flygym.utils.math import Rotation3D
        from flygym_demo.complex_terrain import (
            HybridTurningController,
            make_locomotion_fly,
        )

        self._np = np
        self.BodySegment = BodySegment
        self.fly = make_locomotion_fly(name="nmf", colorize=colorize)
        self.camera = self._add_tracking_camera(camera_config or {})
        self.world = FlatGroundWorld(half_size=arena_half_size_mm)
        for marker in scene_markers or []:
            self.world.mjcf_root.worldbody.add(
                "geom",
                name=marker.name,
                type=marker.geom_type,
                size=marker.size,
                pos=marker.pos,
                rgba=marker.rgba,
                contype=0,
                conaffinity=0,
            )
        self.world.add_fly(
            self.fly,
            spawn_position=(0, 0, 0.8),
            spawn_rotation=Rotation3D("quat", (1, 0, 0, 0)),
        )
        self.sim = Simulation(self.world)
        self.controller = HybridTurningController(timestep=self.sim.timestep)
        self.controller.reset(seed=seed)
        body_order = self.fly.get_bodysegs_order()
        self.thorax_idx = body_order.index(BodySegment("c_thorax"))

    def _add_tracking_camera(self, camera_config: dict[str, Any]):
        camera_kwargs: dict[str, Any] = {}
        if "pos_offset" in camera_config:
            camera_kwargs["pos_offset"] = tuple(camera_config["pos_offset"])
        if "fovy" in camera_config:
            camera_kwargs["fovy"] = float(camera_config["fovy"])
        return self.fly.add_tracking_camera(**camera_kwargs)

    @property
    def timestep(self) -> float:
        return float(self.sim.timestep)

    @property
    def fly_name(self) -> str:
        return self.fly.name

    def setup_renderer(self, render_config: dict[str, Any]) -> None:
        self.sim.set_renderer(
            self.camera,
            camera_res=tuple(render_config["camera_res"]),
            playback_speed=float(render_config["playback_speed"]),
            output_fps=int(render_config["output_fps"]),
        )

    def warmup(self, duration_s: float) -> None:
        self.sim.warmup(duration_s=duration_s)

    def pose(self) -> BodyPose:
        body_id = self.sim._internal_bodyids_by_fly[self.fly.name][self.thorax_idx]
        thorax_xyz = self.sim.get_body_positions(self.fly.name)[self.thorax_idx]
        thorax_xmat = self.sim.mj_data.xmat[body_id].reshape(3, 3)
        heading_xy = thorax_xmat[:, 0][:2]
        norm = self._np.linalg.norm(heading_xy)
        if norm <= 1e-9:
            heading = (1.0, 0.0)
        else:
            heading = (float(heading_xy[0] / norm), float(heading_xy[1] / norm))
        return BodyPose(
            time_s=float(self.sim.mj_data.time),
            thorax_xyz_mm=(
                float(thorax_xyz[0]),
                float(thorax_xyz[1]),
                float(thorax_xyz[2]),
            ),
            heading_xy=heading,
        )

    def apply_descending_drive(self, left: float, right: float):
        import numpy as np
        from flygym_demo.complex_terrain import apply_locomotion_action

        action = self.controller.step(
            np.array([left, right], dtype=float), self.sim, self.fly.name
        )
        apply_locomotion_action(self.sim, self.fly.name, action)
        return action

    def step(self, *, render: bool) -> None:
        self.sim.step()
        if render:
            self.sim.render_as_needed()

    def save_video(self, path: Path) -> None:
        self.sim.renderer.save_video(path)

    def close(self) -> None:
        self.sim.close()


def make_scene_markers(scene_config: dict[str, Any]) -> list[SceneMarker]:
    food_x, food_y = scene_config["food_position_mm"]
    food_radius = float(scene_config["food_contact_radius_mm"])
    cue_radius = float(scene_config["food_cue_radius_mm"])
    return [
        SceneMarker(
            name="l4_food_marker",
            geom_type="sphere",
            size=(0.26,),
            pos=(food_x, food_y, 0.26),
            rgba=(0.9, 0.1, 0.05, 1.0),
        ),
        SceneMarker(
            name="l4_food_contact_radius",
            geom_type="cylinder",
            size=(food_radius, 0.01),
            pos=(food_x, food_y, 0.012),
            rgba=(0.9, 0.15, 0.05, 0.18),
        ),
        SceneMarker(
            name="l4_food_cue_radius",
            geom_type="cylinder",
            size=(cue_radius, 0.006),
            pos=(food_x, food_y, 0.008),
            rgba=(0.9, 0.6, 0.05, 0.06),
        ),
    ]
