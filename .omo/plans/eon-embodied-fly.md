# eon-embodied-fly - Work Plan

## TL;DR (For humans)
**What you'll get:** A two-process Digital Fruit Fly prototype that runs a bounded arena with sugar and dust, a FlyGym body, a Shiu/Brian2 brain, brain-body messages every 15 ms, and a final Eon-style demo video with trajectory, event, and neural activity logs.

**Why this approach:** Eon did not publish the bridge code, so the project should build the missing bridge as auditable infrastructure first. Realtime interactive viewing remains a target, but the first guaranteed milestone is deterministic closed-loop replay and final video because this machine's FlyGym import currently hangs and full-brain realtime throughput is unproven.

**What it will NOT do:** It will not implement visual control, claim Eon's unpublished 91% metric, bypass the brain by sending behavior labels directly from arena logic to the body, or overwrite the existing report/design files.

**Effort:** XL
**Risk:** High - FlyGym/MuJoCo runtime stability and full-brain tick performance are unvalidated.
**Decisions to sanity-check:** stdlib TCP framed JSON for IPC v1, staged realtime target, provisional neural motor-readout mappings until curated descending-neuron IDs are available.

Your next move: start execution with `$start-work`, or request a high-accuracy review of this plan first. Full execution detail follows below.

---

> TL;DR (machine): XL/high-risk architecture plan for arena + FlyGym body + Shiu/Brian2 brain + 15 ms IPC + sensory/motor bridge + video/neural observability; realtime viewer is stretch after P0 runtime proof.

## Scope
### Must have
- Create a Python package under `src/digital_fruit_fly/` plus scripts under `scripts/` and configs under `configs/`; keep `external/drosophila_brain_model/`, `outputs/`, `reports/`, and `DESIGN.md` out of implementation edits unless a task explicitly reads them.
- Preserve the existing two-environment architecture from `README.md:7` to `README.md:22`: brain process runs with `/opt/miniconda3/envs/brain_env/bin/python`; body process runs with `/opt/miniconda3/envs/flygym_env/bin/python`.
- Build six independently testable components: `arena`, `brain`, `body`, `bridge`, `behavior`, and `observability`.
- Use a canonical 15 ms brain-body tick because the report records Eon's public sync grain at `reports/eon_embodied_fly_technical_report.html:713` to `reports/eon_embodied_fly_technical_report.html:715` and `reports/eon_embodied_fly_technical_report.html:857` to `reports/eon_embodied_fly_technical_report.html:863`.
- Implement a bounded arena with configurable dimensions, sugar food source geometry, nonzero-area gustatory cue, contact detection, dust accumulation, and dust removal during grooming.
- Implement upward sensory encoding from arena/body observations into brain input channels. Minimum channels: left/right sugar cue, food contact, dust load, ground contact, joint/proprioception summary, and action-state feedback.
- Implement downward motor decoding from brain spike/rate outputs into body controller targets. Minimum outputs: forward locomotion intensity, turn left/right bias, feeding intensity, grooming intensity, stop/brake intensity, proboscis extension amplitude, and proboscis extension direction from food-relative bearing/elevation.
- Feeding must visibly extend the proboscis using rostrum/haustellum DOFs when available, with extension direction adjusted from the food source's position in fly-centric coordinates.
- Grooming must visibly move the anterior cleaning apparatus toward the face/antenna region. Target implementation is a face-grooming primitive using controllable antenna/head/front-leg DOFs and site-position checks; if installed FlyGym exposes only a subset, the limitation must be recorded and the closest anatomically named controllable DOFs used without claiming exact biological grooming.
- Use Shiu sugar-sensing FlyWire IDs from `external/drosophila_brain_model/example.ipynb:68` to `external/drosophila_brain_model/example.ipynb:147` as the initial gustatory mapping, stored in config rather than code.
- Run the demo as two processes:
  - Brain: `/opt/miniconda3/envs/brain_env/bin/python scripts/run_brain.py --config configs/eon_demo.yaml`
  - Body: `/opt/miniconda3/envs/flygym_env/bin/python scripts/run_body.py --config configs/eon_demo.yaml`
  - Optional orchestrator: `python3 scripts/run_demo.py --config configs/eon_demo.yaml --output outputs/runs/<run_id>`
- Produce one complete final run directory under `outputs/runs/<run_id>/` with `manifest.json`, `events.jsonl`, `trajectory.parquet` or `trajectory.csv`, `brain/spikes.parquet` or `brain/spikes.csv`, `brain/rates.parquet` or `brain/rates.csv`, `control.jsonl`, `arena.jsonl`, `video/fly_demo.mp4`, `video/brain_activity.mp4` or equivalent, and `summary.json`.
- Support deterministic closed-loop replay first; support realtime viewer/camera adjustment only after P0 proves FlyGym/MuJoCo viewer mode is stable.
- Keep tests agent-executable with no manual validation as a requirement for completion.

