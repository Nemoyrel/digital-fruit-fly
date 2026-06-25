from __future__ import annotations

import importlib.util
import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from digital_fruit_fly.runtime.logging import read_jsonl

LIVE_FLYGYM_MODULES = ("flygym", "glfw")
MISSING_LIVE_FLYGYM_MODULES = tuple(
    name for name in LIVE_FLYGYM_MODULES if importlib.util.find_spec(name) is None
)
LIVE_FLYGYM_AVAILABLE = len(MISSING_LIVE_FLYGYM_MODULES) == 0
LIVE_FLYGYM_SKIP_REASON = (
    "requires live FlyGym modules; missing: " + ", ".join(MISSING_LIVE_FLYGYM_MODULES)
    if MISSING_LIVE_FLYGYM_MODULES
    else "requires live FlyGym modules"
)


class TestBodyServer(unittest.TestCase):
    def test_append_tick_writes_bridge_frames_in_sensory_brain_control_order(self) -> None:
        # Given: a prepared body run context and two synthetic live ticks.
        from digital_fruit_fly.arena.dust import DustState
        from digital_fruit_fly.arena.model import FlyPose2D
        from digital_fruit_fly.body.controllers import BodyCommand, ControllerMode, LocomotionTarget
        from digital_fruit_fly.body.server_artifacts import build_context, prepare_artifacts
        from digital_fruit_fly.body.server_loop import _append_tick
        from digital_fruit_fly.body.server_types import BodyServerConfig
        from digital_fruit_fly.bridge.messages import decode_message
        from digital_fruit_fly.runtime.config import load_config
        from digital_fruit_fly.runtime.run_manifest import create_run_layout

        with tempfile.TemporaryDirectory() as temp_root:
            output_dir = Path(temp_root) / "outputs" / "body_server"
            runtime = load_config(REPO_ROOT / "configs" / "bridge_smoke.yaml")
            config = BodyServerConfig(
                config_path=REPO_ROOT / "configs" / "bridge_smoke.yaml",
                output_dir=output_dir,
                brain_mode="fixture",
                max_ticks=2,
                timeout_s=1.0,
                host="127.0.0.1",
                brain_port=9,
                record_codec="definitely-not-a-codec",
                viewer_requested=False,
            )
            layout = create_run_layout(output_dir, output_dir.name)
            context = build_context(config, runtime, layout)
            prepare_artifacts(context)

            # When: the live loop appends two ticks.
            for tick_index in range(2):
                _append_tick(context, _tick_record(layout.run_id, tick_index), {"live": True, "step_index": tick_index})

            # Then: frames.jsonl contains sensory/brain/control triplets in live emission order.
            self.assertTrue(context.artifacts.frames_path.is_file())
            frames = [
                decode_message(line.encode("utf-8"))
                for line in context.artifacts.frames_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                [type(frame).__name__ for frame in frames],
                ["SensoryFrame", "BrainFrame", "ControlFrame", "SensoryFrame", "BrainFrame", "ControlFrame"],
            )
            self.assertEqual([frame.frame_index for frame in frames], [0, 0, 0, 1, 1, 1])

    @unittest.skipUnless(LIVE_FLYGYM_AVAILABLE, LIVE_FLYGYM_SKIP_REASON)
    def test_fixture_mode_writes_live_flygym_tick_artifacts_when_run_standalone(self) -> None:
        # Given: a fixture-mode body server request with no external brain process.
        from digital_fruit_fly.body.server import BodyServerConfig, serve_body

        with tempfile.TemporaryDirectory() as temp_root:
            output_dir = Path(temp_root) / "outputs" / "body_server"
            config = BodyServerConfig(
                config_path=REPO_ROOT / "configs" / "bridge_smoke.yaml",
                output_dir=output_dir,
                brain_mode="fixture",
                max_ticks=5,
                timeout_s=0.5,
                host="127.0.0.1",
                brain_port=9,
                record_codec="definitely-not-a-codec",
                viewer_requested=False,
            )

            # When: the server runs its fixture-brain loop.
            result = serve_body(config)

            # Then: downstream logs prove one live FlyGym step per body tick.
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.ticks, 5)
            trajectory = read_jsonl(result.trajectory_path)
            control = read_jsonl(result.control_path)
            arena = read_jsonl(result.arena_path)
            self.assertEqual(len(trajectory), 5)
            self.assertEqual(len(control), 5)
            self.assertEqual(len(arena), 5)
            self.assertEqual([row["tick_index"] for row in trajectory], [0, 1, 2, 3, 4])
            self.assertTrue(result.recording_metadata_path.is_file())
            recording = json.loads(result.recording_metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(recording["status"], "fallback_frames")
            self.assertEqual(recording["frame_count"], 5)
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "ok")
            self.assertEqual(manifest["ticks"], 5)
            self.assertTrue(manifest["flygym_live"])
            self.assertIn("FlyGym", manifest["simulation_backend"])
            self.assertIn("NeuroMechFly", manifest["simulation_backend"])
            self.assertEqual(manifest["flygym"]["live_step_count"], 5)
            self.assertEqual(manifest["flygym"]["simulation_class"], "flygym.simulation.Simulation")
            self.assertEqual(arena[-1]["flygym"]["step_index"], 4)

    def test_connect_mode_writes_error_manifest_when_brain_is_unreachable(self) -> None:
        # Given: connect mode points at a loopback port with no listening brain server.
        from digital_fruit_fly.body.server import BodyServerConfig, serve_body

        with tempfile.TemporaryDirectory() as temp_root:
            output_dir = Path(temp_root) / "outputs" / "body_no_brain"
            config = BodyServerConfig(
                config_path=REPO_ROOT / "configs" / "bridge_smoke.yaml",
                output_dir=output_dir,
                brain_mode="connect",
                max_ticks=3,
                timeout_s=0.2,
                host="127.0.0.1",
                brain_port=_unused_loopback_port(),
                record_codec="definitely-not-a-codec",
                viewer_requested=False,
            )

            # When: the body server tries to connect.
            result = serve_body(config)

            # Then: it exits cleanly with structured error artifacts and no tick logs.
            self.assertEqual(result.status, "error")
            self.assertEqual(result.ticks, 0)
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "error")
            self.assertEqual(manifest["error"]["code"], "brain_unreachable")
            events = read_jsonl(result.events_path)
            self.assertIn("body_server_error", {row["kind"] for row in events})

    def test_body_entrypoints_do_not_import_brian_or_shiu_modules(self) -> None:
        # Given: the process-boundary body entrypoints.
        forbidden = ("import brian2", "from brian2", "shiu_adapter", "drosophila_brain_model")
        paths = (
            REPO_ROOT / "src" / "digital_fruit_fly" / "body" / "server.py",
            REPO_ROOT / "scripts" / "run_body.py",
        )

        # When: their source is scanned.
        combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in paths)

        # Then: body process code does not import the incompatible brain runtime.
        for needle in forbidden:
            self.assertNotIn(needle, combined)


