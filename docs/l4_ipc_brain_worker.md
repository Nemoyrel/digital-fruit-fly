# L4 Full Shiu IPC Demo

This branch is L4-only. It generates precomputed presentation artifacts by running the FlyGym body loop in `flygym_env` and the full Shiu Brian2 brain model in `brain_env`.

The two processes exchange `sensory_state -> brain_readout` over this project's TCP JSON-lines protocol. Eon's public article describes a brain/body synchronization loop but does not disclose its transport protocol, so this repository must not describe TCP JSON-lines as Eon's IPC mechanism.

## Brain Backend

The production backend is `shiu_full`.

`shiu_full` imports `external/drosophila_brain_model/model.py`, calls `create_model()`, constructs a Brian2 `Network`, injects request-specific sugar/JON Poisson inputs, runs one configured brain window, and reads out configured FlyWire IDs:

- MN9: `720575940660219265`
- grooming/mechanosensory readouts: DN1/DN2/aBN IDs used in the Shiu figure 5 workflow

There is no production fallback backend on this branch. If full Shiu startup or `Network.run()` fails, the worker reports `brain_worker_failed` metadata and exits nonzero.

## Run Flow

Brain worker:

```bash
/opt/miniconda3/envs/brain_env/bin/python scripts/run_l4_brain_worker.py --backend shiu_full --host 127.0.0.1 --port 8765
```

Embodied loop:

```bash
/opt/miniconda3/envs/flygym_env/bin/python scripts/run_l4_ipc_embodied_demo.py --host 127.0.0.1 --port 8765 --combine-video
```

Worker smoke check:

```bash
/opt/miniconda3/envs/brain_env/bin/python scripts/run_l4_brain_worker.py --backend shiu_full --once-smoke --max-startup-s 0
```

## Outputs

The demo writes to `outputs/l4_ipc_embodied_loop/`:

- body FlyGym video;
- black-background brain activity MP4 or GIF fallback;
- combined side-by-side video with body left and brain right;
- regular telemetry plot;
- IPC telemetry plot;
- telemetry CSV with `ipc_*` fields;
- benchmark JSON with worker latency and combined-video status;
- metadata JSON with config, events, notes, sources, and output paths.

## Interpretation

The full Brian2 model provides neural dynamics and spike/rate readouts. The low-dimensional body command mapping remains project-owned bridge logic. Reports should distinguish those layers clearly.

This is not a fly upload and not a reproduction of Eon's private bridge. It is a public-component integration and precomputed demonstration.
