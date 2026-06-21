"""Project paths, JSON configs, and local runtime cache setup."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "configs"
OUTPUT_DIR = PROJECT_ROOT / "outputs"

L1_CONFIG_PATH = CONFIG_DIR / "l1_body.json"
L2_CONFIG_PATH = CONFIG_DIR / "l2_embodied_loop.json"
L3_CONFIG_PATH = CONFIG_DIR / "l3_embodied_loop.json"
L4_CONFIG_PATH = CONFIG_DIR / "l4_embodied_loop.json"
L3_LOOKUP_CONFIG_PATH = CONFIG_DIR / "l3_brain_lookup.json"


def configure_local_caches(output_dir: Path) -> None:
    cache_dir = output_dir / "cache"
    os.environ.setdefault("MPLCONFIGDIR", str(cache_dir / "matplotlib"))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_dir / "xdg"))


def load_json_config(path: Path) -> dict[str, Any]:
    with path.open() as f:
        return json.load(f)


def apply_run_overrides(
    config: dict[str, Any],
    *,
    duration_s: float | None = None,
    seed: int | None = None,
    log_every_steps: int | None = None,
) -> dict[str, Any]:
    updated = json.loads(json.dumps(config))
    if duration_s is not None:
        updated["run"]["duration_s"] = duration_s
    if seed is not None:
        updated["run"]["seed"] = seed
    if log_every_steps is not None:
        updated["run"]["log_every_steps"] = log_every_steps
    return updated
