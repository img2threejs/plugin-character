"""Native protocol/counterexamples, not independent expert or visual qualification."""
import copy
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import rigged_artifact as api
import routed_native as subject
import native_glb_freeze
from test_rigged_artifact import fixture_glb


class NativeBoundaryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.delivery = self.root / "delivery.glb"
        fixture_glb(self.delivery)
        self.extracted = api.extract_glb(self.delivery)

    def poses(self):
        mesh = self.extracted["meshBuffers"]["meshes"][0]
        values = mesh["attributes"]["position"]
        positions = [values[i:i + 3] for i in range(0, len(values), 3)]
        fractions = (0, .25, .5, .75, 1)
        receipt = {"restWorld": {"Body": positions}, "poseSamples": {"nod": [
            {"fraction": t, "meshes": {"Body": copy.deepcopy(positions)}} for t in fractions]}}
        runtime = {"poseSamples": {"nod": [
            {"fraction": t, "meshes": {mesh["name"]: list(values)}} for t in fractions]}}
        return receipt, runtime

    def test_native_python_preserves_venv_symlink_invocation(self):
        # Resolver fixture only; these bytes are never executed as Python.
        target = self.root / "python-real"
        target.write_bytes(b"resolver-only fixture")
        target.chmod(0o700)
        directory = self.root / "venv" / "bin"
        directory.mkdir(parents=True)
        link = directory / "python"
        link.symlink_to(target)
        previous = os.environ.get("IMG2_CHARACTER_BPY_PYTHON")
        try:
            os.environ["IMG2_CHARACTER_BPY_PYTHON"] = str(link)
            self.assertEqual(subject.native_python(), str(link.parent.resolve() / link.name))
            self.assertTrue(Path(subject.native_python()).is_symlink())
            os.environ["IMG2_CHARACTER_BPY_PYTHON"] = "relative/python"
            with self.assertRaisesRegex(ValueError, "must be absolute"):
                subject.native_python()
        finally:
            if previous is None:
                os.environ.pop("IMG2_CHARACTER_BPY_PYTHON", None)
            else:
                os.environ["IMG2_CHARACTER_BPY_PYTHON"] = previous

    def test_freeze_reads_actual_prebind_bytes_and_rejects_a_moved_vertex(self):
        base = self.root / "base.glb"
        fixture_glb(base, skin=False)
        manifest = subject.freeze_export(base, self.delivery, {"meshes": ["Body"]})
        self.assertTrue(api.parity.verify(api.parity.Manifest.from_dict(manifest), self.extracted["meshBuffers"]).ok)
        document, binary, _ = api.glb.parse_glb(base)
        primitive = document["meshes"][0]["primitives"][0]
        accessor = document["accessors"][primitive["attributes"]["POSITION"]]
        view = document["bufferViews"][accessor["bufferView"]]
        binary = bytearray(binary)
        struct.pack_into("<f", binary, view.get("byteOffset", 0) + accessor.get("byteOffset", 0), 5.)
        encoded = json.dumps(document).encode()
        encoded += b" " * (-len(encoded) % 4)
        body = struct.pack("<II", len(encoded), 0x4e4f534a) + encoded + struct.pack("<II", len(binary), 0x004e4942) + binary
        base.write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body)
        with self.assertRaisesRegex(ValueError, "frozen binary"):
            subject.freeze_export(base, self.delivery, {"meshes": ["Body"]})

    def rewritten(self, semantic, change):
        document, binary, _ = api.glb.parse_glb(self.delivery)
        accessor = document["accessors"][document["meshes"][0]["primitives"][0]["attributes"][semantic]]
        view = document["bufferViews"][accessor["bufferView"]]
        start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
        data = bytearray(binary)
        for i in range(accessor["count"]):
            offset = start + i * view.get("byteStride", 12)
            values = struct.unpack_from("<3f", data, offset)
            struct.pack_into("<3f", data, offset, *change(values))
        encoded = json.dumps(document).encode()
        encoded += b" " * (-len(encoded) % 4)
        body = struct.pack("<II", len(encoded), 0x4e4f534a) + encoded + struct.pack("<II", len(data), 0x004e4942) + data
        path = self.root / "raw-bound.glb"
        path.write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body)
        return path

    def test_normal_preservation_changes_no_rig_geometry_order_or_animation_bytes(self):
        raw = self.rewritten("NORMAL", lambda v: (v[0], v[1], v[2] + 2**-23))
        result = self.root / "normal-preserved.glb"
        native_glb_freeze.preserve_normals(self.delivery, raw, result)
        self.assertEqual(result.read_bytes(), self.delivery.read_bytes())

    def test_translated_export_regression_is_not_repaired_or_frozen_after_binding(self):
        # The observed bpy failure baked the object's .5 world translation only
        # into bound positions. Such a post-freeze shift must still be rejected.
        raw = self.rewritten("POSITION", lambda v: (v[0], v[1] + .5, v[2]))
        with self.assertRaisesRegex(ValueError, "exact frozen position"):
            native_glb_freeze.preserve_normals(self.delivery, raw, self.root / "must-not-exist.glb")
        self.assertFalse((self.root / "must-not-exist.glb").exists())

    def test_pose_comparison_covers_every_actual_export_vertex(self):
        receipt, runtime = self.poses()
        result = subject.compare_poses(receipt, self.extracted, runtime)
        self.assertEqual(result["vertexComparisons"], 66 * 5)
        runtime["poseSamples"]["nod"][2]["meshes"][self.extracted["meshBuffers"]["meshes"][0]["name"]][0] += .1
        with self.assertRaisesRegex(ValueError, "posed vertex parity failed"):
            subject.compare_poses(receipt, self.extracted, runtime)

    def test_static_export_tracks_cannot_pass_when_actual_native_source_deforms(self):
        receipt, runtime = self.poses()
        receipt["poseSamples"]["nod"][2]["meshes"]["Body"][0][0] += .025
        with self.assertRaisesRegex(ValueError, "posed vertex parity failed"):
            subject.compare_poses(receipt, self.extracted, runtime)

    def test_missing_clip_frame_or_vertex_is_not_a_passing_native_receipt(self):
        for mutation in ("clip", "frame", "vertex"):
            receipt, runtime = self.poses()
            if mutation == "clip":
                runtime["poseSamples"].clear()
            elif mutation == "frame":
                runtime["poseSamples"]["nod"].pop()
            else:
                runtime["poseSamples"]["nod"][0]["meshes"][self.extracted["meshBuffers"]["meshes"][0]["name"]].pop()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                subject.compare_poses(receipt, self.extracted, runtime)

    def test_coincident_native_vertices_cannot_choose_whichever_pose_passes(self):
        receipt, runtime = self.poses()
        receipt["restWorld"]["Body"].append(list(receipt["restWorld"]["Body"][0]))
        for frame in receipt["poseSamples"]["nod"]:
            point = list(frame["meshes"]["Body"][0])
            point[0] += .2
            frame["meshes"]["Body"].append(point)
        with self.assertRaisesRegex(ValueError, "ambiguous native"):
            subject.compare_poses(receipt, self.extracted, runtime)

    @unittest.skipUnless(os.environ.get("IMG2_CHARACTER_RUN_LIVE_TESTS") == "1",
                         "requires explicitly enabled real bpy producer")
    def test_master_replay_rejects_extra_visible_mesh_rig_and_modifier(self):
        import gate_routed_terminal as gate
        python = subject.native_python()
        source = self.root / "source.blend"
        built = subprocess.run([python, "-I", "-B", str(ROOT / "tests/build_native_rig_fixture.py"),
                                "--out", str(source)], env=gate.child_environment(),
                               capture_output=True, text=True, timeout=120)
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        native = {"source": {"path": source.name, "sha256": gate.file_sha(source)},
                  "spec": {"armature": "DiagnosticRig", "meshes": ["DiagnosticBody"], "actions": ["nod"]}}
        subject.run_native(api.Evidence(self.root), native, self.root / "original")
        master = self.root / "original/character.blend"
        # Prove the unmodified actual master satisfies the same replay boundary.
        subject.run_native(api.Evidence(self.root), native, self.root / "valid-replay",
                           master={"path": "original/character.blend", "sha256": gate.file_sha(master)})
        mutations = {
            "mesh": ("bpy.ops.mesh.primitive_cube_add(); "
                     "bpy.context.object.name='UnapprovedVisibleGeometry'", "every renderable mesh"),
            "rig": ("data=bpy.data.armatures.new('UnapprovedRig'); "
                    "obj=bpy.data.objects.new('UnapprovedRig',data); "
                    "bpy.context.collection.objects.link(obj)", "only the approved armature"),
            "modifier": ("bpy.data.objects['DiagnosticBody'].modifiers.new(name='UnapprovedDeform',type='DISPLACE')",
                         "owned linear binding"),
        }
        for name, (mutation, reason) in mutations.items():
            with self.subTest(mutation=name):
                changed = self.root / f"{name}.blend"
                script = ("import bpy; bpy.context.preferences.filepaths.use_scripts_auto_execute=False; "
                          f"bpy.ops.wm.open_mainfile(filepath={str(master)!r},load_ui=False,use_scripts=False); "
                          + mutation + "; "
                          f"bpy.ops.wm.save_as_mainfile(filepath={str(changed)!r},check_existing=False)")
                edited = subprocess.run([python, "-I", "-B", "-c", script], env=gate.child_environment(),
                                        capture_output=True, text=True, timeout=120)
                self.assertEqual(edited.returncode, 0, edited.stdout + edited.stderr)
                with self.assertRaisesRegex(ValueError, reason):
                    subject.run_native(api.Evidence(self.root), native, self.root / f"replay-{name}",
                                       master={"path": changed.name, "sha256": gate.file_sha(changed)})

    def test_child_cannot_supply_an_executable_or_measurement_callback(self):
        with self.assertRaisesRegex(ValueError, "source blend and explicit binding spec"):
            subject.run_native(api.Evidence(self.root), {"source": {}, "spec": {}, "callback": "pass"}, self.root / "capture")


if __name__ == "__main__":
    unittest.main()
