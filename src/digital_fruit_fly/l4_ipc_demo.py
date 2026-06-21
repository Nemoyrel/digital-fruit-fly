"""L4 IPC embodied demo runner."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .config import (
    L4_IPC_CONFIG_PATH,
    OUTPUT_DIR,
    apply_run_overrides,
    load_json_config,
)
from .demo_video import combine_side_by_side_video
from .embodied_loop import run_embodied_loop
from .l4_ipc_bridge import IpcBrainBridge
from .telemetry import (
    make_l4_brain_state_gif,
    make_l4_brain_state_video,
    make_l4_embodied_plot,
)


def run_l4_ipc_embodied_demo(
    *,
    duration_s: float | None = None,
    seed: int | None = None,
    log_every_steps: int | None = None,
    output_dir: Path | None = None,
    no_video: bool = False,
    no_plot: bool = False,
    host: str | None = None,
    port: int | None = None,
    timeout_s: float | None = None,
    start_worker: bool | None = None,
    combine_video: bool = False,
) -> dict[str, Any]:
    config = apply_run_overrides(
        load_json_config(L4_IPC_CONFIG_PATH),
        duration_s=duration_s,
        seed=seed,
        log_every_steps=log_every_steps,
    )
    ipc_config = dict(config["ipc"])
    if host is not None:
        ipc_config["host"] = host
    if port is not None:
        ipc_config["port"] = port
    if timeout_s is not None:
        ipc_config["timeout_s"] = timeout_s
    if start_worker is not None:
        ipc_config["start_worker"] = start_worker
    config["ipc"] = ipc_config

    worker_process = None
    if ipc_config.get("start_worker", False):
        worker_process = subprocess.Popen(
            [
                str(ipc_config["brain_env_python"]),
                "scripts/run_l4_brain_worker.py",
                "--host",
                str(ipc_config["host"]),
                "--port",
                str(ipc_config["port"]),
                "--backend",
                str(ipc_config.get("backend", "auto")),
            ],
            cwd=Path(__file__).resolve().parents[2],
        )

    bridge = IpcBrainBridge.from_config(ipc_config)

    def build_l4_ipc_outputs(
        rows: list[dict[str, Any]],
        metadata: dict[str, Any],
        run_output_dir: Path,
        stem: str,
    ) -> dict[str, str | None]:
        ipc_plot_path = None
        if not no_plot:
            ipc_plot_path = run_output_dir / f"{stem}_ipc_telemetry.png"
            make_l4_embodied_plot(rows, ipc_plot_path)

        brain_video_path = None
        brain_gif_path = None
        if not no_video:
            candidate_video = run_output_dir / f"{stem}_brain_state.mp4"
            if make_l4_brain_state_video(rows, candidate_video):
                brain_video_path = candidate_video
            else:
                candidate_gif = run_output_dir / f"{stem}_brain_state.gif"
                if make_l4_brain_state_gif(rows, candidate_gif):
                    brain_gif_path = candidate_gif

        combined_video_path = None
        combined_metadata = {"combined": False, "reason": "not_requested"}
        body_video = Path(metadata["outputs"]["video_mp4"]) if metadata["outputs"]["video_mp4"] else None
        if combine_video and body_video is not None and brain_video_path is not None:
            candidate_combined = run_output_dir / f"{stem}_combined.mp4"
            combined_metadata = combine_side_by_side_video(
                body_video=body_video,
                brain_video=brain_video_path,
                output_video=candidate_combined,
            )
            if combined_metadata["combined"]:
                combined_video_path = candidate_combined
        metadata["ipc_summary"] = {
            "request_count": bridge.request_count,
            "timeout_count": bridge.timeout_count,
            "backend": bridge.last_backend,
            "combine_video_requested": combine_video,
            "combined_video": combined_metadata,
        }
        return {
            "ipc_telemetry_plot_png": str(ipc_plot_path) if ipc_plot_path else None,
            "brain_state_video_mp4": str(brain_video_path) if brain_video_path else None,
            "brain_state_animation_gif": str(brain_gif_path) if brain_gif_path else None,
            "combined_video_mp4": str(combined_video_path) if combined_video_path else None,
        }

    try:
        return run_embodied_loop(
            config=config,
            config_path=L4_IPC_CONFIG_PATH,
            bridge=bridge,
            output_dir=output_dir or OUTPUT_DIR / "l4_ipc_embodied_loop",
            stem_prefix="l4_ipc_embodied_loop",
            level="L4-IPC",
            description="Cross-environment IPC embodied loop using a brain_env worker.",
            notes=[
                "FlyGym loop runs in flygym_env while brain worker is intended to run in brain_env.",
                "IPC transport is this project's TCP JSON-lines bridge, not an Eon-disclosed protocol.",
                "Worker backend records whether Shiu full model was attempted or proxy fallback was used.",
            ],
            sources=[
                "https://eon.systems/updates/embodied-brain-emulation",
                "external/drosophila_brain_model/model.py",
                "configs/l4_ipc_embodied_loop.json",
            ],
            no_video=no_video,
            no_plot=no_plot,
            extra_outputs_builder=build_l4_ipc_outputs,
        )
    finally:
        if worker_process is not None:
            worker_process.terminate()
            worker_process.wait(timeout=2.0)