### Must NOT have (guardrails, anti-slop, scope boundaries)
- Do not implement visual input, retina/optic-lobe encoding, camera-to-brain pipelines, or visual navigation. Rendering/video is allowed only for human observation.
- Do not claim an individual "brain upload", Eon's 91% behavior accuracy, or biological equivalence beyond a public-component closed-loop prototype; the report explicitly warns about this boundary at `reports/eon_embodied_fly_technical_report.html:772` to `reports/eon_embodied_fly_technical_report.html:779` and `reports/eon_embodied_fly_technical_report.html:949` to `reports/eon_embodied_fly_technical_report.html:960`.
- Do not send direct arena-derived behavior labels such as `groom_now` or `feed_now` to the body. Arena/body facts may become sensory messages; body action modes must come from brain output decoded by `bridge`.
- Do not hard-code FlyWire IDs in Python logic. Every neuron group must live in versioned config or data files.
- Do not edit the upstream Shiu files in `external/drosophila_brain_model/`; wrap or import them from project code.
- Do not add heavyweight cross-environment dependencies for IPC v1. Use stdlib TCP framed JSON/JSONL unless a later approved task replaces transport.
- Do not make realtime interactive viewing a blocking first milestone. If viewer mode fails, headless deterministic recording remains the milestone target.
- Do not beautify the arena with textures, shaders, or decorative UI before the closed-loop behavior and logs pass.
- Do not commit generated run artifacts from `outputs/` or large copied external data.

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: tests-after for integration-heavy work, with TDD-style unit tests for pure protocol/config/replay modules before wiring them into runtime scripts. Use `python -m unittest` as the baseline because the project has no dependency file yet; add pytest only if the implementation explicitly introduces it and both conda envs can run it.
- Unit command: `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'`
- Static syntax command: `python3 -m compileall src scripts tests`
- Brain smoke command: `/opt/miniconda3/envs/brain_env/bin/python scripts/smoke_brain.py --config configs/brain_smoke.yaml --output outputs/smoke/brain`
- Body smoke command: `/opt/miniconda3/envs/flygym_env/bin/python scripts/smoke_body.py --config configs/body_smoke.yaml --output outputs/smoke/body --headless --steps 20 --timeout-sec 60`
- Bridge contract command: `PYTHONPATH=src python3 scripts/smoke_bridge.py --config configs/bridge_smoke.yaml --ticks 1000 --output outputs/smoke/bridge`
- Final demo command: `python3 scripts/run_demo.py --config configs/eon_demo.yaml --output outputs/runs/eon_demo_smoke --duration-sec 60 --seed 1`
- Replay command: `PYTHONPATH=src python3 scripts/replay_run.py --input outputs/runs/eon_demo_smoke --verify`
- Evidence root: `.omo/evidence/`; every todo writes a task-specific log or JSON evidence file named `.omo/evidence/task-<N>-eon-embodied-fly.<ext>`.
- Runtime scripts must set writable cache locations internally where needed, especially `MPLCONFIGDIR` under the run/evidence temp path, because the earlier probe showed `/Users/lins/.matplotlib` was not writable.
- The FlyGym smoke task must use timeout protection and must terminate hung probes; a hanging import is a failing test, not an interactive blocker.

## Execution strategy
### Parallel execution waves
> Target 5-8 todos per wave. Fewer than 3 (except the final) means you under-split.
- Wave 1 - foundation: todos 1-5. Builds package, config, manifest/logging, protocol, and test harness.
- Wave 2 - runtime baselines: todos 6-8. Validates brain env, body env, and locks installed FlyGym API facts before body implementation depends on them.
- Wave 3 - simulation state: todos 9-10. Implements arena, sugar, and dust independent of FlyGym.
- Wave 4 - brain service: todos 11-14. Implements neuron mapping data, tickable Brian2 wrapper, brain server, and neural visualization.
- Wave 5 - body service: todos 15-18. Implements FlyGym observation/action adapters, camera/recording, and body server.
- Wave 6 - bridge and behavior: todos 19-22. Implements encoders/decoders, integrated runner, replay, and calibration.
- Wave 7 - demo delivery: todo 23 plus final verification wave.

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 1 | none | 2,3,4,5 | none |
| 2 | 1 | 6-23 | 3,4,5 |
| 3 | 1 | 6-23 | 2,4,5 |
| 4 | 1 | 19,21 | 2,3,5 |
| 5 | 1 | all verification | 2,3,4 |
| 6 | 2,3,5 | 11-14,21-23 | 7,8,9 |
| 7 | 2,3,5 | 15-18,21-23 | 6,8,9 |
| 8 | 7 | 15-18 | 6,9,10 |
| 9 | 2,3,5 | 10,19,21,22 | 6,7,11 |
| 10 | 9 | 19,22 | 11,12 |
| 11 | 2,6 | 12,13,20,22 | 9,10,15 |
| 12 | 6,11 | 13,20,21,22 | 15,16 |
| 13 | 4,12 | 20,21,22 | 17 |
| 14 | 13 | 23 | 17,18 |
| 15 | 7,8 | 16,18,19,21 | 11,12 |
| 16 | 8,15 | 18,20,21,22 | 12,13 |
| 17 | 7,8,15 | 18,23 | 13,14 |
| 18 | 4,15,16,17 | 19,20,21,22 | 14 |
| 19 | 4,9,10,15,18 | 21,22 | 20 |
| 20 | 11,12,13,16,18 | 21,22 | 19 |
| 21 | 13,18,19,20 | 22,23 | none |
| 22 | 21 | 23 | none |
| 23 | 14,17,22 | final verification | none |

## Todos
> Implementation + Test = ONE todo. Never separate.
<!-- APPEND TASK BATCHES BELOW THIS LINE WITH edit/apply_patch - never rewrite the headers above. -->
- [x] 1. Create the project package skeleton and environment-neutral utilities
  What to do / Must NOT do: Create `src/digital_fruit_fly/` with subpackages `arena`, `brain`, `body`, `bridge`, `behavior`, `observability`, and `runtime`; add `__init__.py` files; add minimal package metadata only if needed for editable installs; add `tests/` package structure. Must not move or edit `external/drosophila_brain_model/`, `reports/`, or `DESIGN.md`.
  Parallelization: Wave 1 | Blocked by: none | Blocks: all other implementation tasks
  References (executor has NO interview context - be exhaustive): `README.md:27` to `README.md:34`; `reports/eon_embodied_fly_technical_report.html:966` to `reports/eon_embodied_fly_technical_report.html:1028`; dirty worktree note from draft.
  Acceptance criteria (agent-executable): `find src/digital_fruit_fly -maxdepth 2 -type f | sort` shows the package files; `PYTHONPATH=src python3 -c "import digital_fruit_fly"` exits 0; `git status --short` shows no modifications under `external/drosophila_brain_model/`.
  QA scenarios (name the exact tool + invocation): happy: `PYTHONPATH=src python3 -c "import digital_fruit_fly; print(digital_fruit_fly.__name__)"`; failure: temporarily run `PYTHONPATH=src python3 -c "import digital_fruit_fly.brain, digital_fruit_fly.body"` and confirm missing subpackages fail before fixing, then rerun after fixing. Evidence `.omo/evidence/task-1-eon-embodied-fly.txt`
  Commit: Y | chore(scaffold): add digital fruit fly package skeleton

