"""Routed-only gate tests. CPU fixtures/negative cases are NOT visual qualification.

The opt-in integration test launches the actual available Chromium, owns its capture,
and measures the fixture GLB; even that is not real-subject/Blender qualification.
"""
import json
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

    def test_normal_diagnostics_cannot_be_bound_as_material_review(self):
        sweep = {"frames": [{"width": 1, "height": 1}]}
        with self.assertRaisesRegex(ValueError, "normal diagnostics are not material"):
            gate.bind_material_frames(api.Evidence(self.workspace), sweep, {},
                                      {"measurement": {"diagnostic": "opaque-source-sided-normal-v1"}})
        with self.assertRaisesRegex(ValueError, "incomplete"):
            gate.bind_material_frames(api.Evidence(self.workspace), sweep, {},
                                      {"measurement": {"materialCapture": gate.MATERIAL_CAPTURE}})

    def test_material_pose_images_are_hash_bound_and_dimension_checked(self):
        # Image protocol only: these owned pixels do not claim real browser/PBR qualification.
        image = self.fixture.put("material.png", png())
        rgba = self.fixture.put("material.rgba", bytes([127, 127, 127, 255]))
        files = {"0-material.png": image, "0-material.rgba": rgba}
        receipt = {"measurement": {"materialCapture": gate.MATERIAL_CAPTURE}}
        sweep = {"frames": [{"width": 1, "height": 1, "clip": "nod", "time": 0}]}
        gate.bind_material_frames(api.Evidence(self.workspace), sweep, files, receipt)
        self.assertEqual(sweep["frames"][0]["material"], image)
        self.assertEqual(sweep["frames"][0]["materialRgba"], rgba)
        wrong_size = {"frames": [{"width": 2, "height": 1}]}
        with self.assertRaisesRegex(ValueError, "PNG dimensions"):
            gate.bind_material_frames(api.Evidence(self.workspace), wrong_size, files, receipt)
        (self.workspace / "material.rgba").write_bytes(bytes([1, 2, 3, 255]))
        with self.assertRaisesRegex(ValueError, "stale evidence"):
            gate.bind_material_frames(api.Evidence(self.workspace), sweep, files, receipt)

    @unittest.skipUnless(os.environ.get("IMG2_CHARACTER_RUN_LIVE_TESTS") == "1" and hasattr(os, "setsid"),
                         "requires explicitly enabled real Chromium navigation/cleanup diagnostic")
    def test_navigation_timeout_closes_its_real_browser(self):
        import http.server
        import signal
        import threading
        import time

        node = gate.executable("IMG2_CHARACTER_NODE", "node")
        browser = gate.executable("IMG2_CHARACTER_BROWSER", "chromium")
        three = gate.reviewed_three()
        release = threading.Event()

        class HangingProxy(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                release.wait(120)  # Deliberate owned transport failure, never a rendered pass.

            do_CONNECT = do_GET

            def log_message(self, *args):
                pass

        proxy = http.server.ThreadingHTTPServer(("127.0.0.1", 0), HangingProxy)
        threading.Thread(target=proxy.serve_forever, daemon=True).start()
        self.addCleanup(proxy.server_close)
        self.addCleanup(proxy.shutdown)
        self.addCleanup(release.set)
        pid_file = self.workspace / "browser.pid"
        wrapper = self.workspace / "hanging-browser"
        wrapper.write_text(
            f"#!{sys.executable}\nimport os, sys\nfrom pathlib import Path\n"
            f"if '--version' not in sys.argv[1:]:\n"
            f"    os.setsid()\n    Path({str(pid_file)!r}).write_text(str(os.getpid()))\n"
            f"os.execv({browser!r}, [{browser!r}, "
            f"'--proxy-server=http://127.0.0.1:{proxy.server_port}', "
            f"'--proxy-bypass-list=<-loopback>', *sys.argv[1:]])\n")
        wrapper.chmod(0o700)

        def cleanup_browser():
            if pid_file.exists():
                try:
                    os.killpg(int(pid_file.read_text()), signal.SIGTERM)
                except ProcessLookupError:
                    pass

        self.addCleanup(cleanup_browser)
        request = self.fixture.case()
        sweep = json.loads((self.workspace / request["sweep"]["path"]).read_bytes())
        frame = sweep["frames"][0]
        job = self.fixture.put("navigation-job.json", {
            "candidatePath": str(self.workspace / request["glb"]["path"]),
            "baselinePath": str(self.workspace / sweep["baselineGlb"]["path"]),
            "glbSha256": request["glb"]["sha256"],
            "baselineGlbSha256": sweep["baselineGlb"]["sha256"],
            "frames": [{**frame, "camera": json.loads((self.workspace / frame["camera"]["path"]).read_bytes())}]})
        result = subprocess.run([node, str(ROOT / "tools/capture_routed_rig.mjs"),
                                 "--input", str(self.workspace / job["path"]),
                                 "--out", str(self.workspace / "hung-capture")],
                                env=gate.child_environment(node=node, browser=str(wrapper), three=three),
                                text=True, capture_output=True, timeout=90)
        pid = int(pid_file.read_text())
        alive = True
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                os.killpg(pid, 0)
            except ProcessLookupError:
                alive = False
                break
            time.sleep(.05)
        self.fixture.put("browser-cleanup.json", {
            "pid": pid, "pgid": pid, "driverExit": result.returncode,
            "ownedGroupAliveAfterDriver": alive})
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("capture missing event: Page.loadEventFired", result.stderr)
        self.assertFalse(alive, f"capture abandoned owned browser group {pid}")

    @unittest.skipUnless(os.environ.get("IMG2_CHARACTER_RUN_LIVE_TESTS") == "1",
                         "requires explicitly enabled real Chromium material capture")
    def test_material_colour_changes_review_pixels_but_not_normal_diagnostics(self):
        from PIL import Image
        node = gate.executable("IMG2_CHARACTER_NODE", "node")
        browser = gate.executable("IMG2_CHARACTER_BROWSER", "chromium")
        three = gate.reviewed_three()
        control = self.workspace / "control.glb"
        order = api.extract_glb(self.workspace / "character.glb")["skeleton"]["skin"]["joints"]
        artifact_tests.fixture_glb(control, weights=(.75, .25, 0, 0),
                                   joints=[order.index(0), order.index(self.fixture.ids["hips"]), 0, 0])
        captures = []
        for name, colour in (("red", [1, 0, 0, 1]), ("blue", [0, 0, 1, 1])):
            source = self.workspace / f"{name}.glb"
            artifact_tests.fixture_glb(source, base_color=colour)
            frame = {"clip": "nod", "time": 0, "side": "front", "azimuth": 0,
                     "width": 64, "height": 64, "camera": {
                         "matrixWorld": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, .5, 3, 1],
                         "projectionMatrix": [4/3, 0, 0, 0, 0, 4/3, 0, 0, 0, 0, -2/9.9, 0, 0, 0, -10.1/9.9, 1]}}
            job = self.fixture.put(f"{name}-job.json", {
                "candidatePath": str(source), "baselinePath": str(control),
                "glbSha256": gate.file_sha(source), "baselineGlbSha256": gate.file_sha(control),
                "frames": [frame]})
            output = self.workspace / f"{name}-capture"
            result = subprocess.run([node, str(ROOT / "tools/capture_routed_rig.mjs"),
                                     "--input", str(self.workspace / job["path"]), "--out", str(output)],
                                    env=gate.child_environment(node=node, browser=browser, three=three),
                                    text=True, capture_output=True, timeout=240)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            receipt = json.loads((output / "capture.json").read_bytes())
            self.assertEqual(receipt["measurement"]["materialCapture"], gate.MATERIAL_CAPTURE)
            normal = (output / "0-candidate.rgba").read_bytes()
            material = (output / "0-material.rgba").read_bytes()
            visible = [material[i:i + 4] for i in range(0, len(material), 4) if material[i + 3] == 255]
            self.assertTrue(visible, "material render has no opaque subject pixels")
            sums = [sum(pixel[channel] for pixel in visible) for channel in range(3)]
            self.assertGreater(sums[0 if name == "red" else 2], sums[2 if name == "red" else 0])
            with Image.open(output / "0-material.png") as image:
                expected = b"".join(material[y * 256:(y + 1) * 256] for y in range(63, -1, -1))
                self.assertEqual(image.convert("RGBA").tobytes(), expected)
            captures.append((normal, material))
        self.assertEqual(captures[0][0], captures[1][0], "material edits changed the normal diagnostic")
        self.assertNotEqual(captures[0][1], captures[1][1], "material edits disappeared from review pixels")

    def test_routed_program_refuses_self_control_before_live_capture(self):
        request, artifact = self.admitted()
        sweep = json.loads((self.workspace / request["sweep"]["path"]).read_bytes())
        sweep["baselineGlb"] = request["glb"]
        request["sweep"] = self.fixture.put(request["sweep"]["path"], sweep)
        record = json.loads((self.workspace / gate.ADMISSION).read_bytes())
        record["inputs"] = request
        record["boundInputs"] = [request["sweep"] if ref["path"] == request["sweep"]["path"] else ref
                                 for ref in record["boundInputs"]]
        admission = self.fixture.put(gate.ADMISSION, record)
        artifact["files"] = [admission if ref["path"] == gate.ADMISSION else
                             request["sweep"] if ref["path"] == request["sweep"]["path"] else ref
                             for ref in artifact["files"]]
        self.fixture.put("artifact.json", artifact)
        result = self.run_gate()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        verdict = json.loads(result.stdout)
        self.assertEqual(verdict["status"], "error")
        self.assertTrue(any("independent blend-off baseline" in reason for reason in verdict["reasons"]))

    def test_routed_terminal_has_a_distinct_program_identity(self):
        card = json.loads((ROOT / "route.json").read_bytes())
        self.assertEqual(card["routedTerminalGate"], {"id": "character-routed-terminal", "script": "tools/gate_routed_terminal.py"})

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

    def test_identical_browser_receipt_retains_distinct_exact_native_closures(self):
        # Persistence-only bytes: not a purported Blender/visual qualification.
        output = self.workspace / "fresh-native"
        output.mkdir()
        (output / "character.glb").write_bytes(b"unchanged delivered GLB storage fixture")
        (output / "character.blend").write_bytes(b"first native container")
        (output / "native.json").write_bytes(api.canonical({"container": "first"}))
        browser = api.canonical({"browser": "identical receipt storage fixture"})
        browser_path = f".img2/artifacts/character/terminal-live/{api.digest(browser)}/capture.json"
        first_browser = gate.retain_measurement(api.Evidence(self.workspace), browser_path, browser)
        first = gate.retain_native_bundle(api.Evidence(self.workspace), output)
        old = {ref["path"]: ((self.workspace / ref["path"]).read_bytes(),
                             (self.workspace / ref["path"]).stat().st_mtime_ns) for ref in first}
        (output / "character.blend").write_bytes(b"second native container")
        (output / "native.json").write_bytes(api.canonical({"container": "second"}))
        # Reopen persistence for the next replay, not a shared in-memory dedup map.
        second_browser = gate.retain_measurement(api.Evidence(self.workspace), browser_path, browser)
        second = gate.retain_native_bundle(api.Evidence(self.workspace), output)
        self.assertEqual(first_browser, second_browser)
        self.assertNotEqual({ref["path"] for ref in first}, {ref["path"] for ref in second})
        for refs in (first, second):
            inventory = {"kind": "img2.character-terminal-native-bundle", "version": 1,
                         "files": [{"path": Path(ref["path"]).name, "sha256": ref["sha256"]} for ref in refs]}
            directory = ".img2/artifacts/character/terminal-native/" + api.digest(api.canonical(inventory))
            self.assertEqual({str(Path(ref["path"]).parent) for ref in refs}, {directory})
            for ref in refs:
                api.Evidence(self.workspace).read(ref, json_data=False)
        for name, expected in old.items():
            path = self.workspace / name
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), expected)
        self.assertEqual(gate.retain_native_bundle(api.Evidence(self.workspace), output), second)
        # The roster, not just the bag of file digests, participates in the identity.
        (output / "character.blend").rename(output / "renamed.blend")
        renamed = gate.retain_native_bundle(api.Evidence(self.workspace), output)
        self.assertNotEqual(Path(second[0]["path"]).parent, Path(renamed[0]["path"]).parent)
        (self.workspace / renamed[0]["path"]).write_bytes(b"altered retained proof")
        with self.assertRaisesRegex(ValueError, "immutable terminal measurement was altered"):
            gate.retain_native_bundle(api.Evidence(self.workspace), output)

    @unittest.skipUnless(os.environ.get("IMG2_CHARACTER_RUN_LIVE_TESTS") == "1",
                         "requires explicitly enabled real bpy and Chromium producers")
    def test_native_browser_delivery_replays_source_and_binds_exact_artifact(self):
        result = subprocess.run([sys.executable, str(ROOT / "tests/native_routed_smoke.py"),
                                 "--workspace", str(self.workspace / "native-live")],
                                capture_output=True, text=True, timeout=600)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        value = json.loads(result.stdout)
        self.assertFalse(value["qualification"])
        self.assertGreater(value["nativeDeformation"], 0)
        self.assertGreater(value["nativeParity"]["vertexComparisons"], 0)
        self.assertEqual(len(value["gates"]), 12)
        self.assertTrue(all(row["status"] == "pass" for row in value["gates"]))
        record = value["measurement"]
        self.assertEqual(api.digest((self.workspace / "native-live" / record["path"]).read_bytes()), record["sha256"])


if __name__ == "__main__":
    unittest.main()
