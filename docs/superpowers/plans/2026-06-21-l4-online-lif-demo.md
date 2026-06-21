# L4 Online LIF Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Level 4 online LIF attempt and Eon-style demo presentation without changing the stable L3 runner.

**Architecture:** L4 adds an `OnlineLIFBrainBridge` that updates a small online brain-state proxy at a configurable sync interval and reuses cached readouts between sync ticks. The existing embodied loop records optional bridge telemetry and writes L4-specific brain benchmark and visualization outputs.

**Tech Stack:** Python standard library, existing FlyGym wrapper, matplotlib for plots/animations, unittest for bridge tests.

---

### Task 1: Online LIF Bridge

**Files:**
- Create: `src/digital_fruit_fly/l4_online_lif.py`
- Create: `tests/test_l4_online_lif.py`
- Modify: `src/digital_fruit_fly/__init__.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_l4_online_lif.py` with tests that import `OnlineLIFBrainBridge`, construct `SensoryState` objects, and assert these behaviors:

```python
from digital_fruit_fly.l4_online_lif import OnlineLIFBrainBridge
from digital_fruit_fly.state import BehaviorState, SensoryState


def make_state(time_s, *, food_cue=0.0, dust_level=0.0, dust_threshold=False, contact=False):
    return SensoryState(
        time_s=time_s,
        food_cue=food_cue,
        turn_bias=0.25,
        dust_level=dust_level,
        dust_threshold_reached=dust_threshold,
        food_contact=contact,
        food_distance_mm=5.0,
    )


def test_bridge_caches_between_sync_ticks():
    bridge = OnlineLIFBrainBridge(brain_sync_interval_s=0.05)
    first = bridge.step(make_state(0.00, food_cue=0.4))
    cached = bridge.step(make_state(0.01, food_cue=1.0))

    assert bridge.last_runtime_state.brain_updated is False
    assert bridge.cached_step_count == 1
    assert cached.mn9_rate_hz == first.mn9_rate_hz


def test_dust_threshold_grooms_then_clears():
    bridge = OnlineLIFBrainBridge(brain_sync_interval_s=0.01, grooming_duration_s=0.1)

    grooming = bridge.step(make_state(0.02, dust_level=1.0, dust_threshold=True))
    assert grooming.behavior_state == BehaviorState.GROOMING
    assert grooming.forward_drive == 0.0

    cleared = bridge.step(make_state(0.14, dust_level=1.0, dust_threshold=True))
    assert cleared.behavior_state == BehaviorState.FORAGING
    assert cleared.dust_clearance == 1.0
    assert bridge.just_completed_grooming is True


def test_food_contact_feeds_with_mn9_readout():
    bridge = OnlineLIFBrainBridge(brain_sync_interval_s=0.01, feeding_hold_s=0.2)

    feeding = bridge.step(make_state(0.02, food_cue=1.0, contact=True))

    assert feeding.behavior_state == BehaviorState.FEEDING
    assert feeding.forward_drive == 0.0
    assert feeding.feeding_score > 0.8
    assert feeding.mn9_rate_hz > 40.0


def test_runtime_summary_reports_update_costs():
    bridge = OnlineLIFBrainBridge(brain_sync_interval_s=0.01)
    bridge.step(make_state(0.00, food_cue=0.2))
    bridge.step(make_state(0.02, dust_level=0.4))

    summary = bridge.benchmark_summary()

    assert summary["target_sync_interval_s"] == 0.01
    assert summary["brain_update_count"] >= 1
    assert summary["mean_update_wall_time_ms"] >= 0.0
    assert "realtime_target_met" in summary
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `PYTHONPATH=src python -m unittest discover -s tests -p 'test_l4_online_lif.py' -v`

Expected: fails because `digital_fruit_fly.l4_online_lif` does not exist.

- [ ] **Step 3: Implement bridge**

Create `src/digital_fruit_fly/l4_online_lif.py` with:

- `OnlineBrainRuntimeState` dataclass for timing and membrane/rate fields.
- `OnlineLIFBrainBridge.step()` implementing cached readouts, grooming/feeding priority, and LIF-like state updates.
- `telemetry_fields()` returning `l4_*` fields for the current row.
- `benchmark_summary()` returning update timing statistics and realtime target status.

- [ ] **Step 4: Export bridge and run tests**

Modify `src/digital_fruit_fly/__init__.py` to export `OnlineLIFBrainBridge` and `OnlineBrainRuntimeState`.

Run: `PYTHONPATH=src python -m unittest discover -s tests -p 'test_l4_online_lif.py' -v`

Expected: all tests pass.

### Task 2: L4 Loop Outputs

**Files:**
- Modify: `src/digital_fruit_fly/embodied_loop.py`
- Modify: `src/digital_fruit_fly/telemetry.py`

- [ ] **Step 1: Add loop extension points**

Update `run_embodied_loop()` to accept optional keyword arguments:

```python
extra_outputs_builder: Callable[[list[dict[str, Any]], dict[str, Any], Path, str], dict[str, str | None]] | None = None
```

During row logging, if `bridge` has `telemetry_fields()`, merge those fields into the row. After base outputs and metadata are prepared, call `extra_outputs_builder()` and merge returned paths into `metadata["outputs"]`.

- [ ] **Step 2: Add L4 telemetry plot**

Add `make_l4_embodied_plot(rows, plot_path)` to `telemetry.py`. It should plot sensory values, readout values, behavior state, and `l4_update_wall_time_ms` against simulation time.

- [ ] **Step 3: Add brain-state animation helper**

Add `make_l4_brain_state_video(rows, video_path)`. It should use matplotlib animation with an ffmpeg writer when available and return `True`; if encoding fails, return `False` after closing the figure.

- [ ] **Step 4: Run syntax verification**

Run: `python -m compileall src/digital_fruit_fly`

Expected: exit code 0.

### Task 3: L4 Runner, Config, And CLI

**Files:**
- Create: `configs/l4_embodied_loop.json`
- Create: `src/digital_fruit_fly/l4_demo.py`
- Create: `scripts/run_l4_embodied_demo.py`
- Modify: `src/digital_fruit_fly/config.py`
- Modify: `src/digital_fruit_fly/__init__.py`

- [ ] **Step 1: Add config path**

Add `L4_CONFIG_PATH = CONFIG_DIR / "l4_embodied_loop.json"` to `config.py`.

- [ ] **Step 2: Add L4 config**

Create `configs/l4_embodied_loop.json` using the L3 scene defaults, `duration_s` of `6.5`, `log_every_steps` of `50`, and a bridge config containing `brain_sync_interval_s`, `grooming_duration_s`, `feeding_hold_s`, and `max_turn_drive`.

- [ ] **Step 3: Add runner**

Create `run_l4_embodied_demo()` in `l4_demo.py`. It should load `L4_CONFIG_PATH`, construct `OnlineLIFBrainBridge`, call `run_embodied_loop()`, and use an extra outputs builder to write:

- `*_brain_benchmark.json`
- `*_brain_state.mp4` when ffmpeg succeeds, or `*_brain_state.gif` when pillow fallback succeeds
- `*_l4_telemetry.png`

- [ ] **Step 4: Add CLI**

Create `scripts/run_l4_embodied_demo.py` matching the L3 CLI flags: `--duration`, `--seed`, `--log-every-steps`, `--output-dir`, `--no-video`, and `--no-plot`.

- [ ] **Step 5: Export runner**

Export `run_l4_embodied_demo` from `src/digital_fruit_fly/__init__.py`.

### Task 4: Documentation And Verification

**Files:**
- Create: `docs/l4_online_lif.md`
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Document L4**

Create `docs/l4_online_lif.md` describing commands, outputs, timing benchmark fields, and scientific boundaries.

- [ ] **Step 2: Update README**

Add L4 status and quick-run commands without changing L3 instructions.

- [ ] **Step 3: Update AGENTS**

Add L4-specific implementation notes: keep L3 stable, keep L4 outputs separate, and document online proxy/fallback status.

- [ ] **Step 4: Run verification**

Run:

```bash
PYTHONPATH=src python -m unittest discover -s tests -p 'test_l4_online_lif.py' -v
python -m compileall src scripts
python scripts/run_l4_embodied_demo.py --duration 0.2 --no-video --no-plot
```

Expected: tests pass, compile succeeds, and the short L4 run writes telemetry, benchmark, and metadata if FlyGym is installed in the active environment. If FlyGym is unavailable, report that integration verification requires `flygym_env`.
