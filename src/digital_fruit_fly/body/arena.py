"""场景几何体的构建：有界场地围墙、糖食物源 + 黄色气味斑、覆盖全场的落灰，
以及一层仿 Eon 演示视频的低多边形远景（淡雾天空 + 沙地竞技场 + 环绕的绿草地、
绿丘陵与奶白树冠的树）。

通过往 ``world.mjcf_root.worldbody`` 添加 MuJoCo geom 实现。所有装饰性几何体设为
``contype=0, conaffinity=0``（仅可视、不参与碰撞）；围墙保持可碰撞以形成有界场地。
天空盒与地面材质则直接改写 FlyGym 默认资产（纯白天空盒 + 灰色棋盘）而非新建。

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
    scenery_geom_names: tuple[str, ...] = ()


def add_boundary_walls(
    world: Any,
    *,
    half_size: float,
    height: float = 4.0,
    thickness: float = 1.5,
    rgba: tuple[float, float, float, float] = (0.80, 0.72, 0.55, 1.0),
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
        size=(contact_radius * 1, contact_radius * 1, 0.35),
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


def paint_environment(
    world: Any,
    *,
    sky_top: tuple[float, float, float] = (0.70, 0.78, 0.85),
    sky_horizon: tuple[float, float, float] = (0.92, 0.93, 0.92),
    sand_rgb1: tuple[float, float, float] = (0.82, 0.75, 0.59),
    sand_rgb2: tuple[float, float, float] = (0.86, 0.79, 0.63),
) -> None:
    """改写 FlyGym 默认资产：纯白天空盒 → 淡雾天空渐变；灰色棋盘地面 → 沙地。

    ``BaseWorld`` 已建了名为 ``skybox`` 的天空盒（rgb1=rgb2=白），``FlatGroundWorld``
    已建了名为 ``checker`` 的灰棋盘纹理与 ``grid`` 材质。这里就地改色，不新建资产。
    """
    asset = world.mjcf_root.asset
    sky = asset.find("texture", "skybox")
    if sky is not None:
        sky.builtin = "gradient"
        sky.rgb1 = sky_top       # 天顶（偏蓝灰）
        sky.rgb2 = sky_horizon   # 地平线（发白起雾）
        sky.width = 256
        sky.height = 256
    checker = asset.find("texture", "checker")
    if checker is not None:
        checker.rgb1 = sand_rgb1
        checker.rgb2 = sand_rgb2
    grid = asset.find("material", "grid")
    if grid is not None:
        grid.reflectance = 0.05  # 沙地少反光


def add_scenery(
    world: Any,
    *,
    half_size: float,
    seed: int = 7,
    grass_rgba: tuple[float, float, float, float] = (0.47, 0.57, 0.37, 1.0),
    n_hills: int = 22,
    n_trees: int = 16,
) -> tuple[str, ...]:
    """在场地外围加一圈低多边形远景：大片草地 + 绿丘陵 + 奶白树冠的树（仅可视）。

    所有几何体均在围墙之外（半径 > half_size），且 ``contype=0, conaffinity=0``，
    只作背景观感，不影响果蝇的物理与碰撞。返回新增 geom 名字元组。
    """
    import random

    wb = world.mjcf_root.worldbody
    rng = random.Random(seed)
    names: list[str] = []

    # 竞技场之外的大片草地（沙地围墙外的绿地），略低于地面避免 z-fighting
    wb.add(
        "geom", name="far_grass", type="plane",
        size=(half_size * 6, half_size * 6, 1), pos=(0, 0, -0.05),
        rgba=grass_rgba, contype=0, conaffinity=0,
    )
    names.append("far_grass")

    # 远景丘陵：一圈压扁的绿色椭球，远而矮，在地平线上连成一条低多边形绿带
    hill_palette = [
        (0.38, 0.52, 0.31, 1.0), (0.44, 0.58, 0.35, 1.0), (0.32, 0.46, 0.28, 1.0),
    ]
    for i in range(int(n_hills)):
        ang = 2.0 * math.pi * i / max(1, n_hills) + rng.uniform(-0.08, 0.08)
        R = half_size * rng.uniform(2.4, 3.6)
        rx = half_size * rng.uniform(0.8, 1.4)
        ry = half_size * rng.uniform(0.8, 1.4)
        rz = half_size * rng.uniform(0.32, 0.52)
        name = f"hill_{i}"
        wb.add(
            "geom", name=name, type="ellipsoid",
            size=(rx, ry, rz),
            pos=(R * math.cos(ang), R * math.sin(ang), rz * 0.1),
            rgba=rng.choice(hill_palette), contype=0, conaffinity=0,
        )
        names.append(name)

    # 低多边形树：棕色圆柱树干 + 奶白/淡黄球冠，冒出丘陵之上点缀地平线
    # canopy_palette = [
    #     (0.93, 0.93, 0.88, 1.0), (0.95, 0.94, 0.83, 1.0), (0.90, 0.91, 0.86, 1.0),
    # ]
    # trunk_rgba = (0.40, 0.28, 0.18, 1.0)
    # for i in range(int(n_trees)):
    #     ang = 2.0 * math.pi * i / max(1, n_trees) + rng.uniform(-0.18, 0.18)
    #     R = half_size * rng.uniform(2.3, 3.6)
    #     x, y = R * math.cos(ang), R * math.sin(ang)
    #     trunk_h = half_size * rng.uniform(0.18, 0.30)   # 圆柱半长
    #     trunk_r = half_size * rng.uniform(0.020, 0.032)
    #     tname = f"tree_trunk_{i}"
    #     wb.add(
    #         "geom", name=tname, type="cylinder",
    #         size=(trunk_r, trunk_h), pos=(x, y, trunk_h),
    #         rgba=trunk_rgba, contype=0, conaffinity=0,
    #     )
    #     can_r = half_size * rng.uniform(0.13, 0.20)
    #     cname = f"tree_canopy_{i}"
    #     wb.add(
    #         "geom", name=cname, type="sphere",
    #         size=(can_r,), pos=(x, y, 2.0 * trunk_h + can_r * 0.4),
    #         rgba=rng.choice(canopy_palette), contype=0, conaffinity=0,
    #     )
    #     names.extend([tname, cname])

    return tuple(names)


def populate_arena(
    world: Any,
    scene: dict,
    *,
    dust_count: int = 220,
    dust_seed: int = 3,
    walls: bool = True,
    scenery: bool = True,
) -> ArenaInfo:
    """按场景配置往 world 添加围墙、食物源、气味斑、落灰与（可选）远景贴图。"""
    half = float(scene["arena_half_size_mm"])
    food_xy = tuple(scene["food_position_mm"])
    cue_radius = float(scene["food_cue_radius_mm"])
    contact_radius = float(scene["food_contact_radius_mm"])
    scenery_names: tuple[str, ...] = ()
    if scenery and bool(scene.get("scenery", True)):
        paint_environment(world)
        scenery_names = add_scenery(world, half_size=half, seed=int(dust_seed) + 4)
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
        scenery_geom_names=scenery_names,
    )
