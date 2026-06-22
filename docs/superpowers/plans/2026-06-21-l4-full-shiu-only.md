# L4 Full Shiu Only Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the branch into an L4-only precomputed demo that uses the full Shiu Brian2 backend as the only production brain model.

**Architecture:** The FlyGym side keeps the embodied loop and IPC client. The brain worker instantiates Shiu's full Brian2 model through `external/drosophila_brain_model/model.py:create_model()`, runs configured sensory windows, and reports benchmark metadata. Presentation output remains a body-left, brain-right combined video, with the brain side rendered as a dark activity panel from full-backend telemetry.

**Tech Stack:** Python standard library, Brian2, pandas/parquet through Shiu's upstream model, FlyGym/NeuroMechFly, matplotlib animation, ffmpeg when available, unittest.

---

### Task 1: Lock L4-Only Cleanup With Tests

**Files:**
- Create: `tests/test_l4_only_cleanup.py`
- Modify: `src/digital_fruit_fly/__init__.py`
- Modify: `src/digital_fruit_fly/config.py`
- Delete: legacy staged scripts, configs, data, source files, and docs

- [x] **Step 1: Write failing cleanup tests**

Tests assert public exports are L4-only and legacy staged artifacts are absent.

- [x] **Step 2: Run cleanup tests and verify failure**

Run: `python -m unittest tests.test_l4_only_cleanup -v`

Expected before implementation: FAIL.

- [x] **Step 3: Delete legacy artifacts and update exports/config**

Keep only L4 IPC scripts, L4 IPC config, and shared L4 runtime modules.

- [x] **Step 4: Run cleanup tests**

Run: `python -m unittest tests.test_l4_only_cleanup -v`

Expected after implementation: PASS.

### Task 2: Keep Only L4 Bridge Helpers

**Files:**
- Modify: `src/digital_fruit_fly/brain_bridge.py`
- Modify: `src/digital_fruit_fly/embodied_loop.py`
- Modify: `src/digital_fruit_fly/state.py`
- Modify: `src/digital_fruit_fly/flygym_body.py`
- Modify: `src/digital_fruit_fly/virtual_environment.py`

- [x] **Step 1: Write focused import test**

The test asserts legacy bridge classes are absent and `readout_to_descending_signal` remains.

- [x] **Step 2: Run focused test and verify failure**

Run: `python -m unittest tests.test_l4_only_cleanup.L4OnlyCleanupTest.test_brain_bridge_only_exposes_l4_helpers -v`

Expected before implementation: FAIL.

- [x] **Step 3: Keep only helper functions and L4 protocol typing**

`brain_bridge.py` now contains `_clip()` and `readout_to_descending_signal()`. The embodied loop defines its local protocol for body-facing brain bridges.

- [x] **Step 4: Run cleanup tests**

Run: `python -m unittest tests.test_l4_only_cleanup -v`

Expected after implementation: PASS.

### Task 3: Specify Full Shiu Backend Behavior

**Files:**
- Modify: `tests/test_brain_worker.py`
- Modify: `src/digital_fruit_fly/brain_worker.py`

- [x] **Step 1: Replace old backend tests with fake full-backend tests**

Use fake Shiu and fake Brian2-style network objects so tests prove the call chain without loading the real connectome.

- [x] **Step 2: Run worker tests and verify failure**

Run: `python -m unittest tests.test_brain_worker -v`

Expected before implementation: FAIL.

### Task 4: Implement Full Shiu Backend

**Files:**
- Modify: `src/digital_fruit_fly/brain_worker.py`
- Modify: `scripts/run_l4_brain_worker.py`
- Modify: `configs/l4_ipc_embodied_loop.json`

- [x] **Step 1: Add explicit full-backend error type and config fields**

`BrainBackendUnavailable` records stage, reason, and metadata. `BrainWorkerConfig` records Shiu paths, input IDs, readout IDs, rates, and timing.

- [x] **Step 2: Make backend selection full-only**

