# Global Review Context Fix - Brian2 Default Demo Brain Mode

Date: 2026-06-25

## Root Cause

`src/digital_fruit_fly/demo/process_run.py` hard-coded the default separate-process brain child command as `scripts/run_brain.py --mode fixture`. That made the final acceptance path attempt fixture brain mode unless the caller explicitly chose another process mode.

## Red Evidence

Command:

```bash
PYTHONPATH=src python3 -m unittest tests.test_demo_runner.TestDemoRunner.test_default_demo_is_honest_about_real_subprocess_acceptance
```

Result before fix:

```text
AssertionError: 'fixture' != 'brian2'
 : ['/opt/miniconda3/envs/brain_env/bin/python', 'scripts/run_brain.py', '--config', 'configs/eon_demo.yaml', '--mode', 'fixture', ...]
```

Focused failure-priority test before classification fix:

```text
AssertionError: 'p0_body_process_failed' != 'p0_brain_process_failed'
```

## Fix

- Default separate-process brain command now uses `--mode brian2`.
- Default demo tests assert `--mode brian2` in success and failure manifests.
- If a ready brain child exits nonzero on its own while the body also fails, the top-level blocker is now `p0_brain_process_failed`.

## Acceptance Facts

Command:

```bash
python3 scripts/run_demo.py --config configs/eon_demo.yaml --output outputs/runs/eon_demo_smoke --duration-sec 60 --seed 1
```

Result after fix:

- Exit code: `1`
- `outputs/runs/eon_demo_smoke/failure_manifest.json`: `status=failed`, `mode=separate_processes`, `error_code=p0_brain_process_failed`
- Brain command: `/opt/miniconda3/envs/brain_env/bin/python scripts/run_brain.py --config configs/eon_demo.yaml --mode brian2 --max-ticks 4000 --output outputs/runs/eon_demo_smoke --timeout-sec 60.0`
- `outputs/runs/eon_demo_smoke/summary.json`: absent
- `children_alive_after_cleanup`: `[]`
- Brian2 blocker: `UnknownSensoryChannelError: unknown sensory channel: food_bearing_rad`

## Verification

```bash
PYTHONPATH=src python3 -m unittest tests.test_demo_runner
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
PYTHONPYCACHEPREFIX=/private/tmp/dff_pycache python3 -m py_compile src/digital_fruit_fly/demo/process_run.py tests/test_demo_runner.py
python3 -m json.tool .omo/evidence/task-23-eon-embodied-fly.json
```

All commands passed, except exact acceptance intentionally exits nonzero with the documented Brian2 final-path blocker above.
