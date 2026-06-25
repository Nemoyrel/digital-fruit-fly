status: approved
verdict: approved
qa_check: F4 scope fidelity for .omo/plans/eon-embodied-fly.md
generated_at: 2026-06-25

# Scope Fidelity Verification

## Inputs Parsed

- `outputs/runs/eon_demo_final/summary.json`: absent.
- `outputs/runs/eon_demo_final/failure_manifest.json`: absent.
- `outputs/runs/eon_demo_smoke/failure_manifest.json`: present and parsed.
- `.omo/evidence/task-23-eon-embodied-fly.json`: present and parsed; content matches the smoke failure manifest.
- Supplemental current smoke artifacts inspected: `outputs/runs/eon_demo_smoke/frames.jsonl`, `outputs/runs/eon_demo_smoke/control.jsonl`, `outputs/runs/eon_demo_smoke/behavior_evidence.json`, `outputs/runs/eon_demo_smoke/video/fly_demo.metadata.json`, and `outputs/runs/eon_demo_smoke/video/brain_activity.metadata.json`.

## Verdict Rationale

Approved for scope fidelity because the current final/smoke acceptance state is not a fake success. The only current final-like structured evidence is a failed separate-process run:

- `outputs/runs/eon_demo_smoke/failure_manifest.json` records `status: failed`, `mode: separate_processes`, `error_code: p0_body_process_timeout`, and `error: body subprocess timed out while connected to brain`.
- The body command in that failure manifest used `--brain-mode connect`, but timed out and was terminated with `returncode: -15`.
- The brain subprocess command is explicitly labeled `--mode fixture`; it exited `ok`, so no Brian2/full-Shiu brain success is implied by this run.
- `children_alive_after_cleanup` is empty.

## Required Checks

1. Current artifact parsing: passed.
   - Final output directory artifacts were absent, so verification correctly fell back to `outputs/runs/eon_demo_smoke/failure_manifest.json` and `.omo/evidence/task-23-eon-embodied-fly.json`.
   - Both parsed failure manifests report the same body timeout blocker.

2. Visual control is not passed off as brain control: passed.
   - No inspected final/smoke summary claims visual control as brain control.
   - `outputs/runs/eon_demo_smoke/video/fly_demo.metadata.json` labels the body video source as `fixture_demo:deterministic_probe_frames`, not as a live brain controller.
   - Body control code routes `BrainFrame`/`ControlFrame` through decoded control and `select_body_command`; no visual-renderer output is used as the action source.

3. No unearned Eon 91% or equivalent fidelity claim: passed.
   - `rg -n "91|0\\.91|ninety|Eon fidelity|Eon-level|Eon level|equivalent to Eon|matches Eon|uploaded fruit fly|brain upload|multi-behavior brain upload|fidelity" README* docs src scripts configs .omo/evidence` found no 91% or equivalent fidelity claim. Matches were numeric IDs, source references, or unrelated evidence paths.
   - README only describes the project as an attempt to reproduce Eon's embodied fly using public components and lists Eon articles as references.

4. No direct non-brain action selection in final demo path: passed with blocker context.
   - `src/digital_fruit_fly/demo/process_run.py` starts the body with `--brain-mode connect` in the default separate-process path and records failure instead of success when the body times out.
   - `src/digital_fruit_fly/body/server_loop.py` gets each brain reply from the peer before building a control frame and applying a body tick.
   - `src/digital_fruit_fly/body/server_motion.py` converts `BrainFrame` rates into a `ControlFrame`; `src/digital_fruit_fly/body/controllers.py` selects a body mode from decoded control intensities.
   - `outputs/runs/eon_demo_smoke/control.jsonl` contains 4,000 rows, all `mode: stop`, with `arena_state_used_for_mode: false`; it does not demonstrate locomotion/feeding/grooming in the failed separate-process run.
   - The deterministic fixture path is labeled in fixture brain frames via `payload.fixture_mode` and in fixture demo summaries/runtime limitations in source. It is not the current final success state.

5. Realtime viewer status is honestly reported: passed for available artifacts; absent from the blocked final manifest.
   - The final failure manifest has no top-level viewer status because no success summary was written.
   - Supplemental video metadata reports `viewer_status: skipped_headless`.
   - Source fixture rendering passes `--viewer-status skipped_headless` and records fixture limitations.

