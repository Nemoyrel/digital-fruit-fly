"""M2 回归：FlyGym 身体在平坦场地直线行走，位移前进、无穿墙。

需在 flygym_env 运行（依赖 flygym 2.0.2 + flygym_demo）：

    /opt/miniconda3/envs/flygym_env/bin/python tests/test_body_walk.py
"""

from __future__ import annotations

import sys
import time
from math import hypot
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

SCENE = {
    "arena_half_size_mm": 60.0,
    "food_position_mm": [30.0, 20.0],
    "food_cue_radius_mm": 20.0,
    "food_contact_radius_mm": 3.0,
}


def run(walk_s: float = 0.6, drive: float = 1.0):
    from digital_fruit_fly.body.fly_body import FlyGymBody

    body = FlyGymBody(scene=SCENE, seed=1, dust_count=0, colorize=False)
    print(f">>> FlyGymBody 构建成功, timestep={body.timestep:.2e}s")
    body.warmup(0.05)

    p0 = body.pose()
    n_steps = int(walk_s / body.timestep)
    print(f">>> 直线行走 {walk_s}s ({n_steps} 步), drive={drive} ...")
    t0 = time.perf_counter()
    for i in range(n_steps):
        pose = body.pose()
        body.apply_behavior("foraging", drive, drive, pose.time_s)
        body.step(render=False)
    wall = time.perf_counter() - t0
    p1 = body.pose()
    body.close()

    dx = p1.thorax_xyz_mm[0] - p0.thorax_xyz_mm[0]
    dy = p1.thorax_xyz_mm[1] - p0.thorax_xyz_mm[1]
    disp = hypot(dx, dy)
    half = SCENE["arena_half_size_mm"]
    print(f">>> 起点 xy=({p0.thorax_xyz_mm[0]:.1f},{p0.thorax_xyz_mm[1]:.1f})  "
          f"终点 xy=({p1.thorax_xyz_mm[0]:.1f},{p1.thorax_xyz_mm[1]:.1f})")
    print(f">>> 位移={disp:.2f}mm  仿真挂钟={wall:.1f}s  实时比={wall/walk_s:.1f}x")

    assert disp > 1.0, f"M2 失败：{walk_s}s 行走位移仅 {disp:.2f}mm，未明显前进"
    assert abs(p1.thorax_xyz_mm[0]) < half and abs(p1.thorax_xyz_mm[1]) < half, "M2 失败：穿出场地"
    print(">>> ✅ M2 PASS: 果蝇直线行走前进且未穿墙")
    return {"displacement_mm": disp, "wall_s": wall}


if __name__ == "__main__":
    run()
