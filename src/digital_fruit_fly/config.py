"""项目路径、JSON 配置加载与本地运行缓存设置。

本模块只依赖标准库，导入它不需要 flygym 或 brian2。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "configs"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
EXTERNAL_DIR = PROJECT_ROOT / "external"

DEMO_CONFIG_PATH = CONFIG_DIR / "demo.json"


def load_json_config(path: Path) -> dict[str, Any]:
    """读取一个 JSON 配置文件。"""
    with Path(path).open() as f:
        return json.load(f)


def configure_local_caches(output_dir: Path) -> None:
    """把 matplotlib / XDG / mujoco 等缓存重定向到 output_dir 下，避免污染 $HOME。

    使用 ``setdefault``，因此外部已显式设置的环境变量优先。
    """
    cache_dir = Path(output_dir) / ".cache"
    os.environ.setdefault("MPLCONFIGDIR", str(cache_dir / "matplotlib"))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_dir / "xdg"))
    for sub in ("matplotlib", "xdg"):
        (cache_dir / sub).mkdir(parents=True, exist_ok=True)


def apply_run_overrides(
    config: dict[str, Any],
    *,
    duration_s: float | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """返回 config 的深拷贝，并按需覆盖 run 段的少量字段。"""
    updated = json.loads(json.dumps(config))
    if duration_s is not None:
        updated["run"]["duration_s"] = duration_s
    if seed is not None:
        updated["run"]["seed"] = seed
    return updated
