from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, SupportsFloat, TypeAlias, runtime_checkable

from digital_fruit_fly.runtime.timeouts import JsonScalar, JsonValue


@runtime_checkable
class SupportsToList(Protocol):
    def tolist(self) -> JsonValue: ...


RawObservationValue: TypeAlias = None | bool | str | SupportsFloat | SupportsToList | Sequence["RawObservationValue"] | Mapping[str, "RawObservationValue"]


@dataclass(frozen=True, slots=True)
class MissingObservationField(Exception):
    category: str
    missing: tuple[str, ...]

    def __str__(self) -> str:
        return f"{self.category}: missing {', '.join(self.missing)}"


@dataclass(frozen=True, slots=True)
class ObservationValueError(Exception):
    category: str
    field: str
    reason: str

    def __str__(self) -> str:
        return f"{self.category}.{self.field}: {self.reason}"


def read_named(
    readout: RawObservationValue, order: tuple[str, ...], name: str
) -> RawObservationValue | None:
    if isinstance(readout, Mapping):
        return readout.get(name)
    items = sequence_items(readout)
    if items is None:
        return None
    try:
        index = order.index(name)
    except ValueError:
        return None
    return items[index] if index < len(items) else None


def optional_scalars(readout: RawObservationValue | None, category: str) -> tuple[float, ...]:
    return () if readout is None else scalars(readout, category)


def scalars(readout: RawObservationValue, category: str) -> tuple[float, ...]:
    if isinstance(readout, Mapping):
        return tuple(_contact_number(value, category, name) for name, value in readout.items())
    items = sequence_items(readout)
    if items is not None:
        return tuple(_contact_number(value, category, str(index)) for index, value in enumerate(items))
    raise ObservationValueError(category, category, "must be a mapping or sequence")


def optional_vectors(readout: RawObservationValue | None, category: str) -> tuple[tuple[float, ...], ...]:
    if readout is None:
        return ()
    if isinstance(readout, Mapping):
        return tuple(vector_components(value, category, name) for name, value in readout.items())
    items = sequence_items(readout)
    if items is not None:
        return tuple(vector_components(value, category, str(index)) for index, value in enumerate(items))
    raise ObservationValueError(category, category, "must be a mapping or sequence")


def vector3(name: str, value: RawObservationValue, category: str) -> list[JsonValue]:
    components = vector_components(value, category, name)
    if len(components) < 3:
        raise MissingObservationField(category, (name,))
    return [components[0], components[1], components[2]]


def vector_components(value: RawObservationValue, category: str, field: str) -> tuple[float, ...]:
    if isinstance(value, Mapping):
        return tuple(number(required_raw(value, key, category), category, field + "." + key) for key in ("x_mm", "y_mm", "z_mm"))
    items = sequence_items(value)
    if items is not None:
        return tuple(number(item, category, field) for item in items)
    raise ObservationValueError(category, field, "must be a vector sequence or mapping")


def json_scalar(value: RawObservationValue, category: str, field: str) -> JsonScalar:
    return value if value is None or isinstance(value, (bool, str)) else number(value, category, field)


def number(value: RawObservationValue, category: str, field: str) -> float:
    if value is None or isinstance(value, (bool, str, Mapping)) or sequence_items(value) is not None:
        raise ObservationValueError(category, field, "must be a finite number")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ObservationValueError(category, field, "must be a finite number") from exc
    if not math.isfinite(parsed):
        raise ObservationValueError(category, field, "must be finite")
    return parsed


def sequence_items(value: RawObservationValue) -> tuple[RawObservationValue, ...] | None:
    if isinstance(value, (str, bytes, bytearray, Mapping)):
        return None
    if isinstance(value, SupportsToList):
        return sequence_items(value.tolist())
    return tuple(value) if isinstance(value, Sequence) else None


def raw_mapping(raw: Mapping[str, RawObservationValue], key: str) -> Mapping[str, RawObservationValue]:
    value = required_raw(raw, key, key)
    if isinstance(value, Mapping):
        return value
    raise ObservationValueError(key, key, "must be a mapping")


def required_raw(raw: Mapping[str, RawObservationValue], key: str, category: str) -> RawObservationValue:
    if key not in raw:
        raise MissingObservationField(category, (key,))
    return raw[key]


def json_mapping(raw: Mapping[str, JsonValue], key: str) -> Mapping[str, JsonValue]:
    value = raw.get(key)
    if isinstance(value, dict):
        return value
    raise ObservationValueError("api_report", key, "must be an object")


def json_string_tuple(raw: Mapping[str, JsonValue], key: str) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ObservationValueError("api_report", key, "must be a list of strings")
    return tuple(value)


def json_bool(raw: Mapping[str, JsonValue], key: str) -> bool:
    value = raw.get(key)
    if isinstance(value, bool):
        return value
    raise ObservationValueError("api_report", key, "must be a boolean")


def mean_abs(values: tuple[float, ...]) -> float:
    return 0.0 if len(values) == 0 else sum(abs(value) for value in values) / len(values)


def _contact_number(value: RawObservationValue, category: str, field: str) -> float:
    return float(value) if isinstance(value, bool) else number(value, category, field)
