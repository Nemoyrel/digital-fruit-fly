from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import os
import platform
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Optional, Sequence

from digital_fruit_fly.body.flygym_api import build_installed_api_report
from digital_fruit_fly.body.flygym_api_docs import write_api_artifacts
from digital_fruit_fly.body.rendering import prepare_glfw_platform, select_renderer
from digital_fruit_fly.runtime.timeouts import (
    JsonObject,
    SubprocessRunRequest,
    TIMEOUT_EXIT_CODE,
    run_subprocess_request,
    write_json_evidence,
)


RENDERERS: Final = frozenset(("auto", "none", "glfw", "egl", "osmesa"))
CHILD_RESULT: Final = "child_probe.json"


@dataclass(frozen=True)
class BodyProbeRequest:
    config_path: Path
    output_dir: Path
    steps: int
    timeout_sec: float
    headless: bool
    renderer: str
    evidence_path: Path
    api_report: bool
    fixture_sleep_sec: float


@dataclass(frozen=True)
class ProbeOutcome:
    exit_code: int
    payload: JsonObject
    evidence_path: Path


@dataclass(frozen=True)
class ChildProbeRequest:
    output_path: Path
    steps: int
    headless: bool
    renderer: str
    api_report: bool
    fixture_sleep_sec: float


def run_body_probe(request: BodyProbeRequest) -> ProbeOutcome:
    request.output_dir.mkdir(parents=True, exist_ok=True)
    renderer_error = validate_renderer(request.renderer)
    if renderer_error is not None:
        return _record_argument_failure(request, renderer_error)
    if request.steps <= 0:
        return _record_argument_failure(request, "steps must be positive")
    if request.timeout_sec <= 0.0:
        return _record_argument_failure(request, "timeout-sec must be positive")

    child_result = request.output_dir / CHILD_RESULT
    child_result.unlink(missing_ok=True)
    command = _child_command(request, child_result)
    result = run_subprocess_request(
        SubprocessRunRequest(
            command=command,
            timeout_sec=request.timeout_sec,
            evidence_path=request.output_dir / "child_timeout.json",
            cwd=Path.cwd(),
            env=_child_env(),
        )
    )
    if result.exit_code != 0:
        return _record_child_failure(request, result)

    payload = _read_child_payload(child_result)
    payload["script"] = "smoke_body"
    payload["status"] = "ok"
    payload["config"] = str(request.config_path)
    artifacts = [str(request.output_dir / "body_env.json"), str(child_result)]
    if request.api_report:
        artifacts.append(str(request.output_dir / "flygym_api.json"))
    payload["artifacts"] = artifacts
    write_json_evidence(request.output_dir / "body_env.json", payload)
    write_json_evidence(request.evidence_path, payload)
    return ProbeOutcome(0, payload, request.evidence_path)


def validate_renderer(renderer: str) -> Optional[str]:
    if renderer in RENDERERS:
        return None
    allowed = ", ".join(sorted(RENDERERS))
    return f"renderer must be one of: {allowed}"


def run_child_probe(request: ChildProbeRequest) -> int:
    request.output_path.parent.mkdir(parents=True, exist_ok=True)
    _set_writable_cache_dirs(request.output_path.parent)
    started = time.monotonic()
    if request.fixture_sleep_sec > 0.0:
        time.sleep(request.fixture_sleep_sec)

    try:
        payload = _run_real_probe(request, started)
    except Exception as exc:  # noqa: BLE001 - child boundary must serialize import/runtime failures.
        payload = _child_error_payload(exc, started)
        write_json_evidence(request.output_path, payload)
        print(json.dumps(payload, sort_keys=True), file=sys.stderr)
        return 1

    write_json_evidence(request.output_path, payload)
    print(json.dumps(payload, sort_keys=True))
    return 0


