"""Dependency-free JSONL logging helpers for run artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Union


JsonScalar = Union[str, int, float, bool, None]
JsonValue = Union[JsonScalar, list["JsonValue"], dict[str, "JsonValue"]]
JsonRecord = dict[str, JsonValue]

def append_jsonl(path: Path, record: Mapping[str, JsonValue]) -> None:
    """Append one JSON object as a single UTF-8 JSONL line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        json.dump(dict(record), handle, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def read_jsonl(path: Path) -> list[JsonRecord]:
    """Read a UTF-8 JSONL file into JSON object records."""
    records: list[JsonRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                parsed = json.loads(stripped)
                if not isinstance(parsed, dict):
                    raise JsonlFormatError(path, "line is not a JSON object")
                records.append(parsed)
    return records


class JsonlFormatError(ValueError):
    """Raised when a JSONL file contains a non-object record."""

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"{path}: {reason}")
