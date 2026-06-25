from __future__ import annotations

import csv
import io
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


REQUIRED_COLUMNS = frozenset(("frame_index", "simulation_time_s", "readout", "rate_hz", "spike_delta"))


@dataclass(frozen=True)
class RenderRequest:
    input_path: Path
    output_path: Path


@dataclass(frozen=True)
class RenderResult:
    artifact_path: Path
    metadata_path: Path
    summary_csv_path: Path
    mode: Literal["video", "png_fallback", "csv_fallback"]
    frame_count: int
    row_count: int
    readouts: tuple[str, ...]
    fallback_reason: str | None


@dataclass(frozen=True)
class ActivityRow:
    frame_index: int
    simulation_time_s: float
    readout: str
    rate_hz: float
    spike_delta: int


@dataclass(frozen=True)
class ActivityTable:
    rows: tuple[ActivityRow, ...]
    frames: tuple[int, ...]
    readouts: tuple[str, ...]


@dataclass(frozen=True)
class RenderContext:
    requested_output_path: Path
    metadata_path: Path
    summary_csv_path: Path
    table: ActivityTable


@dataclass(frozen=True)
class RenderArtifact:
    path: Path
    mode: Literal["video", "png_fallback", "csv_fallback"]
    fallback_reason: str | None


@dataclass(frozen=True)
class BrainActivityInputError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


def render_brain_activity(request: RenderRequest) -> RenderResult:
    _remove_stale_requested_output(request)
    table = _load_activity_table(_rates_path(request.input_path))
    request.output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_csv_path = request.output_path.with_suffix(".summary.csv")
    metadata_path = request.output_path.with_suffix(".metadata.json")
    _write_summary_csv(summary_csv_path, table)
    context = RenderContext(request.output_path, metadata_path, summary_csv_path, table)
    return _render_best_effort(context)


def _remove_stale_requested_output(request: RenderRequest) -> None:
    if request.input_path == request.output_path:
        return
    try:
        request.output_path.unlink(missing_ok=True)
    except OSError as exc:
        raise BrainActivityInputError(f"unable to remove stale requested output: {request.output_path}: {exc}") from exc


def _rates_path(input_path: Path) -> Path:
    if input_path.is_file():
        return input_path
    rates_path = input_path / "brain" / "rates.csv"
    if rates_path.is_file():
        return rates_path
    raise BrainActivityInputError(f"missing brain rates log: {rates_path}")


def _load_activity_table(path: Path) -> ActivityTable:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            _require_columns(path, reader.fieldnames)
            rows = tuple(_parse_row(row, index + 2, path) for index, row in enumerate(reader))
    except OSError as exc:
        raise BrainActivityInputError(f"unable to read brain rates log: {path}: {exc}") from exc
    if len(rows) == 0:
        raise BrainActivityInputError(f"no activity rows in brain rates log: {path}")
    frames = tuple(sorted({row.frame_index for row in rows}))
    readouts = tuple(sorted({row.readout for row in rows}))
    return ActivityTable(rows=rows, frames=frames, readouts=readouts)


def _require_columns(path: Path, fieldnames: list[str] | None) -> None:
    if fieldnames is None:
        raise BrainActivityInputError(f"empty brain rates log: {path}")
    missing = sorted(REQUIRED_COLUMNS.difference(fieldnames))
    if len(missing) > 0:
        raise BrainActivityInputError(f"brain rates log missing columns {missing}: {path}")


def _parse_row(row: dict[str, str], line_number: int, path: Path) -> ActivityRow:
    try:
        readout = row["readout"].strip()
        if len(readout) == 0:
            raise BrainActivityInputError(f"blank readout at {path}:{line_number}")
        return ActivityRow(
            frame_index=int(row["frame_index"]),
            simulation_time_s=float(row["simulation_time_s"]),
            readout=readout,
            rate_hz=float(row["rate_hz"]),
            spike_delta=int(row["spike_delta"]),
        )
    except KeyError as exc:
        raise BrainActivityInputError(f"brain rates row missing field {exc} at {path}:{line_number}") from exc
    except ValueError as exc:
        raise BrainActivityInputError(f"malformed numeric value at {path}:{line_number}: {exc}") from exc