def _unused_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _tick_record(run_id: str, tick_index: int) -> TickRecord:
    from digital_fruit_fly.arena.dust import DustState
    from digital_fruit_fly.arena.model import FlyPose2D
    from digital_fruit_fly.body.controllers import BodyCommand, ControllerMode, LocomotionTarget
    from digital_fruit_fly.body.server_types import BodyState, TickRecord
    from digital_fruit_fly.bridge.messages import BrainFrame, ControlFrame, SensoryFrame, payload_checksum

    sensory_payload = {
        "encoder_audit": {"raw": {"dust_load": float(tick_index)}},
        "rates_hz": {"sugar_left": 0.0, "sugar_right": 0.0},
    }
    brain_payload = {
        "rates_hz": {
            "forward": 0.0,
            "feed": 0.0,
            "turn": 0.0,
            "groom": 0.0,
            "stop": 0.0,
        }
    }
    control_payload = {"decoder_audit": {"selected_action": "locomotion"}}
    sensory = SensoryFrame(1, run_id, tick_index, float(tick_index), float(tick_index), sensory_payload, payload_checksum(sensory_payload))
    brain = BrainFrame(1, run_id, tick_index, float(tick_index), float(tick_index), brain_payload, payload_checksum(brain_payload))
    control = ControlFrame(1, run_id, tick_index, float(tick_index), float(tick_index), control_payload, payload_checksum(control_payload))
    command = BodyCommand(
        ControllerMode.LOCOMOTION,
        {},
        LocomotionTarget(0.0, 0.0, False, "fixture.HybridTurningController"),
        {"selected_mode": "locomotion"},
    )
    return TickRecord(
        state=BodyState(FlyPose2D(1.0, 2.0, 0.0), DustState.clean()),
        sensory=sensory,
        brain=brain,
        control=control,
        command=command,
        collided=False,
        dust_events=(),
    )


if __name__ == "__main__":
    unittest.main()
