# L4 Online LIF Demo Design

## Goal

Build a Level 4 demo branch that preserves the stable L3 lookup-table demo while adding a minimal online LIF attempt, real-time-style brain-state visualization, and telemetry views for the three required behaviors:

- Foraging toward food using a taste cue.
- Feeding after food contact.
- Stopping locomotion and entering grooming after fictive dust reaches its threshold.

## Scope

L4 will not claim to run Eon Systems' private code or a complete online 140k-neuron whole-brain emulation. It will implement a small Brian2-style or pure-Python LIF proxy in the embodied loop, benchmark the brain update cost, and record whether the requested control cadence is feasible on the local machine.

The stable L3 workflow remains intact:

- `scripts/run_l3_embodied_demo.py` continues to use `LookupBrainBridge`.
- `configs/l3_embodied_loop.json` remains the L3 default.
- L4 gets separate config, runner, outputs, docs, and metadata.

## Architecture

L4 reuses the current embodied-loop structure and swaps in a new bridge:

```text
VirtualEnvironment
  -> SensoryState
  -> OnlineLIFBrainBridge
  -> BrainReadout + BrainRuntimeState
  -> FlyGymLocomotionBody
  -> telemetry rows + body video + brain-state video + plots
```

The online bridge owns a small deterministic LIF state machine. It updates membrane-like variables and rates at a configurable `brain_sync_interval_s`, using sensory inputs as stimulus strengths:

- `food_cue` drives an MN9-like feeding channel.
- `dust_level` drives a grooming channel.
- `turn_bias` is seeded random-search steering outside the cue radius and chemotaxis steering only after `food_cue > 0`; L4 maps off-cue search with a separate `search_turn_gain` so random search is visible.

When a physics step happens between brain sync ticks, the bridge reuses the previous online readout and records it as a cached brain state. This makes the timing behavior explicit and supports the L4 fallback requirement.

## Outputs

Each L4 run writes to `outputs/l4_embodied_loop/`:

- FlyGym body video: real-time-style embodied motion reference.
- Brain-state visualization video, or GIF fallback if ffmpeg is unavailable: live-looking MN9/grooming membrane, spike/rate, behavior, and runtime cadence.
- Telemetry CSV: one row per logged sample with sensory state, brain readout, behavior, body action, and online brain timing.
- Telemetry PNG: `dust_level`, `food_cue`, behavior, readouts, and brain update timing.
- Brain benchmark JSON: mean, p95, max update time, target sync interval, achieved update frequency, and fallback/cached-step counts.
- Metadata JSON: config, sources, notes, outputs, and event times.

If MP4 encoding for the brain-state animation is unavailable, L4 attempts a GIF fallback. If no animation writer is available, it still writes the telemetry PNG and metadata note. The FlyGym body video remains the primary motion artifact.

## Behavior Rules

The behavior priority remains intentionally simple and explainable:

1. Grooming has highest priority when dust reaches the threshold.
2. During grooming, forward drive and turn drive are zero.
3. After the configured grooming hold, dust is cleared and foraging resumes.
4. Feeding starts on food contact and holds for the configured feeding duration.
5. Foraging uses seeded random search before cue entry, then food cue strength and local sensory turn bias to drive the existing FlyGym turning controller.

## Files

Create:

- `configs/l4_embodied_loop.json`: L4 defaults.
- `scripts/run_l4_embodied_demo.py`: CLI entry point.
- `src/digital_fruit_fly/l4_online_lif.py`: online LIF bridge and runtime state.
- `src/digital_fruit_fly/l4_demo.py`: L4 runner.
- `docs/l4_online_lif.md`: user-facing L4 notes.
- `tests/test_l4_online_lif.py`: unit tests for online brain timing and behavior.

Modify:

- `src/digital_fruit_fly/config.py`: add `L4_CONFIG_PATH`.
- `src/digital_fruit_fly/embodied_loop.py`: optionally accept extra telemetry fields and extra post-run visualization callbacks.
- `src/digital_fruit_fly/telemetry.py`: add L4 telemetry plot and brain-state animation helpers.
- `src/digital_fruit_fly/__init__.py`: export the L4 runner and bridge.
- `README.md`: document the L4 command and boundaries.
- `AGENTS.md`: add any new implementation constraints learned from L4.

## Testing

Standard-library unit tests cover the new L4 bridge without requiring FlyGym:

- Brain updates occur only on configured sync ticks.
- Cached steps preserve the previous readout and increment cached counters.
- Dust threshold enters grooming, holds locomotion at zero, clears dust after the hold, and returns to foraging.
- Food contact enters feeding and produces a high MN9-like readout.
- Benchmark summaries include update time statistics and fallback status.

Integration verification uses:

- `PYTHONPATH=src python -m unittest discover -s tests -p 'test_l4_online_lif.py' -v`
- `python scripts/run_l4_embodied_demo.py --duration 6.5 --no-video` for headless telemetry and plots.
- `python scripts/run_l4_embodied_demo.py --duration 6.5` when FlyGym rendering is available.

## Boundaries

L4 is a documented online LIF attempt and demonstration layer. It must say clearly when it is using a proxy or cached update rather than a full Shiu connectome run. The final report should frame this as public-component reproduction plus project-owned brain-body bridge logic, not as a complete biological reproduction.

Primary public references:

- Eon Systems, "How the Eon Team Produced a Virtual Embodied Fly", published 2026-03-10.
- Shiu et al., "A Drosophila computational brain model reveals sensorimotor processing", Nature 634, 210-219 (2024).
- FlyGym/NeuroMechFly public documentation and examples.
