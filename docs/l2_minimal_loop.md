# L2 Minimal Embodied Loop

L2 adds a small closed loop on top of the FlyGym body baseline:

```text
virtual scene -> sensory_state -> rule brain_bridge -> behavior_state
-> descending drive -> FlyGym body -> telemetry/video
```

## Run

```bash
conda activate flygym_env
python scripts/run_l2_embodied_demo.py --duration 10
```

Useful quick checks:

```bash
python scripts/run_l2_embodied_demo.py --duration 0.6 --no-video --no-plot
python scripts/run_l2_embodied_demo.py --duration 3 --log-every-steps 50
```

## Outputs

The script writes files under `outputs/l2_embodied_loop/`:

- `*.mp4`: FlyGym rendered demo video
- `*.csv`: telemetry log with sensory state, bridge readout, behavior state, action, and pose
- `*_telemetry.png`: compact plot of sensory cues, readouts, behavior, and left/right drive
- `*_metadata.json`: run config, event times, output paths, and notes

## What L2 Implements

- A larger flat arena, with the default half-size set in `configs/l2_embodied_loop.json`.
- A food marker, food cue radius, and food contact radius in the MuJoCo scene.
- Tracking camera parameters are read from `configs/l2_embodied_loop.json` under `camera`, currently `pos_offset` and `fovy`.
- Global fictive falling dust: `dust_level` accumulates over time across the whole arena, triggers grooming at a threshold, and is cleared after the grooming state finishes.
- `SensoryState` fields: `food_cue`, `turn_bias`, `dust_level`, `dust_threshold_reached`, `food_contact`, food distance, and time.
- Rule-based `BrainReadout` fields: `forward_drive`, `turn_bias`, `grooming_score`, `feeding_score`, `mn9_rate_hz`, and `behavior_state`.
- Behavior states: `foraging`, `grooming`, and `feeding`.
- L2 only halts locomotion during grooming/feeding state output. It does not yet add custom head, front-leg, or proboscis actuators for visible grooming or feeding motions.

## Boundary

The L2 bridge is an engineering placeholder. It does not claim to be a brain model.
In L3, the source of key `BrainReadout` values should be replaced by an empirical
lookup table generated from Shiu et al.-style LIF experiments.

## Source Note

The global dust accumulation rule follows Eon Systems' public description that
fictive dust accumulates on the embodied fly, causing it to stop, groom, and then
continue. Source: <https://eon.systems/updates/embodied-brain-emulation>.
