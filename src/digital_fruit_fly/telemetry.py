"""遥测写出与汇总图（CSV / JSON / matplotlib）。"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def make_summary_plot(rows: list[dict[str, Any]], plot_path: Path) -> bool:
    """画一张紧凑的汇总图：感觉量 / 神经读出 / 行为。"""
    if not rows:
        return False
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = [float(r["time_s"]) for r in rows]
    behavior_level = {"foraging": 0, "grooming": 1, "feeding": 2, "halted": 3}
    behavior = [behavior_level.get(r["behavior_state"], 3) for r in rows]

    fig, axes = plt.subplots(3, 1, figsize=(10, 7), sharex=True)
    axes[0].plot(t, [float(r["food_cue"]) for r in rows], label="food_cue")
    axes[0].plot(t, [float(r["dust_level"]) for r in rows], label="dust_level")
    axes[0].set_ylabel("sensory")
    axes[0].legend(loc="upper right")

    axes[1].plot(t, [float(r["mn9_rate_hz"]) for r in rows], label="mn9_rate_hz")
    axes[1].plot(t, [float(r["feeding_score"]) for r in rows], label="feeding_score")
    axes[1].plot(t, [float(r["grooming_score"]) for r in rows], label="grooming_score")
    axes[1].plot(t, [float(r.get("active_neuron_count", 0)) for r in rows],
                 label="active_neurons", alpha=0.5)
    axes[1].set_ylabel("brain readout")
    axes[1].legend(loc="upper right", ncol=2)

    axes[2].step(t, behavior, where="post", label="behavior")
    axes[2].plot(t, [float(r["descending_left"]) for r in rows], label="left")
    axes[2].plot(t, [float(r["descending_right"]) for r in rows], label="right")
    axes[2].set_yticks([0, 1, 2, 3], ["forage", "groom", "feed", "halt"])
    axes[2].set_ylabel("body drive")
    axes[2].set_xlabel("simulation time (s)")
    axes[2].legend(loc="upper right", ncol=3)

    fig.tight_layout()
    Path(plot_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)
    return True
