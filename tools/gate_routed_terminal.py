#!/usr/bin/env python3
"""Route-only D18 gate. Recompute admission and execute a fresh owned browser capture.

Never registered in legacy gates.json. The base separately authenticates/pins this script;
a JSON marker or an old passing receipt cannot authorize this program's verdict.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from contextlib import redirect_stdout
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

GATE_ID = "character-routed-terminal"
TOOLS = Path(__file__).resolve().parent
ADMISSION = ".img2/artifacts/character/rig-admission.json"
SHA = re.compile(r"[0-9a-f]{64}\Z")
THREE_FILES = ("build/three.core.js", "build/three.module.js",
               "examples/jsm/loaders/GLTFLoader.js", "examples/jsm/utils/BufferGeometryUtils.js",
               "examples/jsm/utils/SkeletonUtils.js", "package.json")
OS_ENVIRONMENT = ("HOME", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "LC_CTYPE", "SYSTEMROOT", "WINDIR")


def executable(environment, fallback):
    override = os.environ.get(environment)
    if override is not None and (not override or not Path(override).is_absolute()):
        raise ValueError(f"producer-dependency-invalid: {environment} must be an absolute executable")
    selected = override if override is not None else shutil.which(fallback)
    if selected is None:
        raise ValueError(f"producer-dependency-missing: {fallback} ({environment})")
    try:
        path = Path(selected).resolve(strict=True)
    except OSError as error:
        raise ValueError(f"producer-dependency-unavailable: {environment}={selected}: {error}") from error
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError(f"producer-dependency-unavailable: {path}")
    return str(path)


def file_sha(path):
    result = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def strict_json(data):
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError(f"non-finite JSON: {value}")
    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)


def child_environment(*, node=None, browser=None, three=None):
    """No loader hooks, native preloads, proxies or credentials cross this boundary."""
    environment = {key: os.environ[key] for key in OS_ENVIRONMENT if key in os.environ}
    environment["PATH"] = os.defpath
    if node is not None:
        environment["IMG2_CHARACTER_NODE"] = node
    if browser is not None:
        environment["IMG2_CHARACTER_BROWSER"] = browser
    if three is not None:
        environment["IMG2_CHARACTER_THREE_ROOT"] = three["root"]
        environment["IMG2_CHARACTER_THREE_SHA256"] = three["sha256"]
    return environment


def reviewed_three():
    """Validate host approval of exact bytes, not a third-party authenticity claim."""
    selected = os.environ.get("IMG2_CHARACTER_THREE_ROOT")
    approved = os.environ.get("IMG2_CHARACTER_THREE_SHA256")
    if not selected or not Path(selected).is_absolute() or not isinstance(approved, str) or not SHA.fullmatch(approved):
        raise ValueError("producer-dependency-missing: absolute IMG2_CHARACTER_THREE_ROOT and reviewed IMG2_CHARACTER_THREE_SHA256 required")
    root = Path(selected).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("host-approved Three root is not a package directory")
    files = []
    for name in sorted(THREE_FILES):
        path = root / name
        if not path.resolve(strict=True).is_relative_to(root) or not path.is_file() or path.is_symlink():
            raise ValueError("host-approved Three contains foreign/aliased module files")
        files.append({"path": name, "sha256": file_sha(path)})
    package = strict_json((root / "package.json").read_bytes())
    if package.get("version") != "0.186.1":
        raise ValueError("producer-dependency-mismatch: Three.js 0.186.1 required")
    inventory = {"kind": "img2.character-three-package", "version": 1, "files": files}
    actual = hashlib.sha256(json.dumps(inventory, sort_keys=True, separators=(",", ":"),
                                      ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    if actual != approved:
        raise ValueError("host-approved Three package digest mismatch")
    return {"root": str(root), "version": "0.186.1", "sha256": actual,
            "files": files, "approval": "host-approved"}


def view_coverage(frames, source_frames, axes):
    """Different labels cannot turn the identical camera/ROI into an orbit sweep."""
    azimuths, sides = {}, {}
    for frame, source in zip(frames, source_frames):
        world = frame["camera"]["matrixWorld"]
        length = math.hypot(*world[8:11])
        if not math.isfinite(length) or length == 0:
            raise ValueError("render camera has no finite view direction")
        direction = tuple(value / length for value in world[8:11])
        azimuths.setdefault((frame["clip"], frame["time"], frame["side"]), set()).add(direction)
        sides.setdefault((frame["clip"], frame["time"], frame["azimuth"]), set()).add((direction, source["roi"]["sha256"]))
    if any(len(values) != len(axes["azimuths"]) for values in azimuths.values()):
        raise ValueError("placeholder sweep: declared azimuths repeat the same actual view direction")
    if any(len(values) != len(axes["sides"]) for values in sides.values()):
        raise ValueError("placeholder sweep: declared sides repeat the same actual camera and ROI")


def preflight(workspace, artifact_name="artifact.json", *, verdict_evidence=None):
    # Import lazily: a missing core link/dependency must still emit a gate envelope.
    import rigged_artifact as api
    evidence = api.Evidence(workspace, publish=False)
    path = Path(artifact_name)
    if path.is_absolute():
        path = path.relative_to(evidence.root)
    name = path.as_posix()
    artifact_path = evidence.path(name)
    artifact_bytes = artifact_path.read_bytes()
    if verdict_evidence is not None:
        verdict_evidence["artifact"] = {"path": str(artifact_path), "sha256": api.digest(artifact_bytes)}
    artifact = strict_json(artifact_bytes)
    state_path = evidence.path("state.json")
    state_bytes = state_path.read_bytes()
    state = strict_json(state_bytes)
    child = state.get("routeChild")
    required_child = {"runId", "objectId", "revision", "ownerRoute", "outputKind", "cropSha256"}
    if (not isinstance(child, dict) or set(child) != required_child or child["outputKind"] != "rigged-3d"
            or any(not isinstance(child[key], str) or not child[key] for key in ("runId", "objectId", "ownerRoute"))
            or type(child["revision"]) is not int or child["revision"] < 0
            or not isinstance(child["cropSha256"], str) or not SHA.fullmatch(child["cropSha256"])):
        raise ValueError("missing or malformed routed rigged child marker")
    if (not isinstance(artifact, dict) or set(artifact) != {"objectId", "outputKind", "files", "frame", "pivot", "scaleEstimate", "rig"}
            or artifact["objectId"] != child["objectId"] or artifact["outputKind"] != "rigged-3d"
            or artifact["frame"] != api.FRAME or artifact["pivot"] != "bottom-centre"
            or not api.positive(artifact["scaleEstimate"])):
        raise ValueError("terminal artifact does not match the routed child/D18 frame")
    reference_name = state.get("artifacts", {}).get("reference")
    reference = {"path": reference_name, "sha256": child["cropSha256"]}
    if not evidence.read(reference, json_data=False):
        raise ValueError("empty child reference")
    if not isinstance(artifact["files"], list) or not artifact["files"]:
        raise ValueError("terminal artifact has no files")
    refs, inodes = {}, set()
    for ref in artifact["files"]:
        if (not isinstance(ref, dict) or set(ref) != {"path", "sha256"}
                or not isinstance(ref["sha256"], str) or not SHA.fullmatch(ref["sha256"])):
            raise ValueError("invalid terminal file binding")
        if ref["path"] in refs:
            raise ValueError("duplicate terminal file path")
        data = evidence.read(ref, json_data=False)
        info = evidence.path(ref["path"]).stat()
        identity = (info.st_dev, info.st_ino)
        if identity in inodes or not data:
            raise ValueError("aliased or empty terminal evidence")
        inodes.add(identity)
        refs[ref["path"]] = ref
    if ADMISSION not in refs:
        raise ValueError("authoritative rig-admission is not bound by the artifact")
    admission = strict_json(evidence.read(refs[ADMISSION], json_data=False))
    if (admission.get("kind") != "img2.character-rig-admission" or admission.get("version") != 1
            or not isinstance(admission.get("inputs"), dict)):
        raise ValueError("invalid authoritative rig-admission")
    request = admission["inputs"]
    if request.get("objectId") != child["objectId"] or refs.get(request["glb"]["path"]) != request["glb"]:
        raise ValueError("rig admission names a foreign object or unbound delivery GLB")
    extracted = api.extract_glb(evidence.path(request["glb"]["path"]))
    if extracted["skeleton"]["glbSha256"] != admission.get("glbSha256"):
        raise ValueError("rig admission refers to stale/foreign GLB")
    rig = artifact["rig"]
    if not isinstance(rig, dict) or set(rig) != {"skeletonSha", "clips"} or not isinstance(rig["clips"], list):
        raise ValueError("actual skeleton and clips are mandatory")
    def sidecar(sha, expected):
        matches = [ref for ref in refs.values() if ref["sha256"] == sha]
        if len(matches) != 1:
            raise ValueError("skeleton/clip evidence is missing or ambiguous")
        data = evidence.read(matches[0], json_data=False)
        if data != api.canonical(expected):
            raise ValueError("skeleton/clip sidecar does not match actual GLB accessor data")
    sidecar(rig["skeletonSha"], extracted["skeleton"])
    if len(rig["clips"]) != len(extracted["clips"]):
        raise ValueError("terminal clip roster differs from the actual GLB")
    for claim, actual in zip(rig["clips"], extracted["clips"]):
        if not isinstance(claim, dict) or set(claim) != {"name", "sha256"} or claim["name"] != actual["name"]:
            raise ValueError("foreign/reordered clip binding")
        sidecar(claim["sha256"], actual)
    # This is an evaluation, not a trust decision about an old receipt. No source writes.
    recomputed = api.admit(evidence.root, request, publish=False)
    if recomputed["artifact"] != artifact or recomputed["gateReport"] != admission.get("gateReport"):
        raise ValueError("authoritative rig admission/manifest does not reproduce from current files")
    bound = admission.get("boundInputs")
    if not isinstance(bound, list) or not bound:
        raise ValueError("rig admission has no bound measurement inputs")
    for ref in bound:
        evidence.read(ref, json_data=False)
    return {"api": api, "evidence": evidence, "artifact": artifact, "request": request,
            "extracted": extracted, "subject": child, "reference": reference,
            "stateSha256": api.digest(state_bytes),
            "artifactRef": {"path": str(artifact_path), "sha256": api.digest(artifact_bytes)},
            "admissionRef": refs[ADMISSION], "report": recomputed["gateReport"]}


def retain_measurement(evidence, name, data):
    import rigged_artifact as api
    path = evidence.path(name)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("immutable terminal measurement was altered")
    else:
        api.atomic(path, data)
    return {"path": name, "sha256": api.digest(data)}


def retain_native_bundle(evidence, output):
    """Address exact native bytes independently of the browser receipt.

    Blender containers may differ between semantically identical native replays.
    Every filename and actual SHA participates in this immutable closure identity;
    these storage identities are not native geometry/pixel replay comparisons.
    """
    import rigged_artifact as api
    paths = sorted(output.iterdir())
    if not paths or any(path.is_symlink() or not path.is_file() for path in paths):
        raise ValueError("native closure must contain only regular output files")
    inventory = {"kind": "img2.character-terminal-native-bundle", "version": 1,
                 "files": [{"path": path.name, "sha256": file_sha(path)} for path in paths]}
    relative = ".img2/artifacts/character/terminal-native/" + api.digest(api.canonical(inventory))
    refs = []
    for path, ref in zip(paths, inventory["files"]):
        data = path.read_bytes()
        if api.digest(data) != ref["sha256"]:
            raise ValueError("native capture bytes changed during retention")
        refs.append(retain_measurement(evidence, f"{relative}/{path.name}", data))
    return refs


def live_measurement(context):
    import routed_native
    api, original = context["api"], context["evidence"]
    program_sha = file_sha(__file__)
    producer_paths = {"tools/capture_routed_rig.mjs": TOOLS / "capture_routed_rig.mjs",
                      "runner.mjs": TOOLS.parent / "runtime/rig-terminal-capture.mjs",
                      "rig-measurements.mjs": TOOLS.parent / "runtime/rig-measurements.mjs"}
    producer_paths.update({"tools/" + name: TOOLS / name for name in
                           ("bpy_capture_routed_rig.py", "routed_native.py",
                            "prepare_softbody.py", "rigged_artifact.py",
                            "rig_glb_reference.py", "rig_mesh_parity.py",
                            "rig_gate_core.py", "native_glb_freeze.py")})
    producer_hashes = {name: file_sha(path) for name, path in producer_paths.items()}
    node = executable("IMG2_CHARACTER_NODE", "node")
    node_sha = file_sha(node)
    version = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10,
                             env=child_environment())
    node_version = version.stdout.strip()
    node_match = re.fullmatch(r"v(\d+)\.\d+\.\d+(?:[-+][\w.-]+)?", node_version)
    if version.returncode or node_match is None or int(node_match[1]) < 22:
        raise ValueError(f"producer-dependency-missing: character-node>=22.0; actual {node_version!r} at {node}")
    browser = executable("IMG2_CHARACTER_BROWSER", "chromium")
    browser_sha = file_sha(browser)
    version = subprocess.run([browser, "--version"], capture_output=True, text=True, timeout=10,
                             env=child_environment())
    browser_version = re.search(r"(\d+)\.\d+", version.stdout)
    if version.returncode or browser_version is None or int(browser_version[1]) < 1:
        raise ValueError(f"producer-dependency-missing: character-chromium>=1.0; actual {version.stdout.strip()!r} at {browser}")
    three = reviewed_three()
    # A disposable workspace lets the actual producers run without mutating the accepted
    # artifact, original captures, pre-bind manifest, source master or incumbent revision.
    with tempfile.TemporaryDirectory(prefix="img2-rig-terminal-") as temporary:
        root = Path(temporary)
        working = root / "workspace"
        working.mkdir()
        for ref in original.files.values():
            data = original.read(ref, json_data=False)
            path = working / ref["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        request = deepcopy(context["request"])
        native = request.get("native")
        if native is None:
            raise ValueError("program-owned native source/freeze/bind capture is required")
        native_output = root / "native"
        native_receipt, native_executable = routed_native.run_native(
            original, native, native_output, master=request["nativeMaster"])
        if native_receipt["glbSha256"] != request["glb"]["sha256"]:
            raise ValueError("fresh native source replay does not reproduce exact delivery GLB bytes")
        native_freeze = routed_native.freeze_export(native_output / "base.glb",
                                                    native_output / "character.glb", native["spec"])
        if native_freeze != strict_json(original.read(request["freezeManifest"], json_data=False)):
            raise ValueError("fresh native pre-bind freeze differs from admitted freeze")
        saved_native = strict_json(original.read(request["nativeCapture"], json_data=False))
        for key in ("sourceSha256", "spec", "baseGlbSha256", "glbSha256", "sourceGeometry",
                    "frameNormalization", "normalPreservation", "nativeGeometry", "restWorld", "poseSamples"):
            if saved_native.get(key) != native_receipt[key]:
                raise ValueError("saved native capture does not reproduce from actual source")
        sweep = strict_json(original.read(request["sweep"], json_data=False))
        frames = []
        for frame in sweep["frames"]:
            if frame["width"] * frame["height"] > 16_777_216:
                raise ValueError("render allocation exceeds the local capture safety limit")
            frames.append({**{key: frame[key] for key in ("clip", "time", "side", "azimuth", "width", "height")},
                           "camera": strict_json(original.read(frame["camera"], json_data=False))})
        view_coverage(frames, sweep["frames"], sweep["axes"])
        job = {"candidatePath": str(working / request["glb"]["path"]),
               "baselinePath": str(working / sweep["baselineGlb"]["path"]),
               "glbSha256": request["glb"]["sha256"], "baselineGlbSha256": sweep["baselineGlb"]["sha256"],
               "frames": frames}
        job_path = root / "job.json"
        job_path.write_bytes(api.canonical(job))
        output = root / "capture"
        command = [node, str(TOOLS / "capture_routed_rig.mjs"), "--input", str(job_path), "--out", str(output)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=240, cwd=TOOLS,
                                env=child_environment(node=node, browser=browser, three=three))
        if result.returncode:
            raise ValueError("live measurement producer failed: " + (result.stderr or result.stdout).strip())
        receipt_bytes = (output / "capture.json").read_bytes()
        receipt = strict_json(receipt_bytes)
        if (receipt.get("kind") != "img2.character-live-capture" or receipt.get("version") != 1
                or receipt.get("glbSha256") != job["glbSha256"] or receipt.get("baselineGlbSha256") != job["baselineGlbSha256"]
                or receipt.get("measurement", {}).get("frameCount") != len(frames)):
            raise ValueError("live capture is incomplete or foreign")
        if (receipt.get("node") != {"executable": node, "version": node_version, "sha256": node_sha}
                or receipt.get("browserExecutable", {}).get("path") != browser
                or receipt["browserExecutable"].get("sha256") != browser_sha):
            raise ValueError("capture ran with an unbound/foreign executable")
        if any(receipt.get("producerFiles", {}).get(name) != producer_hashes[name] for name in
               ("tools/capture_routed_rig.mjs", "runner.mjs", "rig-measurements.mjs")):
            raise ValueError("capture driver/runtime source hash does not match the owned producer")
        if receipt.get("three") != three:
            raise ValueError("live capture did not use the exact host-approved Three package")
        bundle = api.digest(receipt_bytes)
        relative = f".img2/artifacts/character/terminal-live/{bundle}"
        fresh = api.Evidence(working)
        capture_files = {}
        for ref in receipt["files"]:
            if not isinstance(ref, dict) or set(ref) != {"path", "sha256"} or "/" in ref["path"] or "\\" in ref["path"]:
                raise ValueError("invalid owned capture output path")
            data = (output / ref["path"]).read_bytes()
            if api.digest(data) != ref["sha256"]:
                raise ValueError("live capture bytes changed")
            name = f"{relative}/{ref['path']}"
            path = fresh.path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            capture_files[ref["path"]] = {"path": name, "sha256": ref["sha256"]}
        if len(capture_files) != 1 + 2 * len(frames):
            raise ValueError("live capture omitted/repeated output files")
        for i, frame in enumerate(sweep["frames"]):
            for kind in ("candidate", "baseline"):
                frame[kind] = capture_files[f"{i}-{kind}.rgba"]
                data = (working / frame[kind]["path"]).read_bytes()
                roi = original.read(frame["roi"], json_data=False)
                if not any(selected and data[index * 4 + 3] == 255 for index, selected in enumerate(roi)):
                    raise ValueError("live sweep ROI contains no observed opaque subject; placeholder/off-camera view")
        request["runtime"] = capture_files["runtime.json"]
        request["sweep"] = fresh.save(f"{relative}/sweep.json", sweep)
        measured = api.admit(working, request, publish=False)
        native_parity = routed_native.compare_poses(
            native_receipt, context["extracted"],
            strict_json((working / request["runtime"]["path"]).read_bytes()))
        restored = strict_json((working / request["runtime"]["path"]).read_bytes())["measurements"]["bindRestore"]
        vertex_delta = restored.get("maxBindRestoreVertexDelta")
        if (type(vertex_delta) not in (int, float) or not math.isfinite(vertex_delta)
                or not 0 <= vertex_delta <= api.gates.BIND_RESTORE_TOLERANCE):
            raise ValueError("live bind-pose vertex restoration is missing or fails parity")
        expected_restore = {mesh["name"]: {"vertexCount": len(mesh["attributes"]["position"]) // 3}
                            for mesh in context["extracted"]["meshBuffers"]["meshes"]}
        if restored.get("meshes") != expected_restore:
            raise ValueError("live bind-pose restoration skipped actual GLB vertices")
        if file_sha(node) != node_sha or file_sha(browser) != browser_sha:
            raise ValueError("measurement executable changed during capture")
        if file_sha(__file__) != program_sha or any(file_sha(producer_paths[name]) != sha for name, sha in producer_hashes.items()):
            raise ValueError("measurement program changed during capture")
        if reviewed_three() != three:
            raise ValueError("host-approved Three changed during capture")
        # Recheck original inputs after browser work; changed state/evidence cannot inherit this run.
        for ref in tuple(original.files.values()):
            original.read(ref, json_data=False)
        if api.digest(original.path("state.json").read_bytes()) != context["stateSha256"]:
            raise ValueError("routed child changed during measurement")
        if api.digest(Path(context["artifactRef"]["path"]).read_bytes()) != context["artifactRef"]["sha256"]:
            raise ValueError("artifact changed during measurement")
        # Retain real new measurements, not transient paths or a receipt with vanished captures.
        persisted = api.Evidence(original.root)
        def retain(name, data):
            return retain_measurement(persisted, name, data)
        for ref in [*capture_files.values(), request["sweep"]]:
            retain(ref["path"], (working / ref["path"]).read_bytes())
        receipt_ref = retain(f"{relative}/capture.json", api.canonical(receipt))
        native_refs = retain_native_bundle(persisted, native_output)
        measurement = {"kind": "img2.character-terminal-measurement", "version": 1,
                       "artifact": context["artifactRef"], "subject": context["subject"],
                       "reference": context["reference"], "stateSha256": context["stateSha256"],
                       "capture": receipt_ref, "runtime": request["runtime"], "sweep": request["sweep"],
                       "gateReport": measured["gateReport"], "bindRestore": restored,
                       "executables": {"node": receipt["node"], "browser": receipt["browserExecutable"]},
                       "three": three,
                       "producerFiles": producer_hashes,
                       "native": {"source": native["source"], "captureFiles": native_refs,
                                  "executable": native_executable, "parity": native_parity},
                       "program": {"path": str(Path(__file__).resolve()), "sha256": program_sha},
                       "boundInputs": list(original.files.values())}
        measurement_ref = retain(f".img2/artifacts/character/terminal-measurements/{api.digest(api.canonical(measurement))}.json", api.canonical(measurement))
        return {"measurement": measurement_ref, "capture": receipt_ref, "gates": measured["gateReport"]["gates"],
                "browser": receipt["browser"], "renderer": receipt["measurement"],
                "producerFiles": receipt["producerFiles"], "bindRestore": restored,
                "three": three,
                "native": {"source": native["source"], "captureFiles": native_refs,
                           "executable": native_executable, "parity": native_parity},
                "program": {"path": str(Path(__file__).resolve()), "sha256": program_sha},
                "executables": {"node": receipt["node"], "browser": receipt["browserExecutable"]}}


def evaluate(workspace, artifact="artifact.json"):
    evidence = {}
    status, reasons, code = "error", [], 2
    try:
        with redirect_stdout(sys.stderr):
            context = preflight(workspace, artifact, verdict_evidence=evidence)
            evidence = {"artifact": context["artifactRef"], "reference": context["reference"],
                        "subject": context["subject"], "rigAdmission": context["admissionRef"]}
            evidence.update(live_measurement(context))
            evidence["measurementOrigin"] = "live-native-and-browser"
            status, code = "pass", 0
    except (Exception, SystemExit) as error:
        reasons = [f"routed rig gate blocked: {error}"]
        report = getattr(error, "gate_report", None)
        if isinstance(report, dict):
            evidence["gates"] = report["gates"]
            if any(row["status"] == "fail" for row in report["gates"]):
                status, code = "fail", 1
    return ({"kind": "img2.gate-verdict", "version": 1, "gate": GATE_ID,
             "plugin": "character", "status": status, "reasons": reasons, "evidence": evidence}, code)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--artifact", default="artifact.json")
    args = parser.parse_args(argv)
    verdict, code = evaluate(args.workspace, args.artifact)
    print(json.dumps(verdict, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
