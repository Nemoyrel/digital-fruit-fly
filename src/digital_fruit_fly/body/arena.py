"""场景几何体的构建：有界场地围墙、糖食物源 + 黄色气味斑、覆盖全场的落灰。

通过往 ``world.mjcf_root.worldbody`` 添加 MuJoCo geom 实现。所有装饰性几何体设为
``contype=0, conaffinity=0``（仅可视、不参与碰撞）；围墙保持可碰撞以形成有界场地。

注意：``flygym`` 仅在函数内部使用（通过传入的 world 对象），本模块导入不需要 flygym。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ArenaInfo:
    """populate_arena 的产物元信息。"""

    food_position_mm: tuple[float, float]
    cue_radius_mm: float
    contact_radius_mm: float
    dust_geom_names: tuple[str, ...]


def add_boundary_walls(
    world: Any,
    *,
    half_size: float,
    height: float = 6.0,
    thickness: float = 1.5,
    rgba: tuple[float, float, float, float] = (0.55, 0.42, 0.30, 1.0),
) -> None:
    """在场地四周加四面可碰撞围墙，形成有界场地。"""
    wb = world.mjcf_root.worldbody
    s, h, t = half_size, height, thickness
    specs = [
        ("wall_n", (s + t, t, h), (0.0, s + t, h)),
        ("wall_s", (s + t, t, h), (0.0, -(s + t), h)),
        ("wall_e", (t, s + t, h), (s + t, 0.0, h)),
        ("wall_w", (t, s + t, h), (-(s + t), 0.0, h)),
    ]
    for name, size, pos in specs:
        wb.add("geom", name=name, type="box", size=size, pos=pos, rgba=rgba)


def add_food_source(
    world: Any,
    *,
    pos_xy: tuple[float, float],
    contact_radius: float,
    cue_radius: float,
    food_rgba: tuple[float, float, float, float] = (0.96, 0.82, 0.16, 1.0),
    cue_rgba: tuple[float, float, float, float] = (0.92, 0.80, 0.18, 0.16),
) -> None:
    """加一个糖食物源（黄色食物块）+ 一片覆盖一定面积的半透明黄色气味斑。"""
    wb = world.mjcf_root.worldbody
    fx, fy = pos_xy
    # 半透明黄色气味斑（薄圆盘，覆盖嗅觉羽流面积）
    wb.add(
        "geom", name="odor_patch", type="cylinder",
        size=(cue_radius, 0.01), pos=(fx, fy, 0.01), rgba=cue_rgba,
        contype=0, conaffinity=0,
    )
    # 接触判定半径的淡环
    wb.add(
        "geom", name="food_contact_ring", type="cylinder",
        size=(contact_radius, 0.012), pos=(fx, fy, 0.013), rgba=(0.96, 0.7, 0.1, 0.30),
        contype=0, conaffinity=0,
    )
    # 糖食物块（压扁的椭球，黄色）
    wb.add(
        "geom", name="food_blob", type="ellipsoid",
        size=(contact_radius * 0.7, contact_radius * 0.5, 0.35),
        pos=(fx, fy, 0.35), rgba=food_rgba, contype=0, conaffinity=0,
    )


def add_dust_specks(
    world: Any,
    *,
    half_size: float,
    count: int = 220,
    seed: int = 3,
    rgba: tuple[float, float, float, float] = (0.85, 0.84, 0.78, 0.55),
    exclude_radius_mm: float = 5.0,
) -> tuple[str, ...]:
    """在全场随机撒落细小灰尘斑点（仅可视）。返回 geom 名字元组。"""
    import random

    wb = world.mjcf_root.worldbody
    rng = random.Random(seed)
    names: list[str] = []
    margin = max(2.0, half_size * 0.04)
    for i in range(int(count)):
        x = rng.uniform(-half_size + margin, half_size - margin)
        y = rng.uniform(-half_size + margin, half_size - margin)
        if math.hypot(x, y) < exclude_radius_mm:  # 别盖住果蝇出生点
            continue
        r = rng.uniform(0.18, 0.42)
        name = f"dust_{i}"
        wb.add(
            "geom", name=name, type="box", size=(r, r, 0.01),
            pos=(x, y, 0.01), rgba=rgba, contype=0, conaffinity=0,
        )
        names.append(name)
    return tuple(names)


def populate_arena(
    world: Any,
    scene: dict,
    *,
    dust_count: int = 220,
    dust_seed: int = 3,
    walls: bool = True,
) -> ArenaInfo:
    """按场景配置往 world 添加围墙、食物源、气味斑与落灰。"""
    half = float(scene["arena_half_size_mm"])
    food_xy = tuple(scene["food_position_mm"])
    cue_radius = float(scene["food_cue_radius_mm"])
    contact_radius = float(scene["food_contact_radius_mm"])
    if walls:
        add_boundary_walls(world, half_size=half)
    add_food_source(
        world, pos_xy=food_xy, contact_radius=contact_radius, cue_radius=cue_radius
    )
    dust_names = add_dust_specks(
        world, half_size=half, count=dust_count, seed=dust_seed
    )
    return ArenaInfo(
        food_position_mm=food_xy,
        cue_radius_mm=cue_radius,
        contact_radius_mm=contact_radius,
        dust_geom_names=dust_names,
    )
