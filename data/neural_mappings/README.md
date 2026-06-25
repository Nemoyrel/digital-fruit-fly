# Neural Mappings

This directory documents versioned channel mappings between body/arena signals and the Shiu Brian2 FlyWire index space.

The active mapping file is `configs/brain_mapping.yaml`. It is JSON-compatible YAML so it can be parsed with the Python standard library in normal tests and in `brain_env` smoke runs.

## Resolution Rule

Shiu `model.py` builds Brian neuron indices by reading the completeness CSV with the FlyWire ID as the index and enumerating that index order:

`flywire_id -> enumerate(pd.read_csv(path_comp, index_col=0).index)`

The local validator mirrors that rule with the CSV module and does not import Brian2 or pandas at package import time.

## Curation Status

`sugar_grn` is biologically curated from the Shiu example notebook `neu_sugar` assignment. Todo 6 showed the configured 783 completeness table is missing one of those IDs, while the 630 completeness table resolves all 21 sugar IDs.

`dust_load`, `left_mechanosensory`, `right_mechanosensory`, and all motor readout groups are engineering provisional. Their IDs are resolvable in the Shiu 630 completeness table, but they are not biological claims. Each provisional group is labeled with `provisional: true`, `biologically_curated: false`, and a rationale in the mapping file so downstream code cannot silently treat them as curated channels.

## Validation

Run:

```bash
/opt/miniconda3/envs/brain_env/bin/python scripts/smoke_brain.py --config configs/brain_smoke.yaml --validate-mapping --output outputs/smoke/brain
```

The smoke result fails if any configured FlyWire ID cannot be resolved. Failed channels are reported as unusable with channel names and bad IDs.
