from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Literal, Type, Union


SCHEMA_VERSION = 1
FORBIDDEN_PAYLOAD_KEYS = frozenset(("groom_now", "feed_now"))

JsonScalar = Union[None, bool, int, float, str]
JsonValue = Union[JsonScalar, List["JsonValue"], Dict[str, "JsonValue"]]
JsonObject = Dict[str, JsonValue]
FrameType = Literal["hello", "sensory_frame", "brain_frame", "control_frame", "heartbeat", "error", "shutdown"]


@dataclass(frozen=True)
class FrameHeader:
    schema_version: int
    run_id: str
    frame_index: int
    simulation_time_s: float
    sent_monotonic_s: float


@dataclass(frozen=True, init=False)
class Hello(FrameHeader):
    role: str

    def __init__(
        self,
        schema_version: int = SCHEMA_VERSION,
        run_id: str = "",
        frame_index: int = 0,
        simulation_time_s: float = 0.0,
        sent_monotonic_s: float = 0.0,
        role: str = "unspecified",
    ) -> None:
        object.__setattr__(self, "schema_version", schema_version)
        object.__setattr__(self, "run_id", run_id)
        object.__setattr__(self, "frame_index", frame_index)
        object.__setattr__(self, "simulation_time_s", simulation_time_s)
        object.__setattr__(self, "sent_monotonic_s", sent_monotonic_s)
        object.__setattr__(self, "role", role)


@dataclass(frozen=True)
class PayloadFrame(FrameHeader):
    payload: JsonObject
    payload_checksum: str


@dataclass(frozen=True)
class SensoryFrame(PayloadFrame):
    pass


@dataclass(frozen=True)
class BrainFrame(PayloadFrame):
    pass


@dataclass(frozen=True)
class ControlFrame(PayloadFrame):
    pass


@dataclass(frozen=True)
class Heartbeat(FrameHeader):
    pass


@dataclass(frozen=True)
class ErrorFrame(FrameHeader):
    code: str
    message: str
    details: JsonObject


@dataclass(frozen=True)
class Shutdown(FrameHeader):
    reason: str


BridgeFrame = Union[Hello, SensoryFrame, BrainFrame, ControlFrame, Heartbeat, ErrorFrame, Shutdown]


class MessageCodecError(ValueError):
    """Raised when a local frame cannot be serialized."""


