"""FlyGym 果蝇身体封装：运动 / 梳理 / 进食三种动作 + 位姿 + 渲染。

``flygym`` / ``flygym_demo`` 仅在方法内部惰性导入，因此导入本包不需要 flygym_env。

身体模型为 ``make_locomotion_fly`` 构建的 legs-only 果蝇（只有腿部 DoF 被驱动，
没有喙/触角 DoF）。三种动作的实现：
- 运动 FORAGING：``HybridTurningController`` 接收下行驱动 [left, right] 行走/转向。
- 梳理 GROOMING：停步（驱动≈0），抬起两条前腿并高频对搓（覆写前腿关节角 + 关闭前腿吸附）。
- 进食 FEEDING：停步并在食物处做缓慢的前腿/低头摆动，表现取食。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class BodyPose:
    time_s: float
    thorax_xyz_mm: tuple[float, float, float]
    heading_xy: tuple[float, float]


@dataclass(frozen=True)
class BodyAction:
    mean_joint_angle_rad: float
    adhesion_on_count: int


class FlyGymBody:
    """封装 FlyGym 世界 / 控制器 / 渲染器，并提供三种动作驱动。"""

    def __init__(
        self,
        *,
        scene: dict,
        seed: int,
        camera_config: dict[str, Any] | None = None,
        dust_count: int = 220,
        colorize: bool = True,
    ) -> None:
        from flygym.anatomy import BodySegment
        from flygym.compose import FlatGroundWorld
        from flygym.simulation import Simulation
        from flygym.utils.math import Rotation3D
        from flygym_demo.complex_terrain import (
            HybridTurningController,
            get_default_locomotion_dof_order,
            make_locomotion_fly,
        )

        from .arena import populate_arena

        self._BodySegment = BodySegment
        self.scene = scene
        self.fly = make_locomotion_fly(name="nmf", colorize=colorize)
        self.camera = self._add_tracking_camera(camera_config or {})

        half = float(scene["arena_half_size_mm"])
        self.world = FlatGroundWorld(half_size=half)
        self.arena_info = populate_arena(
            self.world, scene, dust_count=dust_count, dust_seed=int(seed) + 3
        )
        self.world.add_fly(
            self.fly,
            spawn_position=(0.0, 0.0, 0.8),
            spawn_rotation=Rotation3D("quat", (1, 0, 0, 0)),
        )
        self.sim = Simulation(self.world)
        self.controller = HybridTurningController(timestep=self.sim.timestep)
        self.controller.reset(seed=int(seed))

        body_order = self.fly.get_bodysegs_order()
        self.thorax_idx = body_order.index(BodySegment("c_thorax"))

        # 前腿 DoF 索引（与 action.joint_angles 同序）及其链节/侧别
        self._dofs = get_default_locomotion_dof_order()
        self._front_idx = [
            i for i, d in enumerate(self._dofs) if d.child.pos in ("lf", "rf")
        ]
        self._front_link = {i: self._dofs[i].child.link for i in self._front_idx}
        self._front_side = {i: self._dofs[i].child.pos for i in self._front_idx}
        # 前腿在 6 腿吸附数组中的位置（顺序 = LEGS = lf,lm,lh,rf,rm,rh）
        self._front_leg_adhesion_idx = [0, 3]
        self._renderer_ready = False

    def _add_tracking_camera(self, camera_config: dict[str, Any]):
        kwargs: dict[str, Any] = {}
        if "pos_offset" in camera_config:
            kwargs["pos_offset"] = tuple(camera_config["pos_offset"])
        if "fovy" in camera_config:
            kwargs["fovy"] = float(camera_config["fovy"])
        return self.fly.add_tracking_camera(**kwargs)

    # ---- lifecycle ----
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
            playback_speed=float(render_config.get("playback_speed", 1.0)),
            output_fps=int(render_config.get("output_fps", 30)),
        )
        self._renderer_ready = True

    def warmup(self, duration_s: float) -> None:
        self.sim.warmup(duration_s=duration_s)

    def close(self) -> None:
        self.sim.close()

    # ---- state ----
    def pose(self) -> BodyPose:
        body_id = self.sim._internal_bodyids_by_fly[self.fly.name][self.thorax_idx]
        thorax_xyz = self.sim.get_body_positions(self.fly.name)[self.thorax_idx]
        xmat = self.sim.mj_data.xmat[body_id].reshape(3, 3)
        heading_xy = xmat[:, 0][:2]
        norm = float(np.linalg.norm(heading_xy))
        if norm <= 1e-9:
            heading = (1.0, 0.0)
        else:
            heading = (float(heading_xy[0] / norm), float(heading_xy[1] / norm))
        return BodyPose(
            time_s=float(self.sim.mj_data.time),
            thorax_xyz_mm=(float(thorax_xyz[0]), float(thorax_xyz[1]), float(thorax_xyz[2])),
            heading_xy=heading,
        )

    # ---- behaviors ----
    def _apply(self, action) -> BodyAction:
        from flygym_demo.complex_terrain import apply_locomotion_action

        apply_locomotion_action(self.sim, self.fly.name, action)
        adh = 0 if action.adhesion_onoff is None else int(np.sum(action.adhesion_onoff))
        return BodyAction(
            mean_joint_angle_rad=float(np.mean(action.joint_angles)),
            adhesion_on_count=adh,
        )

    def _walk(self, left: float, right: float) -> BodyAction:
        action = self.controller.step(np.array([left, right], dtype=float), self.sim, self.fly.name)
        return self._apply(action)

    def _front_leg_override(self, time_s: float, *, lift: dict[str, float], amp: dict[str, float], freq: float, lift_front_legs: bool) -> BodyAction:
        action = self.controller.step(np.array([0.0, 0.0]), self.sim, self.fly.name)
        for i in self._front_idx:
            link = self._front_link[i]
            side_phase = 0.0 if self._front_side[i] == "lf" else np.pi
            osc = np.sin(2.0 * np.pi * freq * time_s + side_phase)
            action.joint_angles[i] += lift.get(link, 0.0) + amp.get(link, 0.0) * osc
        if lift_front_legs and action.adhesion_onoff is not None:
            for k in self._front_leg_adhesion_idx:
                action.adhesion_onoff[k] = False
        return self._apply(action)

    def _groom(self, time_s: float) -> BodyAction:
        # 抬起前腿快速对搓
        return self._front_leg_override(
            time_s,
            lift={"coxa": 0.5, "trochanterfemur": 0.9, "tibia": -0.6, "tarsus1": -0.3},
            amp={"coxa": 0.15, "trochanterfemur": 0.35, "tibia": 0.5, "tarsus1": 0.2},
            freq=7.0,
            lift_front_legs=True,
        )

    def _feed(self, time_s: float) -> BodyAction:
        # 停在食物处，前腿向前下方缓慢摆动表现取食
        return self._front_leg_override(
            time_s,
            lift={"coxa": 0.25, "trochanterfemur": 0.35, "tibia": -0.2, "tarsus1": 0.0},
            amp={"coxa": 0.05, "trochanterfemur": 0.12, "tibia": 0.15, "tarsus1": 0.05},
            freq=2.5,
            lift_front_legs=False,
        )

    def apply_behavior(self, behavior: str, left: float, right: float, time_s: float) -> BodyAction:
        if behavior == "grooming":
            return self._groom(time_s)
        if behavior == "feeding":
            return self._feed(time_s)
        return self._walk(left, right)

    # ---- stepping / frames ----
    def step(self, *, render: bool) -> bool:
        self.sim.step()
        if render and self._renderer_ready:
            return self.sim.render_as_needed()
        return False

    def body_frames(self) -> list[np.ndarray]:
        if not self._renderer_ready or self.sim.renderer is None:
            return []
        frames = self.sim.renderer.frames
        cam_name = next(iter(frames.keys()))
        return frames[cam_name]

    def save_body_video(self, path: Path) -> None:
        self.sim.renderer.save_video(path)