6. Final behavior evidence vs blocker: passed as blocked, not as live success.
   - The current failure manifest precisely explains the final blocker: body subprocess timeout after 60 seconds while connected to the brain fixture server for 4,000 requested ticks.
   - `outputs/runs/eon_demo_smoke/behavior_evidence.json` does demonstrate locomotion, feeding, and grooming events with brain rates, but those events come from the bridge fixture artifacts (`bridge-smoke-*` frame IDs), not from a successful final separate-process run.
   - `outputs/runs/eon_demo_smoke/frames.jsonl` contains 4,000 `brain_frame` records with `fixture_mode` values `feeding`, `grooming`, and `locomotion`, plus matching `control_frame` records. This is acceptable fixture evidence only when treated as fixture evidence.

## Findings

- No P0/P1 scope-fidelity failure found in the current final/smoke artifacts.
- The final demo is blocked, not successful: body timeout is the honest acceptance state.
- The separate-process body control log does not demonstrate the requested multi-behavior sequence; all 4,000 body control rows are `stop`.
- The multi-behavior sequence exists in bridge fixture artifacts and is labeled at the frame/source level, not as a live Brian2/FlyGym final success.

## Residual Risks

- Fixture success artifacts coexist in the same `outputs/runs/eon_demo_smoke` directory as the failed separate-process manifest. Consumers must treat `failure_manifest.json` / task-23 evidence as authoritative for final acceptance status.
- `behavior_evidence.json` itself uses `mode: verify_behavior` and `bridge-smoke-*` frame IDs, but does not have a top-level `fixture` field. The fixture source is recoverable from `frames.jsonl` and source paths, but a top-level label would reduce ambiguity.
- A future successful `separate_processes` summary should include the brain subprocess mode at top level, because the current default separate-process implementation starts `run_brain.py --mode fixture`.

## Commands Run

