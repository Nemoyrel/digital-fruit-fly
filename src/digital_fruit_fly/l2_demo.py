"""L2 rule-based embodied-loop demo runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .brain_bridge import RuleBrainBridge
from .config import (
    L2_CONFIG_PATH,
    OUTPUT_DIR,
    apply_run_overrides,
    load_json_config,
)
from .embodied_loop import run_embodied_loop


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
    bridge = RuleBrainBridge(**config["bridge"])
    return run_embodied_loop(
        config=config,
        config_path=L2_CONFIG_PATH,
        bridge=bridge,
        output_dir=output_dir or OUTPUT_DIR / "l2_embodied_loop",
        stem_prefix="l2_embodied_loop",
        level="L2",
        description="Rule-based sensory_state to brain_readout embodied loop.",
        notes=[
            "Brain readouts are rule-based L2 placeholders.",
            "Dust is global fictive dust that accumulates on the fly until grooming clears it.",
            "Grooming/feeding are state outputs only; no custom grooming or proboscis actuators are used in L2.",
            "L3 should replace readout_source with empirical LIF lookup-table outputs.",
        ],
        sources=["https://eon.systems/updates/embodied-brain-emulation"],
        no_video=no_video,
        no_plot=no_plot,
    )
