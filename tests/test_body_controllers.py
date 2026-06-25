from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from digital_fruit_fly.bridge.messages import (
    SCHEMA_VERSION,
    ControlFrame,
    payload_checksum,
)
from digital_fruit_fly.runtime.timeouts import JsonValue


API_REPORT_PATH = REPO_ROOT / "outputs" / "smoke" / "body" / "flygym_api.json"


class TestBodyControllers(unittest.TestCase):
    def test_locomotion_control_frame_maps_to_forward_turning_target(self) -> None:
        # Given: a decoded brain control frame selecting walking and right turn bias.
        from digital_fruit_fly.body.controllers import (
            BodyControllerRequest,
            ControllerMode,
            build_controller_contract,
            decoded_control_from_frame,
            select_body_command,
        )

        control = decoded_control_from_frame(_control_frame({"forward": 0.8, "turn_bias": -0.35}))

        # When: the body adapter translates the decoded frame.
        command = select_body_command(
            BodyControllerRequest(control=control, contract=build_controller_contract(_load_api_report()))
        )

        # Then: locomotion is selected from the brain frame, with installed controller metadata.
        self.assertEqual(command.mode, ControllerMode.LOCOMOTION)
        self.assertAlmostEqual(command.locomotion.forward_intensity, 0.8)
        self.assertAlmostEqual(command.locomotion.turn_bias, -0.35)
        self.assertFalse(command.locomotion.brake)
        self.assertIn("HybridTurningController", command.locomotion.controller_import_path)
        self.assertEqual(command.audit["selection"]["selected_mode"], "locomotion")

    def test_changing_food_relative_bearing_changes_proboscis_target_sign(self) -> None:
        # Given: two feeding frames with opposite food-relative bearing.
        from digital_fruit_fly.body.controllers import (
            BodyControllerRequest,
            ControllerMode,
            build_controller_contract,
            decoded_control_from_frame,
            select_body_command,
        )

        contract = build_controller_contract(_load_api_report())
        positive = decoded_control_from_frame(
            _control_frame(_feeding_payload(bearing_rad=0.42, elevation_rad=-0.08))
        )
        negative = decoded_control_from_frame(
            _control_frame(_feeding_payload(bearing_rad=-0.42, elevation_rad=-0.08))
        )

        # When: each frame is translated into actuator targets.
        positive_command = select_body_command(BodyControllerRequest(control=positive, contract=contract))
        negative_command = select_body_command(BodyControllerRequest(control=negative, contract=contract))

        # Then: the proboscis yaw target follows the bearing sign.
        yaw_name = "c_head-c_rostrum-yaw"
        self.assertEqual(positive_command.mode, ControllerMode.FEEDING)
        self.assertGreater(positive_command.actuator_targets[yaw_name], 0.0)
        self.assertLess(negative_command.actuator_targets[yaw_name], 0.0)
        self.assertEqual(
            positive_command.audit["feeding"]["target_proboscis_direction"]["yaw_sign"],
            "positive",
        )
        self.assertEqual(
            negative_command.audit["feeding"]["target_proboscis_direction"]["yaw_sign"],
            "negative",
        )

    def test_face_grooming_targets_front_legs_antennae_and_logs_distance(self) -> None:
        # Given: a brain frame selecting face grooming and feedback distances.
        from digital_fruit_fly.body.controllers import (
            BodyControllerFeedback,
            BodyControllerRequest,
            ControllerMode,
            build_controller_contract,
            decoded_control_from_frame,
            select_body_command,
        )

        control = decoded_control_from_frame(_control_frame({"grooming": 0.9, "sweep_phase": 0.25}))
        feedback = BodyControllerFeedback(face_distance_mm=0.7, antenna_distance_mm=0.4)

        # When: the grooming primitive is generated.
        command = select_body_command(
            BodyControllerRequest(
                control=control,
                contract=build_controller_contract(_load_api_report()),
                feedback=feedback,
            )
        )

        # Then: it drives front legs, antennae, and logs target vs measured distances.
        self.assertEqual(command.mode, ControllerMode.GROOMING)
        self.assertTrue(any("-lf_" in name or "-rf_" in name for name in command.actuator_targets))
        self.assertTrue(any("pedicel" in name or "funiculus" in name for name in command.actuator_targets))
        self.assertAlmostEqual(command.audit["grooming"]["target_face_distance_mm"], 0.25)
        self.assertAlmostEqual(command.audit["grooming"]["measured_face_distance_mm"], 0.7)
        self.assertAlmostEqual(command.audit["grooming"]["measured_antenna_distance_mm"], 0.4)

    def test_stop_control_frame_brakes_and_zeroes_actuator_targets(self) -> None:
        # Given: a stop signal conflicting with forward locomotion.
        from digital_fruit_fly.body.controllers import (
            BodyControllerRequest,
            ControllerMode,
            build_controller_contract,
            decoded_control_from_frame,
            select_body_command,
        )

        control = decoded_control_from_frame(_control_frame({"forward": 1.0, "stop": 1.0}))

        # When: priorities are applied.
        command = select_body_command(
            BodyControllerRequest(control=control, contract=build_controller_contract(_load_api_report()))
        )

        # Then: stop wins, brakes locomotion, and emits zero position targets.
        self.assertEqual(command.mode, ControllerMode.STOP)
        self.assertTrue(command.locomotion.brake)
        self.assertGreater(len(command.actuator_targets), 0)
        self.assertTrue(all(value == 0.0 for value in command.actuator_targets.values()))
        self.assertEqual(command.audit["selection"]["selected_mode"], "stop")

    def test_arena_state_alone_cannot_select_feed_or_groom_mode(self) -> None:
        # Given: food and dust cues without decoded feeding or grooming intensity.
        from digital_fruit_fly.body.controllers import (
            ArenaControllerSignals,
            BodyControllerRequest,
            ControllerMode,
            FoodDirection,
            build_controller_contract,
            decoded_control_from_frame,
            select_body_command,
        )

        control = decoded_control_from_frame(_control_frame({"forward": 0.0}))
        arena = ArenaControllerSignals(
            food_contact=True,
            dust_load=1.0,
            food_direction=FoodDirection(bearing_rad=0.3, elevation_rad=-0.1, distance_mm=2.0),
        )

        # When: the body adapter selects a mode.
        command = select_body_command(
            BodyControllerRequest(
                control=control,
                contract=build_controller_contract(_load_api_report()),
                arena=arena,
            )
        )

        # Then: mode selection stays driven by decoded control, not arena state.
        self.assertEqual(command.mode, ControllerMode.STOP)
        self.assertEqual(command.audit["selection"]["arena_state_used_for_mode"], False)

    def test_feed_groom_conflict_uses_configured_priority_and_logs_tie_break(self) -> None:
        # Given: feeding and grooming intensities both exceed threshold.
        from digital_fruit_fly.body.controllers import (
            BodyControllerRequest,
            ControllerMode,
            ControllerPriority,
            build_controller_contract,
            decoded_control_from_frame,
            select_body_command,
        )

        control = decoded_control_from_frame(_control_frame(_feeding_payload(grooming=0.85)))
        priority = ControllerPriority(
            mode_order=(
                ControllerMode.STOP,
                ControllerMode.FEEDING,
                ControllerMode.GROOMING,
                ControllerMode.LOCOMOTION,
            )
        )

        # When: the configured priority prefers feeding over grooming.
        command = select_body_command(
            BodyControllerRequest(
                control=control,
                contract=build_controller_contract(_load_api_report()),
                config=priority,
            )
        )

        # Then: the tie break is visible in the audit metadata.
        self.assertEqual(command.mode, ControllerMode.FEEDING)
        self.assertEqual(command.audit["selection"]["conflict_modes"], ["feeding", "grooming"])
        self.assertEqual(command.audit["selection"]["priority_order"][1:3], ["feeding", "grooming"])
        self.assertEqual(command.audit["selection"]["tie_break"], "configured_priority")

    def test_feeding_without_food_relative_direction_refuses_stale_direction(self) -> None:
        # Given: one valid feeding frame followed by a feeding frame with no direction.
        from digital_fruit_fly.body.controllers import (
            BodyControllerRequest,
            MissingFoodDirection,
            build_controller_contract,
            decoded_control_from_frame,
            select_body_command,
        )

        contract = build_controller_contract(_load_api_report())
        valid = decoded_control_from_frame(_control_frame(_feeding_payload(bearing_rad=0.2)))
        missing_direction = decoded_control_from_frame(
            _control_frame({"feeding": 1.0, "proboscis_extension": 1.0})
        )
        select_body_command(BodyControllerRequest(control=valid, contract=contract))

        # When / Then: the next frame must fail instead of reusing the previous direction.
        with self.assertRaises(MissingFoodDirection) as raised:
            select_body_command(BodyControllerRequest(control=missing_direction, contract=contract))
        self.assertAlmostEqual(raised.exception.feeding_intensity, 1.0)


def _load_api_report() -> dict[str, JsonValue]:
    return json.loads(API_REPORT_PATH.read_text(encoding="utf-8"))


def _control_frame(payload: dict[str, JsonValue]) -> ControlFrame:
    return ControlFrame(
        schema_version=SCHEMA_VERSION,
        run_id="body-controller-test",
        frame_index=1,
        simulation_time_s=0.015,
        sent_monotonic_s=10.0,
        payload=payload,
        payload_checksum=payload_checksum(payload),
    )


def _feeding_payload(
    bearing_rad: float = 0.3,
    elevation_rad: float = -0.1,
    grooming: float = 0.0,
) -> dict[str, JsonValue]:
    return {
        "feeding": 0.9,
        "grooming": grooming,
        "proboscis_extension": 0.75,
        "food_relative": {
            "bearing_rad": bearing_rad,
            "elevation_rad": elevation_rad,
            "distance_mm": 2.0,
        },
    }


if __name__ == "__main__":
    unittest.main()
