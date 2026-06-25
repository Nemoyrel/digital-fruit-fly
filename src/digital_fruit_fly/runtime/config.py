from __future__ import annotations

from dataclasses import dataclass; from pathlib import Path; from typing import Dict, Final, Optional, Union


BRAIN_PYTHON: Final = "/opt/miniconda3/envs/brain_env/bin/python"; BODY_PYTHON: Final = "/opt/miniconda3/envs/flygym_env/bin/python"

ConfigScalar = Union[str, int, float, bool]; ConfigValue = Union[ConfigScalar, Dict[str, "ConfigValue"]]; ConfigMap = Dict[str, ConfigValue]


@dataclass(frozen=True)
class ConfigError(Exception):
    path: str; reason: str; line: Optional[int] = None

    def __str__(self) -> str:
        location = self.path if self.line is None else f"{self.path}:{self.line}"
        return f"{location}: {self.reason}"


@dataclass(frozen=True)
class SugarConfig: center_x_mm: float; center_y_mm: float; radius: float; cue_radius: float


@dataclass(frozen=True)
class DustConfig: accumulation_rate_per_sec: float; threshold: float; cleaning_rate_per_sec: float


@dataclass(frozen=True)
class ArenaConfig: width_mm: float; height_mm: float; sugar: SugarConfig; dust: DustConfig


@dataclass(frozen=True)
class ProcessConfig: host: str; brain_port: int; body_port: int


@dataclass(frozen=True)
class CameraConfig: enabled: bool; fps: int; width_px: int; height_px: int; follow_fly: bool


@dataclass(frozen=True)
class BrainConfig: python: str; mapping_path: str; shiu_repo_path: str; completeness_path: str; connectivity_path: str


@dataclass(frozen=True)
class BodyConfig: python: str


@dataclass(frozen=True)
class DecoderConfig: locomotion_threshold: float; turn_threshold: float; feeding_threshold: float; grooming_threshold: float; stop_threshold: float


@dataclass(frozen=True)
class RuntimeConfig: tick_ms: int; duration_sec: float; seed: int; arena: ArenaConfig; process: ProcessConfig; camera: CameraConfig; brain: BrainConfig; body: BodyConfig; decoder: DecoderConfig


def load_config(path: Union[str, Path]) -> RuntimeConfig:
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(str(source), "config file does not exist") from exc

    return _build_runtime_config(_parse_yaml_subset(text, source), source)


def _parse_yaml_subset(text: str, source: Path) -> ConfigMap:
    root: ConfigMap = {}
    stack = [(-1, root)]

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if stripped == "" or stripped.startswith("#"):
            continue
        if "\t" in raw_line:
            raise ConfigError(str(source), "tabs are not supported", line_number)

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent % 2 != 0:
            raise ConfigError(str(source), "indentation must use two spaces", line_number)
        if indent > stack[-1][0] + 2:
            raise ConfigError(str(source), "indentation skipped a level", line_number)

        while indent <= stack[-1][0]:
            stack.pop()

        if ":" not in stripped:
            raise ConfigError(str(source), "expected 'key: value'", line_number)
        key, value_text = stripped.split(":", 1)
        key = key.strip()
        value_text = value_text.strip()
        if key == "":
            raise ConfigError(str(source), "empty keys are not supported", line_number)

        parent = stack[-1][1]
        if value_text == "":
            child: ConfigMap = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(value_text, source, line_number)

    return root


def _parse_scalar(value: str, source: Path, line_number: int) -> ConfigScalar:
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if value.startswith(("'", '"')) or value.endswith(("'", '"')):
        if len(value) < 2 or value[0] != value[-1] or value[0] not in ("'", '"'):
            raise ConfigError(str(source), "malformed quoted string", line_number)
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value

