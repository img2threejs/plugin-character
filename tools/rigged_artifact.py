#!/usr/bin/env python3
"""D18 extraction and fail-closed rigged admission. No cross-repository imports.

`extract` writes inspectable canonical skeleton/clip data, not an accepted artifact.
`admit` recomputes GLB binding/parity, motion and rendered sweep measurements before
publishing artifact.json. Host evidence is hash-bound, not cryptographically attested.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import re
import tempfile

import rig_glb_reference as glb
import rig_gate_core as gates
import rig_mesh_parity as parity

FRAME = {"units": "m", "up": "+Y", "forward": "+Z"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".rig-artifact-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Evidence:
    def __init__(self, workspace, *, publish=True):
        self.root = Path(workspace).resolve(strict=True)
        self.files = {}
        self.publish = publish

    def path(self, name):
        if not isinstance(name, str) or not name or Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("evidence paths must be workspace-relative")
        path = self.root / name
        current = self.root
        for part in Path(name).parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("symlink evidence is not admitted")
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("evidence escapes workspace")
        return path

    def read(self, ref, *, json_data=True):
        if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
            raise ValueError("evidence requires path and sha256")
        path = self.path(ref["path"])
        data = path.read_bytes()
        if digest(data) != ref["sha256"]:
            raise ValueError(f"stale evidence: {ref['path']}")
        self.files[ref["path"]] = dict(ref)
        value = json.loads(data) if json_data else data
        if json_data:
            canonical(value)
        return value

    def save(self, name, value):
        if name in self.files:
            raise ValueError("artifact output aliases an input")
        data = canonical(value)
        if self.publish:
            atomic(self.path(name), data)
        ref = {"path": name, "sha256": digest(data)}
        self.files[name] = ref
        return ref


def extract_glb(path):
    """Decode actual accessor bytes; do not use accessor min/max or reader fallbacks."""
    source_sha = digest(Path(path).read_bytes())
    rig = glb.read_rig(path)
    document, binary, _ = glb.parse_glb(Path(path))
    if rig.structural_failure or not rig.joints or rig.unsupported_interpolation_clips:
        raise ValueError(rig.structural_failure or "missing joints or unsupported animation")
    # Embedded GLB only. External resources need their own packaging/provenance producer.
    if any("uri" in buffer for buffer in document.get("buffers", [])) or any(
            "uri" in image for image in document.get("images", [])):
        raise ValueError("external GLB resources are not packaged by this producer")
    canonical(document)
    nodes = document.get("nodes", [])
    claimed_children = set()
    for node in nodes:
        for child in node.get("children", []):
            if type(child) is not int or not 0 <= child < len(nodes) or child in claimed_children:
                raise ValueError("invalid or multiply-parented GLB node")
            claimed_children.add(child)
        if "matrix" in node and len(node["matrix"]) != 16:
            raise ValueError("node matrix must have sixteen components")
    world = glb.rest_world_matrices(rig)
    joint_ids = [joint.node_index for joint in rig.joints]
    if len(set(joint_ids)) != len(joint_ids) or any(not 0 <= j < len(nodes) for j in joint_ids):
        raise ValueError("invalid skin joint order")
    skin = document["skins"][0]
    if any(type(index) is not int for index in skin["joints"]):
        raise ValueError("skin joint indices must be integers, never coerced")
    if "skeleton" in skin and (type(skin["skeleton"]) is not int or not 0 <= skin["skeleton"] < len(nodes)):
        raise ValueError("skin skeleton root is missing")
    ibm = skin.get("inverseBindMatrices")
    inverse = ([list(glb.IDENTITY_MATRIX) for _ in joint_ids] if ibm is None
               else [list(value) for value in glb.read_accessor(document, binary, ibm)])
    if len(inverse) != len(joint_ids) or any(len(value) != 16 for value in inverse):
        raise ValueError("inverse binds missing or malformed; no identity repair is allowed")
    skeleton = {
        "kind": "img2.character-skeleton", "version": 1, "glbSha256": source_sha,
        "skin": {"joints": joint_ids, "skeleton": skin.get("skeleton"),
                 "inverseBindMatrices": inverse, "inverseBindSource": rig.inverse_bind_source},
        "nodes": [{"nodeIndex": i, "parentNodeIndex": rig._parents[i],
                   "name": node.get("name"),
                   "localMatrix": list(node.get("matrix", glb.compose_trs(*glb._node_rest_trs(node))))}
                  for i, node in enumerate(nodes)],
    }
    canonical(skeleton)  # Reject all non-finite matrices, including unused nodes.
    extracted_clips = []
    for i, animation in enumerate(document.get("animations", [])):
        name = animation.get("name") or f"animation-{i}"
        samplers = []
        for sampler in animation.get("samplers", []):
            times = glb.read_accessor(document, binary, sampler["input"])
            values = glb.read_accessor(document, binary, sampler["output"])
            if not times or not values or any(len(t) != 1 for t in times):
                raise ValueError("animation sampler has no usable data")
            if any(times[j][0] >= times[j + 1][0] for j in range(len(times) - 1)):
                raise ValueError("animation times are not strictly increasing")
            samplers.append({"interpolation": sampler.get("interpolation", "LINEAR"),
                             "times": [t[0] for t in times], "values": [list(v) for v in values]})
        channels = animation.get("channels", [])
        if not channels:
            raise ValueError("empty animation cannot establish a playable clip")
        for channel in channels:
            target = channel["target"]
            if (type(target["node"]) is not int or type(channel["sampler"]) is not int
                    or not 0 <= target["node"] < len(nodes) or not 0 <= channel["sampler"] < len(samplers)):
                raise ValueError("animation targets a missing node or sampler")
            sampler = samplers[channel["sampler"]]
            path_name = target["path"]
            if path_name not in ("translation", "rotation", "scale"):
                raise ValueError("unsupported animation channel requires a separate deformation producer")
            components = 4 if path_name == "rotation" else 3
            if (sampler["interpolation"] not in ("LINEAR", "STEP")
                    or len(sampler["times"]) != len(sampler["values"])
                    or sampler["times"][0] < 0
                    or any(len(value) != components for value in sampler["values"])):
                raise ValueError("malformed/unsupported animation sampler")
        extracted_clips.append({"kind": "img2.character-clip", "version": 1,
                                "glbSha256": source_sha, "name": name,
                                "channels": channels, "samplers": samplers})
    if len({clip["name"] for clip in extracted_clips}) != len(extracted_clips):
        raise ValueError("duplicate clip names")
    mesh_buffers, positions, indices, weights, part_ids = [], [], [], [], []
    low, high = [math.inf] * 3, [-math.inf] * 3
    # A selected scene is mandatory so detached/hidden meshes cannot inflate the roster/bounds.
    scene = document.get("scene", 0)
    if type(scene) is not int or not 0 <= scene < len(document.get("scenes", [])):
        raise ValueError("GLB selected scene is missing or invalid")
    roots = document.get("scenes", [])[scene]["nodes"]
    active = set()
    def visit(index):
        if type(index) is not int or not 0 <= index < len(nodes):
            raise ValueError("scene references a missing node")
        if index in active:
            raise ValueError("scene hierarchy repeats a node")
        active.add(index)
        for child in nodes[index].get("children", []):
            visit(child)
    for root in roots:
        if type(root) is not int or not 0 <= root < len(nodes) or rig._parents[root] is not None:
            raise ValueError("scene root is missing or has a parent")
        visit(root)
    for node_index in sorted(active):
        node = nodes[node_index]
        if "mesh" not in node:
            continue
        if type(node.get("skin")) is not int or node["skin"] != 0:
            raise ValueError("every delivered visible mesh must reference the GLB skin")
        if type(node["mesh"]) is not int or not 0 <= node["mesh"] < len(document.get("meshes", [])):
            raise ValueError("GLB node references a missing mesh")
        mesh = document["meshes"][node["mesh"]]
        for primitive_index, primitive in enumerate(mesh["primitives"]):
            if primitive.get("mode", 4) != 4 or "targets" in primitive:
                raise ValueError("non-triangle/morph mesh requires a separate parity producer")
            if "KHR_draco_mesh_compression" in primitive.get("extensions", {}):
                raise ValueError("compressed geometry requires an actual decompression producer")
            attributes = primitive["attributes"]
            if any(key not in attributes for key in ("POSITION", "JOINTS_0", "WEIGHTS_0")):
                raise ValueError("GLB primitive is missing positions or skin attributes")
            if any(key.startswith(("JOINTS_", "WEIGHTS_")) and key not in ("JOINTS_0", "WEIGHTS_0")
                   for key in attributes):
                raise ValueError("more than four influences requires an explicit conditioning producer")
            joint_accessor = document["accessors"][attributes["JOINTS_0"]]
            if joint_accessor["componentType"] not in (5121, 5123) or joint_accessor.get("normalized", False):
                raise ValueError("JOINTS_0 must be unsigned, unnormalized glTF indices")
            decoded = {}
            for source, target in (("POSITION", "position"), ("NORMAL", "normal"), ("TEXCOORD_0", "uv"),
                                   ("JOINTS_0", "skinIndex"), ("WEIGHTS_0", "skinWeight")):
                if source in attributes:
                    decoded[target] = glb.read_accessor(document, binary, attributes[source])
            count = len(decoded["position"])
            if not count or any(len(values) != count for values in decoded.values()):
                raise ValueError("mesh attribute counts differ")
            if any(len(v) != 3 for v in decoded["position"]) or any(
                    len(v) != 4 for key in ("skinIndex", "skinWeight") for v in decoded[key]):
                raise ValueError("malformed skin/position component count")
            joint_values = [v for row in decoded["skinIndex"] for v in row]
            if any(not math.isfinite(v) or int(v) != v for v in joint_values):
                raise ValueError("joint indices must be integers")
            name = f"node:{node_index}/primitive:{primitive_index}"
            if "indices" in primitive:
                index_accessor = document["accessors"][primitive["indices"]]
                if (index_accessor["type"] != "SCALAR" or index_accessor["componentType"] not in (5121, 5123, 5125)
                        or index_accessor.get("normalized", False)):
                    raise ValueError("triangle indices must be unsigned, unnormalized scalars")
            index = (None if "indices" not in primitive else
                     [int(v[0]) for v in glb.read_accessor(document, binary, primitive["indices"])])
            if index is not None and any(not 0 <= v < count for v in index):
                raise ValueError("triangle index out of range")
            if (len(index) if index is not None else count) % 3:
                raise ValueError("triangle vertex/index count is incomplete")
            mesh_buffers.append({"name": name, "attributes": {
                key: [v for row in rows for v in row] for key, rows in decoded.items()}, "index": index})
            positions.extend([list(v) for v in decoded["position"]])
            indices.extend(int(v) for v in joint_values)
            weights.extend(v for row in decoded["skinWeight"] for v in row)
            part_ids.extend([name] * count)
            matrix = world[node_index]
            for point in decoded["position"]:
                transformed = [sum(matrix[column * 4 + axis] * point[column] for column in range(3))
                               + matrix[12 + axis] for axis in range(3)]
                for axis, value in enumerate(transformed):
                    low[axis], high[axis] = min(low[axis], value), max(high[axis], value)
    if not mesh_buffers:
        raise ValueError("GLB contains no scene mesh")
    result = {"rig": rig, "skeleton": skeleton, "clips": extracted_clips,
              "meshBuffers": {"meshes": mesh_buffers}, "bounds": {"min": low, "max": high},
              "binding": {"positions": positions, "skinIndices": indices, "skinWeights": weights,
                          "jointCount": len(joint_ids), "partIds": part_ids}}
    canonical({key: value for key, value in result.items() if key != "rig"})
    return result


def measure_sweep(evidence, spec, clip_names, source_sha, candidate):
    """Count transparent pixels inside independently authored seam ROIs in actual RGBA buffers.

    RGBA buffers come from readRenderTargetPixels with a transparent background. ROI bytes
    must mark only expected interior skin, not silhouette/background. Creases are a separately
    reported dark-pixel diagnostic, not a new acceptance threshold or a claimed skin classifier.
    """
    if spec.get("kind") != "img2.character-sweep" or spec.get("version") != 1 or spec.get("glbSha256") != source_sha:
        raise ValueError("missing/stale rendered sweep producer")
    evidence.read(spec["baselineGlb"], json_data=False)
    baseline = extract_glb(evidence.path(spec["baselineGlb"]["path"]))
    without_source = lambda value: {key: data for key, data in value.items() if key != "glbSha256"}
    if (without_source(baseline["skeleton"]) != without_source(candidate["skeleton"])
            or [without_source(clip) for clip in baseline["clips"]] != [without_source(clip) for clip in candidate["clips"]]
            or not parity.verify(parity.freeze(candidate["meshBuffers"]), baseline["meshBuffers"]).ok):
        raise ValueError("blend-off baseline does not preserve this subject's skeleton, clips and frozen geometry")
    evidence.read(spec["roiSource"], json_data=False)
    axes = spec["axes"]
    if set(axes) != {"clips", "times", "sides", "azimuths"} or axes["clips"] != clip_names:
        raise ValueError("sweep does not cover the GLB clip roster")
    for key, values in axes.items():
        if not isinstance(values, list) or not values or len(set(values)) != len(values):
            raise ValueError(f"sweep axis {key} is empty or duplicated")
    if (any(type(t) not in (int, float) or not math.isfinite(t) or not 0 <= t <= 1 for t in axes["times"])
            or 0 not in axes["times"] or 1 not in axes["times"]
            or any(type(a) not in (int, float) or not math.isfinite(a) or not 0 <= a < 360 for a in axes["azimuths"])):
        raise ValueError("sweep times must be normalized clip fractions and azimuths measured degrees")
    expected = set(itertools.product(*(axes[key] for key in ("clips", "times", "sides", "azimuths"))))
    seen, totals = set(), {"candidate": [0, 0], "baseline": [0, 0]}
    threshold = spec["creaseLuminanceMax"]
    if type(threshold) is not int or not 0 <= threshold <= 255:
        raise ValueError("crease diagnostic threshold must be declared")
    for frame in spec["frames"]:
        key = tuple(frame[key] for key in ("clip", "time", "side", "azimuth"))
        if key not in expected or key in seen:
            raise ValueError("unexpected/duplicate sweep frame")
        seen.add(key)
        width, height = frame["width"], frame["height"]
        if type(width) is not int or type(height) is not int or min(width, height) <= 0:
            raise ValueError("invalid render dimensions")
        camera = evidence.read(frame["camera"])
        if (not isinstance(camera, dict) or camera.get("glbSha256") != source_sha
                or camera.get("baselineGlbSha256") != spec["baselineGlb"]["sha256"]
                or any(camera.get(name) != frame[name] for name in ("clip", "time", "side", "azimuth"))):
            raise ValueError("matched render camera/source/pose evidence missing")
        for matrix in ("projectionMatrix", "matrixWorld"):
            values = camera.get(matrix)
            if (not isinstance(values, list) or len(values) != 16
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in values)):
                raise ValueError("actual render camera matrices missing")
        roi = evidence.read(frame["roi"], json_data=False)
        if len(roi) != width * height or not any(roi) or any(v not in (0, 1) for v in roi):
            raise ValueError("independent interior seam ROI missing or malformed")
        for kind in totals:
            rgba = evidence.read(frame[kind], json_data=False)
            if len(rgba) != width * height * 4:
                raise ValueError("RGBA byte count does not match render dimensions")
            for i, selected in enumerate(roi):
                if not selected:
                    continue
                r, g, b, alpha = rgba[i * 4:i * 4 + 4]
                if alpha not in (0, 255):
                    raise ValueError("seam ROI includes antialiased/translucent pixels; render an opaque diagnostic")
                if alpha == 0:
                    totals[kind][0] += 1
                elif (2126 * r + 7152 * g + 722 * b) / 10000 <= threshold:
                    totals[kind][1] += 1
    if seen != expected:
        raise ValueError("rendered sweep producer is incomplete")
    return {"frames": len(seen), **{key: len(value) for key, value in axes.items()},
            "backgroundThroughSplitPx": totals["candidate"][0], "creasePx": totals["candidate"][1],
            "baseline": {"backgroundThroughSplitPx": totals["baseline"][0],
                         "creasePx": totals["baseline"][1]}}


class RigAdmissionFailure(ValueError):
    def __init__(self, message, report):
        super().__init__(message)
        self.gate_report = report


def admit(workspace, request, *, publish=True):
    """Publish admission, or return a read-only recomputation for the terminal gate."""
    evidence = Evidence(workspace, publish=publish)
    object_id = request["objectId"]
    if not isinstance(object_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}", object_id):
        raise ValueError("invalid objectId")
    evidence.read(request["glb"], json_data=False)
    extracted = extract_glb(evidence.path(request["glb"]["path"]))
    source_sha = request["glb"]["sha256"]
    if extracted["skeleton"]["glbSha256"] != source_sha:
        raise ValueError("GLB changed while extracting evidence")
    runtime = evidence.read(request["runtime"])
    if (runtime.get("kind") != "img2.character-runtime-measurements" or runtime.get("version") != 1
            or runtime.get("glbSha256") != source_sha):
        raise ValueError("missing/stale runtime measurement producer")
    if runtime.get("meshBuffers") != extracted["meshBuffers"]:
        raise ValueError("runtime mesh buffers do not match the actual GLB")
    measures = runtime.get("measurements", {})
    for key in ("bindingSamples", "deformation", "bindRestore", "meshVisibility"):
        if not isinstance(measures.get(key), dict) or not measures[key]:
            raise ValueError(f"missing measurement producer: {key}")
    names = [clip["name"] for clip in extracted["clips"]]
    if not names:
        raise ValueError("static rig has no motion/sweep producers; not eligible for this animated route")
    expected_meshes = {mesh["name"] for mesh in extracted["meshBuffers"]["meshes"]}
    if set(measures["deformation"].get("meshes", {})) != expected_meshes:
        raise ValueError("deformation producer skipped a GLB mesh")
    samples = measures["bindingSamples"].get("clips", {})
    if set(samples) != set(names):
        raise ValueError("binding producer skipped a GLB clip")
    expected_times = {}
    for clip in extracted["rig"].clips:
        expected_times[clip.name] = [clip.duration * i / 4 for i in range(5)]
    for name, sample in samples.items():
        times = sample.get("sampleTimes")
        if (not isinstance(times, list) or len(times) < 5 or len(times) != sample.get("sampleCount")
                or any(type(t) not in (float, int) or not math.isfinite(t) for t in times)
                or any(a >= b for a, b in zip(times, times[1:]))
                or times[0] != 0 or times[-1] != expected_times[name][-1]):
            raise ValueError("binding sample coverage is incomplete")
        delta = sample.get("maxSampledBindingDelta")
        total_delta = measures["bindingSamples"].get("maxSampledBindingDelta")
        if (type(delta) not in (int, float) or not math.isfinite(delta) or delta < 0
                or type(total_delta) not in (int, float) or not math.isfinite(total_delta)
                or total_delta < delta):
            raise ValueError("binding per-clip measurement missing/inconsistent")
    for name, entry in measures["deformation"]["meshes"].items():
        counts = entry.get("verticesPerFrame")
        expected_frames = sum(sample["sampleCount"] for sample in samples.values())
        vertex_count = next(len(mesh["attributes"]["position"]) // 3
                            for mesh in extracted["meshBuffers"]["meshes"] if mesh["name"] == name)
        if (entry.get("frames") != expected_frames or not isinstance(counts, list)
                or len(counts) != expected_frames or any(count != vertex_count for count in counts)):
            raise ValueError("deformation coverage does not match actual distinct GLB vertices/frames")
    frozen = evidence.read(request["freezeManifest"])
    motion = evidence.read(request["motion"])
    if motion.get("glbSha256") != source_sha:
        raise ValueError("motion evidence is stale")
    evidence.read(motion["sideLabelSource"], json_data=False)
    evidence.read(motion["stanceSource"], json_data=False)
    height = extracted["bounds"]["max"][1] - extracted["bounds"]["min"][1]
    if not positive(height):
        raise ValueError("no measured figure height")
    sampled = glb.sample_clips(extracted["rig"], motion["landmarkNodes"], sample_count=21, figure_height=height)
    if [clip["sourceName"] for clip in sampled["clips"]] != names:
        raise ValueError("GLB motion sampler omitted a clip")
    for clip in sampled["clips"]:
        if clip["sourceName"] in motion.get("stance", {}):
            clip["stance"] = motion["stance"][clip["sourceName"]]
    sweep_spec = evidence.read(request["sweep"])
    sweep = measure_sweep(evidence, sweep_spec, names, source_sha, extracted)
    rig = extracted["rig"]
    world = glb.rest_world_matrices(rig)
    included = {joint.node_index for joint in rig.joints}
    for index in tuple(included):
        parent = rig._parents[index]
        while parent is not None:
            included.add(parent)
            parent = rig._parents[parent]
    # The existing resolver adds translations only. Express each edge as a world-space
    # displacement so rotated/scaled GLB parents cannot silently change the measured anchors.
    anchors = {"joints": [{"id": str(i), "parent": None if rig._parents[i] is None else str(rig._parents[i]),
                           "localPosition": [
                               world[i][12 + axis] - (0 if rig._parents[i] is None
                                                     else world[rig._parents[i]][12 + axis])
                               for axis in range(3)]}
                          for i in sorted(included)], "sideLabels": motion["sideLabels"]}
    payload = {**sampled, **measures, "binding": extracted["binding"],
               "chainAnchors": anchors, "sourceScalesJoints": motion.get("sourceScalesJoints", False),
               "skinIntegritySweep": sweep,
               "meshParity": {"manifest": frozen, "after": extracted["meshBuffers"]},
               "rigReference": {"source": "glb", "glb": rig.to_dict()}}
    count = len(expected_meshes)
    visibility = measures["meshVisibility"]
    if (visibility.get("visibleMeshCount") != count or visibility.get("visibleSkinnedMeshCount") != count
            or visibility.get("unboundMeshes") != []):
        raise ValueError("runtime visibility differs from the actual GLB mesh roster")
    report = gates.run_gates(payload)
    gate_record = {"kind": "img2.character-rig-gates", "version": 1, "glbSha256": source_sha,
                   "gateReport": report.to_dict(), "boundInputs": list(evidence.files.values())}
    gate_ref = evidence.save(f".img2/artifacts/character/gates/{digest(canonical(gate_record))}.json", gate_record)
    if not report.ok:
        problems = [f"{row.id}:{row.status}:{row.reason}" for row in report.results if not row.passed]
        raise RigAdmissionFailure("rig admission blocked: " + "; ".join(problems) + f"; evidence: {gate_ref['path']}", report.to_dict())
    metric = request["metricAnchor"]
    evidence.read(metric["source"], json_data=False)
    if not isinstance(metric.get("method"), str) or not metric["method"].strip() or not positive(metric["metres"]):
        raise ValueError("real metric anchor measurement required")
    a, b = metric["nodes"]
    if any(type(i) is not int or not 0 <= i < len(rig.nodes) for i in (a, b)):
        raise ValueError("metric anchor nodes missing")
    world = glb.rest_world_matrices(rig)
    authored = math.dist(glb.matrix_translation(world[a]), glb.matrix_translation(world[b]))
    if not positive(authored):
        raise ValueError("metric anchor nodes coincide")
    scale = metric["metres"] / authored
    if not positive(scale):
        raise ValueError("invalid measured scale")
    low, high = extracted["bounds"]["min"], extracted["bounds"]["max"]
    tolerance = max(high[i] - low[i] for i in range(3)) * 1e-5
    if abs(low[1]) > tolerance or any(abs((low[i] + high[i]) / 2) > tolerance for i in (0, 2)):
        raise ValueError("GLB pivot is not bottom-centre; normalize before freeze/bind, never at admission")
    if "artifact.json" in evidence.files:
        raise ValueError("terminal artifact aliases an input")
    base = ".img2/artifacts/character"
    skeleton = evidence.save(f"{base}/skeleton.json", extracted["skeleton"])
    clips = []
    for i, clip in enumerate(extracted["clips"]):
        ref = evidence.save(f"{base}/clip-{i}.json", clip)
        clips.append({"name": clip["name"], "sha256": ref["sha256"]})
    evidence.save(f"{base}/rig-admission.json", {"kind": "img2.character-rig-admission", "version": 1,
                  "glbSha256": source_sha, "gateReport": report.to_dict(),
                  "bounds": extracted["bounds"], "metricAnchor": metric,
                  "authoredAnchorDistance": authored, "scaleEstimate": scale,
                  "inputs": request, "boundInputs": list(evidence.files.values())})
    artifact = {"objectId": object_id, "outputKind": "rigged-3d", "frame": dict(FRAME),
                "pivot": "bottom-centre", "scaleEstimate": scale,
                "rig": {"skeletonSha": skeleton["sha256"], "clips": clips},
                "files": sorted((ref for ref in evidence.files.values()
                                 if ref["path"] != sweep_spec["baselineGlb"]["path"]
                                 or ref["path"] == request["glb"]["path"]), key=lambda ref: ref["path"])}
    if publish:
        atomic(evidence.path("artifact.json"), canonical(artifact))
        return artifact
    return {"artifact": artifact, "gateReport": report.to_dict()}


def snapshot_fragment(workspace, source, assets=()):
    """Fresh D21 bindings/observations only; the base owns candidates and authority.

    assets use {role,path,sha256}. No paths enter observations, no unavailable
    render/view is invented, and no provider/semantic judgment can clear a gate.
    """
    evidence = Evidence(workspace)
    evidence.read(source, json_data=False)
    extracted = extract_glb(evidence.path(source["path"]))
    source_sha = extracted["skeleton"]["glbSha256"]
    if source_sha != source["sha256"]:
        raise ValueError("source changed during snapshot")
    bindings = [{"role": "source", **source}]
    observations = {"rig": {"jointCount": len(extracted["rig"].joints),
                            "clipNames": [clip["name"] for clip in extracted["clips"]],
                            "bounds": extracted["bounds"]}}
    seen = {("source", source["path"])}
    for asset in assets:
        if set(asset) != {"role", "path", "sha256"} or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}", asset["role"]):
            raise ValueError("invalid decision evidence binding")
        key = (asset["role"], asset["path"])
        if key in seen:
            raise ValueError("duplicate decision evidence binding")
        seen.add(key)
        data = evidence.read({name: asset[name] for name in ("path", "sha256")}, json_data=False)
        bindings.append(dict(asset))
        if asset["role"] == "gate":
            report = json.loads(data)
            canonical(report)
            if report.get("glbSha256") != source_sha or "gateReport" not in report:
                raise ValueError("gate snapshot does not bind the current GLB")
            if not isinstance(report.get("boundInputs"), list) or not report["boundInputs"]:
                raise ValueError("gate snapshot has no bound measurement inputs")
            for ref in report["boundInputs"]:
                evidence.read(ref, json_data=False)
                if ("gate-input", ref["path"]) not in seen:
                    bindings.append({"role": "gate-input", **ref})
                    seen.add(("gate-input", ref["path"]))
            checks = report["gateReport"].get("gates", [])
            if ({row.get("id") for row in checks} != set(gates.GATE_SPEC_BY_ID)
                    or len(checks) != len(gates.GATE_SPECS)
                    or any(row.get("status") not in ("pass", "fail", "unevaluated") for row in checks)):
                raise ValueError("gate snapshot is incomplete")
            observations["rigGate"] = {
                "checks": [{"id": row["id"], "status": row["status"]} for row in checks]}
    return {"bindings": bindings, "observations": observations}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract")
    extract.add_argument("glb", type=Path)
    extract.add_argument("--out", type=Path, required=True)
    admission = commands.add_parser("admit")
    admission.add_argument("--workspace", type=Path, required=True)
    admission.add_argument("--request", type=Path, required=True)
    snapshot = commands.add_parser("snapshot")
    snapshot.add_argument("--workspace", type=Path, required=True)
    snapshot.add_argument("--request", type=Path, required=True)
    snapshot.add_argument("--out", required=True, help="workspace-relative fragment path")
    args = parser.parse_args(argv)
    try:
        if args.command == "extract":
            result = extract_glb(args.glb)
            outputs = [args.out / name for name in ("mesh-buffers.json", "skeleton.json")]
            outputs.extend(args.out / f"clip-{i}.json" for i in range(len(result["clips"])))
            if any(path.resolve() == args.glb.resolve() for path in outputs):
                raise ValueError("extraction output aliases its GLB source")
            atomic(args.out / "mesh-buffers.json", canonical(result["meshBuffers"]))
            atomic(args.out / "skeleton.json", canonical(result["skeleton"]))
            for i, clip in enumerate(result["clips"]):
                atomic(args.out / f"clip-{i}.json", canonical(clip))
        elif args.command == "admit":
            admit(args.workspace, json.loads(args.request.read_bytes()))
        else:
            request = json.loads(args.request.read_bytes())
            result = snapshot_fragment(args.workspace, request["source"], request.get("assets", []))
            evidence = Evidence(args.workspace)
            input_paths = {binding["path"] for binding in result["bindings"]}
            if args.out in input_paths or evidence.path(args.out) == args.request.resolve():
                raise ValueError("snapshot output aliases an input")
            atomic(evidence.path(args.out), canonical(result))
    except (ValueError, KeyError, IndexError, TypeError, OSError) as error:
        print(f"rigged artifact blocked: {error}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
