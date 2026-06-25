from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from digital_fruit_fly.runtime.timeouts import JsonObject


DEFAULT_API_JSON_PATH: Final = "outputs/smoke/body/flygym_api.json"


@dataclass(frozen=True, slots=True)
class ApiArtifactPaths:
    json_path: Path
    markdown_path: Path


def write_api_artifacts(
    report: JsonObject, output_dir: Path, markdown_path: Path
) -> ApiArtifactPaths:
    json_path = output_dir / "flygym_api.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_markdown_report(report, json_path), encoding="utf-8")
    return ApiArtifactPaths(json_path=json_path, markdown_path=markdown_path)


def _markdown_report(report: JsonObject, json_path: Path) -> str:
    fine_action = report["fine_action_support"]
    actuators = report["actuators"]
    controllers = report["locomotion_controller"]
    return "\n".join(
        (
            "# FlyGym API Probe",
            "",
            f"- JSON report: `{DEFAULT_API_JSON_PATH}`",
            f"- Last generated artifact path: `{json_path}`",
            f"- Schema version: `{report['schema_version']}`",
            f"- FlyGym: `{report['environment']['flygym']}`",
            f"- MuJoCo: `{report['environment']['mujoco']}`",
            f"- Locomotion controller status: `{controllers['status']}`",
            f"- Controller imports: `{', '.join(controllers['controller_imports'])}`",
            f"- Actuator type: `{actuators['actuator_type']}`",
            f"- Actuator count: `{len(actuators['position_actuator_order'])}`",
            f"- Proboscis control: {_support_word(fine_action['supports_proboscis_control'])}",
            f"- Proboscis DOFs: `{', '.join(fine_action['proboscis_dofs'])}`",
            f"- Antenna control: {_support_word(fine_action['supports_antenna_control'])}",
            f"- Antenna DOFs: `{', '.join(fine_action['antenna_dofs'])}`",
            f"- Front-leg face grooming: {_support_word(fine_action['supports_front_leg_face_grooming'])}",
            f"- Front-leg grooming DOFs: `{', '.join(fine_action['front_leg_face_grooming_dofs'])}`",
            f"- Site positions: {_support_word(fine_action['supports_site_positions'])}",
            "",
            "The installed FlyGym 2 surface selected for body work is the compositional",
            "`flygym.Simulation` API with position actuators ordered by the installed",
            "`Skeleton(ALL_BIOLOGICAL, PITCH_ROLL_YAW)` joint DOF order. The report",
            "does not claim a core `flygym` high-level behavior controller when only",
            "`flygym_demo.complex_terrain` controller examples are available.",
            "",
        )
    )


def _support_word(value: bool) -> str:
    return "supported" if value is True else "unsupported"
