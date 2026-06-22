import unittest

import _bootstrap  # noqa: F401

import numpy as np

from digital_fruit_fly.brain_backend import BrainWorkerConfig, ShiuFullBackend
from digital_fruit_fly.messages import SensoryStateMessage
from digital_fruit_fly.state import BehaviorState


class FakeEngine:
    """numpy-only 假引擎：把输入 rate 映射到 MN9 / grooming 读出神经元的计数。"""

    def __init__(self, config: BrainWorkerConfig, n_extra: int = 470):
        ids: list[int] = []
        for fid in (
            list(config.sugar_grn_ids)
            + list(config.jon_grn_ids)
            + [config.mn9_flywire_id]
            + list(config.grooming_readout_ids)
        ):
            if fid not in ids:
                ids.append(fid)
        self.flywire_to_index = {fid: i for i, fid in enumerate(ids)}
        self.n_neurons = len(ids) + n_extra
        self.startup_metadata = {"fake": True, "shiu_full_used": False}
        self._config = config

    def run_window(self, *, food_rate_hz: float, dust_rate_hz: float) -> np.ndarray:
        counts = np.zeros(self.n_neurons, dtype=np.int64)
        win = self._config.brain_window_s
        mn9 = self.flywire_to_index[self._config.mn9_flywire_id]
        counts[mn9] = int(round(food_rate_hz * win * 1.5))
        for fid in self._config.grooming_readout_ids:
            counts[self.flywire_to_index[fid]] = int(round(dust_rate_hz * win * 1.5))
        # 一些下游神经元也点亮，便于可视化采样向量非全零
        counts[self.flywire_to_index[self._config.sugar_grn_ids[0]]] = 1 if food_rate_hz > 0 else 0
        return counts


def _make_backend(**overrides):
    cfg = BrainWorkerConfig(brain_window_s=0.02, viz_neuron_count=50, **overrides)
    return ShiuFullBackend(cfg, engine=FakeEngine(cfg))


def _msg(**kw):
    base = dict(
        request_id=1, time_s=0.0, food_cue=0.0, turn_bias=0.0, dust_level=0.0,
        dust_threshold_reached=False, food_contact=False, food_distance_mm=99.0,
    )
    base.update(kw)
    return SensoryStateMessage(**base)


class BrainBackendTest(unittest.TestCase):
    def test_foraging_default(self):
        backend = _make_backend()
        r = backend.handle(_msg())
        self.assertEqual(r.behavior_state, BehaviorState.FORAGING.value)
        self.assertGreater(r.forward_drive, 0.0)

    def test_feeding_score_rises_with_food_cue(self):
        backend = _make_backend()
        low = backend.handle(_msg(food_cue=0.0))
        high = backend.handle(_msg(food_cue=1.0))
        self.assertGreater(high.feeding_score, low.feeding_score)

    def test_food_contact_triggers_feeding_and_stops(self):
        backend = _make_backend()
        r = backend.handle(_msg(food_cue=1.0, food_contact=True))
        self.assertEqual(r.behavior_state, BehaviorState.FEEDING.value)
        self.assertEqual(r.forward_drive, 0.0)

    def test_dust_threshold_triggers_grooming_then_clears(self):
        backend = _make_backend(grooming_duration_s=1.0)
        r1 = backend.handle(_msg(time_s=0.0, dust_level=1.0, dust_threshold_reached=True))
        self.assertEqual(r1.behavior_state, BehaviorState.GROOMING.value)
        self.assertEqual(r1.forward_drive, 0.0)
        # 时长内仍在梳理
        r2 = backend.handle(_msg(time_s=0.5, dust_level=1.0, dust_threshold_reached=True))
        self.assertEqual(r2.behavior_state, BehaviorState.GROOMING.value)
        # 时长后退出，给一次 dust_clearance
        r3 = backend.handle(_msg(time_s=1.6, dust_level=0.0))
        self.assertEqual(r3.behavior_state, BehaviorState.FORAGING.value)
        self.assertEqual(r3.dust_clearance, 1.0)

    def test_time_rewind_resets_fsm_for_new_episode(self):
        # 长驻 worker 复用场景：先进入 FEEDING，再收到一段时间回退的新 episode 请求，
        # 应重置回 FORAGING 并恢复前进驱动（而不是卡在 feeding）。
        backend = _make_backend()
        fed = backend.handle(_msg(time_s=3.0, food_cue=1.0, food_contact=True))
        self.assertEqual(fed.behavior_state, BehaviorState.FEEDING.value)
        new_episode = backend.handle(_msg(time_s=0.05, food_cue=0.0, food_contact=False))
        self.assertEqual(new_episode.behavior_state, BehaviorState.FORAGING.value)
        self.assertGreater(new_episode.forward_drive, 0.0)

    def test_neuron_activity_downsample_length(self):
        backend = _make_backend()  # viz_neuron_count=50
        r = backend.handle(_msg(food_cue=1.0))
        self.assertEqual(len(r.neuron_activity), 50)
        self.assertGreaterEqual(r.active_neuron_count, 1)
        self.assertEqual(r.total_neuron_count, backend.engine.n_neurons)

    def test_viz_bins_are_deterministic(self):
        b1 = _make_backend()
        b2 = _make_backend()
        np.testing.assert_array_equal(b1._viz_bin_starts, b2._viz_bin_starts)


if __name__ == "__main__":
    unittest.main()
