# L4 IPC Brain Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a cross-environment L4 demo where `brain_env` runs a Brian2 brain worker and `flygym_env` runs the embodied FlyGym loop over local TCP JSON-lines IPC.

**Architecture:** The branch adds a small standard-library TCP JSON-lines protocol, a `brain_env` worker with `brian2_proxy` and `shiu_full` attempt backends, and a FlyGym-side `IpcBrainBridge` client that falls back to cached readouts on timeout. It preserves the fallback `level4-branch` proxy demo and adds side-by-side Eon-style video composition.

**Tech Stack:** Python standard library sockets/JSON/threading, Brian2 in `brain_env`, existing FlyGym wrapper in `flygym_env`, matplotlib/Pillow/ffmpeg fallback for visualization, unittest for non-FlyGym tests.

---

### Task 1: IPC Protocol And Client/Server Primitives

**Files:**
- Create: `src/digital_fruit_fly/ipc_protocol.py`
- Create: `tests/test_ipc_protocol.py`

- [ ] **Step 1: Write failing protocol tests**

Create `tests/test_ipc_protocol.py` with `unittest` tests for:

```python
import unittest

from digital_fruit_fly.ipc_protocol import (
    BrainReadoutMessage,
    SensoryStateMessage,
    decode_message,
    encode_message,
)


class IpcProtocolTest(unittest.TestCase):
    def test_sensory_state_round_trip(self):
        msg = SensoryStateMessage(
            request_id=7,
            time_s=0.15,
            food_cue=0.8,
            turn_bias=-0.2,
            dust_level=0.4,
            dust_threshold_reached=False,
            food_contact=True,
            food_distance_mm=1.2,
        )
        decoded = decode_message(encode_message(msg))
        self.assertEqual(decoded, msg)

    def test_brain_readout_round_trip(self):
        msg = BrainReadoutMessage(
            request_id=7,
            behavior_state="feeding",
            forward_drive=0.0,
            turn_bias=0.0,
            grooming_score=0.1,
            feeding_score=0.95,
            mn9_rate_hz=88.0,
            dust_clearance=0.0,
            source="brain_worker:brian2_proxy",
            backend="brian2_proxy",
            brain_wall_time_ms=1.5,
            brain_simulated_window_s=0.015,
            cache_hit=False,
            extra={"mn9_voltage_mV": -48.0},
        )
        decoded = decode_message(encode_message(msg))
        self.assertEqual(decoded, msg)

    def test_unknown_type_raises_value_error(self):
        with self.assertRaises(ValueError):
            decode_message(b'{"type":"surprise"}\n')
```

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=src python -m unittest tests.test_ipc_protocol -v`

Expected: import fails because `ipc_protocol.py` does not exist.

- [ ] **Step 3: Implement protocol**

Create dataclasses `SensoryStateMessage` and `BrainReadoutMessage`, plus `encode_message()` and `decode_message()`. The encoder returns one UTF-8 JSON object plus newline. The decoder accepts bytes or str and reconstructs the right dataclass by `type`.

- [ ] **Step 4: Run GREEN**

Run: `PYTHONPATH=src python -m unittest tests.test_ipc_protocol -v`

Expected: 3 tests pass.

### Task 2: Brain Worker Backends

**Files:**
- Create: `src/digital_fruit_fly/brain_worker.py`
- Create: `scripts/run_l4_brain_worker.py`
- Create: `tests/test_brain_worker.py`

- [ ] **Step 1: Write failing backend tests**

Create tests for:

- `Brian2ProxyBackend.handle()` maps food cue to high MN9/feeding score.
- dust threshold returns grooming readout and later dust clearance.
- `select_backend("auto")` returns a backend object and selection metadata containing Brian2 version, codegen target, and compiler availability.
- `ShiuFullBackend(..., max_startup_s=0.0).available` is false with a non-empty fallback reason.

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=src python -m unittest tests.test_brain_worker -v`

Expected: import fails because `brain_worker.py` does not exist.

- [ ] **Step 3: Implement backends**

Implement:

- `BrainWorkerConfig`
- `BackendSelection`
- `Brian2ProxyBackend`
- `ShiuFullBackend`
- `select_backend()`
- `L4BrainWorkerServer`

`Brian2ProxyBackend` should run in `brain_env`, set Brian2 prefs to `cython` when possible, and fall back to `numpy` target if compiled runtime fails. `ShiuFullBackend` should attempt imports and metadata/load checks, but must fail fast under configured startup budgets instead of blocking the demo.

- [ ] **Step 4: Add CLI**

`scripts/run_l4_brain_worker.py` supports:

```bash
--host 127.0.0.1
--port 8765
--backend auto|brian2_proxy|shiu_full
--once-smoke
--max-startup-s 10
```

`--once-smoke` should construct the backend, run one synthetic request, print JSON, and exit.

- [ ] **Step 5: Run GREEN**

Run:

```bash
PYTHONPATH=src python -m unittest tests.test_brain_worker -v
/opt/miniconda3/envs/brain_env/bin/python scripts/run_l4_brain_worker.py --backend brian2_proxy --once-smoke
```

Expected: unit tests pass and smoke command prints one `brain_readout` JSON.

### Task 3: TCP JSON-Lines Round Trip

