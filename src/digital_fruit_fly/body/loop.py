"""具身主循环：observe → 脑(IPC) → DN 解码 → 身体动作 → 渲染(身体帧+脑活动帧) → 写产物。

每 15ms 同步窗向脑查询一次（脑较慢，~140ms/窗），窗内物理步复用上次决策。
渲染时把脑活动面板与身体相机帧逐帧并排合成「左身体、右脑」视频。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from ..bridge.ipc import JsonLineClient
from ..bridge.messages import SensoryMessage
from ..viz.brain_panel import BrainPanelRenderer
from ..viz.compositor import hstack_frame, write_video, write_gif
from .fly_body import FlyGymBody
from .motor_controller import MotorController, MotorConfig
from .sensing import SensoryEncoder, SceneConfig


def _clip(v, lo, hi):
    return max(lo, min(hi, v))


def _boundary_steer(left, right, pose, *, half, margin, turn_gain, slowdown):
    """接近围墙时转向场地中心并减速，避免果蝇冲出有界场地。

    仅在搜索/觅食（foraging）行走态调用——搜索阶段无气味 cue 约束方向，
    若不加边界处理，方向一偏就会一路冲出墙外。
    """
    x, y = pose.thorax_xyz_mm[0], pose.thorax_xyz_mm[1]
    d_wall = half - max(abs(x), abs(y))               # 到最近轴向墙的距离
    if d_wall >= margin:
        return left, right
    strength = _clip((margin - d_wall) / max(1e-6, margin), 0.0, 1.0)
    cn = (x * x + y * y) ** 0.5
    if cn < 1e-6:
        return left, right
    cx, cy = -x / cn, -y / cn                          # 指向场地中心的单位向量
    hx, hy = pose.heading_xy
    cross = hx * cy - hy * cx                          # >0：中心在航向左侧 → 应左转
    fwd = 0.5 * (left + right) * (1.0 - slowdown * strength)   # 近墙减速
    turn = 0.5 * (right - left) + turn_gain * strength * (1.0 if cross >= 0 else -1.0)
    return fwd - turn, fwd + turn


def run_embodied_loop(*, config: dict[str, Any], client: JsonLineClient,
                      output_dir: Path, no_video: bool = False) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_cfg = config["run"]
    scene_cfg = config["scene"]
    render_cfg = config["render"]
    viz_cfg = config.get("brain_viz", {})

    encoder = SensoryEncoder(SceneConfig.from_dict(scene_cfg))
    body = FlyGymBody(scene=scene_cfg, seed=int(run_cfg["seed"]),
                      camera_config=config.get("camera"), dust_count=int(scene_cfg.get("dust_count", 220)))
    motor = MotorController(MotorConfig(**config.get("motor", {})))
    if not no_video:
        body.setup_renderer(render_cfg)

    panel = None
    if not no_video:
        cam_h = int(render_cfg["camera_res"][0])
        panel = BrainPanelRenderer(width=int(viz_cfg.get("panel_width", 520)), height=cam_h,
                                   n_points=int(viz_cfg.get("n_points", 4000)),
                                   activity_norm=float(viz_cfg.get("activity_norm", 2.0)))
    activity_decay = float(viz_cfg.get("activity_decay", 0.9))

    body.warmup(float(run_cfg.get("warmup_s", 0.05)))
    window_s = float(config["ipc"].get("window_ms", 15.0)) / 1000.0
    sync_every = max(1, round(window_s / body.timestep))
    n_steps = int(float(run_cfg["duration_s"]) / body.timestep)
    arena_half = float(scene_cfg["arena_half_size_mm"])
    bnd_margin = float(scene_cfg.get("boundary_margin_mm", 12.0))
    bnd_turn = float(scene_cfg.get("boundary_turn_gain", 0.5))
    bnd_slow = float(scene_cfg.get("boundary_slowdown", 0.6))

    rows: list[dict] = []
    brain_frames: list[np.ndarray] = []
    smoothed = np.zeros(0)
    last = {"behavior": "foraging", "left": 0.6, "right": 0.6, "mn9": 0.0,
            "feeding": 0.0, "grooming": 0.0, "active": 0, "total": 0}
    req_id = 0
    events: dict[str, float | None] = {k: None for k in
        ("first_food_cue_s", "first_contact_s", "first_feeding_s", "first_grooming_s", "first_dust_cleared_s")}
    behavior_counts: dict[str, int] = {}

    for step in range(n_steps):
        pose = body.pose()
        t = pose.time_s
        sensory = encoder.observe(t, (pose.thorax_xyz_mm[0], pose.thorax_xyz_mm[1]),
                                  pose.heading_xy, accumulate_dust=(motor.behavior != "grooming"))

        if step % sync_every == 0:
            req_id += 1
            msg = SensoryMessage(
                request_id=req_id, time_s=t,
                food_cue_left=sensory.food_cue_left, food_cue_right=sensory.food_cue_right,
                dust_level_left=sensory.dust_level_left, dust_level_right=sensory.dust_level_right,
                food_contact=sensory.food_contact, food_distance_mm=sensory.food_distance_mm,
            )
            resp = client.request(msg)
            decision = motor.decide(resp, time_s=t, dust_level=sensory.dust_level_left,
                                    food_contact=sensory.food_contact,
                                    cue=max(sensory.food_cue_left, sensory.food_cue_right))
            if motor.just_completed_grooming:
                encoder.clear_dust()
                _stamp(events, "first_dust_cleared_s", True, t)
            mn9 = resp.readout_rates_hz.get("mn9", 0.0)
            # 梳理 viz：用 motor 的 grooming_readout EMA（真脑通路 JON→aBN1→aDN 激活强度，
            # 即触发梳理用的信号），而非 aDN1 单读（在线 15ms 窗量化跳动大）。
            groom_sig = motor.grooming_signal_hz
            last = {"behavior": decision.behavior, "left": decision.left, "right": decision.right,
                    "mn9": mn9, "feeding": _clip(mn9 / 100, 0, 1),
                    "grooming": _clip(groom_sig / 40.0, 0, 1), "grooming_hz": groom_sig,
                    "active": resp.active_neuron_count, "total": resp.total_neuron_count,
                    "forward": decision.forward, "turn": decision.turn,
                    "wall_ms": resp.brain_wall_time_ms}
            if resp.neuron_activity:
                smoothed = np.asarray(resp.neuron_activity, dtype=float)

        lft, rgt = last["left"], last["right"]
        if last["behavior"] == "foraging":
            lft, rgt = _boundary_steer(lft, rgt, pose, half=arena_half,
                                       margin=bnd_margin, turn_gain=bnd_turn, slowdown=bnd_slow)
        action = body.apply_behavior(last["behavior"], lft, rgt, t)
        rendered = body.step(render=not no_video)

        behavior_counts[last["behavior"]] = behavior_counts.get(last["behavior"], 0) + 1
        _stamp(events, "first_food_cue_s", max(sensory.food_cue_left, sensory.food_cue_right) > 0.05, t)
        _stamp(events, "first_contact_s", sensory.food_contact, t)
        _stamp(events, "first_feeding_s", last["behavior"] == "feeding", t)
        _stamp(events, "first_grooming_s", last["behavior"] == "grooming", t)

        if rendered and panel is not None:
            if smoothed.size:
                smoothed = smoothed * activity_decay
            img = panel.render(smoothed, behavior=last["behavior"], feeding_score=last["feeding"],
                               grooming_score=last["grooming"], grooming_hz=last.get("grooming_hz", 0.0),
                               active_neuron_count=last["active"],
                               total_neuron_count=last["total"], window_ms=window_s * 1000)
            brain_frames.append(img)

        if step % max(1, int(run_cfg.get("log_every_steps", 200))) == 0:
            rows.append({"step": step, "time_s": round(t, 3),
                         "x_mm": round(pose.thorax_xyz_mm[0], 2), "y_mm": round(pose.thorax_xyz_mm[1], 2),
                         "cue_l": round(sensory.food_cue_left, 3), "cue_r": round(sensory.food_cue_right, 3),
                         "dust": round(sensory.dust_level_left, 3), "dist_mm": round(sensory.food_distance_mm, 1),
                         "behavior": last["behavior"], "left": round(last["left"], 3), "right": round(last["right"], 3),
                         "mn9_hz": round(last["mn9"], 1), "active": last["active"]})

    # ---- 产物 ----
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"digital_fruit_fly_{stamp}"
    outputs: dict[str, str] = {}
    combined_path = None
    if not no_video:
        body_frames = body.body_frames()
        n = min(len(body_frames), len(brain_frames))
        combined = [hstack_frame(body_frames[i], brain_frames[i]) for i in range(n)]
        fps = int(render_cfg.get("output_fps", 30))
        combined_path = output_dir / f"{stem}_combined.mp4"
        if write_video(combined, combined_path, fps=fps):
            outputs["combined_mp4"] = str(combined_path)
        else:
            gif = output_dir / f"{stem}_combined.gif"
            if write_gif(combined, gif, fps=min(15, fps)):
                outputs["combined_gif"] = str(gif); combined_path = gif
        try:
            body.close()
        except Exception:
            pass

    import json as _json
    (output_dir / f"{stem}_telemetry.json").write_text(
        _json.dumps({"rows": rows, "events": events, "behavior_counts": behavior_counts}, ensure_ascii=False, indent=2))
    outputs["telemetry_json"] = str(output_dir / f"{stem}_telemetry.json")

    return {"stem": stem, "outputs": outputs, "events": events,
            "behavior_counts": behavior_counts, "combined_video": str(combined_path) if combined_path else None}


def _stamp(events, key, cond, t):
    if cond and events.get(key) is None:
        events[key] = round(t, 3)