def _write_summary_csv(path: Path, table: ActivityTable) -> None:
    latest_by_cell = {(row.frame_index, row.readout): row for row in table.rows}
    first_time_by_frame = {row.frame_index: row.simulation_time_s for row in table.rows}
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("frame_index", "simulation_time_s", *table.readouts))
        for frame_index in table.frames:
            writer.writerow(
                (
                    frame_index,
                    first_time_by_frame[frame_index],
                    *(latest_by_cell.get((frame_index, readout)).rate_hz if (frame_index, readout) in latest_by_cell else "" for readout in table.readouts),
                )
            )


def _render_best_effort(context: RenderContext) -> RenderResult:
    try:
        frames = _matplotlib_frames(context.requested_output_path, context.table)
    except ImportError as exc:
        artifact = RenderArtifact(context.summary_csv_path, "csv_fallback", f"matplotlib unavailable: {exc}")
        return _finish(context, artifact)
    try:
        _write_video(context.requested_output_path, frames)
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        png_path = context.requested_output_path.with_suffix(".png")
        _write_png_summary(png_path, context.table)
        artifact = RenderArtifact(png_path, "png_fallback", f"video unavailable: {exc}")
        return _finish(context, artifact)
    return _finish(context, RenderArtifact(context.requested_output_path, "video", None))


def _matplotlib_frames(output_path: Path, table: ActivityTable) -> list[bytes]:
    _prepare_mpl_config(output_path)
    import matplotlib

    matplotlib.use("Agg")
    frames: list[bytes] = []
    for frame_index in table.frames:
        frames.append(_render_png_bytes(table, frame_index))
    return frames


def _write_video(path: Path, frames: list[bytes]) -> None:
    import imageio.v2 as imageio

    images = [imageio.imread(io.BytesIO(frame)) for frame in frames]
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=path.suffix, delete=False) as temp_file:
        temp_path = Path(temp_file.name)
    try:
        imageio.mimsave(temp_path, images, fps=6)
        temp_path.replace(path)
    except (OSError, RuntimeError, ValueError):
        temp_path.unlink(missing_ok=True)
        raise


def _write_png_summary(path: Path, table: ActivityTable) -> None:
    _prepare_mpl_config(path)
    import matplotlib

    matplotlib.use("Agg")
    path.write_bytes(_render_png_bytes(table, table.frames[-1]))


def _render_png_bytes(table: ActivityTable, through_frame: int) -> bytes:
    import matplotlib.pyplot as plt

    rates = _matrix(table, through_frame)
    fig, axis = plt.subplots(figsize=(8, 4.5))
    image = axis.imshow(rates, aspect="auto", cmap="viridis", interpolation="nearest")
    axis.set_title(f"Brain activity through frame {through_frame}")
    axis.set_xlabel("Frame")
    axis.set_ylabel("Readout")
    axis.set_yticks(range(len(table.readouts)), labels=table.readouts)
    axis.set_xticks(range(len(table.frames)), labels=[str(frame) for frame in table.frames], rotation=45)
    fig.colorbar(image, ax=axis, label="Rate (Hz)")
    fig.tight_layout()
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=120)
    plt.close(fig)
    return buffer.getvalue()


def _matrix(table: ActivityTable, through_frame: int) -> list[list[float]]:
    values = {(row.frame_index, row.readout): row.rate_hz for row in table.rows if row.frame_index <= through_frame}
    return [[values.get((frame_index, readout), 0.0) for frame_index in table.frames] for readout in table.readouts]


def _prepare_mpl_config(output_path: Path) -> None:
    mpl_config = output_path.parent / "mplconfig"
    mpl_config.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(mpl_config))


def _finish(context: RenderContext, artifact: RenderArtifact) -> RenderResult:
    result = RenderResult(
        artifact_path=artifact.path,
        metadata_path=context.metadata_path,
        summary_csv_path=context.summary_csv_path,
        mode=artifact.mode,
        frame_count=len(context.table.frames),
        row_count=len(context.table.rows),
        readouts=context.table.readouts,
        fallback_reason=artifact.fallback_reason,
    )
    metadata = {
        "artifact_path": str(result.artifact_path),
        "requested_output_path": str(context.requested_output_path),
        "summary_csv_path": str(result.summary_csv_path),
        "mode": result.mode,
        "frame_count": result.frame_count,
        "row_count": result.row_count,
        "readouts": list(result.readouts),
        "fallback_reason": result.fallback_reason,
    }
    context.metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
