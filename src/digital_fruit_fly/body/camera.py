from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, Protocol, Sequence

from digital_fruit_fly.runtime.timeouts import JsonObject


CameraMode = Literal["tracking", "fixed"]
RecordingStatus = Literal["video", "fallback_frames", "skipped"]
ViewerStatus = Literal["not_requested", "skipped_headless", "available_not_launched"]
RGBPixel = tuple[int, int, int]
RGBRows = Sequence[Sequence[RGBPixel]]
SUPPORTED_CODECS: Final = frozenset(("libx264", "mpeg4", "h264"))


@dataclass(frozen=True, slots=True)
class CameraConfigError(Exception):
    field: str
    reason: str

    def __str__(self) -> str:
        return f"{self.field}: {self.reason}"


@dataclass(frozen=True, slots=True)
class FrameSpec:
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0:
            raise CameraConfigError("width", "must be positive")
        if self.height <= 0:
            raise CameraConfigError("height", "must be positive")


@dataclass(frozen=True, slots=True)
class RgbFrame:
    width: int
    height: int
    rgb: bytes

    def __post_init__(self) -> None:
        FrameSpec(self.width, self.height)
        expected = self.width * self.height * 3
        if len(self.rgb) != expected:
            raise CameraConfigError("rgb", f"expected {expected} bytes")

    @classmethod
    def from_bytes(cls, width: int, height: int, rgb: bytes) -> RgbFrame:
        return cls(width=width, height=height, rgb=bytes(rgb))


@dataclass(frozen=True, slots=True)
class CameraRecordingRequest:
    output_dir: Path
    stem: str
    fps: int
    codec: str
    mode: CameraMode
    source: str
    viewer_status: ViewerStatus
    fallback_reason: str | None = None

    def __post_init__(self) -> None:
        if self.stem == "":
            raise CameraConfigError("stem", "must not be empty")
        if self.fps <= 0:
            raise CameraConfigError("fps", "must be positive")
        if self.mode not in ("tracking", "fixed"):
            raise CameraConfigError("mode", "must be tracking or fixed")


@dataclass(frozen=True, slots=True)
class VideoWriteRequest:
    path: Path
    frames: tuple[RgbFrame, ...]
    recording: CameraRecordingRequest


class VideoWriter(Protocol):
    def write(self, request: VideoWriteRequest) -> None: ...


@dataclass(frozen=True, slots=True)
class RecordingResult:
    status: RecordingStatus
    frame_count: int
    metadata_path: Path
    viewer_status: ViewerStatus
    video_path: Path | None
    fallback_frames: tuple[Path, ...]
    warnings: tuple[str, ...]

    def to_json(self) -> JsonObject:
        return {
            "status": self.status,
            "frame_count": self.frame_count,
            "metadata_path": str(self.metadata_path),
            "viewer_status": self.viewer_status,
            "video_path": None if self.video_path is None else str(self.video_path),
            "fallback_frames": [str(path) for path in self.fallback_frames],
            "warnings": list(self.warnings),
        }


class DefaultImageioVideoWriter:
    def write(self, request: VideoWriteRequest) -> None:
        imageio = importlib.import_module("imageio.v3")
        numpy = importlib.import_module("numpy")
        arrays = [
            numpy.frombuffer(frame.rgb, dtype=numpy.uint8).reshape(
                (frame.height, frame.width, 3)
            )
            for frame in request.frames
        ]
        imageio.imwrite(
            request.path,
            numpy.stack(arrays, axis=0),
            fps=request.recording.fps,
            codec=request.recording.codec,
        )


def rgb_frame_from_rows(rows: RGBRows) -> RgbFrame:
    row_tuple = tuple(tuple(row) for row in rows)
    if len(row_tuple) == 0:
        raise CameraConfigError("rows", "must not be empty")
    width = len(row_tuple[0])
    FrameSpec(width, len(row_tuple))
    pixels = bytearray()
    for row in row_tuple:
        if len(row) != width:
            raise CameraConfigError("rows", "must be rectangular")
        for pixel in row:
            _append_pixel(pixels, pixel)
    return RgbFrame.from_bytes(width, len(row_tuple), bytes(pixels))


def deterministic_probe_frames(width: int, height: int, count: int) -> tuple[RgbFrame, ...]:
    spec = FrameSpec(width, height)
    if count <= 0:
        raise CameraConfigError("count", "must be positive")
    return tuple(_deterministic_probe_frame(spec, index) for index in range(count))


def resolve_viewer_status(headless: bool, viewer_requested: bool) -> ViewerStatus:
    if headless:
        return "skipped_headless"
    if viewer_requested:
        return "available_not_launched"
    return "not_requested"


