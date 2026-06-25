from __future__ import annotations

from digital_fruit_fly.body.server_artifacts import (
    BodyManifestOutcome,
    body_result,
    build_context,
    prepare_artifacts,
    record_body_run,
    write_body_manifest,
)
from digital_fruit_fly.body.server_loop import run_body_loop
from digital_fruit_fly.body.server_types import (
    BodyServerConfig,
    BodyServerConfigError,
    BodyServerResult,
    BodyServerRuntimeError,
)
from digital_fruit_fly.runtime.config import load_config
from digital_fruit_fly.runtime.logging import append_jsonl
from digital_fruit_fly.runtime.run_manifest import create_run_layout

__all__ = (
    "BodyServerConfig",
    "BodyServerConfigError",
    "BodyServerResult",
    "BodyServerRuntimeError",
    "serve_body",
)


def serve_body(config: BodyServerConfig) -> BodyServerResult:
    runtime = load_config(config.config_path)
    layout = create_run_layout(config.output_dir, config.output_dir.name)
    context = build_context(config, runtime, layout)
    prepare_artifacts(context)
    try:
        loop = run_body_loop(context)
    except BodyServerRuntimeError as exc:
        write_body_manifest(context, BodyManifestOutcome("error", 0, None, exc, None))
        append_jsonl(
            layout.events_path,
            {"kind": "body_server_error", "code": exc.code, "message": exc.message},
        )
        return body_result(context, "error", 1, 0)
    recording = record_body_run(context, loop.ticks)
    write_body_manifest(
        context,
        BodyManifestOutcome("ok", loop.ticks, recording.to_json(), None, loop.flygym),
    )
    append_jsonl(
        layout.events_path,
        {"kind": "body_server_stop", "status": "ok", "ticks": loop.ticks},
    )
    return body_result(context, "ok", 0, loop.ticks)