def _run_real_probe(request: ChildProbeRequest, started: float) -> JsonObject:
    import_started = time.monotonic()
    probe_renderer = "none" if request.api_report and request.renderer == "auto" else request.renderer
    glfw = prepare_glfw_platform(request.headless, probe_renderer)
    flygym = importlib.import_module("flygym")
    mujoco = importlib.import_module("mujoco")
    import_latency = time.monotonic() - import_started
    renderer_selection = select_renderer(request.headless, probe_renderer)
    simulation = _run_mujoco_step_probe(mujoco, request.steps)
    renderer = _run_renderer_probe(mujoco, renderer_selection.effective)
    viewer = _run_viewer_probe(request.headless)
    payload: JsonObject = {
        "probe_stage": "complete",
        "duration_sec": time.monotonic() - started,
        "python": sys.executable,
        "platform": platform.platform(),
        "versions": {"flygym": _package_version("flygym"), "mujoco": _package_version("mujoco"), "python": platform.python_version()},
        "imports": {"flygym_module": getattr(flygym, "__name__", "flygym"), "mujoco_module": getattr(mujoco, "__name__", "mujoco"), "latency_sec": import_latency},
        "simulation": simulation,
        "renderer": renderer,
        "renderer_selection": renderer_selection.to_json(),
        "viewer": viewer,
        "glfw": glfw,
        "cache_dirs": _cache_dirs_json(),
    }
    if request.api_report:
        report = build_installed_api_report(flygym, mujoco)
        artifacts = write_api_artifacts(report, request.output_path.parent, Path.cwd() / "docs/runtime/flygym_api_probe.md")
        payload["api_report"] = report
        payload["api_report_path"] = str(artifacts.json_path)
        payload["api_report_doc"] = str(artifacts.markdown_path)
    return payload


def _run_mujoco_step_probe(mujoco_module, steps: int) -> JsonObject:
    xml = (
        "<mujoco model='digital_fruit_fly_probe'><option timestep='0.001'/>"
        "<worldbody><body name='probe_body' pos='0 0 0.05'><joint name='free' type='free'/>"
        "<geom name='probe_geom' type='sphere' size='0.01' mass='0.001'/></body></worldbody></mujoco>"
    )
    model = mujoco_module.MjModel.from_xml_string(xml)
    data = mujoco_module.MjData(model)
    for _ in range(steps):
        mujoco_module.mj_step(model, data)
    return {"status": "ok", "engine": "mujoco", "steps": steps, "time": float(data.time), "nq": int(model.nq), "nv": int(model.nv)}


def _run_renderer_probe(mujoco_module, renderer: str) -> JsonObject:
    if renderer == "none":
        return {"status": "skipped", "renderer": renderer}
    if renderer not in ("auto", "none"):
        os.environ.setdefault("MUJOCO_GL", renderer)
    xml = "<mujoco><worldbody><geom type='sphere' size='0.01'/></worldbody></mujoco>"
    model = mujoco_module.MjModel.from_xml_string(xml)
    data = mujoco_module.MjData(model)
    renderer_obj = mujoco_module.Renderer(model, height=16, width=16)
    try:
        renderer_obj.update_scene(data)
        pixels = renderer_obj.render()
        return {"status": "ok", "renderer": renderer, "height": int(pixels.shape[0]), "width": int(pixels.shape[1])}
    finally:
        renderer_obj.close()


def _run_viewer_probe(headless: bool) -> JsonObject:
    started = time.monotonic()
    try:
        importlib.import_module("mujoco.viewer")
    except ImportError as exc:
        return {"status": "unavailable", "error": str(exc)}
    status = "available_headless_skipped" if headless else "available_not_launched"
    return {"status": status, "latency_sec": time.monotonic() - started}


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _child_error_payload(exc: Exception, started: float) -> JsonObject:
    return {"status": "failed", "probe_stage": "child", "duration_sec": time.monotonic() - started, "error_type": type(exc).__name__, "error": str(exc), "python": sys.executable, "platform": platform.platform(), "cache_dirs": _cache_dirs_json()}


def _record_argument_failure(request: BodyProbeRequest, message: str) -> ProbeOutcome:
    payload: JsonObject = {"script": "smoke_body", "status": "failed", "exit_code": 2, "error": message, "probe_stage": "argument", "config": str(request.config_path)}
    write_json_evidence(request.output_dir / "body_env_error.json", payload)
    write_json_evidence(request.evidence_path, payload)
    return ProbeOutcome(2, payload, request.evidence_path)


