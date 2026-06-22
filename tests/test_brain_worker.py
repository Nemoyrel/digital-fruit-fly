from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from digital_fruit_fly.brain_worker import (
    BrainBackendUnavailable,
    BrainWorkerConfig,
    ShiuFullBackend,
    select_backend,
)
from digital_fruit_fly.ipc_protocol import SensoryStateMessage


def make_msg(
    time_s,
    *,
    food_cue=0.0,
    dust_level=0.0,
    dust_threshold=False,
    food_contact=False,
):
    return SensoryStateMessage(
        request_id=1,
        time_s=time_s,
        food_cue=food_cue,
        turn_bias=0.2,
        dust_level=dust_level,
        dust_threshold_reached=dust_threshold,
        food_contact=food_contact,
        food_distance_mm=2.0,
    )


class FakeSpikeMonitor:
    def __init__(self):
        self.trains = {}

    def spike_trains(self):
        return self.trains


class FakeNetwork:
    def __init__(self, *objects):
        self.objects = list(objects)
        self.run_calls = []
        self.store_name = ""
        self.restore_name = ""

    def store(self, name):
        self.store_name = name

    def restore(self, name):
        self.restore_name = name

    def add(self, *objects):
        self.objects.extend(objects)

    def remove(self, *objects):
        for obj in objects:
            if obj in self.objects:
                self.objects.remove(obj)

    def run(self, duration):
        self.run_calls.append(duration)
        monitor = next(obj for obj in self.objects if isinstance(obj, FakeSpikeMonitor))
        monitor.trains = {2: [0.001, 0.002, 0.003], 3: [0.004, 0.005]}


class FakeShiuModule:
    def __init__(self):
        self.default_params = {
            "r_poi": 0,
            "r_poi2": 0,
            "t_run": 0,
            "n_run": 1,
        }
        self.create_model_calls = []
        self.poi_calls = []

    def create_model(self, path_comp, path_con, params):
        self.create_model_calls.append((path_comp, path_con, params))
        return object(), object(), FakeSpikeMonitor()

    def poi(self, neu, exc, exc2, params):
        self.poi_calls.append((exc, exc2, params["r_poi"], params["r_poi2"]))
        return [object()], neu


class BrainWorkerBackendTest(unittest.TestCase):
    def test_shiu_full_backend_builds_reusable_inputs_and_runs_network(self):
        module = FakeShiuModule()
        config = BrainWorkerConfig(
            project_root=PROJECT_ROOT,
            shiu_completeness_csv=PROJECT_ROOT
            / "tests"
            / "fixtures"
            / "fake_completeness.csv",
            shiu_connectivity_parquet=PROJECT_ROOT
            / "tests"
            / "fixtures"
            / "fake_connectivity.parquet",
            sugar_grn_ids=(10,),
            jon_grn_ids=(11,),
            mn9_flywire_id=12,
            grooming_readout_ids=(13,),
        )
        backend = ShiuFullBackend(
            config,
            shiu_module=module,
            network_factory=FakeNetwork,
            flywire_to_index={10: 0, 11: 1, 12: 2, 13: 3},
        )

        response = backend.handle(make_msg(0.1, food_cue=1.0, dust_level=0.5))

        self.assertEqual(len(module.create_model_calls), 1)
        self.assertEqual(module.poi_calls, [])
        self.assertEqual(backend.sugar_input_indices, [0])
        self.assertEqual(backend.jon_input_indices, [1])
        self.assertEqual(backend.reusable_input_update_count, 1)
        self.assertEqual(response.backend, "shiu_full")
        self.assertEqual(response.source, "brain_worker:shiu_full")
        self.assertGreater(response.mn9_rate_hz, 0.0)
        self.assertGreater(response.extra["grooming_rate_hz"], 0.0)
        self.assertEqual(response.extra["reusable_input_updates"], 1)
        self.assertTrue(response.extra["shiu_full_used"])

    def test_shiu_full_backend_reuses_inputs_across_multiple_requests(self):
        module = FakeShiuModule()
        backend = ShiuFullBackend(
            BrainWorkerConfig(
                project_root=PROJECT_ROOT,
                sugar_grn_ids=(10,),
                jon_grn_ids=(11,),
                mn9_flywire_id=12,
                grooming_readout_ids=(13,),
            ),
            shiu_module=module,
            network_factory=FakeNetwork,
            flywire_to_index={10: 0, 11: 1, 12: 2, 13: 3},
        )

        backend.handle(make_msg(0.1, food_cue=1.0, dust_level=0.25))
        backend.handle(make_msg(0.2, food_cue=0.5, dust_level=0.5))

        self.assertEqual(module.poi_calls, [])
        self.assertEqual(backend.reusable_input_update_count, 2)
        self.assertEqual(backend.request_count, 2)
        self.assertEqual(len(backend.net.run_calls), 2)

    def test_shiu_full_backend_failure_does_not_return_success(self):
        class BrokenModule(FakeShiuModule):
            def create_model(self, path_comp, path_con, params):
                raise RuntimeError("boom")

        with self.assertRaises(BrainBackendUnavailable):
            ShiuFullBackend(
                BrainWorkerConfig(project_root=PROJECT_ROOT),
                shiu_module=BrokenModule(),
                network_factory=FakeNetwork,
                flywire_to_index={},
            )

    def test_select_backend_auto_is_full_backend_alias(self):
        module = FakeShiuModule()
        selection = select_backend(
            "auto",
            BrainWorkerConfig(
                project_root=PROJECT_ROOT,
                sugar_grn_ids=(10,),
                jon_grn_ids=(11,),
                mn9_flywire_id=12,
                grooming_readout_ids=(13,),
            ),
            shiu_module=module,
            network_factory=FakeNetwork,
            flywire_to_index={10: 0, 11: 1, 12: 2, 13: 3},
        )

        self.assertEqual(selection.backend_name, "shiu_full")
        self.assertIsInstance(selection.backend, ShiuFullBackend)


if __name__ == "__main__":
    unittest.main()
