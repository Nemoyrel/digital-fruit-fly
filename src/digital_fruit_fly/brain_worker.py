"""Brain worker backends and TCP server for L4 IPC demos."""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
import json
from pathlib import Path
import shutil
import socket
import threading
from time import perf_counter
from typing import Any, Callable

from .brain_bridge import _clip
from .ipc_protocol import (
    BrainReadoutMessage,
    SensoryStateMessage,
    decode_message,
    encode_message,
)
from .state import BehaviorState


SHIU_SUGAR_GRN_IDS = (
    720575940624963786,
    720575940630233916,
    720575940637568838,
    720575940638202345,
    720575940617000768,
    720575940630797113,
    720575940632889389,
    720575940621754367,
    720575940621502051,
    720575940640649691,
    720575940639332736,
    720575940616885538,
    720575940639198653,
    720575940620900446,
    720575940617937543,
    720575940632425919,
    720575940633143833,
    720575940612670570,
    720575940628853239,
    720575940629176663,
    720575940611875570,
)

SHIU_JON_GRN_IDS = (
    720575940619341105,
    720575940630122015,
    720575940611061526,
    720575940615848788,
    720575940628444667,
    720575940627941431,
    720575940632449619,
    720575940650244342,
    720575940631866508,
    720575940638681845,
    720575940628978450,
    720575940609522461,
    720575940621442224,
    720575940602506208,
    720575940629022149,
    720575940627109991,
    720575940630020111,
    720575940615986459,
    720575940618684481,
    720575940620382889,
    720575940630080071,
    720575940626565455,
    720575940630319671,
    720575940602720940,
    720575940630564179,
    720575940637632419,
    720575940615809349,
    720575940626042149,
    720575940637054835,
    720575940602132509,
    720575940614188149,
    720575940616951124,
    720575940628101126,
    720575940629055721,
    720575940616589878,
    720575940622449388,
    720575940614427195,
    720575940625797617,
    720575940638664437,
    720575940618467195,
    720575940621729757,
    720575940613971485,
    720575940627585688,
    720575940629650997,
    720575940630059847,
    720575940608742409,
    720575940614351477,
    720575940633153375,
    720575940622937528,
    720575940604753437,
    720575940611783464,
    720575940618599872,
    720575940609541917,
    720575940637410869,
    720575940630070343,
    720575940621397417,
    720575940614035485,
    720575940610018266,
    720575940626307902,
    720575940634634606,
    720575940614060829,
    720575940624799290,
    720575940641921421,
    720575940623298559,
    720575940625559358,
    720575940629138959,
    720575940621625597,
    720575940625962568,
    720575940632767383,
    720575940624915230,
    720575940606239243,
    720575940626956777,
    720575940604973746,
    720575940622222856,
    720575940642517284,
    720575940629719404,
    720575940616613022,
    720575940604299454,
    720575940615473186,
    720575940622217992,
    720575940606800341,
    720575940629267498,
    720575940637366335,
    720575940624224408,
    720575940609543197,
    720575940633364179,
    720575940629502009,
    720575940606431189,
    720575940625733960,
    720575940638529525,
    720575940617524053,
    720575940628935564,
    720575940624308355,
    720575940631170346,
    720575940627704375,
    720575940625885512,
    720575940614929245,
    720575940647493241,
    720575940618888368,
    720575940625087546,
    720575940606657493,
    720575940617273560,
    720575940640591861,
    720575940639410035,
    720575940621532413,
    720575940627523584,
    720575940621521917,
    720575940621097398,
    720575940625915338,
    720575940606222428,
    720575940627868471,
    720575940622179497,
    720575940608297774,
    720575940614026269,
    720575940613012959,
    720575940628100614,
    720575940606611401,
    720575940628649465,
    720575940610008217,
    720575940623791152,
    720575940625571240,
    720575940634923621,
    720575940609530653,
    720575940635968745,
    720575940625703434,
    720575940613105311,
    720575940629386819,
    720575940623077389,
    720575940625763015,
    720575940628359017,
    720575940630834171,
    720575940622892988,
    720575940621289537,
    720575940641395163,
    720575940616064546,
    720575940628978409,
    720575940652566177,
    720575940627493096,
    720575940619085397,
    720575940635545310,
    720575940645728803,
    720575940629141775,
    720575940626557995,
    720575940631098338,
    720575940639904475,
    720575940635067034,
)

