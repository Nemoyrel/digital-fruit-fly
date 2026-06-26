"""M3 部分：IPC 编解码与 TCP 往返握手。纯标准库，任一环境可跑。

    /opt/miniconda3/envs/flygym_env/bin/python tests/test_bridge_ipc.py
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def run():
    from digital_fruit_fly.bridge.messages import SensoryMessage, MotorMessage, encode, decode
    from digital_fruit_fly.bridge.ipc import JsonLineServer, JsonLineClient

    # 1) 编解码往返
    s = SensoryMessage(request_id=7, time_s=1.5, food_cue_left=0.8, food_cue_right=0.3,
                       dust_level_left=0.1, dust_level_right=0.2, food_contact=True, food_distance_mm=4.0)
    assert decode(encode(s)) == s, "SensoryMessage 编解码不一致"
    m = MotorMessage(request_id=7, readout_rates_hz={"mn9": 66.7, "dna01_left": 20.0},
                     behavior_state="feeding", active_neuron_count=120, neuron_activity=[1, 2, 3])
    assert decode(encode(m)) == m, "MotorMessage 编解码不一致"
    print(">>> ✅ 编解码往返一致")

    # 2) TCP 往返：服务端把感觉强度回显成 readout
    def handler(req: SensoryMessage) -> MotorMessage:
        return MotorMessage(
            request_id=req.request_id,
            readout_rates_hz={"odn1": 100.0 * (req.food_cue_left + req.food_cue_right),
                              "dna01_left": 50.0 * req.food_cue_right,
                              "dna01_right": 50.0 * req.food_cue_left},
            behavior_state="feeding" if req.food_contact else "foraging",
        )

    server = JsonLineServer(host="127.0.0.1", port=8799, handler=handler)
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    time.sleep(0.2)

    client = JsonLineClient(host="127.0.0.1", port=8799, timeout_s=5.0)
    assert client.wait_until_ready(5.0), "服务端未就绪"
    t0 = time.perf_counter()
    resp = client.request(s)
    rtt_ms = (time.perf_counter() - t0) * 1000.0
    server.shutdown()

    assert resp.request_id == 7
    assert resp.behavior_state == "feeding"
    assert abs(resp.readout_rates_hz["odn1"] - 110.0) < 1e-6
    print(f">>> ✅ TCP 往返成功 RTT={rtt_ms:.2f}ms, behavior={resp.behavior_state}, "
          f"odn1={resp.readout_rates_hz['odn1']:.0f}Hz")
    print(">>> ✅ M3(IPC握手) 传输层验证通过")


if __name__ == "__main__":
    run()