def write_camera_recording(
    request: CameraRecordingRequest,
    frames: Sequence[RgbFrame],
    video_writer: VideoWriter | None = None,
) -> RecordingResult:
    frame_tuple = tuple(frames)
    request.output_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = request.output_dir / f"{request.stem}.metadata.json"
    if len(frame_tuple) == 0:
        warning = "no frames were provided; recording skipped"
        result = RecordingResult(
            status="skipped",
            frame_count=0,
            metadata_path=metadata_path,
            viewer_status=request.viewer_status,
            video_path=None,
            fallback_frames=(),
            warnings=(warning,),
        )
        _write_metadata(metadata_path, request, result)
        return result

    fallback_warnings = _fallback_warnings(request)
    if fallback_warnings:
        return _write_fallback_frames(request, frame_tuple, fallback_warnings)

    video_path = request.output_dir / f"{request.stem}.mp4"
    video_path.unlink(missing_ok=True)
    writer = DefaultImageioVideoWriter() if video_writer is None else video_writer
    try:
        writer.write(VideoWriteRequest(video_path, frame_tuple, request))
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        video_path.unlink(missing_ok=True)
        warning = f"mp4 writer unavailable for codec {request.codec!r}: {type(exc).__name__}: {exc}"
        return _write_fallback_frames(request, frame_tuple, (warning,))

    if not video_path.exists() or video_path.stat().st_size == 0:
        warning = f"mp4 writer produced no bytes for codec {request.codec!r}"
        return _write_fallback_frames(request, frame_tuple, (warning,))

    result = RecordingResult(
        status="video",
        frame_count=len(frame_tuple),
        metadata_path=metadata_path,
        viewer_status=request.viewer_status,
        video_path=video_path,
        fallback_frames=(),
        warnings=(),
    )
    _write_metadata(metadata_path, request, result)
    return result


def _append_pixel(pixels: bytearray, pixel: RGBPixel) -> None:
    red, green, blue = pixel
    for channel in (red, green, blue):
        if channel < 0 or channel > 255:
            raise CameraConfigError("pixel", "RGB channels must be 0..255")
    pixels.extend((red, green, blue))


def _deterministic_probe_frame(spec: FrameSpec, index: int) -> RgbFrame:
    pixels = bytearray(spec.width * spec.height * 3)
    offset = 0
    for y_coord in range(spec.height):
        for x_coord in range(spec.width):
            pixels[offset] = (x_coord + index * 17) % 256
            pixels[offset + 1] = (y_coord + index * 29) % 256
            pixels[offset + 2] = (x_coord + y_coord + index * 43) % 256
            offset += 3
    return RgbFrame.from_bytes(spec.width, spec.height, bytes(pixels))


def _fallback_warnings(request: CameraRecordingRequest) -> tuple[str, ...]:
    warnings: list[str] = []
    if request.fallback_reason is not None:
        warnings.append(request.fallback_reason)
    if request.codec not in SUPPORTED_CODECS:
        warnings.append(
            f"unsupported codec {request.codec!r}; wrote fallback PPM frames instead"
        )
    return tuple(warnings)


def _write_fallback_frames(
    request: CameraRecordingRequest,
    frames: tuple[RgbFrame, ...],
    warnings: tuple[str, ...],
) -> RecordingResult:
    frames_dir = request.output_dir / f"{request.stem}_frames"
    metadata_path = request.output_dir / f"{request.stem}.metadata.json"
    (request.output_dir / f"{request.stem}.mp4").unlink(missing_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old_frame in frames_dir.glob("frame_*.ppm"):
        old_frame.unlink()
    frame_paths = tuple(_write_ppm_frame(frames_dir, index, frame) for index, frame in enumerate(frames))
    result = RecordingResult(
        status="fallback_frames",
        frame_count=len(frames),
        metadata_path=metadata_path,
        viewer_status=request.viewer_status,
        video_path=None,
        fallback_frames=frame_paths,
        warnings=warnings,
    )
    _write_metadata(metadata_path, request, result)
    return result


def _write_ppm_frame(frames_dir: Path, index: int, frame: RgbFrame) -> Path:
    frame_path = frames_dir / f"frame_{index:04d}.ppm"
    header = f"P6\n{frame.width} {frame.height}\n255\n".encode("ascii")
    frame_path.write_bytes(header + frame.rgb)
    return frame_path


def _write_metadata(
    metadata_path: Path, request: CameraRecordingRequest, result: RecordingResult
) -> None:
    payload = result.to_json()
    payload["codec"] = request.codec
    payload["mode"] = request.mode
    payload["source"] = request.source
    metadata_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
