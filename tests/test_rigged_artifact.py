"""D18 protocol/counterexample tests, NOT real-image or browser-sweep qualification.

The positive case decodes a real generated GLB and executes its actual skeleton and
tracks through installed Three.js. RGBA seam fixtures are synthetic diagnostic pixels;
a complete real browser/oracle sweep remains a separate release requirement.
"""
import copy
import itertools
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import rigged_artifact as subject
import rig_mesh_parity as parity
from test_gate_rigging import JOINTS, SIDE_LABELS


def fixture_glb(path, *, skin=True, animation=True, bad_inverse=False, scene=0):
    binary, views, accessors = bytearray(), [], []
    def add(values, kind, components, fmt="f", component_type=5126):
        binary.extend(b"\0" * (-len(binary) % 4))
        data = struct.pack(f"<{len(values)}{fmt}", *values)
        views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(data)})
        binary.extend(data)
        accessors.append({"bufferView": len(views) - 1, "componentType": component_type,
                          "type": kind, "count": len(values) // components})
        return len(accessors) - 1
    ids = {joint["id"]: i for i, joint in enumerate(JOINTS)}
    nodes = [{"name": joint["id"], "translation": joint["localPosition"], "children": []} for joint in JOINTS]
    worlds = []
    for i, joint in enumerate(JOINTS):
        parent = joint["parent"]
        parent_world = [0, 0, 0] if parent is None else worlds[ids[parent]]
        worlds.append([a + b for a, b in zip(parent_world, joint["localPosition"])])
        if parent is not None:
            nodes[ids[parent]]["children"].append(i)
    order = list(reversed(range(len(JOINTS))))  # Deliberately NOT traversal order.
    vertices = [[(i % 11) / 10 - .5, (i // 11) / 5, -.2 if i % 2 else .2] for i in range(66)]
    attributes = {"POSITION": add([v for row in vertices for v in row], "VEC3", 3),
                  "NORMAL": add([0, 0, 1] * 66, "VEC3", 3),
                  "TEXCOORD_0": add([0, 0] * 66, "VEC2", 2)}
    if skin:
        attributes["JOINTS_0"] = add([order.index(0), 0, 0, 0] * 66, "VEC4", 4, "H", 5123)
        attributes["WEIGHTS_0"] = add([1, 0, 0, 0] * 66, "VEC4", 4)
    mesh_node = len(nodes)
    nodes[0]["children"].append(mesh_node)
    nodes.append({"name": "Body", "mesh": 0, **({"skin": 0} if skin else {})})
    document = {"asset": {"version": "2.0"}, "scene": scene, "scenes": [{"nodes": [0]}],
                "nodes": nodes, "meshes": [{"primitives": [{"attributes": attributes}]}]}
    if skin:
        inverse = []
        for index in order:
            x, y, z = worlds[index]
            inverse.extend([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -x, -y, -z, 1])
        if bad_inverse:
            inverse = inverse[:-16]
        document["skins"] = [{"joints": order, "skeleton": 0,
                              "inverseBindMatrices": add(inverse, "MAT4", 16)}]
    if animation:
        times = add([0, 1], "SCALAR", 1)
        head = JOINTS[ids["head"]]["localPosition"]
        values = add([*head, head[0], head[1] + .02, head[2]], "VEC3", 3)
        document["animations"] = [{"name": "nod", "samplers": [{"input": times, "output": values}],
                                   "channels": [{"sampler": 0, "target": {"node": ids["head"], "path": "translation"}}]}]
    document.update({"buffers": [{"byteLength": len(binary)}], "bufferViews": views, "accessors": accessors})
    data = json.dumps(document).encode()
    data += b" " * (-len(data) % 4)
    binary.extend(b"\0" * (-len(binary) % 4))
    body = struct.pack("<II", len(data), 0x4e4f534a) + data + struct.pack("<II", len(binary), 0x004e4942) + binary
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body)
    return ids


class RiggedArtifactTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        self.ids = fixture_glb(self.workspace / "character.glb")

    def put(self, name, value):
        data = value if isinstance(value, bytes) else subject.canonical(value)
        (self.workspace / name).write_bytes(data)
        return {"path": name, "sha256": subject.digest(data)}

    def ref(self, name):
        return {"path": name, "sha256": subject.digest((self.workspace / name).read_bytes())}

    def case(self, *, real_runtime=False):
        extracted = subject.extract_glb(self.workspace / "character.glb")
        glb_ref = self.ref("character.glb")
        if real_runtime:
            process = subprocess.run(["node", str(ROOT / "tests" / "measure-rig-fixture.mjs"),
                                      str(self.workspace / "character.glb"), str(self.workspace / "runtime.json")],
                                     text=True, capture_output=True)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            runtime = self.ref("runtime.json")
        else:
            # Negative tests need no pretend passing measurement producer.
            runtime = self.put("runtime.json", {"kind": "img2.character-runtime-measurements", "version": 1,
                               "glbSha256": glb_ref["sha256"], "meshBuffers": extracted["meshBuffers"], "measurements": {}})
        frozen_meshes = copy.deepcopy(extracted["meshBuffers"])
        for mesh in frozen_meshes["meshes"]:
            mesh["attributes"].pop("skinIndex")
            mesh["attributes"].pop("skinWeight")
        frozen = self.put("freeze.json", parity.freeze(frozen_meshes).to_dict())
        notes = self.put("source-notes.txt", b"Synthetic fixture: independently labelled sides, stationary feet, 0.5 metre hip anchor. Not a real subject.")
        motion = self.put("motion.json", {"glbSha256": glb_ref["sha256"],
                          "landmarkNodes": {name: self.ids[bone] for name, bone in
                                            {"hip": "hips", "head": "head", "foot.l": "foot.l", "foot.r": "foot.r",
                                             "hand.l": "upperarm.l", "hand.r": "upperarm.r"}.items()},
                          "sideLabels": {str(self.ids[name]): label for name, label in SIDE_LABELS.items()},
                          "sideLabelSource": notes, "stanceSource": notes,
                          "stance": {"nod": {"foot.l": [[0, 1]], "foot.r": [[0, 1]]}}})
        baseline = self.put("baseline.glb", (self.workspace / "character.glb").read_bytes())
        candidate_pixels = self.put("candidate.rgba", bytes([200, 150, 120, 255] * 4))
        baseline_pixels = self.put("baseline.rgba", bytes([200, 150, 120, 255] * 3 + [0, 0, 0, 0]))
        roi = self.put("interior.roi", bytes([1, 1, 1, 1]))
        axes = {"clips": ["nod"], "times": [0, .25, .5, 1], "sides": ["front", "back"], "azimuths": [0, 90]}
        frames = []
        for i, (clip, time, side, azimuth) in enumerate(itertools.product(
                axes["clips"], axes["times"], axes["sides"], axes["azimuths"])):
            pose = {"clip": clip, "time": time, "side": side, "azimuth": azimuth}
            camera = self.put(f"camera-{i}.json", {"kind": "synthetic-test-camera", **pose,
                              "glbSha256": glb_ref["sha256"], "baselineGlbSha256": baseline["sha256"],
                              "projectionMatrix": list(subject.glb.IDENTITY_MATRIX),
                              "matrixWorld": list(subject.glb.IDENTITY_MATRIX)})
            frames.append({**pose, "width": 2, "height": 2, "candidate": candidate_pixels,
                           "baseline": baseline_pixels, "roi": roi, "camera": camera})
        sweep = self.put("sweep.json", {"kind": "img2.character-sweep", "version": 1,
                         "glbSha256": glb_ref["sha256"], "baselineGlb": baseline,
                         "creaseLuminanceMax": 32, "roiSource": notes, "axes": axes, "frames": frames})
        return {"objectId": "character-1", "glb": glb_ref, "runtime": runtime, "freezeManifest": frozen,
                "motion": motion, "sweep": sweep,
                "metricAnchor": {"nodes": [0, self.ids["hips"]], "metres": .5,
                                 "source": notes, "method": "explicit synthetic fixture metric anchor"}}

    def test_extracts_actual_skin_order_inverse_binds_and_animation_values(self):
        result = subject.extract_glb(self.workspace / "character.glb")
        self.assertEqual(result["skeleton"]["skin"]["joints"], list(reversed(range(len(JOINTS)))))
        self.assertEqual(result["clips"][0]["samplers"][0]["times"], [0, 1])
        self.assertNotEqual(result["clips"][0]["samplers"][0]["values"][0], result["clips"][0]["samplers"][0]["values"][1])
        self.assertEqual(len(result["binding"]["positions"]), 66)

    def test_missing_skin_is_never_a_rig(self):
        fixture_glb(self.workspace / "no-skin.glb", skin=False)
        with self.assertRaisesRegex(ValueError, "no skin"):
            subject.extract_glb(self.workspace / "no-skin.glb")

    def test_missing_inverse_bind_data_is_not_replaced_by_identity(self):
        fixture_glb(self.workspace / "broken.glb", bad_inverse=True)
        with self.assertRaisesRegex(ValueError, "inverse binds"):
            subject.extract_glb(self.workspace / "broken.glb")

    def test_static_rig_is_extractable_but_no_static_acceptance_is_invented(self):
        fixture_glb(self.workspace / "static.glb", animation=False)
        self.assertEqual(subject.extract_glb(self.workspace / "static.glb")["clips"], [])

    def test_invalid_scene_index_is_not_interpreted_as_python_negative_index(self):
        fixture_glb(self.workspace / "bad-scene.glb", scene=-1)
        with self.assertRaisesRegex(ValueError, "selected scene"):
            subject.extract_glb(self.workspace / "bad-scene.glb")

    def test_extraction_cannot_overwrite_its_source(self):
        fixture_glb(self.workspace / "skeleton.json")
        before = (self.workspace / "skeleton.json").read_bytes()
        code = subject.main(["extract", str(self.workspace / "skeleton.json"), "--out", str(self.workspace)])
        self.assertEqual(code, 2)
        self.assertEqual((self.workspace / "skeleton.json").read_bytes(), before)

    def test_missing_producer_does_not_publish_artifact(self):
        request = self.case()
        with self.assertRaisesRegex(ValueError, "missing measurement producer: bindingSamples"):
            subject.admit(self.workspace, request)
        self.assertFalse((self.workspace / "artifact.json").exists())

    def test_stale_producer_cannot_be_relabelled_as_current(self):
        request = self.case()
        data = json.loads((self.workspace / "runtime.json").read_bytes())
        data["glbSha256"] = "0" * 64
        request["runtime"] = self.put("runtime.json", data)
        with self.assertRaisesRegex(ValueError, "stale runtime"):
            subject.admit(self.workspace, request)

    def test_sweep_counts_actual_pixels_and_requires_every_view(self):
        request = self.case()
        sweep = json.loads((self.workspace / "sweep.json").read_bytes())
        result = subject.measure_sweep(subject.Evidence(self.workspace), sweep, ["nod"], request["glb"]["sha256"],
                                       subject.extract_glb(self.workspace / "character.glb"))
        self.assertEqual(result["backgroundThroughSplitPx"], 0)
        self.assertEqual(result["baseline"]["backgroundThroughSplitPx"], 16)
        sweep["frames"].pop()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            subject.measure_sweep(subject.Evidence(self.workspace), sweep, ["nod"], request["glb"]["sha256"],
                                  subject.extract_glb(self.workspace / "character.glb"))

    def test_sweep_missing_or_stale_raw_pixels_is_not_a_passing_receipt(self):
        request = self.case()
        sweep = json.loads((self.workspace / "sweep.json").read_bytes())
        (self.workspace / "candidate.rgba").write_bytes(b"not the captured bytes")
        with self.assertRaisesRegex(ValueError, "stale evidence"):
            subject.measure_sweep(subject.Evidence(self.workspace), sweep, ["nod"], request["glb"]["sha256"],
                                  subject.extract_glb(self.workspace / "character.glb"))

    def test_missing_camera_measurements_and_foreign_baseline_are_not_accepted(self):
        request = self.case()
        sweep = json.loads((self.workspace / "sweep.json").read_bytes())
        camera = json.loads((self.workspace / sweep["frames"][0]["camera"]["path"]).read_bytes())
        del camera["projectionMatrix"]
        sweep["frames"][0]["camera"] = self.put("missing-camera.json", camera)
        with self.assertRaisesRegex(ValueError, "camera matrices missing"):
            subject.measure_sweep(subject.Evidence(self.workspace), sweep, ["nod"], request["glb"]["sha256"],
                                  subject.extract_glb(self.workspace / "character.glb"))
        fixture_glb(self.workspace / "different-baseline.glb", animation=False)
        sweep["baselineGlb"] = self.ref("different-baseline.glb")
        with self.assertRaisesRegex(ValueError, "baseline does not preserve"):
            subject.measure_sweep(subject.Evidence(self.workspace), sweep, ["nod"], request["glb"]["sha256"],
                                  subject.extract_glb(self.workspace / "character.glb"))

    def test_actual_glb_and_executed_three_measurements_admit_canonical_sidecars(self):
        request = self.case(real_runtime=True)
        artifact = subject.admit(self.workspace, request)
        self.assertEqual(artifact["scaleEstimate"], 1)
        self.assertEqual(artifact["rig"]["clips"][0]["name"], "nod")
        refs = {ref["sha256"]: ref["path"] for ref in artifact["files"]}
        for sha in [artifact["rig"]["skeletonSha"], artifact["rig"]["clips"][0]["sha256"]]:
            data = (self.workspace / refs[sha]).read_bytes()
            self.assertEqual(subject.digest(data), sha)
            self.assertEqual(data, subject.canonical(json.loads(data)))
            self.assertNotEqual(sha, request["glb"]["sha256"])
        self.assertEqual(json.loads((self.workspace / "artifact.json").read_bytes()), artifact)
        baseline = json.loads((self.workspace / request["sweep"]["path"]).read_bytes())["baselineGlb"]
        self.assertNotIn(baseline["path"], {ref["path"] for ref in artifact["files"]})
        record = json.loads((self.workspace / ".img2/artifacts/character/rig-admission.json").read_bytes())
        self.assertIn(baseline, record["boundInputs"])
        self.assertEqual(subject.digest((self.workspace / baseline["path"]).read_bytes()), baseline["sha256"])

    def test_real_cpu_evidence_cannot_hide_changed_frozen_geometry(self):
        request = self.case(real_runtime=True)
        # Freeze an actually different pre-bind mesh, then keep the post-bind GLB unchanged.
        buffers = subject.extract_glb(self.workspace / "character.glb")["meshBuffers"]
        buffers["meshes"][0]["attributes"]["position"][0] += .01
        frozen = parity.freeze(buffers).to_dict()
        request["freezeManifest"] = self.put("freeze.json", frozen)
        with self.assertRaisesRegex(ValueError, "G11:fail"):
            subject.admit(self.workspace, request)
        self.assertFalse((self.workspace / "artifact.json").exists())

    def test_each_missing_runtime_measurement_blocks_even_with_other_real_cpu_data(self):
        request = self.case(real_runtime=True)
        original = json.loads((self.workspace / "runtime.json").read_bytes())
        for missing in ("bindingSamples", "deformation", "bindRestore", "meshVisibility"):
            with self.subTest(missing=missing):
                runtime = copy.deepcopy(original)
                del runtime["measurements"][missing]
                request["runtime"] = self.put("runtime.json", runtime)
                with self.assertRaisesRegex(ValueError, f"missing measurement producer: {missing}"):
                    subject.admit(self.workspace, request)
                self.assertFalse((self.workspace / "artifact.json").exists())

    def test_restoration_regression_blocks_and_retains_diagnostic_gate_evidence(self):
        request = self.case(real_runtime=True)
        runtime = json.loads((self.workspace / "runtime.json").read_bytes())
        runtime["measurements"]["bindRestore"]["maxBindRestoreDelta"] = .01
        request["runtime"] = self.put("runtime.json", runtime)
        with self.assertRaisesRegex(ValueError, "G3:fail"):
            subject.admit(self.workspace, request)
        self.assertFalse((self.workspace / "artifact.json").exists())
        records = list((self.workspace / ".img2/artifacts/character/gates").glob("*.json"))
        self.assertEqual(len(records), 1)
        record = json.loads(records[0].read_bytes())
        self.assertFalse(record["gateReport"]["ok"])
        gate = {"role": "gate", **self.ref(str(records[0].relative_to(self.workspace)))}
        fragment = subject.snapshot_fragment(self.workspace, request["glb"], [gate])
        self.assertIn({"id": "G3", "status": "fail"}, fragment["observations"]["rigGate"]["checks"])
        # Changed measurement bytes invalidate even an unchanged source/gate-report binding.
        self.put("runtime.json", {})
        with self.assertRaisesRegex(ValueError, "stale evidence"):
            subject.snapshot_fragment(self.workspace, request["glb"], [gate])

    def test_snapshot_exposes_fresh_inputs_without_inventing_candidates_or_views(self):
        fragment = subject.snapshot_fragment(self.workspace, self.ref("character.glb"))
        self.assertEqual(set(fragment), {"bindings", "observations"})
        self.assertEqual(fragment["observations"]["rig"]["clipNames"], ["nod"])
        self.assertNotIn("availableViews", fragment["observations"])
        stale = self.ref("character.glb")
        fixture_glb(self.workspace / "character.glb", animation=False)
        with self.assertRaisesRegex(ValueError, "stale evidence"):
            subject.snapshot_fragment(self.workspace, stale)

    def test_route_requires_rig_intent_and_does_not_claim_global_gate_readiness(self):
        card = json.loads((ROOT / "route.json").read_bytes())
        self.assertEqual(card["kind"], "img2.route-card")
        self.assertEqual(card["outputKind"], "rigged-3d")
        self.assertEqual(card["requires"], {"intent": ["rig"]})
        self.assertTrue(all(isinstance(dep["probe"], str) for dep in card["deps"]))
        gate = json.loads((ROOT / "gates.json").read_bytes())[0]
        self.assertFalse(gate["blocking"], "promotion needs the real oracle/browser proof")

    def test_workspace_escape_and_symlink_evidence_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "workspace-relative"):
            subject.Evidence(self.workspace).read({"path": "../elsewhere", "sha256": "a" * 64})
        (self.workspace / "link.glb").symlink_to(self.workspace / "character.glb")
        with self.assertRaisesRegex(ValueError, "symlink"):
            subject.Evidence(self.workspace).read({"path": "link.glb", "sha256": self.ref("character.glb")["sha256"]})


if __name__ == "__main__":
    unittest.main()
