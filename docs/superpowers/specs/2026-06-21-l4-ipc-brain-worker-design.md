# L4 IPC Brain Worker Design

## Goal

Build a complete embodied fly demo where the FlyGym body loop runs in `flygym_env` and the Brian2 brain worker runs in `brain_env`. The two processes exchange:

```text
sensory_state -> brain_readout
```

over local IPC, then produce an Eon-style combined demonstration video with the embodied fly on the left and live brain-model state on the right.

The existing `level4-branch` fallback demo is preserved as a separate committed branch. This branch builds the stronger cross-environment L4 path.

## Public Reference Findings

Eon's March 10, 2026 article describes the public architecture but does not disclose a concrete IPC protocol. It says sensory events are mapped to neural inputs, brain activity is updated in a connectome-constrained model, selected descending outputs are translated into body commands, and movement feeds back into sensory state. It also says the current system syncs brain and body every about 15 ms: calculate the brain response, then simulate the body for 15 ms.

Eon uses phrases such as "pipe in" for neural activations entering the LIF model, but the official article does not specify socket, HTTP, ZeroMQ, shared memory, file queues, or an equivalent transport. Therefore this project will use a standard-library TCP JSON-lines protocol as its own engineering bridge and will document that choice as project code, not an Eon implementation detail.

## Brian2 Performance Findings

The local `brain_env` already has:

- `brian2 2.9.0`
- `Cython 3.2.5`
- `/usr/bin/clang`, `/usr/bin/gcc`, and `/usr/bin/g++`
- `pandas`, `pyarrow`, `joblib`, and `numpy`

It does not have `pyzmq`, so ZeroMQ would require installing a new dependency in at least `brain_env`.

Brian2's official documentation says C++ code generation is highly recommended because it can drastically increase simulation speed, and that runtime code generation automatically chooses the best target when possible, using `cython` when Cython and a compiler are available. The Shiu repository README similarly warns that default Brian2 performance can be limited and points users to C++ code generation.

For this branch, the worker will:

1. Prefer Brian2 `cython` runtime target when available, because `brain_env` already has Cython and compilers.
2. Avoid installing a new Brian2 package unless a benchmark proves the current environment cannot use compiled code.
3. Record Brian2 version, target, compiler availability, model backend, per-request latency, and any fallback reason.
4. Keep a `brian2_proxy` backend for stable IPC and video generation if the full Shiu backend is too slow.

## Architecture

```text
brain_env process
  scripts/run_l4_brain_worker.py
    L4BrainWorkerServer
      TcpJsonlServer
      Brian2ProxyBackend
      ShiuFullBackend

flygym_env process
  scripts/run_l4_ipc_embodied_demo.py
    IpcBrainBridge
      TcpJsonlClient
      timeout/cache fallback
    run_embodied_loop(...)

post-processing
  combine_body_and_brain_video(...)
  telemetry plots and benchmark JSON
```

The TCP protocol is newline-delimited JSON over `127.0.0.1`. Each request carries a compact sensory state:

```json
{
  "type": "sensory_state",
  "request_id": 17,
  "time_s": 1.245,
  "food_cue": 0.82,
  "turn_bias": -0.13,
  "dust_level": 0.44,
  "dust_threshold_reached": false,
  "food_contact": false,
  "food_distance_mm": 3.2
}
```

Each response carries a body-facing readout and worker timing:

```json
{
  "type": "brain_readout",
  "request_id": 17,
  "behavior_state": "foraging",
  "forward_drive": 0.94,
  "turn_bias": -0.08,
  "grooming_score": 0.44,
  "feeding_score": 0.82,
  "mn9_rate_hz": 74.7,
  "dust_clearance": 0.0,
  "source": "brain_worker:brian2_proxy",
  "backend": "brian2_proxy",
  "brain_wall_time_ms": 1.4,
  "brain_simulated_window_s": 0.015,
  "cache_hit": false
}
```

