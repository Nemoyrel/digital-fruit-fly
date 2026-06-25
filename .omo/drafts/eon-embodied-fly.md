---
slug: eon-embodied-fly
status: planned
intent: clear
pending-action: start execution only after explicit user start-work approval
approach: staged deterministic closed-loop first, realtime viewer as stretch after FlyGym smoke; stdlib TCP framed JSON IPC v1
---

# Draft: eon-embodied-fly

## Components (topology ledger)
| id | outcome (one line) | status | evidence path |
| --- | --- | --- | --- |
| arena | Bounded field, sugar cue geometry, food contact, dust accumulation/cleanup, deterministic serialization. | active | `reports/eon_embodied_fly_technical_report.html:1013` to `reports/eon_embodied_fly_technical_report.html:1016`; user requirements |
| body | FlyGym/NeuroMechFly process exposing observations, decoded action control, directional proboscis feeding, face/antenna grooming, camera/video, optional viewer. | active, P0 runtime risk | `README.md:17` to `README.md:22`; FlyGym import probe hung locally; FlyGym anatomy/source files show antenna and proboscis segments/DOFs |
| brain | Shiu/Brian2 process with dynamic sensory inputs, spike/rate outputs, and neural activity logs. | active | `external/drosophila_brain_model/model.py:58` to `external/drosophila_brain_model/model.py:373` |
| bridge | 15 ms framed JSON IPC, sensory encoder, motor decoder, replay validation. | active | `reports/eon_embodied_fly_technical_report.html:857` to `reports/eon_embodied_fly_technical_report.html:863` |
| behavior | Search, cue approach, food-relative proboscis extension feeding, dust-triggered face/antenna grooming, dust reset, locomotion resume. | active | user requirements; `reports/eon_embodied_fly_technical_report.html:793` to `reports/eon_embodied_fly_technical_report.html:812` |
| observability | Body video, brain activity video or fallback, event/control/trajectory/brain logs, summary metrics. | active | user requirements; `reports/eon_embodied_fly_technical_report.html:1021` to `reports/eon_embodied_fly_technical_report.html:1028` |

## Open assumptions (announced defaults)
| assumption | adopted default | rationale | reversible? |
| --- | --- | --- | --- |
| realtime target | deterministic closed-loop replay and final video are first guaranteed milestone; realtime viewer is stretch after P0 | FlyGym import hung locally and full-brain realtime throughput is unproven | yes |
| IPC dependency | stdlib TCP framed JSON/JSONL v1 | avoids cross-env dependency risk; keeps transport replaceable | yes |
| neural mappings | sugar GRNs from Shiu example; motor/dust mappings explicitly marked provisional until curated | Eon did not publish mappings; IDs must be auditable | yes |
| tests | tests-after for integration plus unit-first tests for config/protocol/replay | project is empty and runtime envs are unvalidated | yes |

