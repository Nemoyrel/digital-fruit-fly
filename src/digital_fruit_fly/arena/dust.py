from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, TypedDict

from digital_fruit_fly.runtime.config import DustConfig


DEFAULT_MAX_LOAD: Final = 1.0
DUST_THRESHOLD_CROSSED: Final = "dust_threshold_crossed"
DUST_CLEAN: Final = "dust_clean"

DustEventName = Literal["dust_threshold_crossed", "dust_clean"]


class DustEventJson(TypedDict):
    name: DustEventName
    dust_load: float
    threshold: float


class DustSensoryJson(TypedDict):
    dust_load: float
    threshold_crossed: bool
    locomotion_sensory_enabled: bool


@dataclass(frozen=True)
class DustConfigError(Exception):
    __slots__ = ("field", "reason")

    field: str
    reason: str

    def __str__(self) -> str:
        return f"{self.field}: {self.reason}"


@dataclass(frozen=True)
class DustDynamicsConfig:
    __slots__ = (
        "accumulation_rate_per_sec",
        "threshold",
        "cleaning_rate_per_sec",
        "max_load",
    )

    accumulation_rate_per_sec: float
    threshold: float
    cleaning_rate_per_sec: float
    max_load: float

    def __post_init__(self) -> None:
        if self.accumulation_rate_per_sec < 0.0:
            raise DustConfigError(
                field="dust.accumulation_rate_per_sec",
                reason="must be non-negative",
            )
        if self.cleaning_rate_per_sec < 0.0:
            raise DustConfigError(
                field="dust.cleaning_rate_per_sec",
                reason="must be non-negative",
            )
        if self.max_load <= 0.0:
            raise DustConfigError(field="dust.max_load", reason="must be positive")
        if self.threshold <= 0.0:
            raise DustConfigError(field="dust.threshold", reason="must be positive")
        if self.threshold > self.max_load:
            raise DustConfigError(
                field="dust.threshold",
                reason="must be less than or equal to max_load",
            )


@dataclass(frozen=True)
class DustEvent:
    __slots__ = ("name", "dust_load", "threshold")

    name: DustEventName
    dust_load: float
    threshold: float

    def to_json_data(self) -> DustEventJson:
        return {
            "name": self.name,
            "dust_load": self.dust_load,
            "threshold": self.threshold,
        }


@dataclass(frozen=True)
class DustSensoryState:
    __slots__ = ("dust_load", "threshold_crossed", "locomotion_sensory_enabled")

    dust_load: float
    threshold_crossed: bool
    locomotion_sensory_enabled: bool

    def to_json_data(self) -> DustSensoryJson:
        return {
            "dust_load": self.dust_load,
            "threshold_crossed": self.threshold_crossed,
            "locomotion_sensory_enabled": self.locomotion_sensory_enabled,
        }


@dataclass(frozen=True)
class DustAdvanceResult:
    __slots__ = ("state", "events", "sensory")

    state: DustState
    events: tuple[DustEvent, ...]
    sensory: DustSensoryState


@dataclass(frozen=True)
class DustState:
    __slots__ = ("dust_load", "threshold_crossed")

    dust_load: float
    threshold_crossed: bool

    @classmethod
    def clean(cls) -> DustState:
        return cls(dust_load=0.0, threshold_crossed=False)

    @property
    def cleaned(self) -> bool:
        return self.dust_load == 0.0

    def advance(
        self,
        config: DustDynamicsConfig,
        tick_seconds: float,
        grooming_active: bool,
    ) -> DustAdvanceResult:
        if tick_seconds < 0.0:
            raise DustConfigError(field="tick_seconds", reason="must be non-negative")

        next_load = self._next_load(config, tick_seconds, grooming_active)
        clean_now = next_load == 0.0
        next_threshold_crossed = False if clean_now else self.threshold_crossed
        threshold_event = (not self.threshold_crossed) and next_load >= config.threshold
        clean_event = self.dust_load > 0.0 and clean_now

        events: tuple[DustEvent, ...] = ()
        if threshold_event:
            next_threshold_crossed = True
            events = (
                DustEvent(
                    name=DUST_THRESHOLD_CROSSED,
                    dust_load=next_load,
                    threshold=config.threshold,
                ),
            )
        if clean_event:
            events = (
                DustEvent(
                    name=DUST_CLEAN,
                    dust_load=0.0,
                    threshold=config.threshold,
                ),
            )

        next_state = DustState(
            dust_load=next_load,
            threshold_crossed=next_threshold_crossed,
        )
        return DustAdvanceResult(
            state=next_state,
            events=events,
            sensory=next_state.to_sensory_state(config),
        )

    def to_sensory_state(self, config: DustDynamicsConfig) -> DustSensoryState:
        threshold_crossed = self.dust_load >= config.threshold
        return DustSensoryState(
            dust_load=self.dust_load,
            threshold_crossed=threshold_crossed,
            locomotion_sensory_enabled=self.dust_load == 0.0,
        )

    def _next_load(
        self,
        config: DustDynamicsConfig,
        tick_seconds: float,
        grooming_active: bool,
    ) -> float:
        if grooming_active:
            return _clamp(
                self.dust_load - (config.cleaning_rate_per_sec * tick_seconds),
                0.0,
                config.max_load,
            )
        return _clamp(
            self.dust_load + (config.accumulation_rate_per_sec * tick_seconds),
            0.0,
            config.max_load,
        )


def build_dust_config_from_runtime(config: DustConfig) -> DustDynamicsConfig:
    return DustDynamicsConfig(
        accumulation_rate_per_sec=config.accumulation_rate_per_sec,
        threshold=config.threshold,
        cleaning_rate_per_sec=config.cleaning_rate_per_sec,
        max_load=DEFAULT_MAX_LOAD,
    )


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)
