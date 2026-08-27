#!/usr/bin/env python3
"""Tests for tools/gate_rigging.py — the one gate row that runs all twelve rig checks.

The gate carries the img2 bootstrap stanza, so it cannot be imported in-process; every test here
subprocesses it under a temporary IMG2_HOME whose `harness` entry points at the img2 checkout, the
way plugin-hello-cube's tests do.

The load-bearing test is `test_one_failing_check_still_reports_every_other_check`. The twelve
checks are one gate row and not twelve because `img2_core.gate_runner` is stop-the-line: the first
non-passing blocking row halts the run and every later row is recorded "skipped". Twelve rows would
surface one violation and eleven skips; the point of the suite is seeing all of them at once.

The payload fixture is ported from forge/tests/test_rig_gates.py — every measurement inside
tolerance and every coverage axis satisfied — so an all-pass expectation here means the same thing
it means upstream.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TOOLS_DIR = PLUGIN_DIR / "tools"
GATE = TOOLS_DIR / "gate_rigging.py"


def _harness_dir():
    """The img2 checkout: named by IMG2_HARNESS_DIR, else a sibling of this plugin."""
    named = os.environ.get("IMG2_HARNESS_DIR")
    if named:
        return Path(named).expanduser().resolve()
    siblings = PLUGIN_DIR.parent
    for name in ("img2", "img2-harness"):
        if (siblings / name / "img2_core").is_dir():
            return (siblings / name).resolve()
    return (siblings / "img2").resolve()


HARNESS_DIR = _harness_dir()
EXPECTED_EXIT = {"pass": 0, "fail": 1, "error": 2}

H = 1.0

# The joint hierarchy G7 resolves chains from: root -> hip branch (mirrored leg pair + medial
# spine) -> shoulder branch (mirrored arm pair + medial neck).
JOINTS = [
    {"id": "root", "parent": None, "localPosition": [0.0, 0.0, 0.0]},
    {"id": "hips", "parent": "root", "localPosition": [0.0, 0.5, 0.0]},
    {"id": "thigh.l", "parent": "hips", "localPosition": [0.1, -0.05, 0.0]},
    {"id": "thigh.r", "parent": "hips", "localPosition": [-0.1, -0.05, 0.0]},
    {"id": "shin.l", "parent": "thigh.l", "localPosition": [0.0, -0.22, 0.0]},
    {"id": "shin.r", "parent": "thigh.r", "localPosition": [0.0, -0.22, 0.0]},
    {"id": "foot.l", "parent": "shin.l", "localPosition": [0.0, -0.23, 0.0]},
    {"id": "foot.r", "parent": "shin.r", "localPosition": [0.0, -0.23, 0.0]},
    {"id": "spine", "parent": "hips", "localPosition": [0.0, 0.15, 0.0]},
    {"id": "chest", "parent": "spine", "localPosition": [0.0, 0.15, 0.0]},
    {"id": "clavicle.l", "parent": "chest", "localPosition": [0.08, 0.05, 0.0]},
    {"id": "clavicle.r", "parent": "chest", "localPosition": [-0.08, 0.05, 0.0]},
    {"id": "upperarm.l", "parent": "clavicle.l", "localPosition": [0.06, 0.0, 0.0]},
    {"id": "upperarm.r", "parent": "clavicle.r", "localPosition": [-0.06, 0.0, 0.0]},
    {"id": "hand.l", "parent": "upperarm.l", "localPosition": [0.18, -0.12, 0.0]},
    {"id": "hand.r", "parent": "upperarm.r", "localPosition": [-0.18, -0.12, 0.0]},
    {"id": "neck", "parent": "chest", "localPosition": [0.0, 0.06, 0.0]},
    {"id": "head", "parent": "neck", "localPosition": [0.0, 0.12, 0.0]},
]

# The side-label claim comes from OUTSIDE the geometry. Without it the chain resolver assigns
# left = +X and G7 compares the geometry against itself, which reports unevaluated, not pass.
SIDE_LABELS = {"thigh.l": "l", "thigh.r": "r", "clavicle.l": "l", "clavicle.r": "r"}

_TORSO_POSITION = [0.0, 0.0, 0.0, 0.1, 0.0, 0.0, 0.1, 0.2, 0.0, 0.0, 0.2, 0.0]
_TORSO_NORMAL = [0.0, 0.0, 1.0] * 4
_TORSO_UV = [0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0]
_TORSO_INDEX = [0, 1, 2, 0, 2, 3]
_ARM_POSITION = [0.2, 0.5, 0.0, 0.3, 0.5, 0.0, 0.3, 0.6, 0.0]
_ARM_NORMAL = [0.0, 0.0, 1.0] * 3
_ARM_UV = [0.0, 0.0, 1.0, 0.0, 1.0, 1.0]
_ARM_INDEX = [0, 1, 2]


def _walk_clip():
    times = [0.0, 0.24, 0.48, 0.72, 0.96, 1.2]
    hip_z = [0.0, 0.096, 0.192, 0.288, 0.384, 0.48]
    return {
        "sourceName": "walk-forward",
        "duration": 1.2,
        "sampleTimes": list(times),
        "landmarkPositions": {
            "hip": [[0.0, 0.5, z] for z in hip_z],
            "head": [[0.0, 0.95, z] for z in hip_z],
            "hand.l": [[0.16, 0.72, z] for z in hip_z],
            "hand.r": [[-0.16, 0.72, z] for z in hip_z],
            "foot.l": [
                [0.1, 0.0, 0.0],
                [0.1, 0.0, 0.0],
                [0.1, 0.0, 0.0],
                [0.1, 0.05, 0.24],
                [0.1, 0.02, 0.40],
                [0.1, 0.0, 0.48],
            ],
            "foot.r": [
                [-0.1, 0.0, -0.24],
                [-0.1, 0.05, 0.0],
                [-0.1, 0.02, 0.12],
                [-0.1, 0.0, 0.24],
                [-0.1, 0.0, 0.24],
                [-0.1, 0.0, 0.24],
            ],
        },
        "jointScaleDelta": [0.0] * len(times),
        "poseReturn": 0.1,
        "stance": {"foot.l": [[0.0, 0.48]], "foot.r": [[0.72, 1.2]]},
    }


def _idle_clip():
    times = [0.0, 0.5, 1.0]
    return {
        "sourceName": "idle-still",
        "duration": 1.0,
        "sampleTimes": list(times),
        "landmarkPositions": {
            "hip": [[0.0, 0.5, 0.0]] * 3,
            "head": [[0.0, 0.95, 0.0]] * 3,
            "hand.l": [[0.16, 0.72, 0.0]] * 3,
            "hand.r": [[-0.16, 0.72, 0.0]] * 3,
            "foot.l": [[0.1, 0.0, 0.0]] * 3,
            "foot.r": [[-0.1, 0.0, 0.0]] * 3,
        },
        "jointScaleDelta": [0.0] * len(times),
        "poseReturn": 0.0,
        "stance": {"foot.l": [[0.0, 1.0]], "foot.r": [[0.0, 1.0]]},
    }


def _binding():
    return {
        "positions": [[0.0, 0.0, 0.0], [0.1, 0.0, 0.0]],
        "partIds": ["torso", "arm"],
        "skinIndices": [0, 1, 2, 3, 1, 2, 3, 0],
        "skinWeights": [0.25] * 8,
        "jointCount": 4,
    }


def _mesh(name, position, normal, uv, index, skinning=False):
    attributes = {"position": list(position), "normal": list(normal), "uv": list(uv)}
    if skinning:
        vertices = len(position) // 3
        # The one thing rigging is allowed to add: skinIndex/skinWeight are outside FROZEN_BUFFERS.
        attributes["skinIndex"] = [0, 1, 0, 0] * vertices
        attributes["skinWeight"] = [1.0, 0.0, 0.0, 0.0] * vertices
    return {"name": name, "attributes": attributes, "index": list(index)}


def _pre_rig_meshes():
    return {
        "meshes": [
            _mesh("torso", _TORSO_POSITION, _TORSO_NORMAL, _TORSO_UV, _TORSO_INDEX),
            _mesh("arm", _ARM_POSITION, _ARM_NORMAL, _ARM_UV, _ARM_INDEX),
        ]
    }


def _post_rig_meshes():
    return {
        "meshes": [
            _mesh("torso", _TORSO_POSITION, _TORSO_NORMAL, _TORSO_UV, _TORSO_INDEX, skinning=True),
            _mesh("arm", _ARM_POSITION, _ARM_NORMAL, _ARM_UV, _ARM_INDEX, skinning=True),
        ]
    }


def _freeze_manifest():
    """Built by calling the ported rig_mesh_parity.freeze rather than hand-written, so the manifest and
    the post-rig payload cannot drift apart and hand us a green test for the wrong reason."""
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))
    import rig_mesh_parity
    return rig_mesh_parity.freeze(_pre_rig_meshes()).to_dict()


def _glb_report():
    return {
        "schemaVersion": 1,
        "kind": "glb-rig-reference",
        "path": "character.glb",
        "nodeCount": 48,
        "skinCount": 1,
        "clipCount": 2,
        "primarySkinIndex": 0,
        "inverseBindSource": "accessor",
        "unsupportedInterpolationClips": [],
        "structuralFailure": None,
        "warnings": [],
        "errors": [],
    }


def full_payload():
    """Every measurement inside tolerance and every coverage axis satisfied."""
    return {
        "figureHeight": H,
        "landmarks": ["hip", "head", "hand.l", "hand.r", "foot.l", "foot.r"],
        "clips": [_walk_clip(), _idle_clip()],
        "sourceScalesJoints": False,
        "bindingSamples": {
            "maxSampledBindingDelta": 3.0e-9,
            "clips": {"walk-forward": 5, "idle-still": 6},
        },
        "deformation": {
            "nonFiniteCount": 0,
            "allFinite": True,
            "meshes": {
                "body": {"frames": 4, "verticesPerFrame": 64},
                "hair": {"frames": 4, "verticesPerFrame": [64, 80, 64, 96]},
            },
        },
        "bindRestore": {"maxBindRestoreDelta": 0.0},
        "binding": _binding(),
        "meshVisibility": {
            "visibleMeshCount": 3,
            "visibleSkinnedMeshCount": 3,
            "unboundMeshes": [],
        },
        "chainAnchors": {"joints": JOINTS, "sideLabels": SIDE_LABELS},
        "skinIntegritySweep": {
            "frames": 32,
            "clips": 2,
            "times": 4,
            "sides": 2,
            "azimuths": 2,
            "backgroundThroughSplitPx": 287,
            "backgroundThroughSplitBlobs": 15,
            "creasePx": 36470,
            "baseline": {
                "backgroundThroughSplitPx": 974,
                "backgroundThroughSplitBlobs": 30,
                "creasePx": 31316,
            },
        },
        "meshParity": {"manifest": _freeze_manifest(), "after": _post_rig_meshes()},
        "rigReference": {"source": "glb", "glb": _glb_report()},
    }


class GateRiggingTest(unittest.TestCase):
    def setUp(self):
        if not (HARNESS_DIR / "img2_core").is_dir():
            self.skipTest("img2 harness checkout not found at %s" % HARNESS_DIR)
        if not (TOOLS_DIR / "rig_gate_core.py").is_file():
            self.skipTest("tools/rig_gate_core.py has not landed yet")
        base = Path(tempfile.mkdtemp(prefix="character-gate-test-"))
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        self.home = base / "img2home"
        self.home.mkdir()
        (self.home / "harness").symlink_to(HARNESS_DIR)
        self.workspace = base / "workspace"
        self.workspace.mkdir()
        self.payload_path = self.workspace / ".img2" / "artifacts" / "character" / "rig-gate-payload.json"
        self.env = {**os.environ, "IMG2_HOME": str(self.home)}
        self.env.pop("IMG2THREEJS_HOME", None)

    # -- helpers ------------------------------------------------------------------------------

    def write_payload(self, payload):
        self.payload_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, str):
            self.payload_path.write_text(payload, encoding="utf-8")
        else:
            self.payload_path.write_text(json.dumps(payload), encoding="utf-8")

    def run_gate(self):
        return subprocess.run(
            [sys.executable, str(GATE), "--workspace", str(self.workspace)],
            capture_output=True, text=True, env=self.env, cwd=self.workspace,
        )

    def verdict(self, proc):
        """Exactly one JSON object on stdout, shaped like an img2 gate verdict."""
        doc, end = json.JSONDecoder().raw_decode(proc.stdout.lstrip())
        self.assertEqual(proc.stdout.lstrip()[end:].strip(), "",
                         "stdout carried more than one JSON object")
        self.assertIsInstance(doc, dict)
        self.assertEqual(doc["kind"], "img2.gate-verdict")
        self.assertEqual(doc["version"], 1)
        self.assertEqual(doc["gate"], "rigging")
        self.assertEqual(doc["plugin"], "character")
        self.assertIn(doc["status"], EXPECTED_EXIT)
        self.assertIsInstance(doc["reasons"], list)
        self.assertIsInstance(doc["evidence"], dict)
        self.assertEqual(proc.returncode, EXPECTED_EXIT[doc["status"]],
                         "exit %d disagrees with status %r" % (proc.returncode, doc["status"]))
        if doc["status"] != "pass":
            self.assertTrue(doc["reasons"], "a non-pass verdict must carry reasons")
        return doc

    # -- the three outcomes -------------------------------------------------------------------

    def test_all_pass_payload_passes(self):
        self.write_payload(full_payload())
        proc = self.run_gate()
        doc = self.verdict(proc)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(doc["status"], "pass")
        self.assertEqual(doc["reasons"], [])
        self.assertTrue(doc["evidence"]["ok"])
        self.assertEqual(doc["evidence"]["failed"], [])
        self.assertEqual(doc["evidence"]["unevaluated"], [])
        self.assertEqual(len(doc["evidence"]["gates"]), 12)

    def test_one_failing_check_still_reports_every_other_check(self):
        """The reason this is one gate row and not twelve: nothing is skipped."""
        payload = full_payload()
        payload["bindRestore"]["maxBindRestoreDelta"] = 1.0e-6  # G3: pose bleed between clips
        self.write_payload(payload)
        proc = self.run_gate()
        doc = self.verdict(proc)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(doc["status"], "fail")
        self.assertEqual(doc["evidence"]["failed"], ["G3"])
        self.assertTrue(any("G3" in reason for reason in doc["reasons"]),
                        "the failing check is not named in reasons: %r" % (doc["reasons"],))
        rows = doc["evidence"]["gates"]
        self.assertEqual([row["id"] for row in rows],
                         ["G%d" % n for n in range(1, 13)])
        for row in rows:
            self.assertIn(row["status"], ("pass", "fail", "unevaluated"))
            self.assertNotEqual(row["status"], "skipped")
        self.assertEqual([row["id"] for row in rows if row["status"] == "fail"], ["G3"])
        self.assertEqual(len([row for row in rows if row["status"] == "pass"]), 11)

    def test_unevaluated_check_is_an_error_and_never_a_status(self):
        payload = full_payload()
        payload.pop("bindRestore")  # G3's only input; nothing else consumes it
        self.write_payload(payload)
        proc = self.run_gate()
        doc = self.verdict(proc)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertEqual(doc["status"], "error")
        self.assertNotEqual(doc["status"], "unevaluated")
        self.assertEqual(doc["evidence"]["failed"], [])
        self.assertEqual(doc["evidence"]["unevaluated"], ["G3"])
        self.assertIn("unevaluated", json.dumps(doc["evidence"]))
        self.assertTrue(any("G3" in reason for reason in doc["reasons"]),
                        "the unevaluated check is not named in reasons: %r" % (doc["reasons"],))
        self.assertTrue(any("bindRestore" in reason for reason in doc["reasons"]),
                        "the absent input is not named in reasons: %r" % (doc["reasons"],))
        self.assertEqual(len(doc["evidence"]["gates"]), 12)

    def test_missing_payload_is_an_error_naming_the_path(self):
        proc = self.run_gate()
        doc = self.verdict(proc)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertEqual(doc["status"], "error")
        self.assertTrue(any(str(self.payload_path) in reason for reason in doc["reasons"]),
                        "the missing path is not named in reasons: %r" % (doc["reasons"],))

    def test_unreadable_payload_is_an_error(self):
        self.write_payload("{not json at all")
        proc = self.run_gate()
        doc = self.verdict(proc)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertEqual(doc["status"], "error")
        self.assertTrue(any(str(self.payload_path) in reason for reason in doc["reasons"]))

    # -- envelope shape and exit-code agreement ------------------------------------------------

    def test_stdout_is_exactly_one_verdict_envelope(self):
        self.write_payload(full_payload())
        proc = self.run_gate()
        self.assertEqual(len([line for line in proc.stdout.splitlines() if line.strip()]), 1)
        doc = json.loads(proc.stdout)
        self.assertEqual(doc["kind"], "img2.gate-verdict")
        self.assertEqual(doc["version"], 1)

    def test_exit_code_agrees_with_status_for_all_three_outcomes(self):
        passing = full_payload()
        failing = full_payload()
        failing["bindRestore"]["maxBindRestoreDelta"] = 1.0e-6
        unevaluated = full_payload()
        unevaluated.pop("bindRestore")
        seen = []
        for payload, expected in ((passing, "pass"), (failing, "fail"), (unevaluated, "error")):
            self.write_payload(payload)
            proc = self.run_gate()
            doc = self.verdict(proc)  # verdict() asserts exit == EXPECTED_EXIT[status]
            self.assertEqual(doc["status"], expected, proc.stdout + proc.stderr)
            seen.append((doc["status"], proc.returncode))
        self.assertEqual(seen, [("pass", 0), ("fail", 1), ("error", 2)])

    # -- through the real runner ---------------------------------------------------------------

    def run_gate_runner(self):
        env = {**self.env, "PYTHONPATH": str(self.home / "harness")}
        return subprocess.run(
            [sys.executable, "-m", "img2_core.gate_runner",
             "--plugin-dir", str(PLUGIN_DIR), "--workspace", str(self.workspace)],
            capture_output=True, text=True, env=env, cwd=self.workspace,
        )

    def test_gate_runner_end_to_end_pass(self):
        self.write_payload(full_payload())
        proc = self.run_gate_runner()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        doc = json.loads(proc.stdout)
        self.assertEqual(doc["kind"], "img2.gate-run")
        self.assertFalse(doc["stopped"])
        [result] = doc["results"]
        self.assertEqual(result["gate"], "rigging")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["envelope"]["plugin"], "character")

    def test_gate_runner_end_to_end_blocking_fail(self):
        payload = full_payload()
        payload["bindRestore"]["maxBindRestoreDelta"] = 1.0e-6
        self.write_payload(payload)
        proc = self.run_gate_runner()
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        doc = json.loads(proc.stdout)
        [result] = doc["results"]
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["exitCode"], 1)
        # The runner keeps the envelope, so every one of the twelve checks reaches the reader.
        self.assertEqual(len(result["envelope"]["evidence"]["gates"]), 12)


if __name__ == "__main__":
    unittest.main()
