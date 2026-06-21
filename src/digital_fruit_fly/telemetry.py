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
