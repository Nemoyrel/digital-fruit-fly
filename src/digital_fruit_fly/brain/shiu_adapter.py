from __future__ import annotations

import ast
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from digital_fruit_fly.runtime.timeouts import JsonObject, JsonValue


SHIU_783_COMPLETENESS = "Completeness_783.csv"
SHIU_783_CONNECTIVITY = "Connectivity_783.parquet"
SHIU_630_COMPLETENESS = "2023_03_23_completeness_630_final.csv"
SHIU_630_CONNECTIVITY = "2023_03_23_connectivity_630_final.parquet"


@dataclass(frozen=True)
class ShiuDiscoveryError(Exception):
    path: Path
    reason: str

    def __str__(self) -> str:
        return f"{self.path}: {self.reason}"


@dataclass(frozen=True)
class SugarValidation:
    expected_ids: Tuple[int, ...]
    present_ids: Tuple[int, ...]
    missing_ids: Tuple[int, ...]

    @property
    def ok(self) -> bool:
        return len(self.missing_ids) == 0

    def to_json(self) -> JsonObject:
        return {
            "ok": self.ok,
            "expected_count": len(self.expected_ids),
            "present_count": len(self.present_ids),
            "missing_ids": list(self.missing_ids),
        }


@dataclass(frozen=True)
class ShiuDataset:
    version: str
    completeness_path: Path
    connectivity_path: Path
    sugar_validation: SugarValidation

    def to_json(self) -> JsonObject:
        return {
            "version": self.version,
            "completeness_path": str(self.completeness_path),
            "connectivity_path": str(self.connectivity_path),
            "sugar_validation": self.sugar_validation.to_json(),
        }


@dataclass(frozen=True)
class ShiuAssets:
    repo_path: Path
    model_path: Path
    notebook_path: Path
    selected_version: str
    selected: ShiuDataset
    available_versions: Dict[str, ShiuDataset]

    def to_json(self) -> JsonObject:
        versions: Dict[str, JsonValue] = {
            name: dataset.to_json()
            for name, dataset in sorted(self.available_versions.items())
        }
        return {
            "repo_path": str(self.repo_path),
            "model_path": str(self.model_path),
            "notebook_path": str(self.notebook_path),
            "selected_version": self.selected_version,
            "selected": self.selected.to_json(),
            "available_versions": versions,
        }


def discover_shiu_assets(
    repo_path: Path,
    completeness_path: Path,
    connectivity_path: Path,
    sugar_neuron_ids: Sequence[int],
) -> ShiuAssets:
    repo = repo_path.resolve()
    _require_dir(repo, "Shiu repository does not exist")
    model_path = _require_file(repo / "model.py", "Shiu model.py is missing")
    notebook_path = _require_file(repo / "example.ipynb", "Shiu example notebook is missing")
    configured_completeness = _require_file(
        completeness_path.resolve(), "configured completeness CSV is missing"
    )
    configured_connectivity = _require_file(
        connectivity_path.resolve(), "configured connectivity parquet is missing"
    )
    fixed_paths = {
        "783": (repo / SHIU_783_COMPLETENESS, repo / SHIU_783_CONNECTIVITY),
        "630": (repo / SHIU_630_COMPLETENESS, repo / SHIU_630_CONNECTIVITY),
    }
    for completeness, connectivity in fixed_paths.values():
        _require_file(completeness, "required Shiu completeness CSV is missing")
        _require_file(connectivity, "required Shiu connectivity parquet is missing")

    available = _build_available_versions(
        configured_completeness,
        configured_connectivity,
        fixed_paths,
        tuple(sugar_neuron_ids),
    )
    selected = _select_dataset(available, _detect_version(configured_completeness))
    return ShiuAssets(
        repo_path=repo,
        model_path=model_path,
        notebook_path=notebook_path,
        selected_version=selected.version,
        selected=selected,
        available_versions=available,
    )


