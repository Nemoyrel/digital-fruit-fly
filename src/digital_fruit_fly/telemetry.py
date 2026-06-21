"""Telemetry writers and plots for demo runs."""

from __future__ import annotations

import csv
import json
import math
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


def _brain_panel_values(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "time_s": float(row.get("time_s", 0.0)),
        "behavior_state": str(row.get("behavior_state", "unknown")),
        "backend": str(row.get("ipc_backend", row.get("readout_source", "unknown"))),
        "mn9_rate_hz": float(row.get("mn9_rate_hz", row.get("l4_mn9_rate_hz", 0.0))),
        "grooming_rate_hz": float(
            row.get(
                "ipc_grooming_rate_hz",
                row.get("l4_grooming_rate_hz", row.get("grooming_score", 0.0)),
            )
        ),
        "brain_wall_time_ms": float(
            row.get("ipc_brain_wall_time_ms", row.get("l4_update_wall_time_ms", 0.0))
        ),
        "brain_window_s": float(
            row.get("ipc_brain_window_s", row.get("l4_target_sync_interval_s", 0.0))
        ),
    }


def _brain_point_cloud() -> tuple[list[float], list[float], list[str]]:
    xs: list[float] = []
    ys: list[float] = []
    regions: list[str] = []
    for side, center_x in (("left", -1.25), ("right", 1.25)):
        for i in range(130):
            angle = i * 2.399963229728653
            radius = math.sqrt((i + 0.5) / 130.0)
            xs.append(center_x + 0.78 * radius * math.cos(angle))
            ys.append(0.04 + 0.58 * radius * math.sin(angle))
            regions.append(side)
    for i in range(120):
        angle = i * 2.399963229728653
        radius = math.sqrt((i + 0.5) / 120.0)
        xs.append(0.0 + 0.95 * radius * math.cos(angle))
        ys.append(-0.03 + 0.42 * radius * math.sin(angle))
        regions.append("central")
    return xs, ys, regions


def _draw_l4_brain_panel(axis, row: dict[str, Any]) -> None:
    values = _brain_panel_values(row)
    xs, ys, regions = _brain_point_cloud()
    mn9_level = _clip_for_plot(values["mn9_rate_hz"] / 100.0)
    grooming_level = _clip_for_plot(values["grooming_rate_hz"] / 100.0)
    colors = []
    sizes = []
    for region in regions:
        if region in {"left", "right"}:
            colors.append((0.18 + 0.75 * mn9_level, 0.24 + 0.62 * mn9_level, 0.30, 0.38 + 0.55 * mn9_level))
            sizes.append(5.5 + 13.0 * mn9_level)
        else:
            colors.append((0.42 + 0.35 * grooming_level, 0.16, 0.50 + 0.46 * grooming_level, 0.36 + 0.58 * grooming_level))
            sizes.append(4.5 + 15.0 * grooming_level)

    axis.set_facecolor("black")
    axis.scatter(xs, ys, s=sizes, c=colors, edgecolors="none")
    axis.scatter(
        [-0.42, 0.42],
        [0.32, 0.32],
        s=[80 + 210 * grooming_level, 80 + 210 * grooming_level],
        c=[(0.95, 0.12, 0.95, 0.88), (0.95, 0.12, 0.95, 0.88)],
        edgecolors="white",
        linewidths=0.4,
    )
    axis.scatter(
        [-1.25, 1.25],
        [0.04, 0.04],
        s=[120 + 280 * mn9_level, 120 + 280 * mn9_level],
        c=[(1.0, 0.88, 0.34, 0.88), (1.0, 0.88, 0.34, 0.88)],
        edgecolors="white",
        linewidths=0.4,
    )
    axis.text(
        -2.08,
        -0.86,
        f"behavior {values['behavior_state']}",
        color="white",
        fontsize=10,
        ha="left",
    )
    axis.text(
        -2.08,
        -1.03,
        f"backend {values['backend']}",
        color="#cfcfcf",
        fontsize=9,
        ha="left",
    )
    axis.text(
        0.15,
        -0.86,
        f"MN9 {values['mn9_rate_hz']:.1f} Hz",
        color="#ffe681",
        fontsize=10,
        ha="left",
    )
    axis.text(
        0.15,
        -1.03,
        f"grooming DN {values['grooming_rate_hz']:.1f} Hz",
        color="#ffa6ff",
        fontsize=9,
        ha="left",
    )
    axis.text(
        1.18,
        -0.86,
        f"window {values['brain_window_s'] * 1000.0:.1f} ms",
        color="#cfcfcf",
        fontsize=9,
        ha="left",
    )
    axis.text(
        1.18,
        -1.03,
        f"wall {values['brain_wall_time_ms']:.1f} ms",
        color="#cfcfcf",
        fontsize=9,
        ha="left",
    )
    axis.set_xlim(-2.2, 2.2)
    axis.set_ylim(-1.15, 1.02)
    axis.set_xticks([])
    axis.set_yticks([])
    for spine in axis.spines.values():
        spine.set_visible(False)


def _clip_for_plot(value: float) -> float:
    return max(0.0, min(1.0, value))


def make_l4_brain_activity_panel_png(
    telemetry_rows: list[dict[str, Any]],
    output_path: Path,
) -> bool:
    """Write one dark brain-activity panel from the final L4 telemetry row."""
    if not telemetry_rows:
        return False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        _write_minimal_black_png(output_path)
        return True

    fig, axis = plt.subplots(figsize=(8, 4.5), facecolor="black")
    _draw_l4_brain_panel(axis, telemetry_rows[-1])
    fig.tight_layout(pad=0.08)
    fig.savefig(output_path, dpi=160, facecolor="black")
    plt.close(fig)
    return True


def _write_minimal_black_png(output_path: Path) -> None:
    import struct
    import zlib

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    width = height = 1
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw_rgb_scanline = b"\x00\x00\x00\x00"
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw_rgb_scanline))
        + chunk(b"IEND", b"")
    )
    output_path.write_bytes(png)


def _save_l4_brain_state_animation(
    telemetry_rows: list[dict[str, Any]],
    output_path: Path,
    writer,
) -> bool:
    """Write an animation of the L4 brain activity panel with a matplotlib writer."""
    import matplotlib.animation as animation
    import matplotlib.pyplot as plt

    if not telemetry_rows:
        return False

    fig, axis = plt.subplots(figsize=(8, 4.5), facecolor="black")

    def update(frame: int):
        axis.clear()
        _draw_l4_brain_panel(axis, telemetry_rows[frame])
        return []

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        anim = animation.FuncAnimation(
            fig,
            update,
            frames=len(telemetry_rows),
            interval=100,
            blit=False,
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
