from __future__ import annotations

from typing import assert_never

from digital_fruit_fly.body.server_motion import (
    apply_tick,
    arena_row,
    control_frame,
    control_row,
    initial_state,
    sensory_frame,
    trajectory_row,
)
from digital_fruit_fly.body.server_artifacts import append_bridge_frame
from digital_fruit_fly.body.server_flygym import FlyGymBodyRuntime, open_flygym_runtime
from digital_fruit_fly.body.server_peer import FixtureBrainPeer, connect_brain_peer
from digital_fruit_fly.body.server_types import (
    BodyLoopResult,
    BodyRunContext,
    BodySimulation,
    BrainPeer,
    TickInputs,
    TickRecord,
)
from digital_fruit_fly.runtime.logging import append_jsonl
from digital_fruit_fly.runtime.timeouts import JsonObject


def run_body_loop(context: BodyRunContext) -> BodyLoopResult:
    match context.config.brain_mode:
        case "fixture":
            peer = FixtureBrainPeer(
                context.config.output_dir.name,
                context.simulation.runtime.tick_ms,
            )
            return _run_with_live_flygym(context, peer)
        case "connect":
            return _run_with_live_flygym(context, connect_brain_peer(context))
        case unreachable:
            assert_never(unreachable)


def _run_with_live_flygym(context: BodyRunContext, peer: BrainPeer) -> BodyLoopResult:
    flygym = open_flygym_runtime()
    live_context = BodyRunContext(
        context.config,
        context.artifacts,
        BodySimulation(context.simulation.runtime, flygym.contract),
    )
    try:
        ticks = _run_loop(live_context, peer, flygym)
        return BodyLoopResult(ticks, flygym.summary())
    finally:
        flygym.close()


def _run_loop(context: BodyRunContext, peer: BrainPeer, flygym: FlyGymBodyRuntime) -> int:
    state = initial_state(context)
    for tick_index in range(context.config.max_ticks):
        sensory = sensory_frame(context, state, tick_index)
        brain = peer.next_frame(sensory)
        control = control_frame(context, sensory, brain)
        record = apply_tick(context, TickInputs(state, sensory, brain, control))
        _append_tick(context, record, flygym.step(record.command))
        state = record.state
    peer.shutdown(
        context.config.max_ticks,
        context.config.max_ticks * context.tick_seconds,
    )
    return context.config.max_ticks


def _append_tick(context: BodyRunContext, record: TickRecord, flygym: JsonObject) -> None:
    arena = arena_row(record)
    arena["flygym"] = flygym
    append_bridge_frame(context.artifacts.frames_path, record.sensory)
    append_bridge_frame(context.artifacts.frames_path, record.brain)
    append_bridge_frame(context.artifacts.frames_path, record.control)
    append_jsonl(context.artifacts.trajectory_path, trajectory_row(record))
    append_jsonl(context.artifacts.layout.control_path, control_row(record))
    append_jsonl(context.artifacts.layout.arena_path, arena)
