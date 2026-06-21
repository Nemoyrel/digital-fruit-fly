"""L4 online LIF embodied demo runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import (
    L4_CONFIG_PATH,
    OUTPUT_DIR,
    apply_run_overrides,
    load_json_config,
)
from .embodied_loop import run_embodied_loop
from .l4_online_lif import OnlineLIFBrainBridge
from .telemetry import (
    make_l4_brain_state_gif,
    make_l4_brain_state_video,
    make_l4_embodied_plot,
    write_json,
)


def run_l4_embodied_demo(
    *,
    duration_s: float | None = None,
    seed: int | None = None,
    log_every_steps: int | None = None,
    output_dir: Path | None = None,
    no_video: bool = False,
    no_plot: bool = False,
) -> dict[str, Any]:
    config = apply_run_overrides(
        load_json_config(L4_CONFIG_PATH),
        duration_s=duration_s,
        seed=seed,
        log_every_steps=log_every_steps,
    )
    bridge = OnlineLIFBrainBridge(**config["bridge"])

    def build_l4_outputs(
        rows: list[dict[str, Any]],
        metadata: dict[str, Any],
        run_output_dir: Path,
        stem: str,
    ) -> dict[str, str | None]:
        benchmark_path = run_output_dir / f"{stem}_brain_benchmark.json"
        benchmark = bridge.benchmark_summary()
        metadata["brain_benchmark"] = benchmark
        write_json(benchmark_path, benchmark)

        l4_plot_path = None
        if not no_plot:
            l4_plot_path = run_output_dir / f"{stem}_l4_telemetry.png"
            make_l4_embodied_plot(rows, l4_plot_path)

        brain_video_path = None
        brain_gif_path = None
        if not no_video:
            candidate_path = run_output_dir / f"{stem}_brain_state.mp4"
            if make_l4_brain_state_video(rows, candidate_path):
                brain_video_path = candidate_path
            else:
                candidate_gif_path = run_output_dir / f"{stem}_brain_state.gif"
                if make_l4_brain_state_gif(rows, candidate_gif_path):
                    brain_gif_path = candidate_gif_path
                    metadata.setdefault("notes", []).append(
                        "Brain-state MP4 was skipped because ffmpeg was unavailable; wrote GIF fallback."
                    )
                else:
                    metadata.setdefault("notes", []).append(
                        "Brain-state animation was skipped because no matplotlib video writer was available."
                    )

        return {
            "brain_benchmark_json": str(benchmark_path),
            "l4_telemetry_plot_png": str(l4_plot_path) if l4_plot_path else None,
            "brain_state_video_mp4": str(brain_video_path) if brain_video_path else None,
            "brain_state_animation_gif": str(brain_gif_path) if brain_gif_path else None,
        }

    return run_embodied_loop(
        config=config,
        config_path=L4_CONFIG_PATH,
        bridge=bridge,
        output_dir=output_dir or OUTPUT_DIR / "l4_embodied_loop",
        stem_prefix="l4_embodied_loop",
        level="L4",
        description="Online LIF-style embodied loop with timing benchmark and brain-state visualization.",
        notes=[
            "This L4 runner attempts online brain updates with a small LIF-style proxy.",
            "It records per-update wall time and cached body steps between brain sync ticks.",
            "The proxy is an engineering fallback, not a full Shiu connectome or Eon private-code reproduction.",
            "The L3 lookup-table runner remains the stable delivery path.",
        ],
        sources=[
            "https://eon.systems/updates/embodied-brain-emulation",
            "external/drosophila_brain_model/model.py",
            "configs/l4_embodied_loop.json",
        ],
        no_video=no_video,
        no_plot=no_plot,
        extra_outputs_builder=build_l4_outputs,
    )