- [x] 2. Add config schema and default configuration files
  What to do / Must NOT do: Add `configs/eon_demo.yaml`, `configs/brain_smoke.yaml`, `configs/body_smoke.yaml`, `configs/bridge_smoke.yaml`, and config-loading code under `src/digital_fruit_fly/runtime/config.py`. Include arena dimensions, sugar source center/radius/cue radius, dust rate/threshold/cleaning rate, 15 ms tick, process host/ports, run duration, seed, camera options, brain mapping paths, decoder thresholds, and env python paths. Use only stdlib config parsing unless PyYAML is already available in every required env; if YAML needs PyYAML, include JSON equivalents or a tiny dependency-free parser for the subset used.
  Parallelization: Wave 1 | Blocked by: 1 | Blocks: 6-23
  References: `README.md:17` to `README.md:22`; `reports/eon_embodied_fly_technical_report.html:857` to `reports/eon_embodied_fly_technical_report.html:863`; draft adopted defaults in `.omo/drafts/eon-embodied-fly.md`.
  Acceptance criteria: `PYTHONPATH=src python3 -m unittest tests.test_config` loads all configs and asserts `tick_ms == 15`, sugar cue radius is greater than food radius, and configured python paths match the README defaults.
  QA scenarios: happy: `PYTHONPATH=src python3 -m unittest tests.test_config`; failure: add a temporary malformed config in the test fixture with `cue_radius < food_radius` and assert the loader rejects it with a typed/configured error. Evidence `.omo/evidence/task-2-eon-embodied-fly.txt`
  Commit: Y | feat(config): define runtime and demo configuration

- [x] 3. Define run manifests, output layout, and evidence logging
  What to do / Must NOT do: Add `src/digital_fruit_fly/runtime/run_manifest.py` and `src/digital_fruit_fly/runtime/logging.py`. Every run creates `outputs/runs/<run_id>/manifest.json`, `events.jsonl`, `control.jsonl`, `arena.jsonl`, `brain/`, `video/`, and `logs/`. Must not write generated artifacts outside `outputs/` or `.omo/evidence/`.
  Parallelization: Wave 1 | Blocked by: 1 | Blocks: 6-23
  References: `README.md:32` to `README.md:33`; `reports/eon_embodied_fly_technical_report.html:1021` to `reports/eon_embodied_fly_technical_report.html:1028`.
  Acceptance criteria: `PYTHONPATH=src python3 -m unittest tests.test_run_manifest` creates a temp run directory, writes manifest and JSONL events, and validates all expected subdirectories exist.
  QA scenarios: happy: `PYTHONPATH=src python3 -m unittest tests.test_run_manifest`; failure: point the manifest writer at `reports/` in a test and assert it refuses non-output roots. Evidence `.omo/evidence/task-3-eon-embodied-fly.json`
  Commit: Y | feat(runtime): add run manifest and log layout

- [x] 4. Implement IPC message schemas and stdlib framed JSON transport
  What to do / Must NOT do: Add `src/digital_fruit_fly/bridge/messages.py` and `src/digital_fruit_fly/bridge/transport.py` with versioned dataclasses or typed dicts for `Hello`, `SensoryFrame`, `BrainFrame`, `ControlFrame`, `Heartbeat`, `ErrorFrame`, and `Shutdown`. Include frame index, simulation time seconds, monotonic sent time, schema version, run ID, and payload checksums where useful. Implement TCP loopback framed JSON with length-prefix or newline framing and explicit timeouts. Must not introduce ZeroMQ or behavior-label shortcuts.
  Parallelization: Wave 1 | Blocked by: 1 | Blocks: 19,21
  References: `reports/eon_embodied_fly_technical_report.html:857` to `reports/eon_embodied_fly_technical_report.html:863`; draft decision "IPC dependency policy".
  Acceptance criteria: `PYTHONPATH=src python3 -m unittest tests.test_bridge_messages tests.test_transport` passes round-trip, schema-version mismatch, timeout, truncated-frame, and invalid-payload tests.
  QA scenarios: happy: `PYTHONPATH=src python3 -m unittest tests.test_bridge_messages tests.test_transport`; failure: send a frame with future schema version and assert the receiver returns `ErrorFrame` and closes cleanly. Evidence `.omo/evidence/task-4-eon-embodied-fly.txt`
  Commit: Y | feat(bridge): add versioned framed JSON transport

- [x] 5. Add smoke-test scripts and common timeout wrappers
  What to do / Must NOT do: Add `src/digital_fruit_fly/runtime/timeouts.py`, `scripts/smoke_brain.py`, `scripts/smoke_body.py`, `scripts/smoke_bridge.py`, and baseline tests for timeout behavior. Scripts must write `.omo/evidence/` logs when invoked during development and `outputs/smoke/` artifacts for runtime probes. Must not leave hung subprocesses running.
  Parallelization: Wave 1 | Blocked by: 1,3 | Blocks: all runtime verification
  References: local FlyGym import probe hung and required process termination; brain import passed with Brian2 2.9.0/pandas 2.3.3/pyarrow 24.0.0; `reports/eon_embodied_fly_technical_report.html:1053` to `reports/eon_embodied_fly_technical_report.html:1057`.
  Acceptance criteria: `PYTHONPATH=src python3 -m unittest tests.test_timeouts` proves a deliberately sleeping child is terminated and recorded; `python3 scripts/smoke_bridge.py --config configs/bridge_smoke.yaml --ticks 3 --output outputs/smoke/bridge_unit` exits 0.
  QA scenarios: happy: `PYTHONPATH=src python3 -m unittest tests.test_timeouts`; failure: run a smoke fixture that sleeps longer than `--timeout-sec 1` and assert exit code is nonzero with a JSON evidence record. Evidence `.omo/evidence/task-5-eon-embodied-fly.json`
  Commit: Y | test(runtime): add smoke harness and timeout guards

- [x] 6. Validate `brain_env` and wrap Shiu data/model discovery
  What to do / Must NOT do: Implement `src/digital_fruit_fly/brain/shiu_adapter.py` and complete `scripts/smoke_brain.py`. The adapter discovers `external/drosophila_brain_model/model.py`, `Completeness_783.csv`, `Connectivity_783.parquet`, and version 630 files; verifies sugar neuron IDs exist in the selected completeness table; records Brian2/pandas/pyarrow versions. The smoke must include a fast metadata check and a bounded Brian2 toy-network check; full Shiu simulation should be behind `--full-shiu` so the normal P0 check is not accidentally multi-hour. Must not modify upstream Shiu files.
  Parallelization: Wave 2 | Blocked by: 2,3,5 | Blocks: 11-14,21-23
  References: `external/drosophila_brain_model/Readme.md:18` to `external/drosophila_brain_model/Readme.md:27`; `external/drosophila_brain_model/model.py:58` to `external/drosophila_brain_model/model.py:127`; `external/drosophila_brain_model/model.py:296` to `external/drosophila_brain_model/model.py:373`; `external/drosophila_brain_model/example.ipynb:68` to `external/drosophila_brain_model/example.ipynb:147`.
  Acceptance criteria: `/opt/miniconda3/envs/brain_env/bin/python scripts/smoke_brain.py --config configs/brain_smoke.yaml --output outputs/smoke/brain` writes `outputs/smoke/brain/brain_env.json` with versions, selected data paths, sugar ID validation, and toy-network spike count.
  QA scenarios: happy: run the brain smoke command above; failure: run it with a config pointing to a nonexistent completeness CSV and assert it fails before importing/running Shiu with a clear error. Evidence `.omo/evidence/task-6-eon-embodied-fly.json`
  Commit: Y | feat(brain): add Shiu adapter and brain smoke

