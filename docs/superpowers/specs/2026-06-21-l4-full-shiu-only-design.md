# L4 Full Shiu Only Design

## Goal

Turn the current branch into a clean L4-only embodied fruit fly demo that uses the full Shiu Brian2 brain model as the only formal brain backend. The project can run slowly before the presentation, but it must not present any alternate backend output as a successful full-brain run.

## Scope

This branch keeps only the L4 IPC system:

- FlyGym/NeuroMechFly body loop;
- minimal virtual scene with food cue, turn bias, dust accumulation, and contact state;
- low-dimensional brain/body readout interface;
- Brian2/Shiu brain worker;
- TCP JSON-lines IPC between body environment and brain environment;
- telemetry, benchmark metadata, plots, and side-by-side presentation videos.

All legacy staged demo artifacts are removed from public code, config, data, and docs.

## Brain Backend

The production backend is `shiu_full`.

`shiu_full` must import `external/drosophila_brain_model/model.py`, load the completeness CSV and connectivity parquet, call `create_model()`, construct a Brian2 `Network`, run configured sensory windows, and compute readouts from full-network spike activity for configured FlyWire IDs.

The first full-backend input/readout set is small but real:

- `food_cue` maps to sugar GRNs used by the Shiu example notebook.
- `dust_level` maps to JON mechanosensory neurons used in the Shiu figure 5 workflow.
- `mn9_rate_hz` reads FlyWire ID `720575940660219265`.
- Grooming and mechanosensory scores read configured DN/aBN targets from the Shiu figure 5 workflow.

The bridge from full-network rates to body commands remains a project-owned engineering bridge.

## Failure Semantics

There is no formal alternate success path on this branch.

If the full backend fails, the run should fail with useful metadata. Failure metadata should include the attempted stage, Brian2 environment, file paths checked, startup time if available, run time if available, and the exception or timeout reason.

## Long-Run Workflow

Because the presentation will use precomputed artifacts rather than live execution, the CLI should optimize for truthful batch generation:

1. Start the brain worker in `brain_env` with `--backend shiu_full`.
2. Run the embodied demo in `flygym_env` against that worker.
3. Write all outputs to `outputs/l4_ipc_embodied_loop/`.
4. Keep benchmark JSON and metadata even if video rendering fails.

The final demo is allowed to take minutes or hours. It should not claim a real-time cadence unless the measured benchmark supports that claim.

## Video Output

The final presentation artifact is an Eon-style side-by-side video:

- left panel: FlyGym body state;
- right panel: black-background brain activity state;
- layout metadata: `body_left_brain_right`.

The brain panel is generated from telemetry and full backend readouts. It uses a stylized brain-shaped activity view with active feeding/MN9 and grooming/DN readouts highlighted by rate.

## Testing

Implementation uses test-first changes. Required coverage:

- public package exports expose only L4 surfaces;
- legacy staged artifacts are absent;
- `ShiuFullBackend` calls a supplied Shiu module's `create_model`;
- `ShiuFullBackend.handle()` runs a Brian2-style network object and returns `backend="shiu_full"` only when that full path succeeds;
- full-backend failures do not return successful readouts;
- backend selection for `auto` is an alias to `shiu_full`;
- combined-video metadata records `body_left_brain_right`;
- brain-panel generation can produce an output from representative telemetry without requiring FlyGym.

## Documentation

README and L4 docs should say:

- this project uses public Shiu/FlyGym components and project-owned bridge logic;
- it does not reproduce Eon private code;
- L4 output is precomputed for presentation;
- the full Shiu backend is attempted directly and failures are reported honestly;
- no legacy staged workflows remain on this branch.

## Sources

- `external/drosophila_brain_model/Readme.md`
- `external/drosophila_brain_model/model.py`
- `external/drosophila_brain_model/example.ipynb`
- `https://eon.systems/updates/embodied-brain-emulation`
