"""Generate compact L3 brain readout lookup tables."""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path
from typing import Any

from .config import (
    L3_LOOKUP_CONFIG_PATH,
    OUTPUT_DIR,
    configure_local_caches,
    load_json_config,
)


def _rate_for_neuron(df, *, flywire_id: int, exp_name: str, t_run_s: float, n_run: int):
    import numpy as np

    rows = df[(df["flywire_id"] == flywire_id) & (df["exp_name"] == exp_name)]
    rates = np.zeros(n_run)
    for trial, trial_rows in rows.groupby("trial"):
        rates[int(trial)] = len(trial_rows) / t_run_s
    return float(rates.mean()), float(rates.std())


def _git_commit(path: Path) -> str | None:
    try:
        return (
            subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"])
            .decode()
            .strip()
        )
    except Exception:
        return None


def _extract_sugar_mn9(config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    import pandas as pd

    source = config["source"]
    repo_path = Path(source["repo_path"])
    mn9_id = int(source["mn9_flywire_id"])
    t_run_s = float(source["example_t_run_s"])
    n_run = int(source["example_n_run"])

    example_files = source["sugar_example_files"]
    frames = []
    for spec in example_files:
        df = pd.read_parquet(repo_path / spec["path"])
        frames.append(df)
    df_spikes = pd.concat(frames, ignore_index=True)

    rates = {}
    stds = {}
    for spec in example_files:
        rate, std = _rate_for_neuron(
            df_spikes,
            flywire_id=mn9_id,
            exp_name=spec["exp_name"],
            t_run_s=t_run_s,
            n_run=n_run,
        )
        rates[spec["exp_name"]] = rate
        stds[spec["exp_name"]] = std

    max_rate = max(rates.values())
    rows = [
        {
            "input_kind": "sugar",
            "input_value": 0.0,
            "stimulus_hz": 0.0,
            "mn9_rate_hz": 0.0,
            "mn9_rate_std_hz": 0.0,
            "grooming_rate_hz": 0.0,
            "feeding_score": 0.0,
            "grooming_score": 0.0,
            "source": "baseline_no_sugar_engineering_anchor",
        }
    ]
    for spec in example_files:
        rate = rates[spec["exp_name"]]
        rows.append(
            {
                "input_kind": "sugar",
                "input_value": float(spec["food_cue"]),
                "stimulus_hz": float(spec["stimulus_hz"]),
                "mn9_rate_hz": rate,
                "mn9_rate_std_hz": stds[spec["exp_name"]],
                "grooming_rate_hz": 0.0,
                "feeding_score": rate / max_rate if max_rate else 0.0,
                "grooming_score": 0.0,
                "source": f"philshiu_example:{spec['exp_name']}",
            }
        )
    rows.sort(key=lambda row: row["input_value"])
    metadata = {
        "mn9_flywire_id": mn9_id,
        "sugar_rates_hz": rates,
        "sugar_rate_std_hz": stds,
        "upstream_commit": _git_commit(repo_path),
    }
    return rows, metadata


def _run_grooming_proxy(config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from brian2 import (
        Hz,
        Network,
        NeuronGroup,
        PoissonInput,
        SpikeMonitor,
        mV,
        ms,
        prefs,
        seed,
        start_scope,
    )

    prefs.codegen.target = "numpy"
    proxy = config["grooming_proxy"]
    duration_s = float(proxy["duration_s"])
    trials = int(proxy["trials"])
    dust_levels = [float(x) for x in proxy["dust_levels"]]
    max_input_hz = float(proxy["max_input_hz"])
    random_seed = int(proxy["seed"])

    eqs = """
    dv/dt = (v_0 - v + g) / t_mbr : volt (unless refractory)
    dg/dt = -g / tau : volt (unless refractory)
    """
    rows = []
    raw_rates = []
    for level in dust_levels:
        trial_rates = []
        for trial in range(trials):
            start_scope()
            seed(random_seed + int(level * 1000) + trial)
            neurons = NeuronGroup(
                1,
                model=eqs,
                method="linear",
                threshold="v > v_th",
                reset="v = v_rst; g = 0 * mV",
                refractory=2.2 * ms,
                namespace={
                    "v_0": -52 * mV,
                    "v_rst": -52 * mV,
                    "v_th": -45 * mV,
                    "t_mbr": 20 * ms,
                    "tau": 5 * ms,
                },
            )
            neurons.v = -52 * mV
            neurons.g = 0 * mV
            poisson = PoissonInput(
                target=neurons[0],
                target_var="v",
                N=1,
                rate=max_input_hz * level * Hz,
                weight=0.275 * mV * 250,
            )
            monitor = SpikeMonitor(neurons)
            net = Network(neurons, poisson, monitor)
            net.run(duration_s * 1000 * ms)
            trial_rates.append(float(monitor.count[0]) / duration_s)
        mean_rate = sum(trial_rates) / len(trial_rates)
        raw_rates.append(mean_rate)
        rows.append(
            {
                "input_kind": "mechanosensory_dust",
                "input_value": level,
                "stimulus_hz": max_input_hz * level,
                "mn9_rate_hz": 0.0,
                "mn9_rate_std_hz": 0.0,
                "grooming_rate_hz": mean_rate,
                "feeding_score": 0.0,
                "grooming_score": 0.0,
                "source": "brian2_lif_grooming_proxy",
            }
        )
    max_rate = max(raw_rates) if raw_rates else 1.0
    for row in rows:
        row["grooming_score"] = row["grooming_rate_hz"] / max_rate if max_rate else 0.0
    return rows, {
        "duration_s": duration_s,
        "trials": trials,
        "max_input_hz": max_input_hz,
        "lif_constants": {
            "v_0_mV": -52.0,
            "v_rst_mV": -52.0,
            "v_th_mV": -45.0,
            "t_mbr_ms": 20.0,
            "tau_ms": 5.0,
            "refractory_ms": 2.2,
            "w_syn_mV": 0.275,
            "f_poi": 250,
        },
        "raw_rates_hz": raw_rates,
        "source_reference": "external/drosophila_brain_model/model.py default_params",
        "note": "Small Brian2 LIF proxy using Shiu-style LIF constants; not a full connectome run.",
    }


def write_lookup(config: dict[str, Any]) -> dict[str, Any]:
    output = config["output"]
    lookup_path = Path(output["lookup_csv"])
    metadata_path = Path(output["metadata_json"])
    report_path = Path(output["report_json"])
    configure_local_caches(OUTPUT_DIR / "l3_brain")

    sugar_rows, sugar_metadata = _extract_sugar_mn9(config)
    grooming_rows, grooming_metadata = _run_grooming_proxy(config)
    rows = sugar_rows + grooming_rows

    lookup_path.parent.mkdir(parents=True, exist_ok=True)
    with lookup_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    metadata = {
        "level": "L3",
        "description": "Compact offline brain readout table for embodied demo.",
        "lookup_csv": str(lookup_path),
        "sugar_mn9": sugar_metadata,
        "grooming_proxy": grooming_metadata,
        "sources": [
            "external/drosophila_brain_model/Readme.md",
            "external/drosophila_brain_model/example.ipynb",
            "external/drosophila_brain_model/model.py",
            "external/drosophila_brain_model/results/example/*.parquet",
            "https://doi.org/10.17617/3.CZODIW",
        ],
        "boundary": [
            "Sugar/MN9 rows are derived from philshiu/Drosophila_brain_model example spike parquet files.",
            "Mechanosensory dust/grooming rows are a small Brian2 LIF proxy using Shiu-style constants, not the full connectome model.",
            "This table is a compact engineering bridge for L3, not a full brain upload or Eon private-code reproduction.",
        ],
    }
    for path in (metadata_path, report_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            json.dump(metadata, f, indent=2)
    return {
        "lookup_csv": lookup_path,
        "metadata_json": metadata_path,
        "report_json": report_path,
        "rows": rows,
    }


def generate_l3_lookup() -> dict[str, Any]:
    return write_lookup(load_json_config(L3_LOOKUP_CONFIG_PATH))
