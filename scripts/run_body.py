#!/usr/bin/env python3
"""身体进程入口（在 flygym_env 运行）：具身觅食/进食/梳理演示，经 IPC 连脑进程。

两种用法：
  # A) 先在另一终端起脑进程，再跑身体：
  /opt/miniconda3/envs/brain_env/bin/python scripts/run_brain.py
  /opt/miniconda3/envs/flygym_env/bin/python scripts/run_body.py

  # B) 让身体进程自行拉起脑子进程（单命令）：
  /opt/miniconda3/envs/flygym_env/bin/python scripts/run_body.py --start-worker
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def main() -> None:
    p = argparse.ArgumentParser(description="数字果蝇身体进程")
    p.add_argument("--config", type=Path, default=PROJECT_ROOT / "configs" / "simulation.json")
    p.add_argument("--duration-s", type=float, default=None)
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "outputs")
    p.add_argument("--no-video", action="store_true")
    p.add_argument("--start-worker", action="store_true", help="自行拉起 brain_env 脑子进程")
    args = p.parse_args()

    config = json.loads(args.config.read_text())
    if args.duration_s is not None:
        config["run"]["duration_s"] = args.duration_s
    if args.port is not None:
        config["ipc"]["port"] = args.port

    from digital_fruit_fly.bridge.ipc import JsonLineClient
    from digital_fruit_fly.body.loop import run_embodied_loop

    ipc = config["ipc"]
    worker = None
    if args.start_worker:
        cmd = [str(ipc["brain_env_python"]), str(PROJECT_ROOT / "scripts" / "run_brain.py"),
               "--port", str(ipc["port"]), "--window-ms", str(ipc.get("window_ms", 15.0))]
        print(json.dumps({"event": "starting_worker", "cmd": cmd}), flush=True)
        worker = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT))

    client = JsonLineClient(host=ipc.get("host", "127.0.0.1"), port=int(ipc["port"]),
                            timeout_s=float(ipc.get("timeout_s", 600.0)))
    print(json.dumps({"event": "waiting_for_brain", "port": ipc["port"]}), flush=True)
    if not client.wait_until_ready(float(ipc.get("worker_ready_timeout_s", 120.0))):
        print(json.dumps({"event": "brain_not_ready"}), flush=True)
        if worker:
            worker.terminate()
        raise SystemExit(2)
    print(json.dumps({"event": "brain_ready_connected"}), flush=True)

    try:
        result = run_embodied_loop(config=config, client=client,
                                   output_dir=args.output_dir, no_video=args.no_video)
    finally:
        if worker:
            worker.terminate()
            try:
                worker.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                worker.kill()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
