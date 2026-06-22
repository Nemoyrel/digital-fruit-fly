"""具身 loop：编排 observe -> 脑 step -> 行为驱动 -> 渲染（身体帧 + 脑帧），并写出产物。

身体侧只通过 ``BodyBrainBridge`` 协议与脑交互（默认实现见 ``brain_link.IpcBrainBridge``）。
每渲染一帧身体画面，就用当前（保持+衰减后的）逐神经元活动渲染一帧脑活动面板，
最后逐帧并排合成“左身体、右脑”的视频。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from .brain_viz import BrainPanelRenderer
from .compositor import hstack_frame, write_gif, write_video
from .config import configure_local_caches
from .drive import readout_to_descending_signal
from .fly_body import FlyGymBody
from .sensing import VirtualEnvironment
from .state import BehaviorState, BrainReadout, SensoryState
from .telemetry import make_summary_plot, write_csv, write_json


class BodyBrainBridge(Protocol):
    behavior_state: BehaviorState
    just_completed_grooming: bool
    last_cache_hit: bool

    def step(self, sensory_state: SensoryState) -> BrainReadout: ...


def run_embodied_loop(
    *,
    config: dict[str, Any],
    config_path: Path,
    bridge: BodyBrainBridge,
    output_dir: Path,
    no_video: bool = False,
    no_plot: bool = False,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    configure_local_caches(output_dir)

    run_cfg = config["run"]
    scene_cfg = config["scene"]
    render_cfg = config["render"]
    viz_cfg = config.get("brain_viz", {})

    scene = VirtualEnvironment.from_dict(scene_cfg)
    body = FlyGymBody(
        scene=scene_cfg,
        seed=int(run_cfg["seed"]),
        camera_config=config.get("camera"),
        dust_count=int(scene_cfg.get("dust_count", 220)),
    )
    if not no_video:
        body.setup_renderer(render_cfg)

    brain_panel: BrainPanelRenderer | None = None
    if not no_video:
        cam_h = int(render_cfg["camera_res"][0])
        brain_panel = BrainPanelRenderer(
            width=int(viz_cfg.get("panel_width", 520)),
            height=cam_h,
            n_points=int(viz_cfg.get("n_points", 4000)),
            seed=int(viz_cfg.get("seed", 0)),
            activity_norm=float(viz_cfg.get("activity_norm", 2.5)),
        )
    activity_decay = float(viz_cfg.get("activity_decay", 0.9))

    body.warmup(float(run_cfg["warmup_s"]))
    n_steps = int(float(run_cfg["duration_s"]) / body.timestep)
    log_every = max(1, int(run_cfg.get("log_every_steps", 50)))

    rows: list[dict[str, Any]] = []
    brain_frames: list[np.ndarray] = []
    smoothed_activity = np.zeros(0)
    last_behavior = "foraging"
    last_feeding = 0.0
    last_grooming = 0.0
    last_active = 0
    last_total = 0
    last_window_ms = float(config["ipc"].get("brain_window_s_hint", 20.0))

    event_times: dict[str, float | None] = {
        "first_food_cue_s": None,
        "first_food_contact_s": None,
        "first_feeding_s": None,
        "first_dust_threshold_s": None,
        "first_grooming_s": None,
        "first_dust_cleared_s": None,
    }
    behavior_counts: dict[str, int] = {}

    for step in range(n_steps):
        pose = body.pose()
        sensory = scene.observe(
            time_s=pose.time_s,
            fly_xy_mm=(pose.thorax_xyz_mm[0], pose.thorax_xyz_mm[1]),
            heading_xy=pose.heading_xy,
            accumulate_dust=bridge.behavior_state != BehaviorState.GROOMING,
        )
        readout = bridge.step(sensory)
        if getattr(bridge, "just_completed_grooming", False):
            scene.clear_dust()

        left, right = readout_to_descending_signal(readout)
        behavior = readout.behavior_state.value
        action = body.apply_behavior(behavior, left, right, pose.time_s)
        rendered = body.step(render=not no_video)

        # 收到新的脑更新时刷新可视化用的活动向量
        fresh = (not getattr(bridge, "last_cache_hit", False)) and bool(readout.neuron_activity)
        if fresh:
            smoothed_activity = np.asarray(readout.neuron_activity, dtype=float)
            last_feeding = readout.feeding_score
            last_grooming = readout.grooming_score
            last_active = readout.active_neuron_count
            last_total = readout.total_neuron_count
        last_behavior = behavior

        if rendered and brain_panel is not None:
            if smoothed_activity.size:
                smoothed_activity = smoothed_activity * activity_decay
            brain_img = brain_panel.render(
                smoothed_activity,
                behavior=last_behavior,
                feeding_score=last_feeding,
                grooming_score=last_grooming,
                active_neuron_count=last_active,
                total_neuron_count=last_total,
                window_ms=last_window_ms,
            )
            brain_frames.append(brain_img)

        # 事件 & 计数
        behavior_counts[behavior] = behavior_counts.get(behavior, 0) + 1
        _stamp(event_times, "first_food_cue_s", sensory.food_cue > 0.05, sensory.time_s)
        _stamp(event_times, "first_food_contact_s", sensory.food_contact, sensory.time_s)
        _stamp(event_times, "first_feeding_s", behavior == "feeding", sensory.time_s)
        _stamp(event_times, "first_dust_threshold_s", sensory.dust_threshold_reached, sensory.time_s)
        _stamp(event_times, "first_grooming_s", behavior == "grooming", sensory.time_s)
        _stamp(event_times, "first_dust_cleared_s", bool(readout.dust_clearance), sensory.time_s)

        if step % log_every == 0 or step == n_steps - 1:
            row = {
                "step": step,
                "time_s": sensory.time_s,
                "thorax_x_mm": pose.thorax_xyz_mm[0],
                "thorax_y_mm": pose.thorax_xyz_mm[1],
                "food_cue": sensory.food_cue,
                "dust_level": sensory.dust_level,
                "food_distance_mm": sensory.food_distance_mm,
                "food_contact": int(sensory.food_contact),
                "behavior_state": behavior,
                "forward_drive": readout.forward_drive,
                "readout_turn_bias": readout.turn_bias,
                "feeding_score": readout.feeding_score,
                "grooming_score": readout.grooming_score,
                "mn9_rate_hz": readout.mn9_rate_hz,
                "dust_clearance": readout.dust_clearance,
                "active_neuron_count": readout.active_neuron_count,
                "descending_left": left,
                "descending_right": right,
                "mean_joint_angle_rad": action.mean_joint_angle_rad,
                "adhesion_on_count": action.adhesion_on_count,
                "readout_source": readout.source,
            }
            tele = getattr(bridge, "telemetry_fields", None)
            if tele is not None:
                row.update(tele())
            rows.append(row)

    # ---- 写出产物 ----
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"digital_fruit_fly_{timestamp}"
    outputs: dict[str, str | None] = {}

    telemetry_csv = output_dir / f"{stem}.csv"
    write_csv(telemetry_csv, rows)
    outputs["telemetry_csv"] = str(telemetry_csv)

    combined_path = None
    body_video_path = None
    if not no_video:
        body_frames = body.body_frames()
        n_pair = min(len(body_frames), len(brain_frames))
        combined = [
            hstack_frame(body_frames[i], brain_frames[i]) for i in range(n_pair)
        ]
        fps = int(render_cfg.get("output_fps", 30))
        combined_path = output_dir / f"{stem}_combined.mp4"
        if write_video(combined, combined_path, fps=fps):
            outputs["combined_video_mp4"] = str(combined_path)
        else:
            gif_path = output_dir / f"{stem}_combined.gif"
            if write_gif(combined, gif_path, fps=min(15, fps)):
                outputs["combined_video_gif"] = str(gif_path)
                combined_path = gif_path
        body_video_path = output_dir / f"{stem}_body.mp4"
        try:
            body.save_body_video(body_video_path)
            outputs["body_video_mp4"] = str(body_video_path)
        except Exception:
            outputs["body_video_mp4"] = None

    if not no_plot:
        plot_path = output_dir / f"{stem}_summary.png"
        if make_summary_plot(rows, plot_path):
            outputs["summary_plot_png"] = str(plot_path)

    benchmark = _benchmark(rows, bridge)
    benchmark_path = output_dir / f"{stem}_benchmark.json"
    write_json(benchmark_path, benchmark)
    outputs["benchmark_json"] = str(benchmark_path)

    metadata = {
        "description": "数字果蝇：FlyGym 身体 + Shiu 全连接组脑（双进程 IPC）具身觅食/梳理/进食演示。",
        "config_path": str(config_path),
        "config": config,
        "events": event_times,
        "behavior_counts": behavior_counts,
        "outputs": outputs,
        "benchmark": benchmark,
        "boundaries": [
            "神经动力学来自 Shiu et al. 公开 Brian2 模型；",
            "感觉编码、readout->身体映射、TCP IPC、脑活动面板布局均为本项目的工程桥接；",
            "脑面板的神经元坐标为确定性合成（公开数据无坐标），但点的亮度来自真实脉冲计数（127400 神经元分箱求和成可视化点）。",
        ],
        "sources": [
            "https://eon.systems/updates/embodied-brain-emulation",
            "https://www.nature.com/articles/s41586-024-07763-9",
            "https://github.com/philshiu/Drosophila_brain_model",
            "https://github.com/NeLy-EPFL/flygym",
        ],
    }
    metadata_path = output_dir / f"{stem}_metadata.json"
    write_json(metadata_path, metadata)
    outputs["metadata_json"] = str(metadata_path)

    if not no_video:
        body.close()

    return {
        "stem": stem,
        "outputs": outputs,
        "events": event_times,
        "behavior_counts": behavior_counts,
        "benchmark": benchmark,
        "combined_video": str(combined_path) if combined_path else None,
    }


def _stamp(events: dict[str, float | None], key: str, condition: bool, time_s: float) -> None:
    if condition and events.get(key) is None:
        events[key] = time_s


def _benchmark(rows: list[dict[str, Any]], bridge: Any) -> dict[str, Any]:
    walls = sorted(
        float(r.get("ipc_brain_wall_time_ms", 0.0))
        for r in rows
        if float(r.get("ipc_brain_wall_time_ms", 0.0)) > 0.0
    )
    if walls:
        mean_w = sum(walls) / len(walls)
        p95_w = walls[int(round((len(walls) - 1) * 0.95))]
        max_w = walls[-1]
    else:
        mean_w = p95_w = max_w = 0.0
    return {
        "request_count": int(getattr(bridge, "request_count", 0)),
        "timeout_count": int(getattr(bridge, "timeout_count", 0)),
        "backend": getattr(bridge, "last_backend", "unknown"),
        "backends_seen": sorted(
            {str(r.get("ipc_backend", "unknown")) for r in rows if r.get("ipc_backend")}
        ),
        "mean_brain_wall_time_ms": mean_w,
        "p95_brain_wall_time_ms": p95_w,
        "max_brain_wall_time_ms": max_w,
    }
