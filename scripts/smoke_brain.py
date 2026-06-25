#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
# ─── How to run ───
# python3 scripts/smoke_brain.py --config configs/brain_smoke.yaml --output outputs/smoke/brain

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
MPLCONFIGDIR = REPO_ROOT / "outputs/smoke/brain/mplconfig"
MPLCONFIGDIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIGDIR))
sys.path.insert(0, str(REPO_ROOT / "src"))

from digital_fruit_fly.runtime.config import ConfigError, load_config  # noqa: E402
from digital_fruit_fly.runtime.timeouts import JsonObject, write_json_evidence  # noqa: E402
from digital_fruit_fly.brain.shiu_adapter import (  # noqa: E402
    ShiuDiscoveryError,
    discover_shiu_assets,
    extract_sugar_neuron_ids,
)
from digital_fruit_fly.brain.mapping import (  # noqa: E402
    MappingValidationError,
    load_brian_index_map,
    load_neural_mapping,
    validate_neural_mapping,
)
from digital_fruit_fly.brain.tickable_network import (  # noqa: E402
    ChannelConfig,
    ReadoutConfig,
    TickableBrainConfig,
    TickableBrainError,
    TickableBrainNetwork,
)


def main() -> int:
    args, unknown_args = _parse_args()
    if args.timeout_sec <= 0.0:
        return _fail(
            BrainSmokeFailure(
                message="timeout-sec must be positive",
                exit_code=2,
                evidence_path=args.evidence,
                output_dir=args.output,
                unknown_args=tuple(unknown_args),
            )
        )
    started = time.monotonic()
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        return _fail(
            BrainSmokeFailure(
                message=str(exc),
                exit_code=2,
                evidence_path=args.evidence,
                output_dir=args.output,
                unknown_args=tuple(unknown_args),
            )
        )

    mapping_validation: JsonObject = {"requested": args.validate_mapping, "status": "not_run"}
    try:
        repo_path = _resolve_repo_path(config.brain.shiu_repo_path)
        sugar_ids = extract_sugar_neuron_ids(repo_path / "example.ipynb")
        assets = discover_shiu_assets(
            repo_path=repo_path,
            completeness_path=_resolve_repo_path(config.brain.completeness_path),
            connectivity_path=_resolve_repo_path(config.brain.connectivity_path),
            sugar_neuron_ids=sugar_ids,
        )
        _validate_brain_python(Path(config.brain.python))
        if args.validate_mapping:
            mapping = load_neural_mapping(_resolve_repo_path(config.brain.mapping_path))
            brian_indices = load_brian_index_map(assets.selected.completeness_path)
            validation = validate_neural_mapping(mapping, brian_indices)
            mapping_validation = validation.to_json()
            args.output.mkdir(parents=True, exist_ok=True)
            write_json_evidence(args.output / "mapping_validation.json", mapping_validation)
            if not validation.ok:
                return _fail(
                    BrainSmokeFailure(
                        message=f"mapping validation failed: {validation.failure_summary()}",
                        exit_code=2,
                        evidence_path=args.evidence,
                        output_dir=args.output,
                        unknown_args=tuple(unknown_args),
                        details={"mapping_validation": mapping_validation},
                    )
                )
        versions = _collect_versions()
        toy_spike_count = _run_brian2_toy_network()
        tickable_payload: JsonObject = {"requested": args.tickable, "status": "not_run"}
        if args.tickable:
            tickable_payload = _run_tickable_fixture(args.ticks, args.output, config.tick_ms)
    except (BrainSmokeError, MappingValidationError, ShiuDiscoveryError, TickableBrainError) as exc:
        return _fail(
            BrainSmokeFailure(
                message=str(exc),
                exit_code=2,
                evidence_path=args.evidence,
                output_dir=args.output,
                unknown_args=tuple(unknown_args),
            )
        )

    args.output.mkdir(parents=True, exist_ok=True)
    payload: JsonObject = {
        "script": "smoke_brain",
        "status": "ok",
        "config": str(args.config),
        "brain_python": config.brain.python,
        "python_executable": sys.executable,
        "versions": versions,
        "shiu": assets.to_json(),
        "mapping_validation": mapping_validation,
        "sugar_neuron_ids": list(sugar_ids),
        "toy_network": {"spike_count": toy_spike_count},
        "tickable": tickable_payload,
        "full_shiu": {"requested": args.full_shiu, "status": "not_run"},
        "duration_sec": time.monotonic() - started,
        "unknown_args": list(unknown_args),
    }
    write_json_evidence(args.output / "brain_env.json", payload)
    write_json_evidence(args.output / "summary.json", payload)
    write_json_evidence(args.evidence, payload)
    print(json.dumps(payload, sort_keys=True))
    return 0


