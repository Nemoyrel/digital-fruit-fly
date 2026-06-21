#!/usr/bin/env python3
"""CLI wrapper for generating the L3 offline brain readout lookup table."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def main() -> None:
    from digital_fruit_fly import generate_l3_lookup

    outputs = generate_l3_lookup()
    print(f"lookup: {outputs['lookup_csv']}")
    print(f"metadata: {outputs['metadata_json']}")
    print(f"report: {outputs['report_json']}")


if __name__ == "__main__":
    main()