SHIU_GROOMING_READOUT_IDS = (
    720575940616185531,
    720575940629806974,
    720575940630907434,
)


class BrainBackendUnavailable(RuntimeError):
    """Raised when the required full Shiu backend cannot start or run."""

    def __init__(self, stage: str, reason: str, metadata: dict[str, Any] | None = None):
        super().__init__(f"{stage}: {reason}")
        self.stage = stage
        self.reason = reason
        self.metadata = metadata or {}


@dataclass(frozen=True)
class BrainWorkerConfig:
    """Runtime configuration for the L4 full Shiu brain worker."""

    brain_window_s: float = 0.015
    grooming_duration_s: float = 1.0
    feeding_hold_s: float = 0.8
    max_turn_drive: float = 0.55
    search_turn_gain: float = 0.75
    min_forward_drive: float = 0.12
    max_forward_drive: float = 1.35
    max_startup_s: float = 0.0
    project_root: Path = field(
        default_factory=lambda: Path(__file__).resolve().parents[2]
    )
    shiu_repo_path: Path | None = None
    shiu_completeness_csv: Path | None = None
    shiu_connectivity_parquet: Path | None = None
    sugar_grn_ids: tuple[int, ...] = SHIU_SUGAR_GRN_IDS
    jon_grn_ids: tuple[int, ...] = SHIU_JON_GRN_IDS
    mn9_flywire_id: int = 720575940660219265
    grooming_readout_ids: tuple[int, ...] = SHIU_GROOMING_READOUT_IDS
    food_max_rate_hz: float = 150.0
    dust_max_rate_hz: float = 220.0
    feeding_rate_norm_hz: float = 100.0
    grooming_rate_norm_hz: float = 100.0


@dataclass(frozen=True)
class BackendSelection:
    """Selected backend and performance/environment metadata."""

    backend_name: str
    backend: Any
    metadata: dict[str, Any]


def _brain2_environment_metadata() -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "compiler_available": any(
            shutil.which(name) for name in ("clang", "gcc", "g++")
        ),
    }
    try:
        import brian2
        from brian2 import prefs

        metadata["brian2_version"] = brian2.__version__
        if metadata["compiler_available"]:
            try:
                prefs.codegen.target = "cython"
            except Exception:
                prefs.codegen.target = "numpy"
        metadata["codegen_target"] = str(prefs.codegen.target)
    except Exception as exc:
        metadata["brian2_version"] = None
        metadata["codegen_target"] = "unavailable"
        metadata["brian2_error"] = repr(exc)
    return metadata