def _build_runtime_config(raw: ConfigMap, source: Path) -> RuntimeConfig:
    arena = _build_arena(_require_map(raw, "arena", source), source)
    process = _build_process(_require_map(raw, "process", source), source)
    camera = _build_camera(_require_map(raw, "camera", source), source)
    brain = _build_brain(_require_map(raw, "brain", source), source)
    body = BodyConfig(python=_require_str(_require_map(raw, "body", source), "python", source))
    decoder = _build_decoder(_require_map(raw, "decoder", source), source)

    config = RuntimeConfig(
        tick_ms=_require_int(raw, "tick_ms", source),
        duration_sec=_require_float(raw, "duration_sec", source),
        seed=_require_int(raw, "seed", source),
        arena=arena,
        process=process,
        camera=camera,
        brain=brain,
        body=body,
        decoder=decoder,
    )
    _validate_runtime(config, source)
    return config


def _build_arena(raw: ConfigMap, source: Path) -> ArenaConfig:
    sugar = _build_sugar(_require_map(raw, "sugar", source), source)
    dust = _build_dust(_require_map(raw, "dust", source), source)
    return ArenaConfig(
        width_mm=_require_float(raw, "width_mm", source),
        height_mm=_require_float(raw, "height_mm", source),
        sugar=sugar,
        dust=dust,
    )


def _build_sugar(raw: ConfigMap, source: Path) -> SugarConfig:
    return SugarConfig(
        center_x_mm=_require_float(raw, "center_x_mm", source),
        center_y_mm=_require_float(raw, "center_y_mm", source),
        radius=_require_float(raw, "radius", source),
        cue_radius=_require_float(raw, "cue_radius", source),
    )


def _build_dust(raw: ConfigMap, source: Path) -> DustConfig:
    return DustConfig(
        accumulation_rate_per_sec=_require_float(
            raw, "accumulation_rate_per_sec", source
        ),
        threshold=_require_float(raw, "threshold", source),
        cleaning_rate_per_sec=_require_float(raw, "cleaning_rate_per_sec", source),
    )


def _build_process(raw: ConfigMap, source: Path) -> ProcessConfig:
    return ProcessConfig(
        host=_require_str(raw, "host", source),
        brain_port=_require_int(raw, "brain_port", source),
        body_port=_require_int(raw, "body_port", source),
    )


def _build_camera(raw: ConfigMap, source: Path) -> CameraConfig:
    return CameraConfig(
        enabled=_require_bool(raw, "enabled", source),
        fps=_require_int(raw, "fps", source),
        width_px=_require_int(raw, "width_px", source),
        height_px=_require_int(raw, "height_px", source),
        follow_fly=_require_bool(raw, "follow_fly", source),
    )


def _build_brain(raw: ConfigMap, source: Path) -> BrainConfig:
    return BrainConfig(
        python=_require_str(raw, "python", source),
        mapping_path=_require_str(raw, "mapping_path", source),
        shiu_repo_path=_require_str(raw, "shiu_repo_path", source),
        completeness_path=_require_str(raw, "completeness_path", source),
        connectivity_path=_require_str(raw, "connectivity_path", source),
    )


def _build_decoder(raw: ConfigMap, source: Path) -> DecoderConfig:
    return DecoderConfig(
        locomotion_threshold=_require_float(raw, "locomotion_threshold", source),
        turn_threshold=_require_float(raw, "turn_threshold", source),
        feeding_threshold=_require_float(raw, "feeding_threshold", source),
        grooming_threshold=_require_float(raw, "grooming_threshold", source),
        stop_threshold=_require_float(raw, "stop_threshold", source),
    )


def _require_map(raw: ConfigMap, key: str, source: Path) -> ConfigMap:
    try:
        value = raw[key]
    except KeyError as exc:
        raise ConfigError(str(source), f"missing required key '{key}'") from exc
    if not isinstance(value, dict):
        raise ConfigError(str(source), f"'{key}' must be a section")
    return value


def _require_str(raw: ConfigMap, key: str, source: Path) -> str:
    value = _require_value(raw, key, source)
    if not isinstance(value, str):
        raise ConfigError(str(source), f"'{key}' must be a string")
    if value == "":
        raise ConfigError(str(source), f"'{key}' must not be empty")
    return value