- [x] 7. Validate `flygym_env`, MuJoCo import, renderer, and viewer mode boundaries
  What to do / Must NOT do: Complete `scripts/smoke_body.py` and add `src/digital_fruit_fly/body/flygym_probe.py`. The probe must import FlyGym/MuJoCo with timeout protection, record versions and import latency, run a minimal headless simulation if possible, and separately probe viewer availability. It must set writable cache dirs internally. If import still hangs, record this as a P0 blocker with reproduction command and do not fake pass.
  Parallelization: Wave 2 | Blocked by: 2,3,5 | Blocks: 8,15-18,21-23
  References: `README.md:11` to `README.md:12`; `reports/eon_embodied_fly_technical_report.html:907` to `reports/eon_embodied_fly_technical_report.html:910`; local prior probe showed `/opt/miniconda3/envs/flygym_env/bin/python` exists but FlyGym/MuJoCo import hung.
  Acceptance criteria: `/opt/miniconda3/envs/flygym_env/bin/python scripts/smoke_body.py --config configs/body_smoke.yaml --output outputs/smoke/body --headless --steps 20 --timeout-sec 60` exits 0 only if import and minimal stepping succeed; otherwise it exits nonzero with `outputs/smoke/body/body_env_error.json`.
  QA scenarios: happy: run the body smoke command above; failure: run with `--timeout-sec 1` or an invalid renderer option and assert it terminates cleanly with no lingering child process. Evidence `.omo/evidence/task-7-eon-embodied-fly.json`
  Commit: Y | feat(body): add FlyGym MuJoCo runtime probe

- [x] 8. Lock the installed FlyGym controller, observation, camera, video, antenna, and proboscis APIs
  What to do / Must NOT do: After todo 7 passes, add `docs/runtime/flygym_api_probe.md` and `outputs/smoke/body/flygym_api.json` documenting the exact installed import paths/classes/functions used for simulation, locomotion controller, observation structure, camera control, frame capture, video writing, skeleton presets, controllable antenna DOFs, controllable proboscis DOFs (`rostrum`/`haustellum`), front-leg DOFs usable for face grooming, actuator order, joint angle readout, and site-position readout. If official tutorial/API names differ from assumptions, choose the installed API and update configs/tests accordingly. Must not proceed with body implementation until this document exists.
  Parallelization: Wave 2 | Blocked by: 7 | Blocks: 15-18
  References: `reports/eon_embodied_fly_technical_report.html:907` to `reports/eon_embodied_fly_technical_report.html:910`; `reports/eon_embodied_fly_technical_report.html:1021` to `reports/eon_embodied_fly_technical_report.html:1028`.
  Acceptance criteria: `/opt/miniconda3/envs/flygym_env/bin/python scripts/smoke_body.py --config configs/body_smoke.yaml --output outputs/smoke/body --api-report` writes a JSON report listing import paths, actuator order, and explicit booleans/DOF lists for `supports_proboscis_control`, `supports_antenna_control`, `supports_front_leg_face_grooming`, and `supports_site_positions`; tests assert required keys are present.
  QA scenarios: happy: run the API report command; failure: monkeypatch or configure a missing proboscis/antenna DOF and assert the API probe fails with "unsupported installed FlyGym fine-action API" rather than falling back silently. Evidence `.omo/evidence/task-8-eon-embodied-fly.md`
  Commit: Y | docs(body): lock installed FlyGym API surface

- [x] 9. Implement deterministic arena geometry, boundaries, sugar cue, and state serialization
  What to do / Must NOT do: Add `src/digital_fruit_fly/arena/model.py` with immutable/configurable arena dimensions, food source position/radius, sugar cue radius, boundary collision/clamping, distance/vector-to-food helpers, left/right cue sampling based on fly pose, and JSON serialization. This is logical arena state; do not depend on FlyGym or MuJoCo here.
  Parallelization: Wave 3 | Blocked by: 2,3,5 | Blocks: 10,19,21,22
  References: user requirement for bounded field with sugar food source and cue area; `reports/eon_embodied_fly_technical_report.html:1021` to `reports/eon_embodied_fly_technical_report.html:1028`.
  Acceptance criteria: `PYTHONPATH=src python3 -m unittest tests.test_arena_model` proves boundary clamping, cue detection inside/outside radius, left/right cue asymmetry, contact detection, and deterministic serialization.
  QA scenarios: happy: `PYTHONPATH=src python3 -m unittest tests.test_arena_model`; failure: configure food outside arena or cue radius smaller than food radius and assert validation rejects it. Evidence `.omo/evidence/task-9-eon-embodied-fly.json`
  Commit: Y | feat(arena): add bounded sugar cue field

- [x] 10. Implement dust accumulation, grooming cleanup dynamics, and arena events
  What to do / Must NOT do: Extend arena/behavior state with global dust accumulation per tick, threshold crossing event, grooming cleanup rate, clean-to-zero event, and event serialization. Dust affects sensory input only; it must not directly command the body to groom.
  Parallelization: Wave 3 | Blocked by: 9 | Blocks: 19,22
  References: user requirement for field-wide dust and grooming threshold; `reports/eon_embodied_fly_technical_report.html:793` to `reports/eon_embodied_fly_technical_report.html:812`.
  Acceptance criteria: `PYTHONPATH=src python3 -m unittest tests.test_dust_dynamics` proves dust accumulates while not grooming, does not exceed configured max, emits threshold event once per dirty cycle, decreases during grooming, reaches zero, and then allows locomotion sensory state again.
  QA scenarios: happy: `PYTHONPATH=src python3 -m unittest tests.test_dust_dynamics`; failure: pass a negative dust rate or cleanup rate and assert config validation rejects it. Evidence `.omo/evidence/task-10-eon-embodied-fly.json`
  Commit: Y | feat(arena): add dust and grooming state dynamics