def _record_child_failure(request: BodyProbeRequest, result) -> ProbeOutcome:
    child_result = request.output_dir / CHILD_RESULT
    command = _child_command(request, child_result)
    child_payload = _read_child_payload(child_result) if child_result.exists() else {}
    status = "timeout" if result.timed_out else "failed"
    message = "FlyGym/MuJoCo probe timed out" if result.timed_out else "FlyGym/MuJoCo probe failed"
    payload: JsonObject = {"script": "smoke_body", "status": status, "severity": "P0", "exit_code": result.exit_code, "timed_out": result.timed_out, "probe_stage": child_payload.get("probe_stage", "fixture" if request.fixture_sleep_sec > 0.0 else "child"), "error": child_payload.get("error", message), "error_type": child_payload.get("error_type", "TimeoutExpired" if result.timed_out else "ChildProbeFailed"), "config": str(request.config_path), "reproduction_command": " ".join(command), "stdout": result.stdout, "stderr": result.stderr, "child_payload": child_payload}
    write_json_evidence(request.output_dir / "body_env_error.json", payload)
    write_json_evidence(request.evidence_path, payload)
    return ProbeOutcome(TIMEOUT_EXIT_CODE if result.timed_out else result.exit_code, payload, request.evidence_path)


def _read_child_payload(path: Path) -> JsonObject:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return raw
    return {"status": "failed", "error": "child payload was not a JSON object"}


def _child_command(request: BodyProbeRequest, child_result: Path) -> tuple[str, ...]:
    command = (
        sys.executable,
        "-m",
        "digital_fruit_fly.body.flygym_probe",
        "--child-probe",
        "--child-output",
        str(child_result),
        "--steps",
        str(request.steps),
        "--renderer",
        request.renderer,
    )
    if request.headless:
        command = (*command, "--headless")
    if request.api_report:
        command = (*command, "--api-report")
    if request.fixture_sleep_sec > 0.0:
        command = (*command, "--fixture-sleep-sec", str(request.fixture_sleep_sec))
    return command


def _child_env() -> dict[str, str]:
    env = dict(os.environ)
    src_path = str(Path(__file__).resolve().parents[2])
    current = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src_path if current is None else f"{src_path}{os.pathsep}{current}"
    return env


def _set_writable_cache_dirs(output_dir: Path) -> None:
    cache_root = output_dir / "cache"
    for name in ("matplotlib", "xdg", "numba"):
        (cache_root / name).mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(cache_root / "matplotlib")
    os.environ["XDG_CACHE_HOME"] = str(cache_root / "xdg")
    os.environ["NUMBA_CACHE_DIR"] = str(cache_root / "numba")


def _cache_dirs_json() -> JsonObject:
    return {"MPLCONFIGDIR": os.environ.get("MPLCONFIGDIR", ""), "XDG_CACHE_HOME": os.environ.get("XDG_CACHE_HOME", ""), "NUMBA_CACHE_DIR": os.environ.get("NUMBA_CACHE_DIR", ""), "MUJOCO_GL": os.environ.get("MUJOCO_GL", "")}


def _parse_child_args(argv: Sequence[str]) -> ChildProbeRequest:
    parser = argparse.ArgumentParser(description="Internal FlyGym child probe.")
    parser.add_argument("--child-probe", action="store_true")
    parser.add_argument("--child-output", type=Path, required=True)
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--renderer", default="auto")
    parser.add_argument("--api-report", action="store_true")
    parser.add_argument("--fixture-sleep-sec", type=float, default=0.0)
    args = parser.parse_args(argv)
    return ChildProbeRequest(args.child_output, args.steps, args.headless, args.renderer, args.api_report, args.fixture_sleep_sec)


def main(argv: Sequence[str] | None = None) -> int:
    child_request = _parse_child_args(sys.argv[1:] if argv is None else argv)
    return run_child_probe(child_request)


if __name__ == "__main__":
    raise SystemExit(main())
