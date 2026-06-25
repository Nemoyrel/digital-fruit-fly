# eon-embodied-fly-brian2-food-bearing-fix - Work Plan

## TL;DR
Fix the remaining P0 Brian2 blocker from the completed `eon-embodied-fly` plan: the final demo currently fails in `run_brain.py --mode brian2` because the brain process treats `food_bearing_rad` as an undeclared sensory channel. The goal is a real end-to-end demo run, not a fake success marker.

## Scope
### Must have
- Reproduce the current Brian2 blocker with evidence: `UnknownSensoryChannelError: unknown sensory channel: food_bearing_rad`.
- Add failing-first regression coverage at the narrowest seam that proves Brian2-facing sensory channel extraction does not reject body context fields like `food_bearing_rad`, while still rejecting genuine undeclared encoded channels.
- Fix the bridge/brain boundary so only configured Brian2 sensory channels are passed into `TickableBrainNetwork.tick`; contextual body fields must remain available for downstream control/provenance and logs.
- Preserve the guardrail that real unknown configured-channel names still fail before Brian2 advances.
- Rerun targeted unit tests, smoke commands, replay verification, and the final demo with Brian2 mode.
- Produce successful `summary.json` and nonempty video/brain artifacts under `outputs/runs/eon_demo_final` or a new clearly named final run directory.

### Must not have
- Do not bypass the Brian2 brain by switching final demo to fixture mode.
- Do not remove `food_bearing_rad`, `food_elevation_rad`, or `food_distance_mm` from body-side context if feeding/proboscis direction still needs them.
- Do not add direct arena-derived behavior labels or action commands.
- Do not edit `external/drosophila_brain_model/`.
- Do not mark completion if final demo only writes a P0 blocker manifest.

## Verification strategy
- Unit: `PYTHONPATH=src python3 -m unittest tests.test_brain_server tests.test_tickable_brain tests.test_sensory_encoder tests.test_motor_decoder`
- Brain-env targeted: `/opt/miniconda3/envs/brain_env/bin/python -m unittest tests.test_tickable_brain`
- Smoke brain Brian2: `/opt/miniconda3/envs/brain_env/bin/python scripts/smoke_brain.py --config configs/brain_smoke.yaml --tickable --ticks 10 --output outputs/smoke/brain_food_bearing_fix`
- Final demo: `python3 scripts/run_demo.py --config configs/eon_demo.yaml --output outputs/runs/eon_demo_final --duration-sec 60 --seed 1`
- Replay: `PYTHONPATH=src python3 scripts/replay_run.py --input outputs/runs/eon_demo_final --verify`

## TODOs
- [x] 24. Fix Brian2 sensory payload filtering for food direction context
  What to do / Must NOT do: Find the exact path that converts a `SensoryFrame.payload` into Brian2 channel values. Add red-first coverage using a payload that includes configured channels plus `food_bearing_rad`, `food_elevation_rad`, and `food_distance_mm`; it must fail before the fix with the current `UnknownSensoryChannelError`. Then implement the minimum boundary fix so configured channels are delivered to Brian2 and body context scalars are ignored by Brian2 validation but preserved in the original payload/logs. Must not weaken `TickableBrainNetwork.validate_sensory_channel_values` for callers that pass true encoded channels directly.
  Acceptance criteria: targeted tests pass; a test still proves an actual undeclared channel is rejected; no behavior-label bypass fields are introduced.
  QA scenarios: happy: run a short brain/body or brain-server fixture interaction with body-style payload and observe a `BrainFrame`; failure: send `unknown_sense` as an encoded channel and observe a protocol/runtime rejection before tick advance.
  Evidence: `.omo/evidence/task-24-brian2-food-bearing-fix.json`

## Final verification wave
- [ ] F5. Final Brian2 demo and artifact verification
  Command/evidence: run the final demo with `run_brain.py --mode brian2` via `scripts/run_demo.py`, replay the output, and inspect `summary.json`, `video/fly_demo.mp4`, and brain activity artifact existence/nonempty size.
  Approval condition: final demo exits 0, replay exits 0, `summary.json` contains the required behavior sequence or explicit pass metrics, and no P0 blocker manifest remains.
- [ ] F6. Global review and debugging gate
  Command/evidence: run the post-implementation review lanes and a debugging-oriented runtime audit with at least three hypotheses about the changed boundary.
  Approval condition: all review lanes pass and all runtime hypotheses are ruled out or fixed with evidence.

## Success criteria
- The current `food_bearing_rad` Brian2 blocker is gone.
- The final demo uses Brian2 mode and completes end to end.
- The final run directory contains `summary.json`, trajectory/control/arena/brain logs, nonempty body video, and brain activity output or documented nonblocking fallback.
- Existing guardrails from `.omo/plans/eon-embodied-fly.md` still hold.