- [x] 11. Create versioned neural mapping files for sensory and motor channels
  What to do / Must NOT do: Add `configs/brain_mapping.yaml` or JSON equivalent plus `data/neural_mappings/README.md`. Include sugar GRN IDs from the Shiu example, provisional dust/mechanosensory input target IDs with explicit `provisional: true`, and provisional motor readout groups for forward/turn/feed/groom/stop with rationale and source status. Every group must include FlyWire IDs, brain index resolution status, channel name, sign, normalization, and whether it is biologically curated or engineering provisional. Must not hide provisional choices in code.
  Parallelization: Wave 4 | Blocked by: 2,6 | Blocks: 12,13,20,22
  References: `external/drosophila_brain_model/example.ipynb:68` to `external/drosophila_brain_model/example.ipynb:147`; `external/drosophila_brain_model/model.py:341` to `external/drosophila_brain_model/model.py:344`; `reports/eon_embodied_fly_technical_report.html:933` to `reports/eon_embodied_fly_technical_report.html:947`.
  Acceptance criteria: `/opt/miniconda3/envs/brain_env/bin/python scripts/smoke_brain.py --config configs/brain_smoke.yaml --validate-mapping --output outputs/smoke/brain` resolves every configured FlyWire ID to Brian index or marks the channel unusable with a failing smoke result; unit tests reject hard-coded channel IDs not present in config.
  QA scenarios: happy: run the mapping validation command; failure: insert a fake FlyWire ID in a temp mapping fixture and assert validation fails with the channel name and bad ID. Evidence `.omo/evidence/task-11-eon-embodied-fly.json`
  Commit: Y | feat(brain): add versioned neural channel mappings

- [x] 12. Build a tickable Brian2 network service layer around Shiu's model
  What to do / Must NOT do: Add `src/digital_fruit_fly/brain/tickable_network.py`. Reuse Shiu's `create_model` where feasible, but add project-owned dynamic sensory input channels using Brian2 constructs that allow rate changes each 15 ms tick, such as `PoissonGroup`/`Synapses` or `SpikeGeneratorGroup`. The wrapper must initialize once, update channel rates per tick, run `net.run(15 * ms)` or configured tick duration, and return spike/rate deltas for configured readout groups. Must not call Shiu `run_exp` per tick because that reconstructs the full network every trial at `external/drosophila_brain_model/model.py:250` to `external/drosophila_brain_model/model.py:293`.
  Parallelization: Wave 4 | Blocked by: 6,11 | Blocks: 13,20,21,22
  References: `external/drosophila_brain_model/model.py:129` to `external/drosophila_brain_model/model.py:188`; `external/drosophila_brain_model/model.py:250` to `external/drosophila_brain_model/model.py:293`; `reports/eon_embodied_fly_technical_report.html:995` to `reports/eon_embodied_fly_technical_report.html:1009`.
  Acceptance criteria: `/opt/miniconda3/envs/brain_env/bin/python -m unittest tests.test_tickable_brain` passes with a small Brian2 fixture network; `/opt/miniconda3/envs/brain_env/bin/python scripts/smoke_brain.py --config configs/brain_smoke.yaml --tickable --ticks 10 --output outputs/smoke/brain` writes per-tick rate/spike deltas. If full Shiu tick mode is too slow, the evidence must report mean tick wall time and still provide deterministic slower-than-realtime output.
  QA scenarios: happy: run the tickable smoke command; failure: configure an unknown sensory channel and assert the service refuses startup before running Brian2. Evidence `.omo/evidence/task-12-eon-embodied-fly.json`
  Commit: Y | feat(brain): add tickable Brian2 network wrapper

- [x] 13. Implement the brain server process and brain logs
  What to do / Must NOT do: Add `scripts/run_brain.py` and `src/digital_fruit_fly/brain/server.py`. The server listens on configured loopback TCP, handshakes with schema version/run ID, receives `SensoryFrame`, updates the tickable network, emits `BrainFrame` with readout rates/spikes, and writes brain logs under the run directory. Must support a deterministic fixture mode for bridge/body tests, but final demo config must use Brian2 mode.
  Parallelization: Wave 4 | Blocked by: 4,12 | Blocks: 20,21,22
  References: `README.md:17` to `README.md:22`; `reports/eon_embodied_fly_technical_report.html:857` to `reports/eon_embodied_fly_technical_report.html:863`; `external/drosophila_brain_model/model.py:214` to `external/drosophila_brain_model/model.py:248`.
  Acceptance criteria: `/opt/miniconda3/envs/brain_env/bin/python scripts/run_brain.py --config configs/bridge_smoke.yaml --mode fixture --max-ticks 5 --output outputs/smoke/brain_server` starts, handshakes with `scripts/smoke_bridge.py`, writes `brain/rates.csv` or `.parquet`, and exits on shutdown.
  QA scenarios: happy: run brain server fixture plus bridge smoke; failure: send a `SensoryFrame` with skipped frame index and assert server logs a protocol error or resync event. Evidence `.omo/evidence/task-13-eon-embodied-fly.json`
  Commit: Y | feat(brain): serve brain frames over IPC

- [x] 14. Generate neural activity visualization artifacts
  What to do / Must NOT do: Add `src/digital_fruit_fly/observability/brain_video.py` and `scripts/render_brain_activity.py`. Render a raster/heatmap style activity video or frame sequence from recorded spikes/rates for selected sensory and motor groups; include a static summary plot if video codecs are unavailable. Must not require GUI display.
  Parallelization: Wave 4 | Blocked by: 13 | Blocks: 23
  References: user requirement for live or post-run brain activity observation; `reports/eon_embodied_fly_technical_report.html:1024` to `reports/eon_embodied_fly_technical_report.html:1027`; local note that `MPLCONFIGDIR` must be writable.
  Acceptance criteria: `/opt/miniconda3/envs/brain_env/bin/python scripts/render_brain_activity.py --input outputs/smoke/brain_server --output outputs/smoke/brain_server/video/brain_activity.mp4` produces a nonempty video or documented fallback PNG/CSV summary; tests assert renderer handles empty spike windows.
  QA scenarios: happy: run renderer on fixture logs; failure: run renderer on an empty/missing brain log and assert it exits nonzero with a clear error and no corrupt MP4. Evidence `.omo/evidence/task-14-eon-embodied-fly.txt`
  Commit: Y | feat(observability): render brain activity video

