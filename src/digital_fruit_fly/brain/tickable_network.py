from __future__ import annotations

import importlib.util
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Dict, List, Mapping, Protocol, Sequence, Tuple


@dataclass(frozen=True)
class TickableBrainError(Exception):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True)
class UnknownSensoryChannelError(TickableBrainError):
    channel_name: str

    def __init__(self, channel_name: str) -> None:
        super().__init__(f"unknown sensory channel: {channel_name}")
        object.__setattr__(self, "channel_name", channel_name)


@dataclass(frozen=True)
class ChannelConfig:
    name: str
    target_indices: Tuple[int, ...]
    max_rate_hz: float


@dataclass(frozen=True)
class ReadoutConfig:
    name: str
    neuron_indices: Tuple[int, ...]


@dataclass(frozen=True)
class TickableBrainConfig:
    tick_ms: float
    sensory_channels: Tuple[ChannelConfig, ...]
    readout_groups: Tuple[ReadoutConfig, ...]


@dataclass(frozen=True)
class ShiuModelPaths:
    repo_path: Path
    completeness_path: Path
    connectivity_path: Path


@dataclass(frozen=True)
class TickResult:
    tick_index: int
    duration_ms: float
    wall_time_sec: float
    spike_deltas: Dict[str, int]
    rate_hz: Dict[str, float]

    def to_json(self) -> Dict[str, int | float | Dict[str, int] | Dict[str, float]]:
        return {
            "tick_index": self.tick_index,
            "duration_ms": self.duration_ms,
            "wall_time_sec": self.wall_time_sec,
            "spike_deltas": dict(self.spike_deltas),
            "rate_hz": dict(self.rate_hz),
        }


class BrianDuration(Protocol):
    pass


class BrianNetworkMember(Protocol):
    pass


class BrianNetworkRuntime(Protocol):
    def run(self, duration: BrianDuration) -> None:
        pass


class BrianQuantity(Protocol):
    pass


class BrianRateGroup(Protocol):
    rates: BrianQuantity


class BrianSpikeMonitor(Protocol):
    count: Sequence[int]


@dataclass(frozen=True)
class NetworkParts:
    network: BrianNetworkRuntime
    sensory_groups: Mapping[str, BrianRateGroup]
    spike_monitor: BrianSpikeMonitor


@dataclass(frozen=True)
class InputBuildContext:
    brian2: ModuleType
    neurons: BrianNetworkMember
    weight_mv: float


class TickableBrainNetwork:
    """Mutable Brian2 runtime wrapper that advances one configured tick at a time."""

    def __init__(self, config: TickableBrainConfig, parts: NetworkParts) -> None:
        _validate_config(config)
        self._config = config
        self._network = parts.network
        self._sensory_groups = dict(parts.sensory_groups)
        self._spike_monitor = parts.spike_monitor
        self._tick_index = 0
        self._last_counts = {readout.name: 0 for readout in config.readout_groups}

    @property
    def tick_index(self) -> int:
        return self._tick_index

    @classmethod
    def fixture(cls, config: TickableBrainConfig) -> TickableBrainNetwork:
        brian2 = _import_brian2()
        brian2.start_scope()
        brian2.seed(1)
        neurons = brian2.NeuronGroup(
            1,
            "dv/dt = -v / (10*ms) : volt",
            threshold="v > -50*mV",
            reset="v = -65*mV",
            method="euler",
            name="tick_fixture_neurons",
        )
        neurons.v = -65 * brian2.mV
        parts = _attach_inputs_and_monitor(
            InputBuildContext(brian2=brian2, neurons=neurons, weight_mv=20.0),
            config,
        )
        return cls(config, parts)

    @classmethod
    def shiu(cls, config: TickableBrainConfig, paths: ShiuModelPaths) -> TickableBrainNetwork:
        brian2 = _import_brian2()
        shiu_model = _load_shiu_model(paths.repo_path)
        brian2.start_scope()
        params = dict(shiu_model.default_params)
        neurons, synapses, monitor = shiu_model.create_model(
            str(paths.completeness_path),
            str(paths.connectivity_path),
            params,
        )
        groups, input_objects = _build_sensory_groups(
            context=InputBuildContext(
                brian2=brian2,
                neurons=neurons,
                weight_mv=float((params["w_syn"] * params["f_poi"]) / brian2.mV),
            ),
            config=config,
        )
        network = brian2.Network(neurons, synapses, monitor, *input_objects)
        return cls(config, NetworkParts(network=network, sensory_groups=groups, spike_monitor=monitor))

    def tick(self, channel_values: Mapping[str, float]) -> TickResult:
        self._reject_unknown_channels(channel_values)
        self._update_rates(channel_values)
        brian2 = _import_brian2()
        started = time.monotonic()
        self._network.run(self._config.tick_ms * brian2.ms)
        wall_time_sec = time.monotonic() - started
        self._tick_index += 1
        deltas = self._read_spike_deltas()
        return TickResult(
            tick_index=self._tick_index,
            duration_ms=self._config.tick_ms,
            wall_time_sec=wall_time_sec,
            spike_deltas=deltas,
            rate_hz=_rates_from_deltas(deltas, self._config),
        )

    def _reject_unknown_channels(self, channel_values: Mapping[str, float]) -> None:
        validate_sensory_channel_values(self._config, channel_values)

    def _update_rates(self, channel_values: Mapping[str, float]) -> None:
        brian2 = _import_brian2()
        by_name = {channel.name: channel for channel in self._config.sensory_channels}
        for channel_name, group in self._sensory_groups.items():
            channel = by_name[channel_name]
            value = _clip_unit(channel_values.get(channel_name, 0.0))
            group.rates = value * channel.max_rate_hz * brian2.Hz

    def _read_spike_deltas(self) -> Dict[str, int]:
        deltas: Dict[str, int] = {}
        counts = tuple(int(count) for count in self._spike_monitor.count)
        for readout in self._config.readout_groups:
            total = sum(counts[index] for index in readout.neuron_indices)
            previous = self._last_counts[readout.name]
            deltas[readout.name] = total - previous
            self._last_counts[readout.name] = total
        return deltas


