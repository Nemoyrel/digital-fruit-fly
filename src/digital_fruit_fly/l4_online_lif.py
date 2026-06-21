"""Small online LIF-style brain bridge for the L4 demo.

This is a deliberately compact proxy used to test online brain/body timing. It
does not run the full Shiu connectome model.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from .brain_bridge import _clip
from .state import BehaviorState, BrainReadout, SensoryState


@dataclass(frozen=True)
class OnlineBrainRuntimeState:
    """Timing and neural-state values recorded for L4 telemetry."""

    time_s: float
    brain_updated: bool
    brain_update_index: int
    target_sync_interval_s: float
    update_wall_time_ms: float
    mn9_voltage_mV: float
    grooming_voltage_mV: float
    mn9_rate_hz: float
    grooming_rate_hz: float
    feeding_score: float
    grooming_score: float
    realtime_target_met: bool


class OnlineLIFBrainBridge:
    """Online LIF-style bridge with cached reads between brain sync ticks."""

    def __init__(
        self,
        *,
        brain_sync_interval_s: float = 0.015,
        grooming_duration_s: float = 1.0,
        feeding_hold_s: float = 0.8,
        max_turn_drive: float = 0.55,
        search_turn_gain: float = 0.75,
        min_forward_drive: float = 0.12,
        max_forward_drive: float = 1.35,
        tau_s: float = 0.02,
        resting_voltage_mV: float = -52.0,
        threshold_voltage_mV: float = -45.0,
    ) -> None:
        self.brain_sync_interval_s = float(brain_sync_interval_s)
        self.grooming_duration_s = float(grooming_duration_s)
        self.feeding_hold_s = float(feeding_hold_s)
        self.max_turn_drive = float(max_turn_drive)
        self.search_turn_gain = float(search_turn_gain)
        self.min_forward_drive = float(min_forward_drive)
        self.max_forward_drive = float(max_forward_drive)
        self.tau_s = float(tau_s)
        self.resting_voltage_mV = float(resting_voltage_mV)
        self.threshold_voltage_mV = float(threshold_voltage_mV)

        self.behavior_state = BehaviorState.FORAGING
        self.state_until_s = 0.0
        self.just_completed_grooming = False

        self.mn9_voltage_mV = self.resting_voltage_mV
        self.grooming_voltage_mV = self.resting_voltage_mV
        self.last_brain_update_s: float | None = None
        self.first_brain_update_s: float | None = None
        self.update_wall_times_ms: list[float] = []
        self.brain_update_count = 0
        self.cached_step_count = 0
        self.last_readout = BrainReadout(
            behavior_state=BehaviorState.FORAGING,
            forward_drive=0.72,
            turn_bias=0.0,
            grooming_score=0.0,
            feeding_score=0.0,
            mn9_rate_hz=5.0,
            source="l4_online_lif_proxy",
        )
        self.last_runtime_state = OnlineBrainRuntimeState(
            time_s=0.0,
            brain_updated=False,
            brain_update_index=0,
            target_sync_interval_s=self.brain_sync_interval_s,
            update_wall_time_ms=0.0,
            mn9_voltage_mV=self.mn9_voltage_mV,
            grooming_voltage_mV=self.grooming_voltage_mV,
            mn9_rate_hz=5.0,
            grooming_rate_hz=0.0,
            feeding_score=0.0,
            grooming_score=0.0,
            realtime_target_met=True,
        )

    def _should_update_brain(self, now: float) -> bool:
        if self.last_brain_update_s is None:
            return True
        elapsed = now - self.last_brain_update_s
        return elapsed + 1e-12 >= self.brain_sync_interval_s

    def _advance_voltage(self, current: float, stimulus: float, dt_s: float) -> float:
        stimulus = _clip(stimulus, 0.0, 1.0)
        target = self.resting_voltage_mV + stimulus * 9.0
        alpha = _clip(dt_s / max(self.tau_s, 1e-9), 0.0, 1.0)
        updated = current + alpha * (target - current)
        if updated >= self.threshold_voltage_mV:
            return self.resting_voltage_mV
        return updated

    def _update_brain_state(self, sensory_state: SensoryState) -> None:
        now = sensory_state.time_s
        dt_s = (
            self.brain_sync_interval_s
            if self.last_brain_update_s is None
            else max(self.brain_sync_interval_s, now - self.last_brain_update_s)
        )
        start = perf_counter()

        self.mn9_voltage_mV = self._advance_voltage(
            self.mn9_voltage_mV,
            sensory_state.food_cue,
            dt_s,
        )
        self.grooming_voltage_mV = self._advance_voltage(
            self.grooming_voltage_mV,
            sensory_state.dust_level,
            dt_s,
        )

        feeding_score = _clip(sensory_state.food_cue, 0.0, 1.0)
        grooming_score = _clip(sensory_state.dust_level, 0.0, 1.0)
        mn9_rate_hz = 5.0 + 85.0 * feeding_score
        grooming_rate_hz = 4.0 + 70.0 * grooming_score

        elapsed_ms = (perf_counter() - start) * 1000.0
        self.update_wall_times_ms.append(elapsed_ms)
        self.brain_update_count += 1
        self.last_brain_update_s = now
        if self.first_brain_update_s is None:
            self.first_brain_update_s = now

        self.last_runtime_state = OnlineBrainRuntimeState(
            time_s=now,
            brain_updated=True,
            brain_update_index=self.brain_update_count,
            target_sync_interval_s=self.brain_sync_interval_s,
            update_wall_time_ms=elapsed_ms,
            mn9_voltage_mV=self.mn9_voltage_mV,
            grooming_voltage_mV=self.grooming_voltage_mV,
            mn9_rate_hz=mn9_rate_hz,
            grooming_rate_hz=grooming_rate_hz,
            feeding_score=feeding_score,
            grooming_score=grooming_score,
            realtime_target_met=elapsed_ms <= self.brain_sync_interval_s * 1000.0,
        )

    def _cache_brain_state(self, now: float) -> None:
        previous = self.last_runtime_state
        self.cached_step_count += 1
        self.last_runtime_state = OnlineBrainRuntimeState(
            time_s=now,
            brain_updated=False,
            brain_update_index=previous.brain_update_index,
            target_sync_interval_s=self.brain_sync_interval_s,
            update_wall_time_ms=0.0,
            mn9_voltage_mV=previous.mn9_voltage_mV,
            grooming_voltage_mV=previous.grooming_voltage_mV,
            mn9_rate_hz=previous.mn9_rate_hz,
            grooming_rate_hz=previous.grooming_rate_hz,
            feeding_score=previous.feeding_score,
            grooming_score=previous.grooming_score,
            realtime_target_met=previous.realtime_target_met,
        )

    def step(self, sensory_state: SensoryState) -> BrainReadout:
        """Update the online brain state and return a body-facing readout."""
        now = sensory_state.time_s
        self.just_completed_grooming = False

        if self._should_update_brain(now):
            self._update_brain_state(sensory_state)
        else:
            self._cache_brain_state(now)

        runtime = self.last_runtime_state

        if self.behavior_state == BehaviorState.GROOMING and now >= self.state_until_s:
            self.behavior_state = BehaviorState.FORAGING
            self.state_until_s = 0.0
            self.just_completed_grooming = True
            self.last_readout = BrainReadout(
                behavior_state=BehaviorState.FORAGING,
                forward_drive=0.65,
                turn_bias=0.0,
                grooming_score=0.0,
                feeding_score=runtime.feeding_score,
                mn9_rate_hz=runtime.mn9_rate_hz,
                dust_clearance=1.0,
                source="l4_online_lif_proxy",
            )
            return self.last_readout

        if self.behavior_state == BehaviorState.GROOMING:
            self.last_readout = BrainReadout(
                behavior_state=BehaviorState.GROOMING,
                forward_drive=0.0,
                turn_bias=0.0,
                grooming_score=runtime.grooming_score,
                feeding_score=runtime.feeding_score,
                mn9_rate_hz=runtime.mn9_rate_hz,
                source="l4_online_lif_proxy",
            )
            return self.last_readout

        if sensory_state.dust_threshold_reached:
            self.behavior_state = BehaviorState.GROOMING
            self.state_until_s = now + self.grooming_duration_s
        elif sensory_state.food_contact:
            self.behavior_state = BehaviorState.FEEDING
            self.state_until_s = max(self.state_until_s, now + self.feeding_hold_s)
        elif now >= self.state_until_s:
            self.behavior_state = BehaviorState.FORAGING

        if self.behavior_state == BehaviorState.FEEDING:
            self.last_readout = BrainReadout(
                behavior_state=BehaviorState.FEEDING,
                forward_drive=0.0,
                turn_bias=0.0,
                grooming_score=runtime.grooming_score,
                feeding_score=runtime.feeding_score,
                mn9_rate_hz=runtime.mn9_rate_hz,
                source="l4_online_lif_proxy",
            )
            return self.last_readout

        if self.behavior_state == BehaviorState.GROOMING:
            self.last_readout = BrainReadout(
                behavior_state=BehaviorState.GROOMING,
                forward_drive=0.0,
                turn_bias=0.0,
                grooming_score=runtime.grooming_score,
                feeding_score=runtime.feeding_score,
                mn9_rate_hz=runtime.mn9_rate_hz,
                source="l4_online_lif_proxy",
            )
            return self.last_readout

        forward_drive = 0.72 + 0.4 * runtime.feeding_score - 0.12 * runtime.grooming_score
        if sensory_state.food_cue <= 0.0:
            turn_drive = sensory_state.turn_bias * self.search_turn_gain
        else:
            turn_drive = sensory_state.turn_bias * (0.25 + 0.75 * runtime.feeding_score)
        self.last_readout = BrainReadout(
            behavior_state=BehaviorState.FORAGING,
            forward_drive=_clip(
                forward_drive,
                self.min_forward_drive,
                self.max_forward_drive,
            ),
            turn_bias=_clip(turn_drive, -self.max_turn_drive, self.max_turn_drive),
            grooming_score=runtime.grooming_score,
            feeding_score=runtime.feeding_score,
            mn9_rate_hz=runtime.mn9_rate_hz,
            source="l4_online_lif_proxy",
        )
        return self.last_readout

    def telemetry_fields(self) -> dict[str, float | int]:
        """Return current online-brain fields for the embodied telemetry row."""
        runtime = self.last_runtime_state
        return {
            "l4_brain_updated": int(runtime.brain_updated),
            "l4_brain_update_index": runtime.brain_update_index,
            "l4_target_sync_interval_s": runtime.target_sync_interval_s,
            "l4_update_wall_time_ms": runtime.update_wall_time_ms,
            "l4_mn9_voltage_mV": runtime.mn9_voltage_mV,
            "l4_grooming_voltage_mV": runtime.grooming_voltage_mV,
            "l4_mn9_rate_hz": runtime.mn9_rate_hz,
            "l4_grooming_rate_hz": runtime.grooming_rate_hz,
            "l4_cached_step_count": self.cached_step_count,
            "l4_realtime_target_met": int(runtime.realtime_target_met),
        }

    def benchmark_summary(self) -> dict[str, float | int | bool | str]:
        """Summarize online brain update timing for reports and metadata."""
        times = sorted(self.update_wall_times_ms)
        if times:
            mean_ms = sum(times) / len(times)
            p95_index = int(round((len(times) - 1) * 0.95))
            p95_ms = times[p95_index]
            max_ms = times[-1]
        else:
            mean_ms = p95_ms = max_ms = 0.0

        if (
            self.first_brain_update_s is not None
            and self.last_brain_update_s is not None
            and self.last_brain_update_s > self.first_brain_update_s
        ):
            achieved_hz = self.brain_update_count / (
                self.last_brain_update_s - self.first_brain_update_s
            )
        else:
            achieved_hz = 0.0

        realtime_target_met = max_ms <= self.brain_sync_interval_s * 1000.0
        status = "online_proxy_met_target" if realtime_target_met else "online_proxy_slow"
        return {
            "target_sync_interval_s": self.brain_sync_interval_s,
            "target_sync_hz": 1.0 / self.brain_sync_interval_s,
            "brain_update_count": self.brain_update_count,
            "cached_step_count": self.cached_step_count,
            "mean_update_wall_time_ms": mean_ms,
            "p95_update_wall_time_ms": p95_ms,
            "max_update_wall_time_ms": max_ms,
            "achieved_update_hz": achieved_hz,
            "realtime_target_met": realtime_target_met,
            "status": status,
            "boundary": "Small online LIF-style proxy; not a full Shiu connectome run.",
        }