- [x] 15. Implement FlyGym body observation adapter
  What to do / Must NOT do: Add `src/digital_fruit_fly/body/observations.py`. Use the locked API report from todo 8 to extract body pose, heading, contact/proprioceptive summaries, joint angles or configured low-dimensional substitutes, food-contact proxy from the arena model, fly-centric food bearing/elevation/distance, proboscis joint angles, antenna/front-leg/head joint angles, and site positions needed to verify face grooming and proboscis extension. Normalize observations into a dependency-light dataclass that the sensory encoder can consume. Must not expose FlyGym raw objects across IPC.
  Parallelization: Wave 5 | Blocked by: 7,8 | Blocks: 16,18,19,21
  References: `reports/eon_embodied_fly_technical_report.html:829` to `reports/eon_embodied_fly_technical_report.html:853`; `reports/eon_embodied_fly_technical_report.html:933` to `reports/eon_embodied_fly_technical_report.html:939`; `docs/runtime/flygym_api_probe.md` from todo 8.
  Acceptance criteria: `/opt/miniconda3/envs/flygym_env/bin/python -m unittest tests.test_body_observations` passes using recorded/probed observation fixtures; adapter output serializes without NumPy-only types and includes food-relative direction plus named proboscis/antenna/front-leg observables when the API probe reports support.
  QA scenarios: happy: run the body observation tests in `flygym_env`; failure: feed an observation missing a configured proboscis or antenna joint field after API support was reported and assert the adapter emits a typed missing-field error. Evidence `.omo/evidence/task-15-eon-embodied-fly.json`
  Commit: Y | feat(body): normalize FlyGym observations

- [x] 16. Implement brain-selected body controller adapters for locomotion, directional proboscis feeding, and face grooming
  What to do / Must NOT do: Add `src/digital_fruit_fly/body/controllers.py`. Wrap the installed FlyGym locomotion/turning controller for forward and turning targets. Implement feeding as a directional proboscis primitive: use rostrum/haustellum/head DOFs reported by todo 8, transform food-relative bearing/elevation into proboscis yaw/pitch/extension targets, and log target vs measured proboscis direction. Implement grooming as a face/antenna cleaning primitive: use controllable antenna/head/front-leg DOFs reported by todo 8 to produce a repeated face-contact or near-face sweep pattern, and log target vs measured face/antenna distance. Body-side controllers may stabilize gait/posture, but the selected mode/intensity/direction must come only from decoded brain output.
  Parallelization: Wave 5 | Blocked by: 8,15 | Blocks: 18,20,21,22
  References: `reports/eon_embodied_fly_technical_report.html:793` to `reports/eon_embodied_fly_technical_report.html:812`; `reports/eon_embodied_fly_technical_report.html:942` to `reports/eon_embodied_fly_technical_report.html:947`; `docs/runtime/flygym_api_probe.md`.
  Acceptance criteria: `/opt/miniconda3/envs/flygym_env/bin/python -m unittest tests.test_body_controllers` proves decoded control frames map to controller targets for locomotion, directional proboscis feeding, face grooming, and stop; tests assert arena dust/food state alone cannot select a controller mode; tests assert changing food-relative bearing changes proboscis target direction with the expected sign.
  QA scenarios: happy: run controller tests in `flygym_env`; failure: construct a control frame with both feeding and grooming above threshold and assert tie-breaking follows decoder priority config and is logged; construct a feeding control frame without food-relative direction and assert the controller refuses directional feeding rather than using stale direction. Evidence `.omo/evidence/task-16-eon-embodied-fly.json`
  Commit: Y | feat(body): adapt decoded controls to FlyGym actions

- [x] 17. Implement camera, recording, and optional viewer controls
  What to do / Must NOT do: Add `src/digital_fruit_fly/body/camera.py`. Use the API locked in todo 8 to support headless frame capture, tracking/fixed camera config, final MP4 writing, and optional viewer mode with user camera adjustment if the smoke probe proves it stable. If viewer mode is not stable, headless recording must still work. Must not block final video generation on live viewer.
  Parallelization: Wave 5 | Blocked by: 7,8,15 | Blocks: 18,23
  References: user requirement for realtime camera and final video; Eon demo video metadata in draft; `reports/eon_embodied_fly_technical_report.html:1013` to `reports/eon_embodied_fly_technical_report.html:1016`.
  Acceptance criteria: `/opt/miniconda3/envs/flygym_env/bin/python scripts/smoke_body.py --config configs/body_smoke.yaml --output outputs/smoke/body_camera --headless --record --steps 20 --timeout-sec 90` writes a nonempty MP4 or documented image sequence fallback; viewer smoke is separately reported as pass/fail without failing headless recording.
  QA scenarios: happy: run headless recording smoke; failure: configure an unsupported codec and assert fallback frames are written with a clear warning. Evidence `.omo/evidence/task-17-eon-embodied-fly.txt`
  Commit: Y | feat(body): add camera and recording support

- [x] 18. Implement the body server process
  What to do / Must NOT do: Add `scripts/run_body.py` and `src/digital_fruit_fly/body/server.py`. The server initializes arena + FlyGym simulation, connects to brain server, sends `SensoryFrame`, receives `BrainFrame`/decoded `ControlFrame` or runs local decoder after brain frame, steps body/arena, records video/logs, and handles shutdown. Must not import Brian2 or Shiu in the body process.
  Parallelization: Wave 5 | Blocked by: 4,15,16,17 | Blocks: 19,20,21,22
  References: `README.md:17` to `README.md:22`; `reports/eon_embodied_fly_technical_report.html:907` to `reports/eon_embodied_fly_technical_report.html:916`; `reports/eon_embodied_fly_technical_report.html:973` to `reports/eon_embodied_fly_technical_report.html:998`.
  Acceptance criteria: `/opt/miniconda3/envs/flygym_env/bin/python scripts/run_body.py --config configs/bridge_smoke.yaml --brain-mode fixture --max-ticks 20 --output outputs/smoke/body_server` writes trajectory/control/video logs and exits 0 in headless mode.
  QA scenarios: happy: run body server against fixture brain mode; failure: start body server with no brain reachable and assert timeout/error handling writes an error manifest and exits cleanly. Evidence `.omo/evidence/task-18-eon-embodied-fly.json`
  Commit: Y | feat(body): serve body simulation over IPC

