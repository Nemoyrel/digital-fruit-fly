from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


REQUIRED_TOP_LEVEL_KEYS = {
    "schema_version",
    "generated_at",
    "environment",
    "imports",
    "simulation",
    "locomotion_controller",
    "observation",
    "camera",
    "video",
    "skeleton",
    "actuators",
    "joint_readout",
    "site_positions",
    "fine_action_support",
}


class TestBodyApiProbe(unittest.TestCase):
    def test_baseline_minimal_api_report_lacked_todo8_contract_keys(self) -> None:
        # Given: the pre-Todo-8 embedded smoke report shape.
        legacy_report = {
            "flygym_attrs": ["Renderer", "Simulation"],
            "mujoco_attrs": ["MjData", "MjModel", "Renderer"],
        }

        # When: consumers look for the Todo 8 contract fields.
        missing_keys = REQUIRED_TOP_LEVEL_KEYS.difference(legacy_report)

        # Then: the old report is characterized as incomplete, not silently enough.
        self.assertEqual(missing_keys, REQUIRED_TOP_LEVEL_KEYS)

    def test_api_report_contains_required_contract_and_fine_action_lists(self) -> None:
        # Given: an installed API surface fixture with fine-action DOFs.
        from digital_fruit_fly.body.flygym_api import ApiReportInputs, build_report_from_names

        joint_dofs = (
            "c_head-c_rostrum-pitch",
            "c_rostrum-c_haustellum-pitch",
            "c_head-l_pedicel-yaw",
            "c_head-r_pedicel-yaw",
            "c_thorax-lf_coxa-pitch",
            "lf_coxa-lf_trochanterfemur-roll",
        )

        # When: the report is built from the deterministic installed-name fixture.
        report = build_report_from_names(
            ApiReportInputs(
                joint_dofs=joint_dofs,
                site_names=("c_head-c_rostrum", "c_head-l_pedicel"),
                controller_imports=("flygym_demo.complex_terrain.hybrid_controller.HybridController",),
                flygym_version="2.0.2",
                mujoco_version="3.6.0",
                python_version="3.12.13",
            )
        )

        # Then: the JSON contract has every required section and explicit support lists.
        self.assertTrue(REQUIRED_TOP_LEVEL_KEYS.issubset(report))
        fine_action = report["fine_action_support"]
        self.assertEqual(fine_action["supports_proboscis_control"], True)
        self.assertEqual(
            fine_action["proboscis_dofs"],
            ["c_head-c_rostrum-pitch", "c_rostrum-c_haustellum-pitch"],
        )
        self.assertEqual(fine_action["supports_antenna_control"], True)
        self.assertEqual(
            fine_action["antenna_dofs"],
            ["c_head-l_pedicel-yaw", "c_head-r_pedicel-yaw"],
        )
        self.assertEqual(fine_action["supports_front_leg_face_grooming"], True)
        self.assertEqual(fine_action["supports_site_positions"], True)
        self.assertEqual(report["actuators"]["position_actuator_order"], list(joint_dofs))

    def test_missing_fine_action_dofs_fail_with_exact_phrase(self) -> None:
        # Given: an installed API fixture that lacks proboscis and antenna controls.
        from digital_fruit_fly.body.flygym_api import (
            ApiReportInputs,
            UNSUPPORTED_FINE_ACTION_API,
            UnsupportedFineActionAPI,
            build_report_from_names,
        )

        # When: the report builder validates fine-action support.
        with self.assertRaises(UnsupportedFineActionAPI) as raised:
            build_report_from_names(
                ApiReportInputs(
                    joint_dofs=("c_thorax-lf_coxa-pitch",),
                    site_names=("c_thorax-lf_coxa",),
                    controller_imports=(),
                    flygym_version="2.0.2",
                    mujoco_version="3.6.0",
                    python_version="3.12.13",
                )
            )

        # Then: callers get the required explicit failure phrase.
        self.assertIn(UNSUPPORTED_FINE_ACTION_API, str(raised.exception))

    def test_writes_json_and_markdown_api_artifacts(self) -> None:
        # Given: a complete API report and an output directory.
        from digital_fruit_fly.body.flygym_api import (
            ApiReportInputs,
            build_report_from_names,
        )
        from digital_fruit_fly.body.flygym_api_docs import write_api_artifacts

        report = build_report_from_names(
            ApiReportInputs(
                joint_dofs=(
                    "c_head-c_rostrum-pitch",
                    "c_rostrum-c_haustellum-pitch",
                    "c_head-l_pedicel-yaw",
                    "c_head-r_pedicel-yaw",
                    "c_thorax-lf_coxa-pitch",
                ),
                site_names=("c_head-c_rostrum", "c_head-l_pedicel"),
                controller_imports=("flygym_demo.complex_terrain.hybrid_controller.HybridController",),
                flygym_version="2.0.2",
                mujoco_version="3.6.0",
                python_version="3.12.13",
            )
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "body"
            docs_path = Path(tmp_dir) / "docs" / "flygym_api_probe.md"

            # When: artifacts are written for the smoke surface.
            written = write_api_artifacts(report, output_dir, docs_path)

            # Then: JSON is parseable and docs point to the JSON surface.
            parsed = json.loads(written.json_path.read_text(encoding="utf-8"))
            markdown = written.markdown_path.read_text(encoding="utf-8")
            self.assertEqual(parsed["schema_version"], 1)
            self.assertIn("outputs/smoke/body/flygym_api.json", markdown)
            self.assertIn("Proboscis control: supported", markdown)


if __name__ == "__main__":
    unittest.main()