class ShiuFullBackend:
    """Full Shiu Brian2 model backend for precomputed L4 demo runs."""

    backend_name = "shiu_full"

    def __init__(
        self,
        config: BrainWorkerConfig,
        *,
        shiu_module: Any | None = None,
        network_factory: Callable[..., Any] | None = None,
        flywire_to_index: dict[int, int] | None = None,
    ) -> None:
        self.config = config
        self.behavior_state = BehaviorState.FORAGING
        self.state_until_s = 0.0
        self.request_count = 0
        self.metadata = _brain2_environment_metadata()
        self.repo_path = config.shiu_repo_path or (
            config.project_root / "external" / "drosophila_brain_model"
        )
        self.path_comp = config.shiu_completeness_csv or (
            self.repo_path / "2023_03_23_completeness_630_final.csv"
        )
        self.path_con = config.shiu_connectivity_parquet or (
            self.repo_path / "2023_03_23_connectivity_630_final.parquet"
        )
        self._injected = shiu_module is not None or network_factory is not None
        self.shiu_module = shiu_module
        self.network_factory = network_factory
        self.flywire_to_index = flywire_to_index
        self.startup_wall_time_s = 0.0
        self._startup()

    def _fail(self, stage: str, reason: str) -> None:
        metadata = {
            **self.metadata,
            "stage": stage,
            "reason": reason,
            "shiu_full_attempted": True,
            "shiu_full_used": False,
            "shiu_repo_path": str(self.repo_path),
            "shiu_completeness_csv": str(self.path_comp),
            "shiu_connectivity_parquet": str(self.path_con),
            "startup_wall_time_s": self.startup_wall_time_s,
        }
        raise BrainBackendUnavailable(stage, reason, metadata)

    def _startup(self) -> None:
        started = perf_counter()
        try:
            if self.shiu_module is None:
                self._check_required_files()
                self.shiu_module = self._import_shiu_module()
            if self.network_factory is None:
                self.network_factory = self._default_network_factory()
            if self.flywire_to_index is None:
                self.flywire_to_index = self._load_flywire_to_index()

            self.params = dict(self.shiu_module.default_params)
            self.params["n_run"] = 1
            self.params["t_run"] = self.config.brain_window_s * 1000.0 * self._ms_unit()
            self.neu, self.syn, self.spk_mon = self.shiu_module.create_model(
                self.path_comp,
                self.path_con,
                self.params,
            )
            self.net = self.network_factory(self.neu, self.syn, self.spk_mon)
            self.net.store("baseline")
        except BrainBackendUnavailable:
            raise
        except Exception as exc:
            self.startup_wall_time_s = perf_counter() - started
            self._fail("startup", repr(exc))
        self.startup_wall_time_s = perf_counter() - started
        if (
            self.config.max_startup_s > 0
            and self.startup_wall_time_s > self.config.max_startup_s
        ):
            self._fail(
                "startup_budget",
                f"startup took {self.startup_wall_time_s:.3f}s",
            )
        self.metadata.update(
            {
                "shiu_full_attempted": True,
                "shiu_full_used": True,
                "startup_wall_time_s": self.startup_wall_time_s,
                "shiu_repo_path": str(self.repo_path),
                "shiu_completeness_csv": str(self.path_comp),
                "shiu_connectivity_parquet": str(self.path_con),
            }
        )

    def _check_required_files(self) -> None:
        missing = [
            str(path)
            for path in (self.repo_path / "model.py", self.path_comp, self.path_con)
            if not path.exists()
        ]
        if missing:
            self._fail("file_check", f"missing Shiu model files: {missing}")

    def _import_shiu_module(self) -> Any:
        model_path = self.repo_path / "model.py"
        spec = importlib.util.spec_from_file_location("shiu_drosophila_model", model_path)
        if spec is None or spec.loader is None:
            self._fail("import_shiu", f"cannot import {model_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _default_network_factory(self) -> Callable[..., Any]:
        try:
            from brian2 import Network
        except Exception as exc:
            self._fail("import_brian2_network", repr(exc))
        return Network

    def _load_flywire_to_index(self) -> dict[int, int]:
        try:
            import pandas as pd

            df_comp = pd.read_csv(self.path_comp, index_col=0)
        except Exception as exc:
            self._fail("load_completeness", repr(exc))
        return {int(flywire_id): idx for idx, flywire_id in enumerate(df_comp.index)}

    def _ms_unit(self):
        if self._injected:
            return 1.0
        try:
            from brian2 import ms
        except Exception as exc:
            self._fail("import_brian2_ms", repr(exc))
        return ms

    def _hz_unit(self):
        if self._injected:
            return 1.0
        try:
            from brian2 import Hz
        except Exception as exc:
            self._fail("import_brian2_hz", repr(exc))
        return Hz

    def _indices(self, flywire_ids: tuple[int, ...]) -> list[int]:
        assert self.flywire_to_index is not None
        indices = [
            self.flywire_to_index[flywire_id]
            for flywire_id in flywire_ids
            if flywire_id in self.flywire_to_index
        ]
        if not indices:
            self._fail("flywire_mapping", f"no configured IDs found in model: {flywire_ids}")
        return indices

    def _rate_for_ids(self, spike_trains: dict[Any, Any], flywire_ids: tuple[int, ...]) -> float:
        assert self.flywire_to_index is not None
        rates = []
        for flywire_id in flywire_ids:
            brian_index = self.flywire_to_index.get(flywire_id)
            if brian_index is None:
                continue
            spikes = spike_trains.get(brian_index, [])
            rates.append(len(spikes) / self.config.brain_window_s)
        if not rates:
            return 0.0
        return float(sum(rates) / len(rates))

    def _run_full_window(self, message: SensoryStateMessage) -> tuple[float, float, dict[str, float]]:
        assert self.shiu_module is not None
        self.net.restore("baseline")
        params = dict(self.params)
        hz = self._hz_unit()
        params["r_poi"] = self.config.food_max_rate_hz * message.food_cue * hz
        params["r_poi2"] = self.config.dust_max_rate_hz * message.dust_level * hz
        exc = self._indices(self.config.sugar_grn_ids)
        exc2 = self._indices(self.config.jon_grn_ids)
        poisson_inputs, self.neu = self.shiu_module.poi(self.neu, exc, exc2, params)
        self.net.add(*poisson_inputs)
        try:
            self.net.run(params["t_run"])
            spike_trains = self.spk_mon.spike_trains()
        finally:
            self.net.remove(*poisson_inputs)

        mn9_rate = self._rate_for_ids(spike_trains, (self.config.mn9_flywire_id,))
        grooming_rate = self._rate_for_ids(spike_trains, self.config.grooming_readout_ids)
        target_rates = {
            "mn9": mn9_rate,
            "grooming_mean": grooming_rate,
        }
        return mn9_rate, grooming_rate, target_rates

    def _state_readout(
        self,
        message: SensoryStateMessage,
        *,
        feeding_score: float,
        grooming_score: float,
        mn9_rate_hz: float,
        dust_clearance: float,
    ) -> tuple[str, float, float]:
        if self.behavior_state == BehaviorState.GROOMING:
            return BehaviorState.GROOMING.value, 0.0, 0.0
        if self.behavior_state == BehaviorState.FEEDING:
            return BehaviorState.FEEDING.value, 0.0, 0.0

        forward_drive = 0.72 + 0.4 * feeding_score - 0.12 * grooming_score
        if message.food_cue <= 0.0:
            turn_drive = message.turn_bias * self.config.search_turn_gain
        else:
            turn_drive = message.turn_bias * (0.25 + 0.75 * feeding_score)
        if dust_clearance:
            turn_drive = 0.0
        return (
            BehaviorState.FORAGING.value,
            _clip(
                forward_drive,
                self.config.min_forward_drive,
                self.config.max_forward_drive,
            ),
            _clip(turn_drive, -self.config.max_turn_drive, self.config.max_turn_drive),
        )

    def handle(self, message: SensoryStateMessage) -> BrainReadoutMessage:
        start = perf_counter()
        self.request_count += 1
        try:
            mn9_rate, grooming_rate, target_rates = self._run_full_window(message)
        except BrainBackendUnavailable:
            raise
        except Exception as exc:
            self._fail("network_run", repr(exc))

        feeding_score = _clip(mn9_rate / self.config.feeding_rate_norm_hz, 0.0, 1.0)
        grooming_score = _clip(
            grooming_rate / self.config.grooming_rate_norm_hz,
            0.0,
            1.0,
        )

        dust_clearance = 0.0
        if (
            self.behavior_state == BehaviorState.GROOMING
            and message.time_s >= self.state_until_s
        ):
            self.behavior_state = BehaviorState.FORAGING
            self.state_until_s = 0.0
            dust_clearance = 1.0
            grooming_score = 0.0
        elif self.behavior_state == BehaviorState.GROOMING:
            pass
        elif message.dust_threshold_reached:
            self.behavior_state = BehaviorState.GROOMING
            self.state_until_s = message.time_s + self.config.grooming_duration_s
        elif message.food_contact:
            self.behavior_state = BehaviorState.FEEDING
            self.state_until_s = max(
                self.state_until_s,
                message.time_s + self.config.feeding_hold_s,
            )
        elif message.time_s >= self.state_until_s:
            self.behavior_state = BehaviorState.FORAGING

        behavior, forward_drive, turn_bias = self._state_readout(
            message,
            feeding_score=feeding_score,
            grooming_score=grooming_score,
            mn9_rate_hz=mn9_rate,
            dust_clearance=dust_clearance,
        )
        wall_ms = (perf_counter() - start) * 1000.0
        return BrainReadoutMessage(
            request_id=message.request_id,
            behavior_state=behavior,
            forward_drive=forward_drive,
            turn_bias=turn_bias,
            grooming_score=grooming_score,
            feeding_score=feeding_score,
            mn9_rate_hz=mn9_rate,
            dust_clearance=dust_clearance,
            source="brain_worker:shiu_full",
            backend=self.backend_name,
            brain_wall_time_ms=wall_ms,
            brain_simulated_window_s=self.config.brain_window_s,
            cache_hit=False,
            extra={
                "grooming_rate_hz": grooming_rate,
                "target_rates_hz": target_rates,
                "request_count": self.request_count,
                "brain_window_s": self.config.brain_window_s,
                "shiu_full_attempted": True,
                "shiu_full_used": True,
                **self.metadata,
            },
        )


def select_backend(
    name: str,
    config: BrainWorkerConfig,
    *,
    shiu_module: Any | None = None,
    network_factory: Callable[..., Any] | None = None,
    flywire_to_index: dict[int, int] | None = None,
) -> BackendSelection:
    """Select the full Shiu backend; auto is an alias, not a fallback."""
    if name not in {"auto", "shiu_full"}:
        raise ValueError(f"Unknown brain worker backend: {name}")
    backend = ShiuFullBackend(
        config,
        shiu_module=shiu_module,
        network_factory=network_factory,
        flywire_to_index=flywire_to_index,
    )
    return BackendSelection("shiu_full", backend, dict(backend.metadata))


class L4BrainWorkerServer:
    """Minimal blocking TCP JSON-lines server for brain worker requests."""

    def __init__(self, *, host: str, port: int, backend: Any) -> None:
        self.host = host
        self.port = port
        self.backend = backend
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def bound_port(self) -> int:
        if self._sock is None:
            return self.port
        return int(self._sock.getsockname()[1])

    def serve_forever(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))
            sock.listen()
            sock.settimeout(0.1)
            self._sock = sock
            while not self._stop.is_set():
                try:
                    conn, _addr = sock.accept()
                except TimeoutError:
                    continue
                with conn:
                    raw = conn.makefile("rb").readline()
                    if not raw:
                        continue
                    request = decode_message(raw)
                    if not isinstance(request, SensoryStateMessage):
                        continue
                    conn.sendall(encode_message(self.backend.handle(request)))

    def serve_background(self) -> threading.Thread:
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()
        return self._thread

    def shutdown(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                with socket.create_connection((self.host, self.bound_port), timeout=0.1):
                    pass
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1.0)


def smoke_response(backend_name: str, config: BrainWorkerConfig) -> dict[str, Any]:
    """Return one synthetic backend response as plain JSON-compatible data."""
    selection = select_backend(backend_name, config)
    message = SensoryStateMessage(
        request_id=1,
        time_s=0.0,
        food_cue=1.0,
        turn_bias=0.0,
        dust_level=0.0,
        dust_threshold_reached=False,
        food_contact=True,
        food_distance_mm=0.5,
    )
    response = selection.backend.handle(message)
    return {
        "selection": {
            "backend_name": selection.backend_name,
            "metadata": selection.metadata,
        },
        "response": json.loads(encode_message(response).decode("utf-8")),
    }
