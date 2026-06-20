"""L2 rule-based embodied-loop demo runner."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .brain_bridge import RuleBrainBridge, readout_to_descending_signal
from .config import (
    L2_CONFIG_PATH,
    OUTPUT_DIR,
    apply_run_overrides,
    configure_local_caches,
    load_json_config,
)
from .flygym_body import FlyGymLocomotionBody, make_l2_scene_markers
from .state import BehaviorState
from .telemetry import make_l2_plot, write_csv, write_json
from .virtual_environment import VirtualEnvironment


def run_l2_embodied_demo(
    *,
    duration_s: float | None = None,
    seed: int | None = None,
    log_every_steps: int | None = None,
    output_dir: Path | None = None,
    no_video: bool = False,
    no_plot: bool = False,
) -> dict[str, Any]:
    config = apply_run_overrides(
        load_json_config(L2_CONFIG_PATH),
        duration_s=duration_s,
        seed=seed,
        log_every_steps=log_every_steps,
    )
    out_dir = output_dir or OUTPUT_DIR / "l2_embodied_loop"
    out_dir.mkdir(parents=True, exist_ok=True)
    configure_local_caches(out_dir)

    scene = VirtualEnvironment.from_dict(config["scene"])
    bridge = RuleBrainBridge(**config["bridge"])
    body = FlyGymLocomotionBody(
        arena_half_size_mm=float(config["scene"]["arena_half_size_mm"]),
        seed=int(config["run"]["seed"]),
        scene_markers=make_l2_scene_markers(config["scene"]),
        camera_config=config.get("camera"),
    )
    if not no_video:
        body.setup_renderer(config["render"])

    body.warmup(float(config["run"]["warmup_s"]))
    n_steps = int(float(config["run"]["duration_s"]) / body.timestep)
    log_every = max(1, int(config["run"]["log_every_steps"]))
    rows: list[dict[str, Any]] = []
    event_times: dict[str, float | None] = {
        "first_dust_threshold_s": None,
        "first_grooming_s": None,
        "first_dust_cleared_s": None,
        "first_food_contact_s": None,
        "first_feeding_s": None,
    }
    behavior_counts: dict[str, int] = {}
    last_logged_behavior: str | None = None

    for step in range(n_steps):
        pose = body.pose()
        sensory_state = scene.observe(
            time_s=pose.time_s,
            fly_xy_mm=(pose.thorax_xyz_mm[0], pose.thorax_xyz_mm[1]),
            heading_xy=pose.heading_xy,
            accumulate_dust=bridge.behavior_state != BehaviorState.GROOMING,
        )
        brain_readout = bridge.step(sensory_state)
        if bridge.just_completed_grooming:
            scene.clear_dust()

        left, right = readout_to_descending_signal(brain_readout)
        action = body.apply_descending_drive(left, right)
        body.step(render=not no_video)

        behavior = brain_readout.behavior_state.value
        behavior_counts[behavior] = behavior_counts.get(behavior, 0) + 1
        if (
            sensory_state.dust_threshold_reached
            and event_times["first_dust_threshold_s"] is None
        ):
            event_times["first_dust_threshold_s"] = sensory_state.time_s
        if behavior == "grooming" and event_times["first_grooming_s"] is None:
            event_times["first_grooming_s"] = sensory_state.time_s
        if brain_readout.dust_clearance and event_times["first_dust_cleared_s"] is None:
            event_times["first_dust_cleared_s"] = sensory_state.time_s
        if sensory_state.food_contact and event_times["first_food_contact_s"] is None:
            event_times["first_food_contact_s"] = sensory_state.time_s
        if behavior == "feeding" and event_times["first_feeding_s"] is None:
            event_times["first_feeding_s"] = sensory_state.time_s

        should_log = (
            step % log_every == 0
            or step == n_steps - 1
            or behavior != last_logged_behavior
            or bool(brain_readout.dust_clearance)
        )
        if should_log:
            rows.append(
                {
                    "step": step,
                    "time_s": sensory_state.time_s,
                    "thorax_x_mm": pose.thorax_xyz_mm[0],
                    "thorax_y_mm": pose.thorax_xyz_mm[1],
                    "thorax_z_mm": pose.thorax_xyz_mm[2],
                    "heading_x": pose.heading_xy[0],
                    "heading_y": pose.heading_xy[1],
                    "food_cue": sensory_state.food_cue,
                    "sensory_turn_bias": sensory_state.turn_bias,
                    "dust_level": sensory_state.dust_level,
                    "dust_threshold_reached": int(sensory_state.dust_threshold_reached),
                    "dust_clearance": brain_readout.dust_clearance,
                    "food_contact": int(sensory_state.food_contact),
                    "food_distance_mm": sensory_state.food_distance_mm,
                    "behavior_state": behavior,
                    "forward_drive": brain_readout.forward_drive,
                    "readout_turn_bias": brain_readout.turn_bias,
                    "grooming_score": brain_readout.grooming_score,
                    "feeding_score": brain_readout.feeding_score,
                    "mn9_rate_hz": brain_readout.mn9_rate_hz,
                    "readout_source": brain_readout.source,
                    "descending_left": left,
                    "descending_right": right,
                    "mean_joint_angle_rad": float(action.joint_angles.mean()),
                    "adhesion_on_count": int(action.adhesion_onoff.sum()),
                }
            )
            last_logged_behavior = behavior

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"l2_embodied_loop_{timestamp}"
    telemetry_path = out_dir / f"{stem}.csv"
    write_csv(telemetry_path, rows)

    video_path = None
    if not no_video:
        video_path = out_dir / f"{stem}.mp4"
        body.save_video(video_path)

    plot_path = None
    if not no_plot:
        plot_path = out_dir / f"{stem}_telemetry.png"
        make_l2_plot(rows, plot_path)

    metadata_path = out_dir / f"{stem}_metadata.json"
    metadata = {
        "level": "L2",
        "description": "Rule-based sensory_state to brain_readout embodied loop.",
        "config_path": str(L2_CONFIG_PATH),
        "config": config,
        "outputs": {
            "telemetry_csv": str(telemetry_path),
            "video_mp4": str(video_path) if video_path is not None else None,
            "telemetry_plot_png": str(plot_path) if plot_path is not None else None,
        },
        "events": event_times,
        "behavior_counts": behavior_counts,
        "notes": [
            "Brain readouts are rule-based L2 placeholders.",
            "Dust is global fictive dust that accumulates on the fly until grooming clears it.",
            "Grooming/feeding are state outputs only; no custom grooming or proboscis actuators are used in L2.",
            "L3 should replace readout_source with empirical LIF lookup-table outputs.",
        ],
        "sources": [
            "https://eon.systems/updates/embodied-brain-emulation",
        ],
    }
    write_json(metadata_path, metadata)
    body.close()

    return {
        "telemetry_csv": telemetry_path,
        "video_mp4": video_path,
        "telemetry_plot_png": plot_path,
        "metadata_json": metadata_path,
        "events": event_times,
    }
