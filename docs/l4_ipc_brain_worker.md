# L4 IPC Brain Worker Demo

This branch adds a stronger L4 attempt: the FlyGym body loop runs in `flygym_env`, while a Brian2 brain worker runs in `brain_env`. The two processes exchange `sensory_state -> brain_readout` over a local TCP JSON-lines protocol.

## Why TCP JSON-Lines

Eon's public article describes a brain/body loop synchronized at about 15 ms, but it does not disclose the transport protocol between the LIF brain model and the embodied simulation. This project therefore uses its own standard-library TCP JSON-lines bridge. Do not describe this as Eon's IPC mechanism.

ZeroMQ was not chosen because `brain_env` does not currently include `pyzmq`; TCP JSON-lines avoids adding a dependency to either conda environment.

## Brian2 Performance

`brain_env` already includes Brian2, Cython, and system compilers. The worker records the Brian2 version, compiler availability, and selected codegen target. In the local check, `brian2_proxy` reports `codegen_target: cython`.

The Shiu repository notes that Brian2 performance can be limited without compiled code generation. This branch attempts a `shiu_full` backend, but it is allowed to fail fast and fall back to `brian2_proxy` if the full model cannot meet the startup or per-request budget. The metadata distinguishes:

- `shiu_full` attempted;
- `shiu_full` used;
- `brian2_proxy` used as stable fallback.

## Run Flow

Terminal 1, brain worker:

```bash
/opt/miniconda3/envs/brain_env/bin/python scripts/run_l4_brain_worker.py --backend auto --host 127.0.0.1 --port 8765
```

Terminal 2, embodied loop:

```bash
/opt/miniconda3/envs/flygym_env/bin/python scripts/run_l4_ipc_embodied_demo.py --duration 8 --combine-video
```

Smoke test the worker without opening a socket:

```bash
/opt/miniconda3/envs/brain_env/bin/python scripts/run_l4_brain_worker.py --backend brian2_proxy --once-smoke
```

Headless IPC run:

```bash
/opt/miniconda3/envs/flygym_env/bin/python scripts/run_l4_ipc_embodied_demo.py --duration 0.5 --no-video --no-plot
```

## Outputs

L4 IPC writes to `outputs/l4_ipc_embodied_loop/`:

- body FlyGym video;
- brain-state MP4, or GIF fallback when ffmpeg is unavailable;
- combined side-by-side video when body and brain MP4s are available;
- regular telemetry plot;
- IPC telemetry plot;
- CSV telemetry with `ipc_*` fields;
- metadata JSON with IPC summary and output paths.

The intended combined video layout is body-left, brain-right, matching the spirit of the Eon website demonstration while staying clear that this is a project-owned bridge.

## Boundaries

This is not a fly upload and not a reproduction of Eon's private bridge. It is a public-component integration attempt:

- FlyGym/NeuroMechFly body simulation;
- Brian2 brain worker in a separate conda environment;
- project-owned TCP IPC bridge;
- Shiu full-model attempt with benchmark/fallback logging;
- stable Brian2 proxy fallback when full online execution is too slow.
