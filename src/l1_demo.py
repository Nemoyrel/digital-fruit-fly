"""L1 body-only demo runner."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .config import (
    L1_CONFIG_PATH,
    OUTPUT_DIR,
    apply_run_overrides,
    configure_local_caches,
    load_json_config,
)
from .flygym_body import FlyGymLocomotionBody
from .telemetry import write_csv


def descending_signal(pattern: str, progress: float) -> tuple[float, float]:
    if pattern == "straight":
        return (1.2, 1.2)
    if pattern == "left":
        return (0.55, 1.25)
    if pattern == "right":
        return (1.25, 0.55)
    if progress < 0.35:
        return (1.15, 1.15)
    if progress < 0.68:
        return (0.55, 1.25)
    return (1.25, 0.55)


def run_l1_body_demo(
    *,
    duration_s: float | None = None,
    seed: int | None = None,
    pattern: str | None = None,
    output_dir: Path | None = None,
    no_video: bool = False,
) -> dict[str, Any]:
    config = apply_run_overrides(
        load_json_config(L1_CONFIG_PATH), duration_s=duration_s, seed=seed
    )
    if pattern is not None:
        config["run"]["pattern"] = pattern

    out_dir = output_dir or OUTPUT_DIR / "flygym_l1"
    out_dir.mkdir(parents=True, exist_ok=True)
    configure_local_caches(out_dir)

    body = FlyGymLocomotionBody(
        arena_half_size_mm=float(config["body"]["arena_half_size_mm"]),
        seed=int(config["run"]["seed"]),
    )
    if not no_video:
        body.setup_renderer(config["render"])

    body.warmup(float(config["run"]["warmup_s"]))
    n_steps = int(float(config["run"]["duration_s"]) / body.timestep)
    log_every_steps = max(1, int(config["run"]["log_every_steps"]))
    rows = []

    for step in range(n_steps):
        progress = step / max(n_steps - 1, 1)
        left, right = descending_signal(config["run"]["pattern"], progress)
        action = body.apply_descending_drive(left, right)
        body.step(render=not no_video)
        if step % log_every_steps == 0 or step == n_steps - 1:
            pose = body.pose()
            rows.append(
                {
                    "step": step,
                    "time_s": pose.time_s,
                    "descending_left": left,
                    "descending_right": right,
                    "thorax_x_mm": pose.thorax_xyz_mm[0],
                    "thorax_y_mm": pose.thorax_xyz_mm[1],
                    "thorax_z_mm": pose.thorax_xyz_mm[2],
                    "mean_joint_angle_rad": float(action.joint_angles.mean()),
                    "adhesion_on_count": int(action.adhesion_onoff.sum()),
                }
            )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"flygym_l1_{config['run']['pattern']}_{timestamp}"
    telemetry_path = out_dir / f"{stem}.csv"
    write_csv(telemetry_path, rows)
    video_path = None
    if not no_video:
        video_path = out_dir / f"{stem}.mp4"
        body.save_video(video_path)
    body.close()

    return {"telemetry_csv": telemetry_path, "video_mp4": video_path}
