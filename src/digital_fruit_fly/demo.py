"""数字果蝇具身演示的编排入口。

在 flygym_env 中运行身体 loop；脑 worker 在 brain_env 中（可由 ``--start-worker``
让本进程自行拉起子进程，或在另一个终端手动启动）。
"""

from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from .config import (
    DEMO_CONFIG_PATH,
    OUTPUT_DIR,
    apply_run_overrides,
    load_json_config,
)
from .brain_link import IpcBrainBridge
from .loop import run_embodied_loop


def _start_worker(ipc_config: dict[str, Any]) -> subprocess.Popen:
    project_root = Path(__file__).resolve().parents[2]
    cmd = [
        str(ipc_config["brain_env_python"]),
        "scripts/run_brain_worker.py",
        "--host", str(ipc_config["host"]),
        "--port", str(ipc_config["port"]),
        "--backend", str(ipc_config.get("backend", "shiu_full")),
        "--brain-window-s", str(ipc_config.get("brain_window_s", 0.05)),
        "--viz-neuron-count", str(ipc_config.get("viz_neuron_count", 4000)),
    ]
    return subprocess.Popen(cmd, cwd=project_root)


def _wait_for_port(host: str, port: int, timeout_s: float) -> bool:
    """轮询直到端口可连接（脑 worker 完成建网开始监听），或超时。"""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, int(port)), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def run_demo(
    *,
    duration_s: float | None = None,
    seed: int | None = None,
    output_dir: Path | None = None,
    no_video: bool = False,
    no_plot: bool = False,
    host: str | None = None,
    port: int | None = None,
    timeout_s: float | None = None,
    start_worker: bool | None = None,
    config_path: Path | None = None,
) -> dict[str, Any]:
    config_path = config_path or DEMO_CONFIG_PATH
    config = apply_run_overrides(
        load_json_config(config_path), duration_s=duration_s, seed=seed
    )
    ipc = dict(config["ipc"])
    if host is not None:
        ipc["host"] = host
    if port is not None:
        ipc["port"] = port
    if timeout_s is not None:
        ipc["timeout_s"] = timeout_s
    if start_worker is not None:
        ipc["start_worker"] = start_worker
    config["ipc"] = ipc
    config.setdefault("ipc", {})["brain_window_s_hint"] = ipc.get("brain_window_s", 0.05) * 1000.0

    worker_process = None
    if ipc.get("start_worker", False):
        worker_process = _start_worker(ipc)
        # 等脑 worker 建完网络开始监听（建网可能耗时数分钟）
        _wait_for_port(
            ipc.get("host", "127.0.0.1"),
            int(ipc.get("port", 8765)),
            float(ipc.get("timeout_s", 600.0)),
        )

    bridge = IpcBrainBridge.from_config(ipc)
    try:
        result = run_embodied_loop(
            config=config,
            config_path=config_path,
            bridge=bridge,
            output_dir=output_dir or OUTPUT_DIR / "digital_fruit_fly",
            no_video=no_video,
            no_plot=no_plot,
        )
    finally:
        if worker_process is not None:
            worker_process.terminate()
            try:
                worker_process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                worker_process.kill()
    return result
