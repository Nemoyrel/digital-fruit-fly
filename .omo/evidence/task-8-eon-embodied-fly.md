# Todo 8 FlyGym API Report Evidence

## Root Cause

Confirmed H1. The API-report child command left the GLFW platform on the default
windowed path when `--api-report` was used without `--headless`. On macOS this
entered AppKit/LaunchServices during FlyGym import and timed out before
`child_probe.json` was written. Forcing the effective renderer to `none` before
`prepare_glfw_platform()` makes the same default API-report command request
GLFW's null platform before importing FlyGym.

## Toggle Proof

Bounded child probes with `/opt/miniconda3/envs/flygym_env/bin/python -m digital_fruit_fly.body.flygym_probe --child-probe --steps 20 --api-report`:

- Default `--renderer auto`: timed out after `45.011s`, no child output, stderr contained `Connection Invalid error for service com.apple.hiservices-xpcservice`.
- `--headless`: exit `0` in `12.093s`, child payload had `glfw={"platform_hint":"null","reason":"headless"}` and renderer skipped.
- `--renderer none`: exit `0` in `0.905s`, child payload had `glfw={"platform_hint":"null","reason":"renderer_none"}` and renderer skipped.

This toggles the failure by toggling the null-platform path, while the report
builder still executes successfully in the passing cases.

## Red / Green Proof

Red test command:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest tests.test_body_smoke.TestBodySmoke.test_child_probe_requests_glfw_null_before_flygym_import_for_api_report
```

Exit code: `1`.

Failure excerpt:

```text
AssertionError: Lists differ: [] != ['glfw.init_hint:1:2']
```

Green focused test command:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest tests.test_body_api_probe tests.test_body_smoke
```

Exit code: `0`.

Pass line:

```text
Ran 10 tests in 0.422s
OK
```

The missing fine-action fixture is covered by
`tests.test_body_api_probe.TestBodyApiProbe.test_missing_fine_action_dofs_fail_with_exact_phrase`,
which asserts the exact phrase `unsupported installed FlyGym fine-action API`.

## Acceptance Smoke

Exact acceptance command:

```bash
/opt/miniconda3/envs/flygym_env/bin/python scripts/smoke_body.py --config configs/body_smoke.yaml --output outputs/smoke/body --api-report
```

Exit code: `0`.

Observed payload facts:

- `status`: `ok`
- `probe_stage`: `complete`
- `glfw`: `{"platform_hint": "null", "reason": "renderer_none"}`
- `renderer`: `{"renderer": "none", "status": "skipped"}`
- `api_report_path`: `outputs/smoke/body/flygym_api.json`
- `api_report_doc`: `/Users/lins/Code/digital-fruit-fly/docs/runtime/flygym_api_probe.md`
- `duration_sec`: about `0.48s`

Flake rerun of the same command with stdout redirected to a temporary file also
exited `0`.

## JSON / Markdown QA

JSON parse command:

```bash
python3 -m json.tool outputs/smoke/body/flygym_api.json >/dev/null
```

Exit code: `0`.

JSON contract assertion command:

```bash
python3 -c 'import json
from pathlib import Path
required={"schema_version","generated_at","environment","imports","simulation","locomotion_controller","observation","camera","video","skeleton","actuators","joint_readout","site_positions","fine_action_support"}
report=json.loads(Path("outputs/smoke/body/flygym_api.json").read_text(encoding="utf-8"))
missing=sorted(required-set(report))
fine=report["fine_action_support"]
for key in ("supports_proboscis_control","supports_antenna_control","supports_front_leg_face_grooming","supports_site_positions"):
    assert isinstance(fine[key], bool), key
for key in ("proboscis_dofs","antenna_dofs","front_leg_face_grooming_dofs"):
    assert isinstance(fine[key], list) and fine[key], key
assert isinstance(report["actuators"]["position_actuator_order"], list) and report["actuators"]["position_actuator_order"]
assert report["actuators"]["position_actuator_order"] == report["joint_readout"]["joint_dof_order"] == report["skeleton"]["joint_dof_order"]
assert report["site_positions"]["supports_site_positions"] is True
assert not missing, missing
print("PASS", {"actuators": len(report["actuators"]["position_actuator_order"]), "proboscis": len(fine["proboscis_dofs"]), "antenna": len(fine["antenna_dofs"]), "front_leg": len(fine["front_leg_face_grooming_dofs"])})'
```

Exit code: `0`.

Output:

```text
PASS {'actuators': 126, 'proboscis': 6, 'antenna': 18, 'front_leg': 22}
```

Generated artifact paths:

- `outputs/smoke/body/flygym_api.json`
- `docs/runtime/flygym_api_probe.md`
- `outputs/smoke/body/child_probe.json`
- `outputs/smoke/body/body_env.json`

Markdown inspection PASS facts:

- Shows FlyGym `2.0.2` and MuJoCo `3.6.0`.
- Shows actuator count `126`.
- Shows proboscis, antenna, front-leg face grooming, and site positions as supported.
- Points to `outputs/smoke/body/flygym_api.json`.

## Cleanup Receipt

- Removed `.debug-journal.md`.
- Removed temporary files:
  - `/private/tmp/dff-todo8-default.json`
  - `/private/tmp/dff-todo8-headless.json`
  - `/private/tmp/dff-todo8-none.json`
  - `/private/tmp/dff-todo8-acceptance-rerun.stdout`
- Debug marker scan over scoped Python files returned no matches for `breakpoint(`, `ipdb`, `pudb`, `pdb.set_trace`, `TODO DEBUG`, `DEBUG:`, `HACK`, or `XXX`.
- Initial sandboxed `ps` was blocked with `operation not permitted`; escalated process inspection was used as required.
- `pgrep -fl 'smoke_body.py|digital_fruit_fly.body.flygym_probe|mujoco|flygym'` exit code: `1`, output empty. No smoke, child probe, MuJoCo, or FlyGym process remained.

## Pure LOC

- `src/digital_fruit_fly/body/flygym_api.py`: `208`
- `src/digital_fruit_fly/body/flygym_api_docs.py`: `57`
- `src/digital_fruit_fly/body/flygym_probe.py`: `247`
- `tests/test_body_api_probe.py`: `116`
- `tests/test_body_smoke.py`: `235`

## Adversarial Classes

- `malformed_input`: covered by existing invalid renderer test.
- `stale_state`: stale child payload test still passes; current child output is unlinked before run.
- `dirty_worktree`: active; repository was already broadly untracked. Only Todo 8 scoped paths were edited.
- `hung_long_commands`: reproduced with bounded child timeout and fixed by pre-import null platform.
- `flaky_tests`: exact acceptance smoke was rerun and passed again.
- `misleading_success_output`: JSON report was parsed and contract-asserted after smoke exit `0`.
- `prompt_injection`: not applicable.
- `cancel_resume`: not applicable.
- `repeated_interruptions`: not applicable.

## Risks

- `flygym_probe.py` remains in the warning band at `247` pure LOC. No extra lines should be added there without splitting another responsibility.
- The generated report depends on the installed FlyGym `2.0.2` API surface; future FlyGym versions may change DOF/site naming and trip the exact fine-action support validation.
