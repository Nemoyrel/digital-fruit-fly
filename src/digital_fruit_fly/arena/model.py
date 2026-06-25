from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TypedDict

from digital_fruit_fly.runtime.config import ArenaConfig


class PointJson(TypedDict):
    x_mm: float
    y_mm: float


class VectorJson(TypedDict):
    dx_mm: float
    dy_mm: float


class DimensionsJson(TypedDict):
    width_mm: float
    height_mm: float


class FoodJson(TypedDict):
    center: PointJson
    radius_mm: float
    cue_radius_mm: float


class CueSensorsJson(TypedDict):
    lateral_offset_mm: float
    forward_offset_mm: float


class ArenaJson(TypedDict):
    dimensions: DimensionsJson
    food: FoodJson
    cue_sensors: CueSensorsJson


@dataclass(frozen=True)
class ArenaConfigError(Exception):
    __slots__ = ("field", "reason")

    field: str
    reason: str

    def __str__(self) -> str:
        return f"{self.field}: {self.reason}"


@dataclass(frozen=True)
class Point2D:
    __slots__ = ("x_mm", "y_mm")

    x_mm: float
    y_mm: float

    def to_json_data(self) -> PointJson:
        return {"x_mm": self.x_mm, "y_mm": self.y_mm}


@dataclass(frozen=True)
class Vector2D:
    __slots__ = ("dx_mm", "dy_mm")

    dx_mm: float
    dy_mm: float

    def to_json_data(self) -> VectorJson:
        return {"dx_mm": self.dx_mm, "dy_mm": self.dy_mm}


@dataclass(frozen=True)
class FlyPose2D:
    __slots__ = ("x_mm", "y_mm", "heading_rad")

    x_mm: float
    y_mm: float
    heading_rad: float

    @property
    def point(self) -> Point2D:
        return Point2D(x_mm=self.x_mm, y_mm=self.y_mm)


@dataclass(frozen=True)
class ArenaDimensions:
    __slots__ = ("width_mm", "height_mm")

    width_mm: float
    height_mm: float

    def __post_init__(self) -> None:
        if self.width_mm <= 0.0:
            raise ArenaConfigError(field="dimensions.width_mm", reason="must be positive")
        if self.height_mm <= 0.0:
            raise ArenaConfigError(field="dimensions.height_mm", reason="must be positive")

    def contains(self, point: Point2D) -> bool:
        return 0.0 <= point.x_mm <= self.width_mm and 0.0 <= point.y_mm <= self.height_mm

    def to_json_data(self) -> DimensionsJson:
        return {"width_mm": self.width_mm, "height_mm": self.height_mm}


@dataclass(frozen=True)
class FoodSource:
    __slots__ = ("center", "radius_mm", "cue_radius_mm")

    center: Point2D
    radius_mm: float
    cue_radius_mm: float

    def __post_init__(self) -> None:
        if self.radius_mm <= 0.0:
            raise ArenaConfigError(field="food.radius_mm", reason="must be positive")
        if self.cue_radius_mm <= self.radius_mm:
            raise ArenaConfigError(
                field="food.cue_radius_mm",
                reason="must be greater than food radius",
            )

    def to_json_data(self) -> FoodJson:
        return {
            "center": self.center.to_json_data(),
            "radius_mm": self.radius_mm,
            "cue_radius_mm": self.cue_radius_mm,
        }


@dataclass(frozen=True)
class CueSensorGeometry:
    __slots__ = ("lateral_offset_mm", "forward_offset_mm")

    lateral_offset_mm: float
    forward_offset_mm: float

    def __post_init__(self) -> None:
        if self.lateral_offset_mm <= 0.0:
            raise ArenaConfigError(field="cue_sensors.lateral_offset_mm", reason="must be positive")
        if self.forward_offset_mm < 0.0:
            raise ArenaConfigError(
                field="cue_sensors.forward_offset_mm",
                reason="must be non-negative",
            )

    def to_json_data(self) -> CueSensorsJson:
        return {
            "lateral_offset_mm": self.lateral_offset_mm,
            "forward_offset_mm": self.forward_offset_mm,
        }


@dataclass(frozen=True)
class BoundaryClampResult:
    __slots__ = ("pose", "collided_x", "collided_y")

    pose: FlyPose2D
    collided_x: bool
    collided_y: bool

    @property
    def collided(self) -> bool:
        return self.collided_x or self.collided_y


@dataclass(frozen=True)
class SugarCueSample:
    __slots__ = ("left", "right")

    left: float
    right: float