**Files:**
- Modify: `src/digital_fruit_fly/brain_worker.py`
- Create: `src/digital_fruit_fly/ipc_client.py`
- Create: `tests/test_ipc_roundtrip.py`

- [ ] **Step 1: Write failing round-trip test**

Create a test that starts `L4BrainWorkerServer` on port `0` in a background thread with `Brian2ProxyBackend`, connects with `TcpJsonlClient`, sends one `SensoryStateMessage`, receives a `BrainReadoutMessage`, then shuts the server down.

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=src python -m unittest tests.test_ipc_roundtrip -v`

Expected: import or missing client failure.

- [ ] **Step 3: Implement client and server loop**

Implement `TcpJsonlClient.request()` with socket timeout, one request per connection or persistent connection if simple. Implement server accept loop, `serve_background()`, and `shutdown()`.

- [ ] **Step 4: Run GREEN**

Run: `PYTHONPATH=src python -m unittest tests.test_ipc_roundtrip -v`

Expected: round trip passes locally without FlyGym.

### Task 4: FlyGym-Side IPC Brain Bridge

**Files:**
- Create: `src/digital_fruit_fly/l4_ipc_bridge.py`
- Create: `configs/l4_ipc_embodied_loop.json`
- Create: `src/digital_fruit_fly/l4_ipc_demo.py`
- Create: `scripts/run_l4_ipc_embodied_demo.py`
- Modify: `src/digital_fruit_fly/__init__.py`
- Create: `tests/test_l4_ipc_bridge.py`

- [ ] **Step 1: Write failing bridge tests**

Tests cover:

- successful response converts to `BrainReadout`;
- timeout returns previous readout and increments timeout count;
- `telemetry_fields()` includes `ipc_request_count`, `ipc_timeout_count`, `ipc_backend`, and `ipc_brain_wall_time_ms`.

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=src python -m unittest tests.test_l4_ipc_bridge -v`

Expected: import fails because `l4_ipc_bridge.py` does not exist.

- [ ] **Step 3: Implement bridge**

`IpcBrainBridge.step()` converts `SensoryState` to `SensoryStateMessage`, sends via `TcpJsonlClient`, and converts `BrainReadoutMessage` to `BrainReadout`. It keeps fallback readout on timeout and records IPC telemetry.

- [ ] **Step 4: Implement runner and config**

`configs/l4_ipc_embodied_loop.json` derives from L4 fallback config and adds:

```json
"ipc": {
  "host": "127.0.0.1",
  "port": 8765,
  "timeout_s": 0.05,
  "start_worker": false,
  "brain_env_python": "/opt/miniconda3/envs/brain_env/bin/python"
}
```

`scripts/run_l4_ipc_embodied_demo.py` mirrors L4 CLI and adds `--host`, `--port`, `--timeout`, `--start-worker`, and `--combine-video`.

- [ ] **Step 5: Run GREEN**

Run: `PYTHONPATH=src python -m unittest tests.test_l4_ipc_bridge -v`

Expected: tests pass.

### Task 5: Eon-Style Combined Video And Plots

**Files:**
- Modify: `src/digital_fruit_fly/telemetry.py`
- Create: `src/digital_fruit_fly/demo_video.py`
- Create: `tests/test_demo_video.py`

- [ ] **Step 1: Write failing planner tests**

Test that `planned_combined_video_paths(stem)` returns body path, brain path candidates, and combined path names. Test that `combine_side_by_side_video(..., dry_run=True)` returns metadata without requiring ffmpeg.

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=src python -m unittest tests.test_demo_video -v`

Expected: import fails because `demo_video.py` does not exist.

- [ ] **Step 3: Implement video helpers**

Implement:

- L4 IPC telemetry plot with worker latency/backend/timeout fields.
- brain-state animation from IPC telemetry.
- side-by-side composition using moviepy/imageio if available, otherwise ffmpeg CLI if available, otherwise write metadata that composition was skipped.

The composed video must place body footage left and brain state right.

- [ ] **Step 4: Run GREEN**

Run: `PYTHONPATH=src python -m unittest tests.test_demo_video -v`

Expected: planner tests pass without video dependencies.

### Task 6: Docs, AGENTS, And Verification

**Files:**
- Create: `docs/l4_ipc_brain_worker.md`
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Write docs**

Document:

- two-terminal run flow;
- Brian2 performance decision;
- Eon IPC finding;
- backend fallback semantics;
- output artifacts.

- [ ] **Step 2: Update README**

Add IPC L4 commands and note that `level4-branch` remains fallback.

- [ ] **Step 3: Update AGENTS**

Add constraints: keep IPC branch outputs in `outputs/l4_ipc_embodied_loop/`, do not claim Eon IPC protocol, record `shiu_full` attempt/fallback.

- [ ] **Step 4: Final verification**

Run:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall src scripts
/opt/miniconda3/envs/brain_env/bin/python scripts/run_l4_brain_worker.py --backend brian2_proxy --once-smoke
```

If FlyGym import is healthy in the current host, also run:

```bash
/opt/miniconda3/envs/flygym_env/bin/python scripts/run_l4_ipc_embodied_demo.py --duration 0.5 --no-video --no-plot
```

If FlyGym import hangs, report that integration video generation requires resolving the local FlyGym initialization issue, while IPC and brain worker tests pass.