def _parse_args() -> Tuple[argparse.Namespace, List[str]]:
    parser = argparse.ArgumentParser(description="Run a light brain smoke probe.")
    parser.add_argument("--config", type=Path, default=Path("configs/brain_smoke.yaml"))
    parser.add_argument("--output", type=Path, default=Path("outputs/smoke/brain"))
    parser.add_argument("--timeout-sec", type=float, default=10.0)
    parser.add_argument("--evidence", type=Path, default=Path(".omo/evidence/smoke_brain_latest.json"))
    parser.add_argument("--full-shiu", action="store_true")
    parser.add_argument("--validate-mapping", action="store_true")
    parser.add_argument("--tickable", action="store_true")
    parser.add_argument("--ticks", type=int, default=10)
    return parser.parse_known_args()


class BrainSmokeError(Exception):
    pass


@dataclass(frozen=True)
class BrainSmokeFailure:
    message: str
    exit_code: int
    evidence_path: Path
    output_dir: Path
    unknown_args: Tuple[str, ...]
    details: Optional[JsonObject] = None


def _resolve_repo_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _validate_brain_python(expected_python: Path) -> None:
    if not expected_python.is_file():
        raise BrainSmokeError(f"brain_env python is missing: {expected_python}")
    expected = expected_python.resolve()
    actual = Path(sys.executable).resolve()
    if actual != expected:
        raise BrainSmokeError(
            f"smoke_brain must run under brain_env python: expected {expected}, got {actual}"
        )


def _collect_versions() -> JsonObject:
    return {
        "python": sys.version.split()[0],
        "brian2": _package_version("brian2"),
        "pandas": _package_version("pandas"),
        "pyarrow": _package_version("pyarrow"),
    }


def _package_version(package_name: str) -> str:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError as exc:
        raise BrainSmokeError(f"required brain_env package is missing: {package_name}") from exc


def _run_brian2_toy_network() -> int:
    try:
        import brian2
    except ImportError as exc:
        raise BrainSmokeError("required brain_env module is missing: brian2") from exc

    brian2.prefs.codegen.target = "numpy"
    brian2.start_scope()
    neurons = brian2.NeuronGroup(
        1,
        "dv/dt = 20*mV/ms : volt",
        threshold="v > -50*mV",
        reset="v = -60*mV",
        method="euler",
        name="brain_smoke_neurons",
    )
    neurons.v = -60 * brian2.mV
    monitor = brian2.SpikeMonitor(neurons, name="brain_smoke_spikes")
    network = brian2.Network(neurons, monitor)
    network.run(5 * brian2.ms)
    return int(monitor.count[0])


def _run_tickable_fixture(ticks: int, output_dir: Path, tick_ms: float) -> JsonObject:
    if ticks <= 0:
        raise BrainSmokeError("ticks must be positive")
    config = TickableBrainConfig(
        tick_ms=tick_ms,
        sensory_channels=(ChannelConfig(name="sugar_grn", target_indices=(0,), max_rate_hz=250.0),),
        readout_groups=(ReadoutConfig(name="fixture_output", neuron_indices=(0,)),),
    )
    network = TickableBrainNetwork.fixture(config)
    rows: List[JsonObject] = []
    started = time.monotonic()
    for tick_index in range(ticks):
        drive = 1.0 if tick_index % 2 == 0 else 0.25
        rows.append(network.tick({"sugar_grn": drive}).to_json())
    total_wall_time = time.monotonic() - started
    tick_dir = output_dir / "tickable"
    tick_dir.mkdir(parents=True, exist_ok=True)
    tick_jsonl = tick_dir / "ticks.jsonl"
    with tick_jsonl.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, sort_keys=True) + "\n")
    summary: JsonObject = {
        "requested": True,
        "status": "ok",
        "mode": "fixture",
        "ticks": ticks,
        "tick_ms": tick_ms,
        "total_wall_time_sec": total_wall_time,
        "mean_tick_wall_time_sec": total_wall_time / ticks,
        "tick_jsonl": str(tick_jsonl),
        "first_tick": rows[0],
        "last_tick": rows[-1],
    }
    write_json_evidence(tick_dir / "summary.json", summary)
    return summary


def _fail(request: BrainSmokeFailure) -> int:
    request.output_dir.mkdir(parents=True, exist_ok=True)
    payload: JsonObject = {
        "script": "smoke_brain",
        "status": "failed",
        "exit_code": request.exit_code,
        "error": request.message,
        "unknown_args": list(request.unknown_args),
    }
    if request.details is not None:
        payload.update(request.details)
    write_json_evidence(request.output_dir / "error.json", payload)
    write_json_evidence(request.evidence_path, payload)
    print(json.dumps(payload, sort_keys=True), file=sys.stderr)
    return request.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
