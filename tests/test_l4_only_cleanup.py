from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import digital_fruit_fly


class L4OnlyCleanupTest(unittest.TestCase):
    def test_public_exports_are_l4_only(self):
        forbidden = {
            "run_l" + "1_body_demo",
            "run_l" + "2_embodied_demo",
            "run_l" + "3_embodied_demo",
            "generate_l" + "3_lookup",
            "Rule" + "BrainBridge",
            "Lookup" + "BrainBridge",
            "OnlineLIF" + "BrainBridge",
        }

        self.assertTrue(forbidden.isdisjoint(set(digital_fruit_fly.__all__)))

    def test_l1_l2_l3_artifacts_are_removed(self):
        removed_paths = [
            "scripts/run_l1_flygym_body_demo.py",
            "scripts/run_l2_embodied_demo.py",
            "scripts/run_l3_embodied_demo.py",
            "scripts/generate_l3_brain_lookup.py",
            "scripts/run_l4_embodied_demo.py",
            "configs/l1_body.json",
            "configs/l2_embodied_loop.json",
            "configs/l3_embodied_loop.json",
            "configs/l3_brain_lookup.json",
            "configs/l4_embodied_loop.json",
            "data/l3_brain_readout_lookup.csv",
            "data/l3_brain_readout_lookup_metadata.json",
            "src/digital_fruit_fly/l1_demo.py",
            "src/digital_fruit_fly/l2_demo.py",
            "src/digital_fruit_fly/l3_demo.py",
            "src/digital_fruit_fly/l3_lookup.py",
            "src/digital_fruit_fly/l4_demo.py",
            "src/digital_fruit_fly/l4_online_lif.py",
            "docs/l2_minimal_loop.md",
            "docs/l3_brain_lookup.md",
            "docs/l4_online_lif.md",
            "minimal-eon-embodied-fly-report.html",
            "digital-fruit-fly-research-report.html",
        ]

        existing = [path for path in removed_paths if (PROJECT_ROOT / path).exists()]
        self.assertEqual(existing, [])

    def test_brain_bridge_only_exposes_l4_helpers(self):
        import digital_fruit_fly.brain_bridge as brain_bridge

        self.assertFalse(hasattr(brain_bridge, "Rule" + "BrainBridge"))
        self.assertFalse(hasattr(brain_bridge, "Lookup" + "BrainBridge"))
        self.assertTrue(hasattr(brain_bridge, "readout_to_descending_signal"))


if __name__ == "__main__":
    unittest.main()
