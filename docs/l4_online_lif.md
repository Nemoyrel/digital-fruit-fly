# L4 Online LIF Attempt

L4 adds an online brain-update attempt on top of the stable L3 embodied demo. It is an Eon-inspired engineering demonstration, not a complete online whole-brain reproduction.

## Run

Use the FlyGym environment for the embodied loop:

```bash
conda activate flygym_env
python scripts/run_l4_embodied_demo.py --duration 8 --log-every-steps 50
```

Headless smoke test:

```bash
conda activate flygym_env
python scripts/run_l4_embodied_demo.py --duration 0.2 --no-video --no-plot
```

## Outputs

Runs write to `outputs/l4_embodied_loop/`:

- `*.mp4`: FlyGym body video showing real-time-style locomotion, feeding halt, and grooming halt.
- `*_brain_state.mp4`: animated online brain proxy state when ffmpeg encoding is available.
- `*_brain_state.gif`: brain-state animation fallback when ffmpeg is unavailable but pillow is available.
- `*_l4_telemetry.png`: L4 telemetry plot with `food_cue`, `dust_level`, readouts, behavior, and update timing.
- `*_brain_benchmark.json`: online update timing, cached body steps, achieved frequency, and realtime target status.
- `*.csv`: logged embodied-loop telemetry, including `l4_*` brain-state fields.
- `*_metadata.json`: config, event times, notes, sources, output paths, and benchmark summary.

## Online Brain Proxy

`OnlineLIFBrainBridge` updates a small deterministic LIF-style proxy at `brain_sync_interval_s` from `configs/l4_embodied_loop.json`. Between sync ticks, the body loop reuses the latest brain readout and records the step as cached.

Mapped channels:

- `food_cue` drives an MN9-like feeding readout.
- `dust_level` drives a grooming-like readout.
- `turn_bias` is random-search steering while `food_cue == 0`, then chemotaxis steering after the fly enters the food cue radius.

Behavior priority:

1. Dust threshold triggers grooming.
2. Grooming sets forward and turn drive to zero.
3. Grooming completion clears dust and returns to foraging.
4. Food contact triggers feeding and holds movement at zero.
5. Foraging performs seeded random search outside the food cue radius, then follows the local food direction after `food_cue > 0`.

## Search And Chemotaxis

The virtual scene no longer exposes global food direction when the fly is outside the cue field. `VirtualEnvironment` returns a seeded random search turn in that case, controlled by `search_seed`, `search_turn_interval_s`, and `search_turn_strength` in `configs/l4_embodied_loop.json`.

`OnlineLIFBrainBridge` then maps off-cue search turns with the separate `search_turn_gain` bridge parameter. This avoids the earlier fixed `0.25` turn scaling and makes random search visible before chemotaxis starts.

Once the fly enters the cue radius, `food_cue` becomes positive and `turn_bias` switches to the local direction of the food source. This makes the demo behavior closer to the intended story: random exploration first, chemotaxis only after a taste/odor-like cue is available.

## Benchmark Fields

The benchmark JSON includes:

- `target_sync_interval_s` and `target_sync_hz`
- `brain_update_count`
- `cached_step_count`
- `mean_update_wall_time_ms`
- `p95_update_wall_time_ms`
- `max_update_wall_time_ms`
- `achieved_update_hz`
- `realtime_target_met`
- `status`

`realtime_target_met` only describes this small proxy on the local machine. It must not be presented as evidence that the complete Shiu connectome can run online inside the FlyGym loop.

## Boundary

L4 is a documented online LIF attempt and fallback demonstration. It preserves L3 as the stable empirical-readout demo. If the full online brain model is too slow or unavailable, the final report should present the L4 benchmark and keep the L3 video/logs as the reliable result.