def _attach_inputs_and_monitor(
    context: InputBuildContext,
    config: TickableBrainConfig,
) -> NetworkParts:
    groups, input_objects = _build_sensory_groups(context=context, config=config)
    monitor = context.brian2.SpikeMonitor(context.neurons, name="tick_fixture_spikes")
    network = context.brian2.Network(context.neurons, monitor, *input_objects)
    return NetworkParts(network=network, sensory_groups=groups, spike_monitor=monitor)


def _build_sensory_groups(
    context: InputBuildContext,
    config: TickableBrainConfig,
) -> Tuple[Dict[str, BrianRateGroup], Tuple[BrianNetworkMember, ...]]:
    groups: Dict[str, BrianRateGroup] = {}
    input_objects: List[BrianNetworkMember] = []
    for channel in config.sensory_channels:
        group = context.brian2.PoissonGroup(
            len(channel.target_indices),
            rates=0 * context.brian2.Hz,
            name=f"tick_input_{channel.name}",
        )
        synapses = context.brian2.Synapses(
            group,
            context.neurons,
            on_pre=f"v_post += {context.weight_mv}*mV",
            name=f"tick_input_{channel.name}_synapses",
        )
        synapses.connect(i=range(len(channel.target_indices)), j=channel.target_indices)
        groups[channel.name] = group
        input_objects.extend((group, synapses))
    return groups, tuple(input_objects)


def _rates_from_deltas(deltas: Mapping[str, int], config: TickableBrainConfig) -> Dict[str, float]:
    tick_seconds = config.tick_ms / 1000.0
    by_name = {readout.name: readout for readout in config.readout_groups}
    return {
        name: delta / tick_seconds / len(by_name[name].neuron_indices)
        for name, delta in deltas.items()
    }


def validate_sensory_channel_values(
    config: TickableBrainConfig,
    channel_values: Mapping[str, float],
) -> None:
    configured = {channel.name for channel in config.sensory_channels}
    for channel_name in channel_values:
        if channel_name not in configured:
            raise UnknownSensoryChannelError(channel_name)


def _validate_config(config: TickableBrainConfig) -> None:
    if config.tick_ms <= 0.0:
        raise TickableBrainError("tick_ms must be positive")
    if len(config.sensory_channels) == 0:
        raise TickableBrainError("at least one sensory channel is required")
    if len(config.readout_groups) == 0:
        raise TickableBrainError("at least one readout group is required")


def _clip_unit(value: float) -> float:
    if value <= 0.0:
        return 0.0
    if value >= 1.0:
        return 1.0
    return value


def _import_brian2() -> ModuleType:
    os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/digital_fruit_fly_mpl")
    try:
        module = __import__("brian2")
    except ImportError as exc:
        raise TickableBrainError("Brian2 is required inside the brain runtime") from exc
    module.prefs.codegen.target = "numpy"
    return module


def _load_shiu_model(repo_path: Path) -> ModuleType:
    model_path = repo_path / "model.py"
    spec = importlib.util.spec_from_file_location("digital_fruit_fly_shiu_model", model_path)
    if spec is None or spec.loader is None:
        raise TickableBrainError(f"could not load Shiu model from {model_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
