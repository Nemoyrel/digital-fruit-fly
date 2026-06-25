from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from digital_fruit_fly.arena.model import (
    ArenaDimensions,
    ArenaGeometry,
    CueSensorGeometry,
    FoodSource,
    Point2D,
)


API_REPORT_PATH = REPO_ROOT / "outputs" / "smoke" / "body" / "flygym_api.json"


class TestBodyObservations(unittest.TestCase):
    def test_serializes_fine_action_fixture_from_current_api_report(self) -> None:
        # Given: the current Todo 8 FlyGym API report and a primitive readout fixture.
        from digital_fruit_fly.body.observations import (
            BodyObservationRequest,
            build_observation_contract,
            normalize_body_observation,
            observation_to_json,
        )

        api_report = _load_api_report()
        contract = build_observation_contract(api_report)
        raw = _raw_fixture(contract)
        arena = _arena()

        # When: the adapter normalizes the primitive FlyGym readout surface.
        normalized = normalize_body_observation(
            BodyObservationRequest(raw=raw, contract=contract, arena=arena)
        )
        encoded = observation_to_json(normalized)
        payload = json.loads(encoded)

        # Then: JSON is stdlib-compatible and exposes named fine-action observables.
        self.assertEqual(payload["pose"]["x_mm"], 10.0)
        self.assertAlmostEqual(payload["food_relative"]["bearing_rad"], math.atan2(4.0, 3.0))
        self.assertAlmostEqual(payload["food_relative"]["elevation_rad"], math.atan2(-1.0, 5.0))
        self.assertAlmostEqual(payload["food_relative"]["distance_mm"], math.sqrt(26.0))
        self.assertFalse(payload["food_contact"])
        self.assertEqual(
            set(payload["joint_angles"]["proboscis"]),
            set(contract.proboscis_dofs),
        )
        self.assertEqual(set(payload["joint_angles"]["antenna"]), set(contract.antenna_dofs))
        self.assertEqual(
            set(payload["joint_angles"]["front_leg"]),
            set(contract.front_leg_dofs),
        )
        self.assertEqual(set(payload["joint_angles"]["head"]), set(contract.head_dofs))
        self.assertGreater(len(payload["site_positions"]), 0)
        json.dumps(payload, allow_nan=False, sort_keys=True)

    def test_missing_proboscis_field_raises_typed_error_when_api_reports_support(self) -> None:
        # Given: API support for proboscis controls but one configured angle is absent.
        from digital_fruit_fly.body.observations import (
            BodyObservationRequest,
            MissingObservationField,
            build_observation_contract,
            normalize_body_observation,
        )

        contract = build_observation_contract(_load_api_report())
        raw = _raw_fixture(contract)
        joint_angles = dict(raw["joint_angles"])
        missing = contract.proboscis_dofs[0]
        del joint_angles[missing]
        raw["joint_angles"] = joint_angles

        # When / Then: the adapter rejects the malformed fixture with a typed error.
        with self.assertRaises(MissingObservationField) as raised:
            normalize_body_observation(
                BodyObservationRequest(raw=raw, contract=contract, arena=_arena())
            )
        self.assertEqual(raised.exception.category, "proboscis_joint_angles")
        self.assertEqual(raised.exception.missing, (missing,))

    def test_missing_antenna_field_raises_typed_error_when_api_reports_support(self) -> None:
        # Given: API support for antenna controls but one configured angle is absent.
        from digital_fruit_fly.body.observations import (
            BodyObservationRequest,
            MissingObservationField,
            build_observation_contract,
            normalize_body_observation,
        )

        contract = build_observation_contract(_load_api_report())
        raw = _raw_fixture(contract)
        joint_angles = dict(raw["joint_angles"])
        missing = contract.antenna_dofs[0]
        del joint_angles[missing]
        raw["joint_angles"] = joint_angles

        # When / Then: the adapter rejects the malformed fixture with a typed error.
        with self.assertRaises(MissingObservationField) as raised:
            normalize_body_observation(
                BodyObservationRequest(raw=raw, contract=contract, arena=_arena())
            )
        self.assertEqual(raised.exception.category, "antenna_joint_angles")
        self.assertEqual(raised.exception.missing, (missing,))


def _load_api_report() -> dict[str, object]:
    return json.loads(API_REPORT_PATH.read_text(encoding="utf-8"))


def _raw_fixture(contract: object) -> dict[str, object]:
    joint_names = contract.joint_dof_order
    site_names = contract.site_order
    return {
        "pose": {"x_mm": 10.0, "y_mm": 10.0, "z_mm": 1.0, "yaw_rad": 0.0},
        "joint_angles": {name: index / 100.0 for index, name in enumerate(joint_names)},
        "joint_velocities": {name: index / 1000.0 for index, name in enumerate(joint_names)},
        "site_positions": {
            name: [float(index), float(index) + 0.5, float(index) + 1.0]
            for index, name in enumerate(site_names)
        },
        "ground_contact": {"lf_tarsus5": 1.0, "rf_tarsus5": 0.0},
        "bodysegment_contact_forces": {
            "lf_tarsus5": [0.0, 0.0, 2.0],
            "rf_tarsus5": [0.0, 0.0, 0.5],
        },
        "dust": {"dust_load": 0.25, "threshold_crossed": False},
    }


def _arena() -> ArenaGeometry:
    return ArenaGeometry(
        dimensions=ArenaDimensions(width_mm=60.0, height_mm=40.0),
        food=FoodSource(center=Point2D(x_mm=13.0, y_mm=14.0), radius_mm=2.0, cue_radius_mm=9.0),
        cue_sensors=CueSensorGeometry(lateral_offset_mm=0.75, forward_offset_mm=0.5),
    )


if __name__ == "__main__":
    unittest.main()