class _DecodeFrameError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def payload_checksum(payload: JsonObject) -> str:
    _ensure_json_object(payload, reject_shortcuts=False)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def encode_message(frame: BridgeFrame) -> bytes:
    return json.dumps(_frame_to_object(frame), sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def decode_message(data: bytes) -> BridgeFrame:
    try:
        raw = json.loads(data.decode("utf-8"), parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return _decode_error(exc)
    try:
        frame = _parse_object(raw)
    except _DecodeFrameError as exc:
        return _error_from_raw(raw, exc.code, exc.message)
    if _schema_version(raw) > SCHEMA_VERSION:
        return _error_from_raw(raw, "schema_version_unsupported", "unsupported schema version")
    return frame


encode_frame = encode_message
decode_frame = decode_message


def _reject_json_constant(value: str) -> None:
    raise ValueError("JSON constants are not supported: " + value)


def _parse_object(raw: JsonValue) -> BridgeFrame:
    if not isinstance(raw, dict):
        raise _DecodeFrameError("malformed_message", "message must be a JSON object")
    if _schema_version(raw) > SCHEMA_VERSION:
        return _error_from_raw(raw, "schema_version_unsupported", "unsupported schema version")
    parser = _PARSERS.get(_required_str(raw, "type"))
    if parser is None:
        raise _DecodeFrameError("unknown_frame_type", "unknown frame type")
    return parser(raw)


def _frame_to_object(frame: BridgeFrame) -> JsonObject:
    frame_type = _TYPE_BY_CLASS.get(frame.__class__)
    if frame_type is None:
        raise MessageCodecError("unsupported frame class")
    result = _header_object(frame, frame_type)
    result.update(_EXTRAS_BY_CLASS[frame.__class__](frame))
    return result


def _header_object(frame: FrameHeader, frame_type: FrameType) -> JsonObject:
    return {
        "type": frame_type,
        "schema_version": frame.schema_version,
        "run_id": frame.run_id,
        "frame_index": frame.frame_index,
        "simulation_time_s": frame.simulation_time_s,
        "sent_monotonic_s": frame.sent_monotonic_s,
    }


def _hello_extras(frame: BridgeFrame) -> JsonObject:
    assert isinstance(frame, Hello)
    return {"role": frame.role}


def _payload_extras(frame: BridgeFrame) -> JsonObject:
    assert isinstance(frame, PayloadFrame)
    _ensure_payload(frame.payload)
    if payload_checksum(frame.payload) != frame.payload_checksum:
        raise MessageCodecError("payload checksum mismatch")
    return {"payload": frame.payload, "payload_checksum": frame.payload_checksum}


def _error_extras(frame: BridgeFrame) -> JsonObject:
    assert isinstance(frame, ErrorFrame)
    return {"code": frame.code, "message": frame.message, "details": frame.details}


def _shutdown_extras(frame: BridgeFrame) -> JsonObject:
    assert isinstance(frame, Shutdown)
    return {"reason": frame.reason}


def _parse_hello(raw: JsonObject) -> BridgeFrame:
    return Hello(**_header(raw), role=_required_str(raw, "role"))


def _parse_payload(raw: JsonObject, frame_class: Type[PayloadFrame]) -> BridgeFrame:
    payload = _required_object(raw, "payload")
    _ensure_payload(payload)
    checksum = _required_str(raw, "payload_checksum")
    if payload_checksum(payload) != checksum:
        raise _DecodeFrameError("invalid_payload", "payload checksum mismatch")
    return frame_class(**_header(raw), payload=payload, payload_checksum=checksum)


def _parse_error(raw: JsonObject) -> BridgeFrame:
    return ErrorFrame(
        **_header(raw),
        code=_required_str(raw, "code"),
        message=_required_str(raw, "message"),
        details=_required_object(raw, "details"),
    )


def _header(raw: JsonObject) -> Dict[str, Union[int, float, str]]:
    return {
        "schema_version": _required_int(raw, "schema_version"),
        "run_id": _required_str(raw, "run_id"),
        "frame_index": _required_int(raw, "frame_index"),
        "simulation_time_s": _required_float(raw, "simulation_time_s"),
        "sent_monotonic_s": _required_float(raw, "sent_monotonic_s"),
    }


def _ensure_payload(payload: JsonObject) -> None:
    _ensure_json_object(payload, reject_shortcuts=True)


def _ensure_json_object(value: JsonObject, reject_shortcuts: bool) -> None:
    for key, item in value.items():
        if not isinstance(key, str):
            raise _DecodeFrameError("invalid_payload", "payload contains non-string key")
        if reject_shortcuts and key in FORBIDDEN_PAYLOAD_KEYS:
            raise _DecodeFrameError("invalid_payload", "payload contains behavior shortcut")
        _ensure_json_value(item, reject_shortcuts)


def _ensure_json_value(value: JsonValue, reject_shortcuts: bool) -> None:
    if value is None or isinstance(value, (bool, str)):
        return
    if isinstance(value, (int, float)):
        if math.isfinite(value):
            return
        raise _DecodeFrameError("invalid_payload", "payload contains non-finite number")
    if isinstance(value, list):
        for item in value:
            _ensure_json_value(item, reject_shortcuts)
        return
    if isinstance(value, dict):
        _ensure_json_object(value, reject_shortcuts)
        return
    raise _DecodeFrameError("invalid_payload", "payload contains unsupported JSON value")


def _required_str(raw: JsonObject, key: str) -> str:
    value = raw.get(key)
    if isinstance(value, str):
        return value
    raise _DecodeFrameError("malformed_message", "missing string field: " + key)


def _required_int(raw: JsonObject, key: str) -> int:
    value = raw.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise _DecodeFrameError("malformed_message", "missing integer field: " + key)


def _required_float(raw: JsonObject, key: str) -> float:
    value = raw.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    raise _DecodeFrameError("malformed_message", "missing finite number field: " + key)


def _required_object(raw: JsonObject, key: str) -> JsonObject:
    value = raw.get(key)
    if isinstance(value, dict):
        return value
    raise _DecodeFrameError("malformed_message", "missing object field: " + key)


def _schema_version(raw: JsonValue) -> int:
    if isinstance(raw, dict):
        value = raw.get("schema_version", SCHEMA_VERSION)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return SCHEMA_VERSION


def _decode_error(exc: BaseException) -> ErrorFrame:
    return ErrorFrame(SCHEMA_VERSION, "", 0, 0.0, 0.0, "malformed_message", str(exc), {})


def _error_from_raw(raw: JsonValue, code: str, message: str) -> ErrorFrame:
    empty = {"run_id": "", "frame_index": 0, "simulation_time_s": 0.0, "sent_monotonic_s": 0.0}
    source = raw if isinstance(raw, dict) else empty
    return ErrorFrame(
        SCHEMA_VERSION,
        source["run_id"] if isinstance(source.get("run_id"), str) else "",
        source["frame_index"] if isinstance(source.get("frame_index"), int) else 0,
        float(source["simulation_time_s"]) if isinstance(source.get("simulation_time_s"), (int, float)) else 0.0,
        float(source["sent_monotonic_s"]) if isinstance(source.get("sent_monotonic_s"), (int, float)) else 0.0,
        code,
        message,
        {},
    )


_TYPE_BY_CLASS: Dict[type, FrameType] = {
    Hello: "hello",
    SensoryFrame: "sensory_frame",
    BrainFrame: "brain_frame",
    ControlFrame: "control_frame",
    Heartbeat: "heartbeat",
    ErrorFrame: "error",
    Shutdown: "shutdown",
}
_EXTRAS_BY_CLASS: Dict[type, Callable[[BridgeFrame], JsonObject]] = {
    Hello: _hello_extras,
    SensoryFrame: _payload_extras,
    BrainFrame: _payload_extras,
    ControlFrame: _payload_extras,
    Heartbeat: lambda frame: {},
    ErrorFrame: _error_extras,
    Shutdown: _shutdown_extras,
}
_PARSERS: Dict[str, Callable[[JsonObject], BridgeFrame]] = {
    "hello": _parse_hello,
    "sensory_frame": lambda raw: _parse_payload(raw, SensoryFrame),
    "brain_frame": lambda raw: _parse_payload(raw, BrainFrame),
    "control_frame": lambda raw: _parse_payload(raw, ControlFrame),
    "heartbeat": lambda raw: Heartbeat(**_header(raw)),
    "error": _parse_error,
    "shutdown": lambda raw: Shutdown(**_header(raw), reason=_required_str(raw, "reason")),
}
