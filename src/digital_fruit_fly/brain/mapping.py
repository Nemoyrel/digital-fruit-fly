from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from digital_fruit_fly.runtime.timeouts import JsonObject, JsonValue


@dataclass(frozen=True)
class MappingValidationError(Exception):
    path: Path
    reason: str

    def __str__(self) -> str:
        return f"{self.path}: {self.reason}"


@dataclass(frozen=True)
class ChannelMapping:
    kind: str
    channel_name: str
    flywire_ids: Tuple[int, ...]
    brain_index_resolution_status: str
    sign: str
    normalization: str
    biologically_curated: bool
    provisional: bool
    source_status: str
    rationale: str


@dataclass(frozen=True)
class NeuralMapping:
    schema_version: str
    mapping_version: str
    sensory_channels: Tuple[ChannelMapping, ...]
    motor_readout_groups: Tuple[ChannelMapping, ...]

    @property
    def channels(self) -> Tuple[ChannelMapping, ...]:
        return self.sensory_channels + self.motor_readout_groups

    @property
    def configured_flywire_ids(self) -> Tuple[int, ...]:
        return tuple(flywire_id for channel in self.channels for flywire_id in channel.flywire_ids)


@dataclass(frozen=True)
class ChannelResolution:
    kind: str
    channel_name: str
    flywire_ids: Tuple[int, ...]
    brian_indices: Tuple[int, ...]
    missing_flywire_ids: Tuple[int, ...]
    brain_index_resolution_status: str
    biologically_curated: bool
    provisional: bool
    source_status: str
    sign: str
    normalization: str
    rationale: str

    @property
    def usable(self) -> bool:
        return self.brain_index_resolution_status == "resolved"

    def to_json(self) -> JsonObject:
        return {
            "kind": self.kind,
            "channel_name": self.channel_name,
            "flywire_ids": list(self.flywire_ids),
            "brian_indices": list(self.brian_indices),
            "missing_flywire_ids": list(self.missing_flywire_ids),
            "brain_index_resolution_status": self.brain_index_resolution_status,
            "usable": self.usable,
            "biologically_curated": self.biologically_curated,
            "provisional": self.provisional,
            "source_status": self.source_status,
            "sign": self.sign,
            "normalization": self.normalization,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class MappingValidationResult:
    schema_version: str
    mapping_version: str
    channels: Tuple[ChannelResolution, ...]

    @property
    def ok(self) -> bool:
        return len(self.unusable_channels) == 0

    @property
    def channel_names(self) -> Tuple[str, ...]:
        return tuple(channel.channel_name for channel in self.channels)

    @property
    def unusable_channels(self) -> Tuple[ChannelResolution, ...]:
        return tuple(channel for channel in self.channels if not channel.usable)

    def failure_summary(self) -> str:
        failures = [
            f"{channel.channel_name}: missing FlyWire IDs "
            f"{', '.join(str(flywire_id) for flywire_id in channel.missing_flywire_ids)}"
            for channel in self.unusable_channels
        ]
        return "; ".join(failures)

    def to_json(self) -> JsonObject:
        return {
            "schema_version": self.schema_version,
            "mapping_version": self.mapping_version,
            "status": "ok" if self.ok else "failed",
            "channel_count": len(self.channels),
            "unusable_channel_count": len(self.unusable_channels),
            "channels": [channel.to_json() for channel in self.channels],
            "failure_summary": self.failure_summary(),
        }


def load_neural_mapping(path: Path) -> NeuralMapping:
    try:
        raw: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MappingValidationError(path, "mapping file does not exist") from exc
    except json.JSONDecodeError as exc:
        raise MappingValidationError(path, f"mapping JSON-compatible YAML is malformed: {exc}") from exc
    root = _require_object(raw, path)
    sensory = _parse_channels(_require_list(root, "sensory_channels", path), "sensory", path)
    motor = _parse_channels(_require_list(root, "motor_readout_groups", path), "motor", path)
    return NeuralMapping(
        schema_version=_require_str(root, "schema_version", path),
        mapping_version=_require_str(root, "mapping_version", path),
        sensory_channels=sensory,
        motor_readout_groups=motor,
    )


def load_brian_index_map(completeness_path: Path) -> Dict[int, int]:
    indices: Dict[int, int] = {}
    try:
        with completeness_path.open(newline="", encoding="utf-8") as file:
            reader = csv.reader(file)
            next(reader, None)
            for brian_index, row in enumerate(reader):
                flywire_id = _read_flywire_id(row, completeness_path)
                indices[flywire_id] = brian_index
    except FileNotFoundError as exc:
        raise MappingValidationError(completeness_path, "completeness CSV does not exist") from exc
    if len(indices) == 0:
        raise MappingValidationError(completeness_path, "completeness CSV contains no FlyWire IDs")
    return indices


def validate_neural_mapping(
    mapping: NeuralMapping, brian_indices: Dict[int, int]
) -> MappingValidationResult:
    channels = tuple(_resolve_channel(channel, brian_indices) for channel in mapping.channels)
    return MappingValidationResult(
        schema_version=mapping.schema_version,
        mapping_version=mapping.mapping_version,
        channels=channels,
    )


def require_configured_flywire_ids(mapping: NeuralMapping, flywire_ids: Sequence[int]) -> None:
    configured = set(mapping.configured_flywire_ids)
    missing = tuple(flywire_id for flywire_id in flywire_ids if flywire_id not in configured)
    if len(missing) > 0:
        missing_text = ", ".join(str(flywire_id) for flywire_id in missing)
        raise MappingValidationError(Path("brain_mapping"), f"FlyWire IDs not configured: {missing_text}")


def _parse_channels(raw_channels: List[JsonValue], kind: str, path: Path) -> Tuple[ChannelMapping, ...]:
    channels = tuple(_parse_channel(_require_object(raw, path), kind, path) for raw in raw_channels)
    names = [channel.channel_name for channel in channels]
    duplicates = _duplicates(names)
    if len(duplicates) > 0:
        raise MappingValidationError(path, f"duplicate channel names: {', '.join(duplicates)}")
    return channels


def _parse_channel(raw: JsonObject, kind: str, path: Path) -> ChannelMapping:
    return ChannelMapping(
        kind=kind,
        channel_name=_require_str(raw, "channel_name", path),
        flywire_ids=_require_int_tuple(raw, "flywire_ids", path),
        brain_index_resolution_status=_require_str(raw, "brain_index_resolution_status", path),
        sign=_require_str(raw, "sign", path),
        normalization=_require_str(raw, "normalization", path),
        biologically_curated=_require_bool(raw, "biologically_curated", path),
        provisional=_require_bool(raw, "provisional", path),
        source_status=_require_str(raw, "source_status", path),
        rationale=_require_str(raw, "rationale", path),
    )


def _resolve_channel(channel: ChannelMapping, brian_indices: Dict[int, int]) -> ChannelResolution:
    present = tuple(brian_indices[flywire_id] for flywire_id in channel.flywire_ids if flywire_id in brian_indices)
    missing = tuple(flywire_id for flywire_id in channel.flywire_ids if flywire_id not in brian_indices)
    status = "resolved" if len(missing) == 0 else "unusable"
    return ChannelResolution(
        kind=channel.kind,
        channel_name=channel.channel_name,
        flywire_ids=channel.flywire_ids,
        brian_indices=present,
        missing_flywire_ids=missing,
        brain_index_resolution_status=status,
        biologically_curated=channel.biologically_curated,
        provisional=channel.provisional,
        source_status=channel.source_status,
        sign=channel.sign,
        normalization=channel.normalization,
        rationale=channel.rationale,
    )


def _read_flywire_id(row: List[str], path: Path) -> int:
    if len(row) == 0:
        raise MappingValidationError(path, "completeness CSV contains an empty row")
    raw_id = row[0].strip()
    if not raw_id.isdecimal():
        raise MappingValidationError(path, f"invalid FlyWire ID in completeness CSV: {raw_id}")
    return int(raw_id)


def _require_object(raw: JsonValue, path: Path) -> JsonObject:
    if not isinstance(raw, dict):
        raise MappingValidationError(path, "mapping section must be an object")
    return raw


def _require_list(raw: JsonObject, key: str, path: Path) -> List[JsonValue]:
    value = _require_value(raw, key, path)
    if not isinstance(value, list):
        raise MappingValidationError(path, f"'{key}' must be a list")
    return value


def _require_str(raw: JsonObject, key: str, path: Path) -> str:
    value = _require_value(raw, key, path)
    if not isinstance(value, str) or value == "":
        raise MappingValidationError(path, f"'{key}' must be a non-empty string")
    return value


def _require_bool(raw: JsonObject, key: str, path: Path) -> bool:
    value = _require_value(raw, key, path)
    if not isinstance(value, bool):
        raise MappingValidationError(path, f"'{key}' must be a boolean")
    return value


def _require_int_tuple(raw: JsonObject, key: str, path: Path) -> Tuple[int, ...]:
    value = _require_value(raw, key, path)
    if not isinstance(value, list) or len(value) == 0:
        raise MappingValidationError(path, f"'{key}' must be a non-empty list")
    ids: List[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            raise MappingValidationError(path, f"'{key}' must contain integer FlyWire IDs")
        ids.append(item)
    return tuple(ids)


def _require_value(raw: JsonObject, key: str, path: Path) -> JsonValue:
    try:
        return raw[key]
    except KeyError as exc:
        raise MappingValidationError(path, f"missing required key '{key}'") from exc


def _duplicates(values: Iterable[str]) -> Tuple[str, ...]:
    seen: set[str] = set()
    duplicated: List[str] = []
    for value in values:
        if value in seen:
            duplicated.append(value)
        seen.add(value)
    return tuple(duplicated)