def _require_int(raw: ConfigMap, key: str, source: Path) -> int:
    value = _require_value(raw, key, source)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(str(source), f"'{key}' must be an integer")
    return value


def _require_float(raw: ConfigMap, key: str, source: Path) -> float:
    value = _require_value(raw, key, source)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(str(source), f"'{key}' must be numeric")
    return float(value)


def _require_bool(raw: ConfigMap, key: str, source: Path) -> bool:
    value = _require_value(raw, key, source)
    if not isinstance(value, bool):
        raise ConfigError(str(source), f"'{key}' must be true or false")
    return value


def _require_value(raw: ConfigMap, key: str, source: Path) -> ConfigValue:
    try:
        return raw[key]
    except KeyError as exc:
        raise ConfigError(str(source), f"missing required key '{key}'") from exc


def _validate_runtime(config: RuntimeConfig, source: Path) -> None:
    for name, value in (("tick_ms", config.tick_ms), ("duration_sec", config.duration_sec)):
        if value <= 0:
            raise ConfigError(str(source), f"{name} must be positive")
    if config.seed < 0:
        raise ConfigError(str(source), "seed must be non-negative")
    _validate_arena(config.arena, source)
    _validate_process(config.process, source)
    _validate_camera(config.camera, source)
    _validate_env_paths(config, source)
    _validate_decoder(config.decoder, source)


def _validate_arena(arena: ArenaConfig, source: Path) -> None:
    if arena.width_mm <= 0.0 or arena.height_mm <= 0.0:
        raise ConfigError(str(source), "arena dimensions must be positive")
    sugar = arena.sugar
    if sugar.radius <= 0.0:
        raise ConfigError(str(source), "sugar radius must be positive")
    if sugar.cue_radius <= sugar.radius:
        raise ConfigError(str(source), "sugar cue_radius must be greater than radius")
    if not 0.0 <= sugar.center_x_mm <= arena.width_mm:
        raise ConfigError(str(source), "sugar center_x_mm must be inside the arena")
    if not 0.0 <= sugar.center_y_mm <= arena.height_mm:
        raise ConfigError(str(source), "sugar center_y_mm must be inside the arena")
    dust = arena.dust
    for name, value in (("dust accumulation rate", dust.accumulation_rate_per_sec), ("dust cleaning rate", dust.cleaning_rate_per_sec)):
        if value < 0.0:
            raise ConfigError(str(source), f"{name} must be non-negative")
    if dust.threshold <= 0.0:
        raise ConfigError(str(source), "dust threshold must be positive")


def _validate_process(process: ProcessConfig, source: Path) -> None:
    if process.host == "":
        raise ConfigError(str(source), "process host must not be empty")
    for name, port in (("brain_port", process.brain_port), ("body_port", process.body_port)):
        if port < 1 or port > 65535:
            raise ConfigError(str(source), f"{name} must be between 1 and 65535")
    if process.brain_port == process.body_port:
        raise ConfigError(str(source), "brain_port and body_port must differ")

def _validate_camera(camera: CameraConfig, source: Path) -> None:
    if camera.fps <= 0:
        raise ConfigError(str(source), "camera fps must be positive")
    if camera.width_px <= 0 or camera.height_px <= 0:
        raise ConfigError(str(source), "camera dimensions must be positive")


def _validate_env_paths(config: RuntimeConfig, source: Path) -> None:
    if config.brain.python != BRAIN_PYTHON:
        raise ConfigError(str(source), "brain python path must match README default")
    if config.body.python != BODY_PYTHON:
        raise ConfigError(str(source), "body python path must match README default")


def _validate_decoder(decoder: DecoderConfig, source: Path) -> None:
    for name, value in (
        ("locomotion_threshold", decoder.locomotion_threshold),
        ("turn_threshold", decoder.turn_threshold),
        ("feeding_threshold", decoder.feeding_threshold),
        ("grooming_threshold", decoder.grooming_threshold),
        ("stop_threshold", decoder.stop_threshold),
    ):
        if value < 0.0:
            raise ConfigError(str(source), f"{name} must be non-negative")
