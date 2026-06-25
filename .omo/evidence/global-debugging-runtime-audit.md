# Global Debugging Runtime Audit

- Verdict: PASS

- Environment Snapshot:
  - Workspace: `/Users/lins/Code/digital-fruit-fly`.
  - Runtime/audit tools: `python3 --version` reported `Python 3.13.9`; JSON manifest parsed with `python3`.
  - Required prior evidence read: `.omo/evidence/global-review-context-rerun.md`.
  - Current artifact parsed: `outputs/runs/eon_demo_smoke/failure_manifest.json`, size `4823`, mtime recorded by the rerun evidence as `2026-06-25 03:56:22 CST`.
  - Current artifact existence checks covered `outputs/runs/eon_demo_smoke/summary.json`, `video/fly_demo.mp4`, `replay_evidence.json`, `task-23-evidence.json`, `manifest.json`, `failure_manifest.json`, `frames.jsonl`, `behavior_summary.json`, `video/fly_demo.metadata.json`, and `video/brain_activity.mp4`.
  - Bounded runtime check: `TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest tests.test_demo_runner` exited 0 and reported `Ran 4 tests in 12.209s` / `OK`.
  - Safe process check: a read-only `ps` scan for `scripts/run_brain.py`, `scripts/run_body.py`, `scripts/run_demo.py`, and `outputs/runs/eon_demo_smoke` returned `NO_MATCHING_DEMO_PROCESSES`.
  - Protected path status before and after runtime checks was unchanged: `?? DESIGN.md` and `?? reports/eon_embodied_fly_technical_report.html`; no protected-path diff was introduced.
  - Stale `outputs/runs/eon_demo_final/failure_manifest.json` was not used for current path judgment.

- Hypotheses:
  - H1:
    - Claim: The current final demo path still silently falls back to fixture brain mode.
    - Distinguishing evidence: The fresh smoke manifest brain subprocess command must contain `--mode brian2`, and the default demo tests must assert Brian2 mode for the default path.
    - Observed value: `outputs/runs/eon_demo_smoke/failure_manifest.json` has `mode == "separate_processes"` and brain command `/opt/miniconda3/envs/brain_env/bin/python scripts/run_brain.py --config configs/eon_demo.yaml --mode brian2 --max-ticks 4000 --output outputs/runs/eon_demo_smoke --timeout-sec 60.0`. `tests.test_demo_runner` passed, including the default-path assertions that call `_assert_brain_command_mode(..., "brian2")`.
    - Verdict: Refuted. Current evidence shows the default separate-process path uses Brian2, not fixture mode.
  - H2:
    - Claim: The demo reports failure but leaves stale success artifacts that could fake completion.
    - Distinguishing evidence: Success sentinel artifacts should be absent from `outputs/runs/eon_demo_smoke`, especially `summary.json`, `video/fly_demo.mp4`, and replay/evidence success artifacts.
    - Observed value: `summary.json: exists=False`; `video/fly_demo.mp4: exists=False`; `replay_evidence.json: exists=False`; `task-23-evidence.json: exists=False`. Failure and partial telemetry artifacts remain, including `failure_manifest.json`, `manifest.json`, `frames.jsonl`, `behavior_summary.json`, `video/fly_demo.metadata.json`, and `video/brain_activity.mp4`, but they do not form a successful final demo completion signal.
    - Verdict: Refuted. The smoke run has explicit failure telemetry and lacks the success sentinel artifacts that would fake completion.
  - H3:
    - Claim: The failed demo leaks child processes or leaves cleanup incomplete.
    - Distinguishing evidence: The manifest should report no alive children after cleanup, subprocess cleanup fields should be terminal states, and a safe process-table scan should not find live demo children.
    - Observed value: `children_alive_after_cleanup == []`; brain subprocess has `cleanup == "exited"`; body subprocess has `cleanup == "completed"`; read-only process scan returned `NO_MATCHING_DEMO_PROCESSES`.
    - Verdict: Refuted. Current manifest and live process state show no leaked demo children.
  - H4:
    - Claim: The top-level blocker is masking a body timeout/failure instead of the required Brian2 final-path blocker.
    - Distinguishing evidence: Top-level `error_code`, brain return code/stderr, and body subprocess status must show whether the primary blocker is Brian2 or a body timeout.
    - Observed value: Top-level `error_code == "p0_brain_process_failed"`. Brain subprocess has `returncode == 1`, `status == "failed"`, `cleanup == "exited"`, and stderr ends in `digital_fruit_fly.brain.tickable_network.UnknownSensoryChannelError: unknown sensory channel: food_bearing_rad`. Body subprocess has `returncode == 1`, `status == "failed"`, `cleanup == "completed"`, and empty stderr; it is not reported as a timeout.
    - Verdict: Refuted as a body-timeout masker. A secondary body failure is present, but the runtime root observable and top-level blocker are the Brian2 final-path sensory-channel failure.

- Accepted P0 Blocker:
  - Error code: `p0_brain_process_failed`.
  - Root runtime observable: Brian2 brain subprocess launched with `--mode brian2`, exited with return code `1`, and emitted `UnknownSensoryChannelError: unknown sensory channel: food_bearing_rad`.
  - Scope judgment: This is the accepted P0 final-path blocker. No other confirmed hypothesis remains as an unhandled failure outside this blocker.

- Cleanup/Artifacts:
  - Repo writes: only this audit file, `.omo/evidence/global-debugging-runtime-audit.md`.
  - Scratch files: no recent `/private/tmp/brian_debug_*` or `/private/tmp/brian_script_*` files were found after the bounded unittest rerun; no scratch cleanup was required.
  - Processes: live process scan found no matching demo, brain, body, or smoke-output processes.
  - Protected paths: `external/drosophila_brain_model/`, `reports/`, and `DESIGN.md` were not edited. Pre-existing untracked protected-path entries remained unchanged: `DESIGN.md` and `reports/eon_embodied_fly_technical_report.html`.

- Blocking Issues:
