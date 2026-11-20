"""Routed-only gate tests. CPU fixtures/negative cases are NOT visual qualification.

The opt-in integration test launches the actual available Chromium, owns its capture,
and measures the fixture GLB; even that is not real-subject/Blender qualification.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import gate_routed_terminal as gate
import rigged_artifact as api
import test_rigged_artifact as artifact_tests


def png():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\0\x7f\x7f\x7f")) + chunk(b"IEND", b""))


class RoutedTerminalGateTests(unittest.TestCase):
    def setUp(self):
        # Reuse the existing actual-GLB fixture without inheriting/rerunning its test suite.
        self.fixture = artifact_tests.RiggedArtifactTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.workspace = self.fixture.workspace

    def state(self):
        reference = self.fixture.put("reference.png", png())
        value = {"routeChild": {"runId": "test-run", "objectId": "character-1", "revision": 1,
                                "ownerRoute": "plugin:character@fixture#character-mesh>rigged-character",
                                "outputKind": "rigged-3d", "cropSha256": reference["sha256"]},
                 "artifacts": {"reference": reference["path"]}}
        self.fixture.put("state.json", value)
        return value

    def admitted(self):
        request = self.fixture.case(real_runtime=True)
        artifact = api.admit(self.workspace, request)
        self.state()
        return request, artifact

    def run_gate(self, env=None):
        return subprocess.run([sys.executable, str(ROOT / "tools/gate_routed_terminal.py"),
                               "--workspace", str(self.workspace)], text=True, capture_output=True,
                              env=env, timeout=300)

    def test_route_registration_is_data_only_and_legacy_registry_is_unchanged(self):
        card = json.loads((ROOT / "route.json").read_bytes())
        self.assertEqual(card["routedTerminalGate"], {"id": "character-routed-terminal", "script": "tools/gate_routed_terminal.py"})
        self.assertEqual(card["deps"], [{"probe": "python3>=3.10"}, {"probe": "character-node>=22.0"}, {"probe": "character-chromium>=1.0"}])
        registry = json.loads((ROOT / "gates.json").read_bytes())
        self.assertEqual(len(registry), 1)
        self.assertEqual(registry[0]["id"], "rigging")
        self.assertFalse(registry[0]["blocking"])

    def test_host_override_and_exact_path_fallback_never_select_another_install(self):
        # Resolve paths only: these bytes are never executed or claimed to be Node.
        configured = self.workspace / "configured-node"
        fallback = self.workspace / "node"
        configured.write_bytes(b"resolver fixture, never executed")
        fallback.write_bytes(b"different resolver fixture, never executed")
        configured.chmod(0o700)
        fallback.chmod(0o700)
        names = ("PATH", "IMG2_CHARACTER_NODE")
        previous = {name: os.environ.get(name) for name in names}
        try:
            os.environ["PATH"] = str(self.workspace)
            os.environ["IMG2_CHARACTER_NODE"] = str(configured)
            self.assertEqual(gate.executable("IMG2_CHARACTER_NODE", "node"), str(configured.resolve()))
            os.environ["IMG2_CHARACTER_NODE"] = "relative-node"
            with self.assertRaisesRegex(ValueError, "absolute executable"):
                gate.executable("IMG2_CHARACTER_NODE", "node")
            del os.environ["IMG2_CHARACTER_NODE"]
            self.assertEqual(gate.executable("IMG2_CHARACTER_NODE", "node"), str(fallback.resolve()))
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_relabelled_identical_camera_frames_are_not_a_real_orbit_sweep(self):
        self.fixture.case()
        sweep = json.loads((self.workspace / "sweep.json").read_bytes())
        frames = [{**frame, "camera": json.loads((self.workspace / frame["camera"]["path"]).read_bytes())}
                  for frame in sweep["frames"]]
        with self.assertRaisesRegex(ValueError, "placeholder sweep"):
            gate.view_coverage(frames, sweep["frames"], sweep["axes"])

    def test_child_environment_blocks_loader_injection_and_credentials(self):
        node = gate.executable("IMG2_CHARACTER_NODE", "node")
        marker = self.workspace / "preload-executed"
        preload = self.workspace / "untrusted-preload.mjs"
        preload.write_text("import {writeFileSync} from 'node:fs';writeFileSync("
                           + json.dumps(str(marker)) + ",'injected');", encoding="utf-8")
        forbidden = ("NODE_OPTIONS", "NODE_PATH", "NODE_EXTRA_CA_CERTS", "LD_PRELOAD", "LD_LIBRARY_PATH",
                     "DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH", "PYTHONPATH", "PYTHONSTARTUP",
                     "BASH_ENV", "ENV", "TYPESAFE_API_KEY", "OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY", "HTTPS_PROXY")
        previous = {name: os.environ.get(name) for name in forbidden}
        try:
            for name in forbidden:
                os.environ[name] = "test-only-do-not-inherit"
            os.environ["NODE_OPTIONS"] = "--import " + preload.as_uri()
            environment = gate.child_environment(node=node)
            for name in forbidden:
                self.assertNotIn(name, environment)
            script = ("process.stdout.write(JSON.stringify(Object.fromEntries("
                      + json.dumps(forbidden) + ".map(key=>[key,process.env[key]??null]))))")
            result = subprocess.run([node, "--input-type=module", "-e", script], env=environment,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), dict.fromkeys(forbidden))
            self.assertFalse(marker.exists(), "untrusted Node preloader executed")
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_three_approval_cannot_be_inferred_when_host_configuration_is_missing(self):
        names = ("IMG2_CHARACTER_THREE_ROOT", "IMG2_CHARACTER_THREE_SHA256")
        previous = {name: os.environ.get(name) for name in names}
        try:
            for name in names:
                os.environ.pop(name, None)
            with self.assertRaisesRegex(ValueError, "reviewed IMG2_CHARACTER_THREE_SHA256 required"):
                gate.reviewed_three()
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    @unittest.skipUnless(os.environ.get("IMG2_CHARACTER_THREE_ROOT"), "requires known local Three package for pin mismatch regression")
    def test_mismatched_host_three_pin_is_rejected(self):
        previous = os.environ.get("IMG2_CHARACTER_THREE_SHA256")
        try:
            os.environ["IMG2_CHARACTER_THREE_SHA256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "package digest mismatch"):
                gate.reviewed_three()
        finally:
            if previous is None:
                os.environ.pop("IMG2_CHARACTER_THREE_SHA256", None)
            else:
                os.environ["IMG2_CHARACTER_THREE_SHA256"] = previous

    def test_missing_artifact_emits_one_nonpassing_program_owned_envelope(self):
        result = self.run_gate()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value["gate"], "character-routed-terminal")
        self.assertEqual(value["status"], "error")
        self.assertTrue(value["reasons"])

    def test_legacy_or_marker_only_state_never_passes_the_routed_gate(self):
        self.state()
        result = self.run_gate()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotEqual(json.loads(result.stdout)["status"], "pass")

    def test_read_only_recomputation_does_not_republish_admitted_files(self):
        request, artifact = self.admitted()
        before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in self.workspace.rglob("*") if path.is_file()}
        checked = gate.preflight(self.workspace)
        self.assertEqual(checked["artifact"], artifact)
        self.assertEqual(api.admit(self.workspace, request, publish=False)["artifact"], artifact)
        for path, expected in before.items():
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), expected)

    def test_wrong_object_and_changed_reference_are_rejected_before_capture(self):
        _, artifact = self.admitted()
        artifact["objectId"] = "other-character"
        self.fixture.put("artifact.json", artifact)
        with self.assertRaisesRegex(ValueError, "routed child"):
            gate.preflight(self.workspace)
        artifact["objectId"] = "character-1"
        self.fixture.put("artifact.json", artifact)
        self.fixture.put("reference.png", png() + b"changed")
        with self.assertRaisesRegex(ValueError, "stale evidence"):
            gate.preflight(self.workspace)

    def test_actual_skeleton_and_animation_sidecars_cannot_be_replaced_with_receipts(self):
        _, artifact = self.admitted()
        skeleton = next(ref for ref in artifact["files"] if ref["sha256"] == artifact["rig"]["skeletonSha"])
        replacement = self.fixture.put(skeleton["path"], {"kind": "receipt", "status": "pass"})
        artifact["files"] = [replacement if ref["path"] == skeleton["path"] else ref for ref in artifact["files"]]
        artifact["rig"]["skeletonSha"] = replacement["sha256"]
        self.fixture.put("artifact.json", artifact)
        with self.assertRaisesRegex(ValueError, "actual GLB accessor"):
            gate.preflight(self.workspace)

    def test_rewritten_admission_cannot_self_authorize_passing_measurements(self):
        _, artifact = self.admitted()
        record = json.loads((self.workspace / gate.ADMISSION).read_bytes())
        record["gateReport"]["gates"][0]["measured"] = {"invented": 0}
        replacement = self.fixture.put(gate.ADMISSION, record)
        artifact["files"] = [replacement if ref["path"] == gate.ADMISSION else ref for ref in artifact["files"]]
        self.fixture.put("artifact.json", artifact)
        with self.assertRaisesRegex(ValueError, "does not reproduce"):
            gate.preflight(self.workspace)

    def test_synthetic_saved_sweep_never_bypasses_unavailable_live_producer(self):
        _, artifact = self.admitted()
        env = {**os.environ, "IMG2_CHARACTER_BROWSER": str(self.workspace / "not-a-browser")}
        result = self.run_gate(env)
        value = json.loads(result.stdout)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(value["status"], "error")
        self.assertNotIn("measurementOrigin", value["evidence"])
        self.assertEqual(value["evidence"]["artifact"], {"path": str((self.workspace / "artifact.json").resolve()),
                                                       "sha256": api.digest(api.canonical(artifact))})
        self.assertTrue(any("capture-unavailable" in reason or "producer-dependency" in reason for reason in value["reasons"]))

    def test_foreign_or_escaped_child_files_are_rejected(self):
        _, artifact = self.admitted()
        artifact["files"].append({"path": "../foreign.glb", "sha256": "0" * 64})
        self.fixture.put("artifact.json", artifact)
        with self.assertRaisesRegex(ValueError, "workspace-relative"):
            gate.preflight(self.workspace)

    @unittest.skipUnless(os.environ.get("IMG2_CHARACTER_RUN_LIVE_TESTS") == "1", "requires explicitly enabled real Chromium capture")
    def test_real_browser_produces_all_frames_and_binds_exact_artifact(self):
        # Give the synthetic test geometry actual non-placeholder cameras and opaque,
        # two-sided source material so every required orbit has observable geometry.
        artifact_tests.fixture_glb(self.workspace / "character.glb")
        document, binary, _ = api.glb.parse_glb(self.workspace / "character.glb")
        document["materials"] = [{"doubleSided": True}]
        document["meshes"][0]["primitives"][0]["material"] = 0
        encoded = json.dumps(document).encode()
        encoded += b" " * (-len(encoded) % 4)
        body = struct.pack("<II", len(encoded), 0x4e4f534a) + encoded + struct.pack("<II", len(binary), 0x004e4942) + binary
        (self.workspace / "character.glb").write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body)
        request = self.fixture.case(real_runtime=True)
        sweep = json.loads((self.workspace / "sweep.json").read_bytes())
        white = self.fixture.put("white.rgba", bytes([220, 220, 220, 255] * (64 * 64)))
        roi = self.fixture.put("render.roi", bytes([1] * (64 * 64)))
        for i, frame in enumerate(sweep["frames"]):
            angle = math.radians(frame["azimuth"] + (180 if frame["side"] == "back" else 0))
            c, s = math.cos(angle), math.sin(angle)
            camera = {**{key: frame[key] for key in ("clip", "time", "side", "azimuth")},
                      "glbSha256": request["glb"]["sha256"], "baselineGlbSha256": sweep["baselineGlb"]["sha256"],
                      "matrixWorld": [c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, 3*s, .5, 3*c, 1],
                      "projectionMatrix": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, -2/9.9, 0, 0, 0, -10.1/9.9, 1]}
            frame.update(width=64, height=64, roi=roi, candidate=white, baseline=white,
                         camera=self.fixture.put(f"live-camera-{i}.json", camera))
        request["sweep"] = self.fixture.put("sweep.json", sweep)
        artifact = api.admit(self.workspace, request)
        self.state()
        result = self.run_gate()
        value = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(value["status"], "pass")
        self.assertEqual(value["evidence"]["measurementOrigin"], "live-browser")
        self.assertEqual(value["evidence"]["artifact"]["sha256"], hashlib.sha256(api.canonical(artifact)).hexdigest())
        self.assertEqual(len(value["evidence"]["gates"]), 12)
        record = value["evidence"]["measurement"]
        self.assertEqual(value["evidence"]["three"]["approval"], "host-approved")
        self.assertEqual(value["evidence"]["three"]["sha256"], os.environ["IMG2_CHARACTER_THREE_SHA256"])
        self.assertIn("three/examples/jsm/utils/SkeletonUtils.js", value["evidence"]["producerFiles"])
        self.assertEqual(api.digest((self.workspace / record["path"]).read_bytes()), record["sha256"])


if __name__ == "__main__":
    unittest.main()
