#!/usr/bin/env python3
"""Real native build and owned-browser D18 production; no acceptance authority.

native: freeze the unbound source and add the declared armature modifier, never
       auto-weight/rebind or repair geometry.
deliver: run actual browser producers for an authored matched-camera/ROI plan,
         compare actual Blender evaluated poses, then emit the existing D18 artifact.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import rigged_artifact as api
import routed_native
import gate_routed_terminal as gate


def native_build(workspace, request, out):
    evidence = api.Evidence(workspace)
    destination = evidence.path(out)
    native = request["native"]
    receipt, identity = routed_native.run_native(evidence, native, destination)
    frozen = routed_native.freeze_export(destination / "base.glb", destination / "character.glb", native["spec"])
    def ref(name):
        path = destination / name
        return {"path": path.relative_to(evidence.root).as_posix(), "sha256": gate.file_sha(path)}
    freeze = evidence.save(f"{out}/freeze.json", frozen)
    inputs = {"native": native, "glb": ref("character.glb"), "nativeCapture": ref("native.json"),
              "nativeMaster": ref("character.blend"), "freezeManifest": freeze}
    evidence.save(f"{out}/native-inputs.json", inputs)
    evidence.save(f"{out}/native-execution.json", {"kind": "img2.character-native-execution", "version": 1,
                  "inputs": inputs, "executable": identity})
    return inputs


def deliver(workspace, request, out):
    evidence = api.Evidence(workspace)
    request = deepcopy(request)
    if "runtime" in request:
        raise ValueError("deliver creates runtime measurements; it never accepts a supplied runtime file")
    # Use the same route identity checks as terminal admission, before expensive producers.
    state = gate.strict_json(evidence.path("state.json").read_bytes())
    child = state.get("routeChild", {})
    if child.get("objectId") != request["objectId"] or child.get("outputKind") != "rigged-3d":
        raise ValueError("delivery request does not match routed child identity")
    evidence.read({"path": state["artifacts"]["reference"], "sha256": child["cropSha256"]}, json_data=False)
    evidence.read(request["glb"], json_data=False)
    native = evidence.read(request["nativeCapture"])
    extracted = api.extract_glb(evidence.path(request["glb"]["path"]))
    sweep = evidence.read(request["sweep"])
    if sweep["glbSha256"] != request["glb"]["sha256"]:
        raise ValueError("sweep plan refers to foreign delivery")
    evidence.read(sweep["baselineGlb"], json_data=False)
    frames = []
    for frame in sweep["frames"]:
        if "candidate" in frame or "baseline" in frame:
            raise ValueError("delivery takes a capture plan, never preaccepted raw sweep buffers")
        camera = evidence.read(frame["camera"])
        if (type(frame["width"]) is not int or type(frame["height"]) is not int
                or min(frame["width"], frame["height"]) <= 0
                or frame["width"] * frame["height"] > 16_777_216):
            raise ValueError("capture dimensions outside local allocation boundary")
        frames.append({**{key: frame[key] for key in ("clip", "time", "side", "azimuth", "width", "height")},
                       "camera": camera})
    gate.view_coverage(frames, sweep["frames"], sweep["axes"])
    node = gate.executable("IMG2_CHARACTER_NODE", "node")
    browser = gate.executable("IMG2_CHARACTER_BROWSER", "chromium")
    three = gate.reviewed_three()
    output = evidence.path(out)
    if output.exists():
        raise ValueError("delivery output directory must be new")
    output.parent.mkdir(parents=True, exist_ok=True)
    job = {"candidatePath": str(evidence.path(request["glb"]["path"])),
           "baselinePath": str(evidence.path(sweep["baselineGlb"]["path"])),
           "glbSha256": request["glb"]["sha256"], "baselineGlbSha256": sweep["baselineGlb"]["sha256"],
           "frames": frames}
    with tempfile.TemporaryDirectory(prefix="img2-delivery-job-") as temporary:
        job_path = Path(temporary) / "job.json"
        job_path.write_bytes(api.canonical(job))
        result = subprocess.run([node, str(gate.PLUGIN / "tools/capture_routed_rig.mjs"),
                                 "--input", str(job_path), "--out", str(output)],
                                capture_output=True, text=True, timeout=240,
                                env=gate.child_environment(node=node, browser=browser, three=three))
    if result.returncode:
        raise ValueError("owned delivery capture failed: " + (result.stderr or result.stdout).strip())
    receipt = gate.strict_json((output / "capture.json").read_bytes())
    files = {}
    for ref in receipt["files"]:
        if "/" in ref["path"] or "\\" in ref["path"]:
            raise ValueError("foreign capture output")
        bound = {"path": f"{out}/{ref['path']}", "sha256": ref["sha256"]}
        evidence.read(bound, json_data=False)
        files[ref["path"]] = bound
    request["runtime"] = files["runtime.json"]
    runtime = evidence.read(request["runtime"])
    parity = routed_native.compare_poses(native, extracted, runtime)
    for index, frame in enumerate(sweep["frames"]):
        frame["candidate"] = files[f"{index}-candidate.rgba"]
        frame["baseline"] = files[f"{index}-baseline.rgba"]
    request["sweep"] = evidence.save(f"{out}/sweep.json", sweep)
    evidence.save(f"{out}/native-parity.json", parity)
    evidence.save(f"{out}/admission-request.json", request)
    # The existing admission runs all twelve checks and preserves actual failure states.
    artifact = api.admit(workspace, request)
    return {"artifact": {"path": "artifact.json", "sha256": api.digest(api.canonical(artifact))},
            "request": f"{out}/admission-request.json", "nativeParity": parity}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("native", "deliver"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--out", required=True, help="new workspace-relative output directory")
    args = parser.parse_args()
    try:
        request = gate.strict_json(args.request.read_bytes())
        result = (native_build if args.command == "native" else deliver)(args.workspace, request, args.out)
        print(json.dumps(result, allow_nan=False))
    except Exception as error:
        print("routed rig production blocked: " + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