def extract_sugar_neuron_ids(notebook_path: Path) -> Tuple[int, ...]:
    notebook = _require_file(notebook_path.resolve(), "Shiu example notebook is missing")
    try:
        payload = json.loads(notebook.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ShiuDiscoveryError(notebook, f"notebook JSON is malformed: {exc}") from exc
    cells = payload.get("cells")
    if not isinstance(cells, list):
        raise ShiuDiscoveryError(notebook, "notebook does not contain a cells list")
    for source in _iter_cell_sources(cells):
        ids = _parse_neu_sugar_assignment(source)
        if len(ids) > 0:
            return ids
    raise ShiuDiscoveryError(notebook, "neu_sugar assignment was not found")


def validate_sugar_ids(completeness_path: Path, sugar_neuron_ids: Sequence[int]) -> SugarValidation:
    present = _read_completeness_ids(_require_file(completeness_path, "completeness CSV is missing"))
    expected = tuple(sugar_neuron_ids)
    missing = tuple(flywire_id for flywire_id in expected if flywire_id not in present)
    matched = tuple(flywire_id for flywire_id in expected if flywire_id in present)
    return SugarValidation(expected_ids=expected, present_ids=matched, missing_ids=missing)


def _build_available_versions(
    configured_completeness: Path,
    configured_connectivity: Path,
    fixed_paths: Dict[str, Tuple[Path, Path]],
    sugar_neuron_ids: Tuple[int, ...],
) -> Dict[str, ShiuDataset]:
    available = {
        version: ShiuDataset(
            version=version,
            completeness_path=completeness.resolve(),
            connectivity_path=connectivity.resolve(),
            sugar_validation=validate_sugar_ids(completeness, sugar_neuron_ids),
        )
        for version, (completeness, connectivity) in fixed_paths.items()
    }
    configured_version = _detect_version(configured_completeness)
    if configured_version not in available:
        available[configured_version] = ShiuDataset(
            version=configured_version,
            completeness_path=configured_completeness,
            connectivity_path=configured_connectivity,
            sugar_validation=validate_sugar_ids(configured_completeness, sugar_neuron_ids),
        )
    return available


def _select_dataset(available: Dict[str, ShiuDataset], configured_version: str) -> ShiuDataset:
    configured = available[configured_version]
    if configured.sugar_validation.ok:
        return configured
    for version in ("630", "783"):
        candidate = available[version]
        if candidate.sugar_validation.ok:
            return candidate
    missing = ", ".join(str(i) for i in configured.sugar_validation.missing_ids)
    raise ShiuDiscoveryError(configured.completeness_path, f"sugar neuron IDs missing: {missing}")


def _detect_version(completeness_path: Path) -> str:
    name = completeness_path.name
    if name == SHIU_783_COMPLETENESS:
        return "783"
    if name == SHIU_630_COMPLETENESS:
        return "630"
    return "configured"


def _iter_cell_sources(cells: Iterable[JsonValue]) -> Iterable[str]:
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        source = cell.get("source")
        if isinstance(source, list):
            yield "".join(line for line in source if isinstance(line, str))
        elif isinstance(source, str):
            yield source


def _parse_neu_sugar_assignment(source: str) -> Tuple[int, ...]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not _assigns_name(node, "neu_sugar"):
            continue
        try:
            value = ast.literal_eval(node.value)
        except ValueError as exc:
            raise ShiuDiscoveryError(Path("example.ipynb"), "neu_sugar must be literal data") from exc
        if not isinstance(value, list):
            raise ShiuDiscoveryError(Path("example.ipynb"), "neu_sugar must be a list")
        return tuple(_parse_int_list(value))
    return ()


def _parse_int_list(values: List[JsonValue]) -> Iterable[int]:
    for value in values:
        if not isinstance(value, int):
            raise ShiuDiscoveryError(Path("example.ipynb"), "neu_sugar must contain integers")
        yield value


def _assigns_name(node: ast.Assign, name: str) -> bool:
    return any(isinstance(target, ast.Name) and target.id == name for target in node.targets)


def _read_completeness_ids(completeness_path: Path) -> Tuple[int, ...]:
    ids: List[int] = []
    with completeness_path.open(newline="", encoding="utf-8") as file:
        reader = csv.reader(file)
        for row in reader:
            if len(row) == 0:
                continue
            raw_id = row[0].strip()
            if raw_id.isdecimal():
                ids.append(int(raw_id))
    if len(ids) == 0:
        raise ShiuDiscoveryError(completeness_path, "completeness CSV contains no FlyWire IDs")
    return tuple(ids)


def _require_dir(path: Path, reason: str) -> Path:
    if not path.is_dir():
        raise ShiuDiscoveryError(path, reason)
    return path


def _require_file(path: Path, reason: str) -> Path:
    if not path.is_file():
        raise ShiuDiscoveryError(path, reason)
    return path