- [x] 19. Implement upward sensory encoder
  What to do / Must NOT do: Add `src/digital_fruit_fly/bridge/sensory_encoder.py`. Convert arena/body observations into configured brain input rates: sugar left/right gradient, food contact, dust load, ground contact, joint/proprioception summary, fly-centric food bearing/elevation/distance, proboscis proprioception, antenna/front-leg/head proprioception, and action feedback. Include normalization, clipping, latency if configured, and audit logging of raw-to-encoded values. Must not pass action decisions or behavior labels upward.
  Parallelization: Wave 6 | Blocked by: 4,9,10,15,18 | Blocks: 21,22
  References: `reports/eon_embodied_fly_technical_report.html:829` to `reports/eon_embodied_fly_technical_report.html:838`; `reports/eon_embodied_fly_technical_report.html:933` to `reports/eon_embodied_fly_technical_report.html:939`; `reports/eon_embodied_fly_technical_report.html:1001` to `reports/eon_embodied_fly_technical_report.html:1004`.
  Acceptance criteria: `PYTHONPATH=src python3 -m unittest tests.test_sensory_encoder` proves monotonic sugar rates, left/right asymmetry, food bearing/elevation encoding sign, distance/contact signal, dust threshold signal, proprioceptive channels for proboscis/grooming DOFs when configured, clipping, and no forbidden behavior-label fields.
  QA scenarios: happy: run sensory encoder tests; failure: create an observation with `behavior="groom"` and assert schema rejects it. Evidence `.omo/evidence/task-19-eon-embodied-fly.json`
  Commit: Y | feat(bridge): encode body observations as brain inputs

- [x] 20. Implement downward motor decoder
  What to do / Must NOT do: Add `src/digital_fruit_fly/bridge/motor_decoder.py`. Convert brain readout rates/spikes into locomotion, turn, feed, groom, stop, proboscis extension amplitude, proboscis yaw/pitch direction, and grooming sweep phase/intensity using configured readout groups, time windows, baselines, smoothing, thresholds, and priority rules. The decoder may combine brain readout with encoded food-relative direction only through explicit sensory-to-brain-to-decoder state, and must log that provenance. Must not let arena food/dust state directly set action mode.
  Parallelization: Wave 6 | Blocked by: 11,12,13,16,18 | Blocks: 21,22
  References: `reports/eon_embodied_fly_technical_report.html:845` to `reports/eon_embodied_fly_technical_report.html:848`; `reports/eon_embodied_fly_technical_report.html:942` to `reports/eon_embodied_fly_technical_report.html:947`; `reports/eon_embodied_fly_technical_report.html:1007` to `reports/eon_embodied_fly_technical_report.html:1010`.
  Acceptance criteria: `PYTHONPATH=src python3 -m unittest tests.test_motor_decoder` proves each readout group can select its action, tie-breaking is deterministic, low-confidence output selects stop/search fallback only through configured brain baselines, feeding output includes extension and direction fields, grooming output includes sweep phase/intensity fields, and audit logs include all thresholds.
  QA scenarios: happy: run motor decoder tests; failure: remove a required readout group from a temp mapping and assert startup fails before any body action. Evidence `.omo/evidence/task-20-eon-embodied-fly.json`
  Commit: Y | feat(bridge): decode brain outputs to body controls

- [x] 21. Implement integrated bridge runner and replay validation
  What to do / Must NOT do: Add `scripts/smoke_bridge.py`, `scripts/replay_run.py`, and integration code that runs fixture brain/body modes for 1,000 ticks with the real protocol, encoder, and decoder. Replay must verify frame continuity, checksums, deterministic decoded controls, event order, and no message loss. Must not require FlyGym or Brian2 for fixture replay tests.
  Parallelization: Wave 6 | Blocked by: 13,18,19,20 | Blocks: 22,23
  References: `reports/eon_embodied_fly_technical_report.html:995` to `reports/eon_embodied_fly_technical_report.html:998`; draft decision "deterministic closed-loop replay first".
  Acceptance criteria: `PYTHONPATH=src python3 scripts/smoke_bridge.py --config configs/bridge_smoke.yaml --ticks 1000 --output outputs/smoke/bridge` exits 0; `PYTHONPATH=src python3 scripts/replay_run.py --input outputs/smoke/bridge --verify` exits 0 and writes replay evidence.
  QA scenarios: happy: run bridge smoke and replay commands; failure: delete one JSONL frame from a copied smoke output and assert replay detects the missing frame. Evidence `.omo/evidence/task-21-eon-embodied-fly.json`
  Commit: Y | feat(bridge): add closed-loop smoke and replay

- [x] 22. Calibrate and verify the Eon-style behavior scenario
  What to do / Must NOT do: Add `src/digital_fruit_fly/behavior/scenario.py`, calibration configs, and summary metrics. The seeded scenario must show: random/search locomotion when sugar cue is absent; movement biased toward food after cue; feeding on food contact with proboscis extension direction following food-relative direction; dust accumulation during field exposure; stop/groom when dust threshold sensory input drives brain output; visible face/antenna grooming sweep; dust returns to zero; locomotion resumes. Calibration may adjust encoder/decoder thresholds and provisional mappings, but action transitions and fine-action targets must remain traceable to brain output logs.
  Parallelization: Wave 6 | Blocked by: 10,19,20,21 | Blocks: 23
  References: user behavior-flow requirements; `reports/eon_embodied_fly_technical_report.html:793` to `reports/eon_embodied_fly_technical_report.html:812`; `reports/eon_embodied_fly_technical_report.html:957` to `reports/eon_embodied_fly_technical_report.html:960`.
  Acceptance criteria: `PYTHONPATH=src python3 scripts/replay_run.py --input outputs/smoke/bridge --verify-behavior configs/eon_demo.yaml` or the first full demo run's `summary.json` contains ordered events `search_started`, `sugar_cue_acquired`, `food_contact`, `feeding_started`, `proboscis_extended`, `dust_threshold_crossed`, `grooming_started`, `face_grooming_sweep_detected`, `dust_clean`, `locomotion_resumed`, with each action event linked to brain-frame IDs. Summary metrics include proboscis target-vs-food-direction angular error and grooming face/antenna proximity or sweep amplitude.
  QA scenarios: happy: run calibrated fixture/full run and verify event sequence plus fine-action metrics; failure: set dust threshold impossibly high in a temp config and assert the behavior verifier reports missing grooming rather than passing; set food bearing left vs right in fixtures and assert proboscis direction metric changes sign. Evidence `.omo/evidence/task-22-eon-embodied-fly.json`
  Commit: Y | feat(behavior): calibrate search feeding grooming scenario

