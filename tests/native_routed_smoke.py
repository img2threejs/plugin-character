#!/usr/bin/env python3
"""Opt-in REAL bpy + browser synthetic-geometry diagnostic, never qualification.

Creates a disposable fixture, executes the owned native/build/delivery/terminal
programs, and requires actual nonzero native deformation and all twelve gates.
No generated pass metrics, fake captures, fixture-expert labels or dependency installs.
"""
import argparse
import itertools
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import gate_routed_terminal as gate
import produce_routed_rig as producer
import rigged_artifact as api
import routed_native


def smoke(workspace):
    workspace.mkdir(parents=True, exist_ok=False)
    evidence = api.Evidence(workspace)
    python = routed_native.native_python()
    source = workspace / "source.blend"
    result = subprocess.run([python, "-I", "-B", str(ROOT / "tests/build_native_rig_fixture.py"), "--out", str(source)],
                            env=gate.child_environment(), capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise ValueError("real native fixture creation failed: " + result.stderr + result.stdout)
    native = {"source": {"path": source.name, "sha256": gate.file_sha(source)},
              "spec": {"armature": "DiagnosticRig", "meshes": ["DiagnosticBody"], "actions": ["nod"]}}
    inputs = producer.native_build(workspace, {"native": native}, "native-build")
    captured = evidence.read(inputs["nativeCapture"])
    displacement = max(math.dist(a, b) for sample in captured["poseSamples"]["nod"]
                       for a, b in zip(sample["meshes"]["DiagnosticBody"], captured["restWorld"]["DiagnosticBody"]))
    if displacement <= 0:
        raise ValueError("native diagnostic did not produce real deformation")
    extracted = api.extract_glb(evidence.path(inputs["glb"]["path"]))
    nodes = {node["name"]: i for i, node in enumerate(extracted["rig"]._document["nodes"]) if "name" in node}
    names = [clip["name"] for clip in extracted["clips"]]
    if names != ["nod"]:
        raise ValueError("native action was not exported as the actual expected clip")
    notes = evidence.save("diagnostic-authorship.json", {
        "kind": "synthetic-native-wiring-fixture", "qualification": False,
        "sideLabels": "Authored fixture left is +X and right is -X, not inferred from runtime",
        "stance": "Authored nod action moves only head; fixture feet are stationary",
        "metric": "Authored root-to-hips distance is exactly 0.5 metres",
        "roi": "Authored interior centre patch of synthetic sphere, not real-character segmentation",
        "control": "Explicit stock-linear self-control: no custom weight blending is used"})
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    image = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
             + chunk(b"IDAT", zlib.compress(b"\0\x7f\x7f\x7f")) + chunk(b"IEND", b""))
    (workspace / "reference.png").write_bytes(image)
    reference = {"path": "reference.png", "sha256": api.digest(image)}
    evidence.save("state.json", {"routeChild": {"runId": "synthetic-native-smoke", "objectId": "character-1",
                  "revision": 1, "ownerRoute": "plugin:character@diagnostic#character-mesh>rigged-character",
                  "outputKind": "rigged-3d", "cropSha256": reference["sha256"]},
                  "artifacts": {"reference": reference["path"]}})
    duration = extracted["rig"].clips[0].duration
    motion = evidence.save("motion.json", {"glbSha256": inputs["glb"]["sha256"],
              "landmarkNodes": {name: nodes[bone] for name, bone in {"hip": "hips", "head": "head",
                                  "foot.l": "foot.l", "foot.r": "foot.r", "hand.l": "hand.l", "hand.r": "hand.r"}.items()},
              "sideLabels": {str(nodes[name]): side for name, side in
                              {"thigh.l": "l", "thigh.r": "r", "clavicle.l": "l", "clavicle.r": "r"}.items()},
              "sideLabelSource": notes, "stanceSource": notes,
              "stance": {"nod": {"foot.l": [[0, duration]], "foot.r": [[0, duration]]}}})
    axes = {"clips": names, "times": [0, .25, .5, 1], "sides": ["front", "back"], "azimuths": [0, 90]}
    roi_bytes = bytes(1 if 28 <= x < 36 and 28 <= y < 36 else 0 for y in range(64) for x in range(64))
    (workspace / "interior.roi").write_bytes(roi_bytes)
    roi = {"path": "interior.roi", "sha256": api.digest(roi_bytes)}
    frames = []
    for index, (clip, time, side, azimuth) in enumerate(itertools.product(*axes.values())):
        pose = {"clip": clip, "time": time, "side": side, "azimuth": azimuth}
        angle = math.radians(azimuth + (180 if side == "back" else 0))
        c, s = math.cos(angle), math.sin(angle)
        camera = evidence.save(f"camera-{index}.json", {**pose,
                  "glbSha256": inputs["glb"]["sha256"], "baselineGlbSha256": inputs["glb"]["sha256"],
                  "matrixWorld": [c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, 3*s, .5, 3*c, 1],
                  "projectionMatrix": [4/3, 0, 0, 0, 0, 4/3, 0, 0, 0, 0, -2/9.9, 0, 0, 0, -10.1/9.9, 1]})
        frames.append({**pose, "width": 64, "height": 64, "camera": camera, "roi": roi})
    sweep = evidence.save("sweep-plan.json", {"kind": "img2.character-sweep", "version": 1,
                          "glbSha256": inputs["glb"]["sha256"], "baselineGlb": inputs["glb"],
                          "roiSource": notes, "creaseLuminanceMax": 32, "axes": axes, "frames": frames})
    request = {**inputs, "objectId": "character-1", "motion": motion, "sweep": sweep,
               "metricAnchor": {"nodes": [nodes["root"], nodes["hips"]], "metres": .5,
                                "source": notes, "method": "authored synthetic fixture 0.5 metre root/hips span"}}
    produced = producer.deliver(workspace, request, "delivery")
    command = [sys.executable, str(ROOT / "tools/gate_routed_terminal.py"),
               "--workspace", str(workspace), "--artifact", "artifact.json"]
    retained = []
    for attempt in range(2):
        # Separate processes close every first-run handle before terminal replay.
        terminal = subprocess.run(command, capture_output=True, text=True, timeout=360)
        if terminal.returncode:
            raise ValueError("actual routed terminal program blocked: " + terminal.stdout + terminal.stderr)
        verdict = json.loads(terminal.stdout)
        if verdict["status"] != "pass":
            raise ValueError("actual routed terminal did not return pass")
        verdict_evidence = verdict["evidence"]
        if len(verdict_evidence["gates"]) != 12 or any(row["status"] != "pass" for row in verdict_evidence["gates"]):
            raise ValueError("native wiring diagnostic did not pass every actual rig gate")
        if (verdict_evidence["native"]["parity"]["maxNativeDisplacement"] <= 0
                or verdict_evidence["native"]["parity"]["maxBrowserDisplacement"] <= 0):
            raise ValueError("actual native/browser diagnostic animation was static")
        for ref in retained:
            evidence.read(ref, json_data=False)
        if attempt == 0:
            first_measurement = verdict_evidence["measurement"]
            retained = [first_measurement, verdict_evidence["capture"],
                        *verdict_evidence["native"]["captureFiles"]]
    summary = {"kind": "img2.character-native-smoke", "qualification": False,
               "artifact": produced["artifact"], "nativeDeformation": displacement,
               "nativeParity": verdict_evidence["native"]["parity"],
               "firstMeasurement": first_measurement,
               "measurement": verdict_evidence["measurement"], "gates": verdict_evidence["gates"]}
    evidence.save("smoke-result.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True, help="new disposable diagnostic directory")
    args = parser.parse_args()
    try:
        print(json.dumps(smoke(args.workspace.resolve()), allow_nan=False))
    except Exception as error:
        print("real native diagnostic blocked: " + str(error), file=sys.stderr)
        raise SystemExit(2)
