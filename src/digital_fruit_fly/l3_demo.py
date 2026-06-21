"""L3 lookup-table-driven embodied demo runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .brain_bridge import LookupBrainBridge
from .config import (
    L3_CONFIG_PATH,
    OUTPUT_DIR,
    apply_run_overrides,
    load_json_config,
)
from .embodied_loop import run_embodied_loop


def run_l3_embodied_demo(
    *,
    duration_s: float | None = None,
    seed: int | None = None,
    log_every_steps: int | None = None,
    output_dir: Path | None = None,
    no_video: bool = False,
    no_plot: bool = False,
) -> dict[str, Any]:
    config = apply_run_overrides(
        load_json_config(L3_CONFIG_PATH),
        duration_s=duration_s,
        seed=seed,
        log_every_steps=log_every_steps,
    )
    bridge = LookupBrainBridge(**config["bridge"])
    return run_embodied_loop(
        config=config,
        config_path=L3_CONFIG_PATH,
        bridge=bridge,
        output_dir=output_dir or OUTPUT_DIR / "l3_embodied_loop",
        stem_prefix="l3_embodied_loop",
        level="L3",
        description="Lookup-table-driven embodied loop using offline brain readouts.",
        notes=[
            "Sugar/MN9 readouts are derived from philshiu/Drosophila_brain_model example parquet outputs.",
            "Dust/grooming readout is a small Brian2 LIF proxy using Shiu-style LIF constants, not a full connectome run.",
            "Body control and behavior-state gating remain this project's engineering bridge.",
        ],
        sources=[
            "external/drosophila_brain_model/Readme.md",
            "external/drosophila_brain_model/example.ipynb",
            "external/drosophila_brain_model/results/example/*.parquet",
            "data/l3_brain_readout_lookup.csv",
        ],
        no_video=no_video,
        no_plot=no_plot,
    )