```bash
pwd
find outputs/runs -maxdepth 3 -type f
find .omo/evidence -maxdepth 1 -type f
rg -n "91%|ninety[- ]one|Eon|fidelity|visual control|visual-control|vision control|brain control|fixture|fake success|realtime|real-time|viewer|headless|skipped_headless|direct action|action selection" README* docs src scripts configs .omo/evidence
python3 -m json.tool outputs/runs/eon_demo_smoke/failure_manifest.json
python3 -m json.tool .omo/evidence/task-23-eon-embodied-fly.json
python3 -m json.tool outputs/runs/eon_demo_smoke/manifest.json
python3 -m json.tool outputs/runs/eon_demo_smoke/behavior_evidence.json
sed -n '1,280p' src/digital_fruit_fly/demo/runner.py
sed -n '1,260p' src/digital_fruit_fly/demo/process_run.py
sed -n '1,240p' src/digital_fruit_fly/demo/process_summary.py
sed -n '1,260p' src/digital_fruit_fly/body/server_loop.py
sed -n '1,340p' src/digital_fruit_fly/body/server_motion.py
sed -n '1,260p' src/digital_fruit_fly/bridge/fixture_model.py
sed -n '1,280p' src/digital_fruit_fly/bridge/fixture_run.py
sed -n '1,260p' scripts/run_demo.py
rg -n "91|0\\.91|ninety|Eon fidelity|Eon-level|Eon level|equivalent to Eon|matches Eon|uploaded fruit fly|brain upload|multi-behavior brain upload|fidelity" README* docs src scripts configs .omo/evidence
python3 -m json.tool outputs/runs/eon_demo_smoke/behavior_summary.json
sed -n '1,240p' configs/eon_demo.yaml
sed -n '1,260p' src/digital_fruit_fly/bridge/motor_decoder.py
sed -n '1,260p' src/digital_fruit_fly/body/controllers.py
nl -ba src/digital_fruit_fly/demo/process_run.py
nl -ba src/digital_fruit_fly/demo/runner.py
nl -ba src/digital_fruit_fly/body/server_loop.py
nl -ba src/digital_fruit_fly/body/server_motion.py
nl -ba src/digital_fruit_fly/body/controllers.py
nl -ba src/digital_fruit_fly/bridge/fixture_model.py
nl -ba src/digital_fruit_fly/bridge/motor_decoder.py
nl -ba outputs/runs/eon_demo_smoke/failure_manifest.json
nl -ba outputs/runs/eon_demo_smoke/behavior_evidence.json
nl -ba outputs/runs/eon_demo_smoke/manifest.json
test -f outputs/runs/eon_demo_final/summary.json
test -f outputs/runs/eon_demo_final/failure_manifest.json
python3 -m json.tool outputs/runs/eon_demo_smoke/video/fly_demo.metadata.json
python3 -m json.tool outputs/runs/eon_demo_smoke/video/brain_activity.metadata.json
ls -la outputs/runs/eon_demo_smoke/video
python3 -c "import json, pathlib; p=pathlib.Path('outputs/runs/eon_demo_smoke/control.jsonl'); rows=[json.loads(line) for line in p.open()]; print({'rows': len(rows), 'first': rows[0]['mode'], 'last': rows[-1]['mode'], 'arena_state_used_values': sorted({row['audit']['selection']['arena_state_used_for_mode'] for row in rows if 'audit' in row and 'selection' in row['audit']}), 'modes': sorted({row['mode'] for row in rows})})"
python3 -c "import json, pathlib; p=pathlib.Path('outputs/runs/eon_demo_smoke/frames.jsonl'); counts={}; fixture_modes=set(); n=0;\nfor line in p.open():\n d=json.loads(line); counts[d['type']]=counts.get(d['type'],0)+1; n+=1;\n if d['type']=='brain_frame': fixture_modes.add(d['payload'].get('fixture_mode'));\nprint({'frames': n, 'counts': counts, 'brain_fixture_modes': sorted(fixture_modes)})"
python3 -c "import pathlib; files=['outputs/runs/eon_demo_final/summary.json','outputs/runs/eon_demo_final/failure_manifest.json','outputs/runs/eon_demo_smoke/failure_manifest.json','.omo/evidence/task-23-eon-embodied-fly.json']; print({f:pathlib.Path(f).exists() for f in files})"
head -n 3 outputs/runs/eon_demo_smoke/frames.jsonl
python3 -c "import json, collections; p='outputs/runs/eon_demo_smoke/frames.jsonl'; counts=collections.Counter(); modes=set(); n=0; f=open(p); exec('for line in f:\\n    d=json.loads(line)\\n    counts[d.get(\\\"type\\\", d.get(\\\"message_type\\\"))]+=1\\n    n+=1\\n    if d.get(\\\"type\\\", d.get(\\\"message_type\\\")) == \\\"brain_frame\\\": modes.add(d.get(\\\"payload\\\",{}).get(\\\"fixture_mode\\\"))'); print({'frames': n, 'counts': dict(counts), 'brain_fixture_modes': sorted(modes)})"
python3 -c "import json; rows=[json.loads(line) for line in open('outputs/runs/eon_demo_smoke/control.jsonl')]; print({'mode_counts': {m:sum(1 for r in rows if r['mode']==m) for m in sorted({r['mode'] for r in rows})}, 'decoded_examples': [rows[i]['decoded_control'] for i in (0,370,542,3999)]})"
python3 -c "import json; rows=[json.loads(line) for line in open('outputs/runs/eon_demo_smoke/events.jsonl')]; print({'events_rows': len(rows), 'first': rows[0] if rows else None, 'last': rows[-1] if rows else None})"
python3 -c "import json; rows=[json.loads(line) for line in open('outputs/runs/eon_demo_smoke/logs/brain_server.jsonl')]; print({'brain_log_rows': len(rows), 'first': rows[0] if rows else None, 'last': rows[-1] if rows else None})"
sed -n '1,260p' .omo/evidence/final-f4-scope-fidelity.md
git diff --name-only -- .omo/evidence/final-f4-scope-fidelity.md
find /private/tmp -maxdepth 1 -name 'final-f4-*' -type f
```

Note: the first `python3 -c` probe for `frames.jsonl` above failed with a shell newline quoting `SyntaxError`; it was immediately rerun successfully with the following `exec(...)`-based command.

## Cleanup

- No temporary files were created.
- No product files, plan, Boulder, or ledger files were edited.
- Only this report was written: `.omo/evidence/final-f4-scope-fidelity.md`.