@dataclass(frozen=True)
class ArenaGeometry:
    __slots__ = ("dimensions", "food", "cue_sensors")

    dimensions: ArenaDimensions
    food: FoodSource
    cue_sensors: CueSensorGeometry

    def __post_init__(self) -> None:
        if not self.dimensions.contains(self.food.center):
            raise ArenaConfigError(field="food.center", reason="must be inside arena bounds")
        if self.food.center.x_mm - self.food.radius_mm < 0.0:
            raise ArenaConfigError(field="food.radius_mm", reason="food disk must be fully inside arena")
        if self.food.center.x_mm + self.food.radius_mm > self.dimensions.width_mm:
            raise ArenaConfigError(field="food.radius_mm", reason="food disk must be fully inside arena")
        if self.food.center.y_mm - self.food.radius_mm < 0.0:
            raise ArenaConfigError(field="food.radius_mm", reason="food disk must be fully inside arena")
        if self.food.center.y_mm + self.food.radius_mm > self.dimensions.height_mm:
            raise ArenaConfigError(field="food.radius_mm", reason="food disk must be fully inside arena")

    def clamp_pose(self, pose: FlyPose2D) -> BoundaryClampResult:
        x_mm = _clamp(pose.x_mm, 0.0, self.dimensions.width_mm)
        y_mm = _clamp(pose.y_mm, 0.0, self.dimensions.height_mm)
        return BoundaryClampResult(
            pose=FlyPose2D(x_mm=x_mm, y_mm=y_mm, heading_rad=pose.heading_rad),
            collided_x=x_mm != pose.x_mm,
            collided_y=y_mm != pose.y_mm,
        )

    def vector_to_food(self, pose: FlyPose2D) -> Vector2D:
        return Vector2D(
            dx_mm=self.food.center.x_mm - pose.x_mm,
            dy_mm=self.food.center.y_mm - pose.y_mm,
        )

    def distance_to_food(self, pose: FlyPose2D) -> float:
        vector = self.vector_to_food(pose)
        return math.hypot(vector.dx_mm, vector.dy_mm)

    def sugar_cue_strength_at(self, point: Point2D) -> float:
        distance = math.hypot(
            self.food.center.x_mm - point.x_mm,
            self.food.center.y_mm - point.y_mm,
        )
        if distance >= self.food.cue_radius_mm:
            return 0.0
        return 1.0 - (distance / self.food.cue_radius_mm)

    def sample_sugar_cue(self, pose: FlyPose2D) -> SugarCueSample:
        left_point = self._sensor_point(pose, lateral_sign=1.0)
        right_point = self._sensor_point(pose, lateral_sign=-1.0)
        return SugarCueSample(
            left=self.sugar_cue_strength_at(left_point),
            right=self.sugar_cue_strength_at(right_point),
        )

    def is_food_contact(self, pose: FlyPose2D) -> bool:
        return self.distance_to_food(pose) <= self.food.radius_mm

    def to_json_data(self) -> ArenaJson:
        return {
            "dimensions": self.dimensions.to_json_data(),
            "food": self.food.to_json_data(),
            "cue_sensors": self.cue_sensors.to_json_data(),
        }

    def _sensor_point(self, pose: FlyPose2D, lateral_sign: float) -> Point2D:
        heading_x = math.cos(pose.heading_rad)
        heading_y = math.sin(pose.heading_rad)
        left_x = -heading_y
        left_y = heading_x
        return Point2D(
            x_mm=pose.x_mm
            + (heading_x * self.cue_sensors.forward_offset_mm)
            + (left_x * self.cue_sensors.lateral_offset_mm * lateral_sign),
            y_mm=pose.y_mm
            + (heading_y * self.cue_sensors.forward_offset_mm)
            + (left_y * self.cue_sensors.lateral_offset_mm * lateral_sign),
        )


def build_arena_geometry_from_runtime(config: ArenaConfig) -> ArenaGeometry:
    return ArenaGeometry(
        dimensions=ArenaDimensions(width_mm=config.width_mm, height_mm=config.height_mm),
        food=FoodSource(
            center=Point2D(
                x_mm=config.sugar.center_x_mm,
                y_mm=config.sugar.center_y_mm,
            ),
            radius_mm=config.sugar.radius,
            cue_radius_mm=config.sugar.cue_radius,
        ),
        cue_sensors=CueSensorGeometry(lateral_offset_mm=0.75, forward_offset_mm=0.5),
    )


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)