- [x] 23. Produce the final demo runner, videos, and run summary
  What to do / Must NOT do: Add or complete `scripts/run_demo.py`, `scripts/render_run_summary.py`, and final docs in `README.md` if needed. The demo runner starts brain and body in separate processes using configured env python paths, waits for readiness, runs the scenario, shuts down cleanly, renders body video and brain activity video, writes summary metrics, and records whether realtime viewer was available. Must not require a user to manually merge logs or hand-run postprocessing.
  Parallelization: Wave 7 | Blocked by: 14,17,22 | Blocks: final verification
  References: `README.md:15` to `README.md:22`; user requirement for camera, interactive target, final generated video, and neural activity observation; Eon MP4 metadata from draft as visual reference only.
  Acceptance criteria: `python3 scripts/run_demo.py --config configs/eon_demo.yaml --output outputs/runs/eon_demo_smoke --duration-sec 60 --seed 1` exits 0 or exits with a documented P0 body-runtime blocker; on success, `outputs/runs/eon_demo_smoke/video/fly_demo.mp4`, neural activity artifact, `summary.json`, and replay-verifiable logs exist and are nonempty.
  QA scenarios: happy: run final demo command and replay verifier; failure: kill the brain subprocess during a short run and assert the orchestrator writes a failure manifest, terminates body subprocess, and leaves no hanging children. Evidence `.omo/evidence/task-23-eon-embodied-fly.json`
  Commit: Y | feat(demo): generate Eon-style embodied fly run artifacts

## Final verification wave
> Runs in parallel after ALL todos. ALL must APPROVE. Surface results and wait for the user's explicit okay before declaring complete.
- [x] F1. Plan compliance audit
  Command/evidence: `python3 - <<'PY'` script or small verifier checks that every Must have has an artifact, every Must NOT has no matching import/field/path, every todo evidence file exists, and `reports/`, `DESIGN.md`, and `external/drosophila_brain_model/` were not modified. Evidence `.omo/evidence/final-f1-plan-compliance.json`
  Approval condition: all scoped deliverables are present and no guardrail violation is found.
- [x] F2. Code quality review
  Command/evidence: `python3 -m compileall src scripts tests`; `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'`; inspect modules for behavior-label bypasses and hard-coded FlyWire IDs. Evidence `.omo/evidence/final-f2-code-quality.txt`
  Approval condition: syntax and unit tests pass; neural IDs live in configs/data; bridge messages do not contain direct action labels from arena.
- [x] F3. Real manual QA
  Command/evidence: agent runs `/opt/miniconda3/envs/brain_env/bin/python scripts/smoke_brain.py --config configs/brain_smoke.yaml --output outputs/smoke/brain_final`, `/opt/miniconda3/envs/flygym_env/bin/python scripts/smoke_body.py --config configs/body_smoke.yaml --output outputs/smoke/body_final --headless --steps 20 --timeout-sec 60`, then `python3 scripts/run_demo.py --config configs/eon_demo.yaml --output outputs/runs/eon_demo_final --duration-sec 60 --seed 1`. Evidence `.omo/evidence/final-f3-real-qa.json`
  Approval condition: final demo succeeds or produces a precise P0 blocker with no fake success; if it succeeds, video/logs/replay summary exist and event sequence matches requirement.
- [x] F4. Scope fidelity
  Command/evidence: compare `outputs/runs/eon_demo_final/summary.json` and logs against user requirements; verify no visual-control implementation, no Eon 91% claim, no direct non-brain action selection, and realtime viewer status is honestly reported. Evidence `.omo/evidence/final-f4-scope-fidelity.md`
  Approval condition: final artifacts demonstrate locomotion, feeding, and grooming controlled through brain output and explain any runtime limitations.

## Commit strategy
- Do not commit unless the user explicitly asks during execution. If commits are requested, use one atomic commit per wave after that wave's acceptance commands pass.
- Keep generated artifacts out of commits unless a tiny fixture is explicitly required for tests.
- Suggested commit order if committing is requested:
  - `chore(scaffold): add digital fruit fly package skeleton`
  - `feat(config): define runtime and demo configuration`
  - `feat(runtime): add manifest logging and smoke harness`
  - `feat(bridge): add protocol transport and replay`
  - `feat(arena): model sugar cue and dust dynamics`
  - `feat(brain): wrap Shiu Brian2 service`
  - `feat(body): wrap FlyGym simulation and recording`
  - `feat(behavior): calibrate closed-loop demo scenario`
  - `feat(demo): generate embodied fly videos and summaries`
- Before any commit, run `git status --short` and keep unrelated untracked `DESIGN.md` and `reports/` handling explicit; do not accidentally stage user-owned files unless the user asks.

## Success criteria
- `configs/eon_demo.yaml` defines a complete, reproducible demo scenario with 15 ms bridge tick, bounded arena, sugar cue geometry, dust dynamics, brain mappings, motor decoder thresholds, camera, and output settings.
- Brain process and body process run in their separate conda environments and communicate through the versioned IPC protocol.
- Upward sensory encoding and downward motor decoding are implemented, logged, tested, and replayable.
- Locomotion, directional proboscis feeding, and face/antenna grooming are selected by decoded brain output, not direct arena/body rule shortcuts.
- The behavior sequence appears in logs and summary: random search, sugar cue acquisition, oriented movement, food contact, feeding, proboscis extension toward food-relative direction, dust threshold, face/antenna grooming sweep, dust reset, and locomotion resume.
- Final run artifacts include body video and brain activity visualization or documented fallback, plus trajectory, events, control, arena, brain spikes/rates, and summary files.
- If realtime viewer works, the run supports interactive camera viewing and still records final video; if it does not, the final summary states the viewer blocker and headless video remains the accepted milestone.
- All unit, smoke, bridge, replay, and final verification commands pass or produce a precise environment blocker without false success.
