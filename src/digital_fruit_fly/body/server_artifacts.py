from __future__ import annotations

import json

from dataclasses import dataclass
from pathlib import Path

from digital_fruit_fly.body.camera import (
    RecordingResult,
    CameraRecordingRequest,
    deterministic_probe_frames,
    resolve_viewer_status,
    write_camera_recording,
)
from digital_fruit_fly.body.server_motion import fixture_contract
from digital_fruit_fly.body.server_types import (
    BodyArtifacts,
    BodyRunContext,
    BodyServerConfig,
    BodyServerResult,
    BodyServerRuntimeError,
    BodySimulation,
    ServerStatus,
)
from digital_fruit_fly.bridge.messages import BridgeFrame, encode_message
from digital_fruit_fly.runtime.config import RuntimeConfig
from digital_fruit_fly.runtime.logging import append_jsonl
from digital_fruit_fly.runtime.run_manifest import RunLayout
from digital_fruit_fly.runtime.timeouts import JsonObject


@dataclass(frozen=True, slots=True)
class BodyManifestOutcome:
    status: ServerStatus
    ticks: int
    recording: JsonObject | None
    error: BodyServerRuntimeError | None
    flygym: JsonObject | None


def build_context(
    config: BodyServerConfig, runtime: RuntimeConfig, layout: RunLayout
) -> BodyRunContext:
    return BodyRunContext(
        config=config,
        artifacts=BodyArtifacts(
            layout=layout,
            frames_path=layout.frames_path,
            trajectory_path=layout.run_dir / "trajectory.jsonl",
        ),
        simulation=BodySimulation(runtime=runtime, contract=fixture_contract()),
    )


def prepare_artifacts(context: BodyRunContext) -> None:
    layout = context.artifacts.layout
    for path in (
        layout.frames_path,
        layout.events_path,
        layout.control_path,
        layout.arena_path,
        context.artifacts.trajectory_path,
    ):
        path.write_text("", encoding="utf-8")
    append_jsonl(
        layout.events_path,
        {
            "kind": "body_server_start",
            "brain_mode": context.config.brain_mode,
            "max_ticks": context.config.max_ticks,
        },
    )


def append_bridge_frame(path: Path, frame: BridgeFrame) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(encode_message(frame).decode("utf-8"))
        handle.write("\n")


def record_body_run(context: BodyRunContext, ticks: int) -> RecordingResult:
    runtime = context.simulation.runtime
    request = CameraRecordingRequest(
        output_dir=context.artifacts.layout.video_dir,
        stem="body_server",
        fps=runtime.camera.fps,
        codec=context.config.record_codec,
        mode="tracking" if runtime.camera.follow_fly else "fixed",
        source="deterministic_body_server_frames",
        viewer_status=resolve_viewer_status(True, context.config.viewer_requested),
        fallback_reason="headless fixture body server writes deterministic frames",
    )
    frames = deterministic_probe_frames(runtime.camera.width_px, runtime.camera.height_px, ticks)
    return write_camera_recording(request, frames)


def write_body_manifest(
    context: BodyRunContext,
    outcome: BodyManifestOutcome,
) -> None:
    layout = context.artifacts.layout
    flygym_payload = _flygym_manifest_payload(outcome.flygym, outcome.error)
    payload: JsonObject = {
        "schema_version": 1,
        "run_id": layout.run_id,
        "status": outcome.status,
        "ticks": outcome.ticks,
        "brain_mode": context.config.brain_mode,
        "simulation_backend": str(flygym_payload["backend"]),
        "flygym_live": flygym_payload["live"] is True,
        "flygym": flygym_payload,
        "jsonl_files": {
            "frames": str(layout.frames_path),
            "trajectory": str(context.artifacts.trajectory_path),
            "control": str(layout.control_path),
            "arena": str(layout.arena_path),
            "events": str(layout.events_path),
        },
        "recording": outcome.recording,
        "error": None
        if outcome.error is None
        else {"code": outcome.error.code, "message": outcome.error.message},
    }
    layout.manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _flygym_manifest_payload(
    flygym: JsonObject | None, error: BodyServerRuntimeError | None
) -> JsonObject:
    if flygym is not None:
        return flygym
    payload: JsonObject = {
        "live": False,
        "backend": "FlyGym/NeuroMechFly live stepping not completed",
    }
    if error is not None and error.code == "flygym_initialization_failed":
        payload["error"] = {"code": error.code, "message": error.message}
    return payload


def body_result(
    context: BodyRunContext, status: ServerStatus, exit_code: int, ticks: int
) -> BodyServerResult:
    layout = context.artifacts.layout
    return BodyServerResult(
        status,
        exit_code,
        ticks,
        layout.run_dir,
        layout.manifest_path,
        layout.events_path,
        context.artifacts.trajectory_path,
        layout.control_path,
        layout.arena_path,
        layout.video_dir / "body_server.metadata.json",
    )