## Findings (cited - path:lines)
- Repo skeleton and two-env architecture: `README.md:7` to `README.md:34`.
- Eon missing bridge details: `reports/eon_embodied_fly_technical_report.html:685` to `reports/eon_embodied_fly_technical_report.html:690`; `reports/eon_embodied_fly_technical_report.html:757` to `reports/eon_embodied_fly_technical_report.html:760`.
- 15 ms sync: `reports/eon_embodied_fly_technical_report.html:713` to `reports/eon_embodied_fly_technical_report.html:715`; `reports/eon_embodied_fly_technical_report.html:857` to `reports/eon_embodied_fly_technical_report.html:863`.
- Vision out of first scope: `reports/eon_embodied_fly_technical_report.html:901` to `reports/eon_embodied_fly_technical_report.html:904`.
- Shiu model is batch-oriented today: `external/drosophila_brain_model/model.py:250` to `external/drosophila_brain_model/model.py:293`.
- Shiu model writes spike parquet from experiments: `external/drosophila_brain_model/model.py:296` to `external/drosophila_brain_model/model.py:373`.
- Sugar GRN IDs are available in the local Shiu example: `external/drosophila_brain_model/example.ipynb:68` to `external/drosophila_brain_model/example.ipynb:147`.
- FlyGym installed source defines `ANTENNA_LINKS = ["pedicel", "funiculus", "arista"]`, `PROBOSCIS_LINKS = ["rostrum", "haustellum"]`, and connected segment pairs for head-to-proboscis and head-to-antenna chains: `/opt/miniconda3/envs/flygym_env/lib/python3.12/site-packages/flygym/anatomy.py:196` to `/opt/miniconda3/envs/flygym_env/lib/python3.12/site-packages/flygym/anatomy.py:224`.
- FlyGym installed source exposes `JointPreset.ALL_POSSIBLE`, `ActuatedDOFPreset.ALL`, and `Fly.add_actuators(...)` for arbitrary joint DOFs, plus simulation read/write methods for joint angles, body/site positions, and actuator inputs: `/opt/miniconda3/envs/flygym_env/lib/python3.12/site-packages/flygym/anatomy.py:388` to `/opt/miniconda3/envs/flygym_env/lib/python3.12/site-packages/flygym/anatomy.py:499`; `/opt/miniconda3/envs/flygym_env/lib/python3.12/site-packages/flygym/compose/fly.py:302` to `/opt/miniconda3/envs/flygym_env/lib/python3.12/site-packages/flygym/compose/fly.py:370`; `/opt/miniconda3/envs/flygym_env/lib/python3.12/site-packages/flygym/simulation.py:151` to `/opt/miniconda3/envs/flygym_env/lib/python3.12/site-packages/flygym/simulation.py:359`.
- FlyGym asset rigging includes `c_rostrum`, `c_haustellum`, `l/r_pedicel`, `l/r_funiculus`, and `l/r_arista`, so the fine-action body parts are present as installed model assets.
- Local `brain_env` probe imported Brian2 2.9.0, pandas 2.3.3, pyarrow 24.0.0.
- Local `flygym_env` Python exists but FlyGym/MuJoCo import probe hung over 60 seconds and was terminated.
- Eon target MP4 is reachable as of 2026-06-24 with HTTP 200 and `content-length: 90960060`.

## Decisions (with rationale)
- Write formal plan to `.omo/plans/eon-embodied-fly.md`.
- Preserve strict two-process architecture and treat `src/digital_fruit_fly/bridge` as the project-owned core.
- Make brain-control auditable: no direct arena-derived behavior labels may control body actuation.
- Do not block v1 on realtime viewer; record realtime status honestly.
- Mandatory Metis subagent review was not spawned because the current subagent tool policy says not to spawn sub-agents unless the user explicitly asks for delegation/parallel agent work. Local gap analysis was folded into the plan by requiring references, acceptance criteria, happy/failure QA, evidence paths, and final compliance checks for every todo.
- User follow-up clarified two Eon-demo fine actions: grooming should include face/antenna cleaning motion, and feeding should extend the proboscis with direction adjusted by the food's position relative to the fly. The formal plan was updated to make these explicit in Must Have, todos 8/15/16/19/20/22, and success criteria.

## Scope IN
- Project skeleton, configs, manifests, smoke harness.
- Brain and body env validation.
- Arena sugar/dust model.
- Shiu/Brian2 wrapper and brain server.
- FlyGym wrapper and body server.
- Sensory encoder, motor decoder, bridge, replay.
- Demo behavior calibration.
- Body video and neural activity visualization.

## Scope OUT (Must NOT have)
- Visual control or optic-lobe pipeline.
- Claims of Eon 91% behavior accuracy or individual upload.
- Direct behavior-label bypass from arena/body rules to body controllers.
- Editing upstream Shiu files.
- Texture/art polish before closed-loop behavior.

## Open questions
- None. The user approved the recommended defaults.

## Approval gate
status: approved-and-planned
formal-plan: `.omo/plans/eon-embodied-fly.md`
next-step: wait for explicit execution request such as `$start-work`
