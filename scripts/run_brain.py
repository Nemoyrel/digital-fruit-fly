#!/usr/bin/env python3
"""脑进程入口（在 brain_env 运行）：构建 Shiu 全连接组在线脑 + 后端，经 TCP 服务身体进程。

    /opt/miniconda3/envs/brain_env/bin/python scripts/run_brain.py [--port 8765] [--window-ms 15]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def main() -> None:
    parser = argparse.ArgumentParser(description="数字果蝇脑进程")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--window-ms", type=float, default=15.0)
    parser.add_argument("--smoke", action="store_true", help="建网+一次合成请求后退出")
    args = parser.parse_args()

    from digital_fruit_fly.brain.backend import BrainBackend
    from digital_fruit_fly.bridge.ipc import JsonLineServer
    from digital_fruit_fly.bridge.messages import SensoryMessage

    print(json.dumps({"event": "brain_building", "window_ms": args.window_ms}), flush=True)
    backend = BrainBackend.build(window_ms=args.window_ms)
    info = backend.startup_info()
    print(json.dumps({"event": "brain_ready", "info": info}, ensure_ascii=False), flush=True)

    if args.smoke:
        msg = SensoryMessage(request_id=1, time_s=0.05, food_cue_left=0.9, food_cue_right=0.2,
                             dust_level_left=0.0, dust_level_right=0.0, food_contact=True, food_distance_mm=2.0)
        for _ in range(5):
            resp = backend.handle(msg)
        print(json.dumps({"event": "smoke", "readout": {k: round(v, 1) for k, v in resp.readout_rates_hz.items()},
                          "active": resp.active_neuron_count, "wall_ms": round(resp.brain_wall_time_ms)},
                         ensure_ascii=False), flush=True)
        return

    server = JsonLineServer(host=args.host, port=args.port, handler=backend.handle)
    print(json.dumps({"event": "brain_serving", "host": args.host, "port": args.port}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
