"""Telemetry writers and plots for demo runs."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(data, f, indent=2)


def make_embodied_plot(telemetry_rows: list[dict[str, Any]], plot_path: Path) -> None:
    import matplotlib.pyplot as plt

    if not telemetry_rows:
        return

    time_s = [float(row["time_s"]) for row in telemetry_rows]
    behavior_to_level = {"foraging": 0, "grooming": 1, "feeding": 2, "halted": 3}
    behavior = [behavior_to_level[row["behavior_state"]] for row in telemetry_rows]

    fig, axes = plt.subplots(3, 1, figsize=(9, 6), sharex=True)
    axes[0].plot(time_s, [float(row["food_cue"]) for row in telemetry_rows], label="food_cue")
    axes[0].plot(time_s, [float(row["dust_level"]) for row in telemetry_rows], label="dust_level")
    axes[0].set_ylabel("sensory")
    axes[0].legend(loc="upper right")

    axes[1].plot(time_s, [float(row["forward_drive"]) for row in telemetry_rows], label="forward_drive")
    axes[1].plot(time_s, [float(row["readout_turn_bias"]) for row in telemetry_rows], label="turn_bias")
    axes[1].plot(time_s, [float(row["grooming_score"]) for row in telemetry_rows], label="grooming_score")
    axes[1].plot(time_s, [float(row["feeding_score"]) for row in telemetry_rows], label="feeding_score")
    axes[1].set_ylabel("readout")
    axes[1].legend(loc="upper right", ncol=2)

    axes[2].step(time_s, behavior, where="post", label="behavior_state")
    axes[2].plot(time_s, [float(row["descending_left"]) for row in telemetry_rows], label="left")
    axes[2].plot(time_s, [float(row["descending_right"]) for row in telemetry_rows], label="right")
    axes[2].set_yticks([0, 1, 2, 3], ["forage", "groom", "feed", "halt"])
    axes[2].set_ylabel("body drive")
    axes[2].set_xlabel("simulation time (s)")
    axes[2].legend(loc="upper right", ncol=3)

    fig.tight_layout()
    plot_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(plot_path, dpi=160)
    plt.close(fig)


def make_l4_embodied_plot(telemetry_rows: list[dict[str, Any]], plot_path: Path) -> None:
    """Write a compact L4 plot with sensory, readout, behavior, and timing."""
    import matplotlib.pyplot as plt

    if not telemetry_rows:
        return

    time_s = [float(row["time_s"]) for row in telemetry_rows]
    behavior_to_level = {"foraging": 0, "grooming": 1, "feeding": 2, "halted": 3}
    behavior = [behavior_to_level[row["behavior_state"]] for row in telemetry_rows]
    update_ms = [
        float(row.get("l4_update_wall_time_ms", 0.0)) for row in telemetry_rows
    ]

    fig, axes = plt.subplots(4, 1, figsize=(10, 7), sharex=True)
    axes[0].plot(time_s, [float(row["food_cue"]) for row in telemetry_rows], label="food_cue")
    axes[0].plot(time_s, [float(row["dust_level"]) for row in telemetry_rows], label="dust_level")
    axes[0].set_ylabel("sensory")
    axes[0].legend(loc="upper right")

    axes[1].plot(time_s, [float(row["mn9_rate_hz"]) for row in telemetry_rows], label="mn9_rate_hz")
    axes[1].plot(time_s, [float(row.get("l4_grooming_rate_hz", 0.0)) for row in telemetry_rows], label="grooming_rate_hz")
    axes[1].set_ylabel("LIF rate")
    axes[1].legend(loc="upper right")

    axes[2].plot(time_s, [float(row["forward_drive"]) for row in telemetry_rows], label="forward_drive")
    axes[2].plot(time_s, [float(row["readout_turn_bias"]) for row in telemetry_rows], label="turn_bias")
    axes[2].plot(time_s, [float(row["grooming_score"]) for row in telemetry_rows], label="grooming_score")
    axes[2].plot(time_s, [float(row["feeding_score"]) for row in telemetry_rows], label="feeding_score")
    axes[2].step(time_s, behavior, where="post", label="behavior")
    axes[2].set_ylabel("readout")
    axes[2].legend(loc="upper right", ncol=3)

    axes[3].plot(time_s, update_ms, label="brain_update_ms")
    axes[3].step(
        time_s,
        [float(row.get("l4_brain_updated", 0.0)) for row in telemetry_rows],
        where="post",
        label="brain_updated",
    )
    axes[3].set_ylabel("timing")
    axes[3].set_xlabel("simulation time (s)")
    axes[3].legend(loc="upper right")

    fig.tight_layout()
    plot_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(plot_path, dpi=160)
    plt.close(fig)


def _save_l4_brain_state_animation(
    telemetry_rows: list[dict[str, Any]],
    output_path: Path,
    writer,
) -> bool:
    """Write an animation of the online brain state with a matplotlib writer."""
    import matplotlib.animation as animation
    import matplotlib.pyplot as plt

    if not telemetry_rows:
        return False

    time_s = [float(row["time_s"]) for row in telemetry_rows]
    mn9_rate = [float(row["mn9_rate_hz"]) for row in telemetry_rows]
    grooming_rate = [
        float(row.get("l4_grooming_rate_hz", row["grooming_score"]))
        for row in telemetry_rows
    ]
    dust = [float(row["dust_level"]) for row in telemetry_rows]
    food = [float(row["food_cue"]) for row in telemetry_rows]
    mn9_v = [float(row.get("l4_mn9_voltage_mV", -52.0)) for row in telemetry_rows]
    grooming_v = [
        float(row.get("l4_grooming_voltage_mV", -52.0)) for row in telemetry_rows
    ]

    fig, axes = plt.subplots(3, 1, figsize=(8, 6), sharex=True)
    fig.suptitle("L4 online brain proxy state")

    axes[0].set_ylabel("input")
    axes[0].set_ylim(-0.05, 1.05)
    food_line, = axes[0].plot([], [], label="food_cue")
    dust_line, = axes[0].plot([], [], label="dust_level")
    axes[0].legend(loc="upper right")

    axes[1].set_ylabel("rate Hz")
    axes[1].set_ylim(0.0, max(max(mn9_rate), max(grooming_rate), 1.0) * 1.15)
    mn9_line, = axes[1].plot([], [], label="MN9-like")
    grooming_line, = axes[1].plot([], [], label="grooming-like")
    axes[1].legend(loc="upper right")

    axes[2].set_ylabel("voltage mV")
    axes[2].set_xlabel("simulation time (s)")
    axes[2].set_ylim(-53.5, -42.0)
    mn9_v_line, = axes[2].plot([], [], label="MN9 V")
    grooming_v_line, = axes[2].plot([], [], label="grooming V")
    state_text = axes[2].text(
        0.01,
        0.04,
        "",
        transform=axes[2].transAxes,
        fontsize=9,
        va="bottom",
    )
    axes[2].legend(loc="upper right")

    for axis in axes:
        axis.set_xlim(time_s[0], time_s[-1] if time_s[-1] > time_s[0] else time_s[0] + 1.0)
        axis.grid(alpha=0.25)

    def update(frame: int):
        end = frame + 1
        current = telemetry_rows[frame]
        food_line.set_data(time_s[:end], food[:end])
        dust_line.set_data(time_s[:end], dust[:end])
        mn9_line.set_data(time_s[:end], mn9_rate[:end])
        grooming_line.set_data(time_s[:end], grooming_rate[:end])
        mn9_v_line.set_data(time_s[:end], mn9_v[:end])
        grooming_v_line.set_data(time_s[:end], grooming_v[:end])
        state_text.set_text(
            "\n".join(
                [
                    f"behavior: {current['behavior_state']}",
                    f"updated: {int(current.get('l4_brain_updated', 0))}",
                    f"update ms: {float(current.get('l4_update_wall_time_ms', 0.0)):.3f}",
                ]
            )
        )
        return (
            food_line,
            dust_line,
            mn9_line,
            grooming_line,
            mn9_v_line,
            grooming_v_line,
            state_text,
        )

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        anim = animation.FuncAnimation(
            fig,
            update,
            frames=len(telemetry_rows),
            interval=100,
            blit=True,
        )
        anim.save(output_path, writer=writer)
    except Exception:
        plt.close(fig)
        return False
    plt.close(fig)
    return True


def make_l4_brain_state_video(
    telemetry_rows: list[dict[str, Any]],
    video_path: Path,
) -> bool:
    """Write an MP4 animation of the online brain state when ffmpeg is available."""
    import matplotlib.animation as animation

    if not animation.writers.is_available("ffmpeg"):
        return False
    writer = animation.FFMpegWriter(fps=12, bitrate=1800)
    return _save_l4_brain_state_animation(telemetry_rows, video_path, writer)


def make_l4_brain_state_gif(
    telemetry_rows: list[dict[str, Any]],
    gif_path: Path,
) -> bool:
    """Write a GIF animation of the online brain state when pillow is available."""
    import matplotlib.animation as animation

    if not animation.writers.is_available("pillow"):
        return False
    writer = animation.PillowWriter(fps=12)
    return _save_l4_brain_state_animation(telemetry_rows, gif_path, writer)