## Brain Backends

### `brian2_proxy`

This backend runs a small Brian2 model inside `brain_env`, using the same LIF constants style as Shiu's `model.py`. It is the stable online worker backend used for IPC tests and demo fallback.

Inputs:

- `food_cue` drives an MN9-like channel.
- `dust_level` drives a grooming-like channel.

Outputs:

- `mn9_rate_hz`
- `feeding_score`
- `grooming_score`
- runtime voltage/rate traces for visualization

### `shiu_full`

This backend attempts to load `external/drosophila_brain_model/model.py`, the local completeness CSV, and connectivity parquet in `brain_env`. It will run a small request window or quantized stimulus experiment using Shiu's Brian2 model code where feasible.

Because reconstructing the full 140k-neuron, 50M-synapse model per body frame is expected to be too slow, the full backend is allowed to:

- warm up/load once at worker startup;
- quantize sensory inputs and cache repeated windows;
- benchmark a small number of requests before the FlyGym loop starts;
- report `fallback_reason` and let the demo switch to `brian2_proxy` when full backend latency exceeds the configured budget.

The final report must clearly distinguish `shiu_full_attempted`, `shiu_full_used`, and `brian2_proxy_used`.

## Body Loop

`run_l4_ipc_embodied_demo.py` starts from the existing L4 fallback runner but swaps in `IpcBrainBridge`.

The bridge:

- sends sensory rows to the brain worker at a configurable control interval, default `0.015s`;
- waits up to a small timeout, default `0.05s`;
- uses the last valid readout on timeout;
- records timeout count, request count, worker latency, and cache-hit count;
- never blocks L3 or the fallback L4 demo.

Behavior priority remains the same:

1. dust threshold triggers grooming;
2. grooming holds locomotion at zero and clears dust after the hold;
3. food contact triggers feeding;
4. foraging follows food cue and turn bias.

## Eon-Style Video Output

Final L4 IPC runs should produce:

- body-only FlyGym video;
- brain-state animation video or GIF;
- combined side-by-side video where the left panel is the embodied fly and the right panel is brain activity/readout state;
- existing telemetry plot;
- L4 IPC plot showing `food_cue`, `dust_level`, worker latency, backend, timeout/cache status, and behavior transitions;
- CSV and JSON metadata with every output path.

If ffmpeg is unavailable, the run should still write the body video if FlyGym can render, a brain-state GIF fallback if pillow is available, and static telemetry plots.

## Testing

Unit tests should not require FlyGym or the full brain model:

- JSON-lines request/response serialization.
- TCP server/client round trip with `brian2_proxy` or a deterministic fake backend.
- `IpcBrainBridge` timeout fallback to the previous readout.
- Backend selection result object records `shiu_full` failure and `brian2_proxy` fallback.
- Combined-video planner returns the expected output names and fallback behavior.

Integration commands:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall src scripts
/opt/miniconda3/envs/brain_env/bin/python scripts/run_l4_brain_worker.py --backend brian2_proxy --once-smoke
/opt/miniconda3/envs/flygym_env/bin/python scripts/run_l4_ipc_embodied_demo.py --duration 0.5 --no-video --no-plot
```

Full demo command:

```bash
/opt/miniconda3/envs/brain_env/bin/python scripts/run_l4_brain_worker.py --backend auto
/opt/miniconda3/envs/flygym_env/bin/python scripts/run_l4_ipc_embodied_demo.py --duration 8 --combine-video
```

## Boundaries

This branch should not claim that the project has reproduced Eon's unpublished IPC or private bridge code. It should say:

- Eon publicly describes a 15 ms brain/body sync loop.
- Eon does not publicly specify the transport protocol.
- This project implements its own TCP JSON-lines IPC bridge.
- Full Shiu Brian2 online operation is attempted and benchmarked.
- Stable demo output may use `brian2_proxy` if full online Shiu latency is too high.