`select_backend("shiu_full")` constructs `ShiuFullBackend`; `auto` is an alias to the same backend.

- [x] **Step 3: Implement Shiu model loading**

The backend imports upstream `model.py`, builds flywire-to-Brian index mapping, calls `create_model()`, constructs a network, and stores a baseline state.

- [x] **Step 4: Implement request handling**

Startup builds reusable sensory input sources once. Each request restores the baseline, updates sugar/JON input rates, runs one configured brain window, computes MN9 and grooming/DN rates, and returns a `BrainReadoutMessage` with `backend="shiu_full"`.

- [x] **Step 5: Run worker tests**

Run: `python -m unittest tests.test_brain_worker -v`

Expected after implementation: PASS.

### Task 5: Carry Full-Backend Extras Through IPC Telemetry

**Files:**
- Modify: `src/digital_fruit_fly/l4_ipc_bridge.py`
- Modify: `tests/test_l4_ipc_bridge.py`

- [x] **Step 1: Add failing bridge test**

The test sends `grooming_rate_hz`, `shiu_full_used`, and `brain_window_s` in response extras and expects fixed telemetry fields.

- [x] **Step 2: Run bridge tests and verify failure**

Run: `python -m unittest tests.test_l4_ipc_bridge -v`

Expected before implementation: FAIL.

- [x] **Step 3: Store known extra fields**

`IpcBrainBridge` stores `response.extra` and returns `ipc_grooming_rate_hz`, `ipc_shiu_full_used`, and `ipc_brain_window_s`.

- [x] **Step 4: Run bridge tests**

Run: `python -m unittest tests.test_l4_ipc_bridge -v`

Expected after implementation: PASS.

### Task 6: Upgrade Brain Activity Panel And Benchmark JSON

**Files:**
- Modify: `src/digital_fruit_fly/telemetry.py`
- Modify: `src/digital_fruit_fly/l4_ipc_demo.py`
- Modify: `tests/test_demo_video.py`

- [x] **Step 1: Add failing output test**

The test writes representative telemetry rows through `make_l4_brain_activity_panel_png()`.

- [x] **Step 2: Run output tests and verify failure**

Run: `python -m unittest tests.test_demo_video -v`

Expected before implementation: FAIL.

- [x] **Step 3: Implement dark brain panel helpers**

The helper renders a black activity panel from MN9/grooming rates, with a minimal PNG fallback if matplotlib is unavailable.

- [x] **Step 4: Write benchmark JSON**

The L4 IPC demo writes request counts, timeout counts, backend names, worker latency stats, and combined-video metadata to `*_benchmark.json`.

- [x] **Step 5: Run output tests**

Run: `python -m unittest tests.test_demo_video -v`

Expected after implementation: PASS.

### Task 7: Rewrite L4-Only Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/l4_ipc_brain_worker.md`
- Modify: `AGENTS.md`

- [x] **Step 1: Rewrite README around the single workflow**

README now documents the brain worker command, embodied-loop command, outputs, and boundaries.

- [x] **Step 2: Rewrite L4 IPC docs**

The doc now describes only full Shiu IPC, outputs, and limitations.

- [x] **Step 3: Update agent instructions**

`AGENTS.md` now describes the L4-only branch and forbids reintroducing legacy staged workflows.

- [x] **Step 4: Run stale-reference scan**

Run: `rg -n "legacy staged names and old backend names" .`

Expected after implementation: no stale public workflow references.

### Task 8: Full Verification

**Files:**
- All changed files

- [x] **Step 1: Run unit tests**

Run: `python -m unittest discover -s tests -v`

Expected: PASS.

- [x] **Step 2: Run brain worker smoke**

Run: `python scripts/run_l4_brain_worker.py --backend shiu_full --once-smoke --max-startup-s 0`

Expected in the current base environment: clear `brain_worker_failed` JSON if Brian2 is unavailable. It must not report successful alternate backend output.

- [x] **Step 3: Check git status**

Run: `git status --short --untracked-files=all`

Expected: only intentional L4-only cleanup and implementation changes.
