"""Native capture/replay and actual Blender-to-browser pose comparison.

Only the host-selected interpreter and owned script execute. Saved native receipts
are data, never authority: the routed gate reopens the bound source and measures again.
"""
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import rigged_artifact as api

PLUGIN = Path(__file__).resolve().parents[1]
# Existing documented native neutral/pose parity limit, reference/blender-rig-interaction.md.
NATIVE_PARITY_OVER_H = 1e-4


def native_python():
    # realpath(python) destroys venv selection for symlinked interpreters.
    selected = os.environ.get("IMG2_CHARACTER_BPY_PYTHON")
    if selected is not None and (not selected or not Path(selected).is_absolute()):
        raise ValueError("producer-dependency-invalid: IMG2_CHARACTER_BPY_PYTHON must be absolute")
    selected = selected if selected is not None else shutil.which("python3")
    if selected is None:
        raise ValueError("producer-dependency-missing: character-bpy>=4.3")
    path = Path(selected)
    invocation = path.parent.resolve(strict=True) / path.name
    if not invocation.is_file() or not os.access(invocation, os.X_OK):
        raise ValueError("producer-dependency-unavailable: native bpy Python")
    return str(invocation)


def run_native(evidence, native, output, *, master=None):
    from gate_routed_terminal import child_environment, file_sha, strict_json
    if not isinstance(native, dict) or set(native) != {"source", "spec"}:
        raise ValueError("native capture requires source blend and explicit binding spec")
    evidence.read(native["source"], json_data=False)
    python = native_python()
    program = PLUGIN / "tools/bpy_capture_routed_rig.py"
    identities = {"executable": python, "sha256": file_sha(python),
                  "programSha256": file_sha(program),
                  "exportHelperSha256": file_sha(PLUGIN / "tools/prepare_softbody.py"),
                  "freezeHelperSha256": file_sha(PLUGIN / "tools/native_glb_freeze.py")}
    job = {"sourcePath": str(evidence.path(native["source"]["path"])),
           "sourceSha256": native["source"]["sha256"], "spec": native["spec"]}
    if master is not None:
        evidence.read(master, json_data=False)
        job.update(masterPath=str(evidence.path(master["path"])), masterSha256=master["sha256"])
    with tempfile.TemporaryDirectory(prefix="img2-native-job-") as temporary:
        path = Path(temporary) / "job.json"
        path.write_bytes(api.canonical(job))
        result = subprocess.run([python, "-I", "-B", str(program), "--input", str(path), "--out", str(output)],
                                env=child_environment(), capture_output=True, text=True, timeout=240)
    if result.returncode:
        raise ValueError("native measurement producer failed: " + (result.stderr or result.stdout).strip())
    receipt = strict_json((output / "native.json").read_bytes())
    if (receipt.get("kind") != "img2.character-native-capture" or receipt.get("version") != 1
            or receipt.get("sourceSha256") != native["source"]["sha256"] or receipt.get("spec") != native["spec"]
            or receipt.get("producerSha256") != identities["programSha256"]):
        raise ValueError("foreign/incomplete owned native capture")
    for ref in receipt["files"]:
        if set(ref) != {"path", "sha256"} or ref["path"] not in ("base.glb", "raw-bound.glb", "character.glb", "character.blend"):
            raise ValueError("foreign native capture output")
        if file_sha(output / ref["path"]) != ref["sha256"]:
            raise ValueError("native capture bytes changed")
    if (file_sha(python) != identities["sha256"] or file_sha(program) != identities["programSha256"]
            or file_sha(PLUGIN / "tools/prepare_softbody.py") != identities["exportHelperSha256"]
            or file_sha(PLUGIN / "tools/native_glb_freeze.py") != identities["freezeHelperSha256"]):
        raise ValueError("owned native executable/program changed")
    evidence.read(native["source"], json_data=False)
    return receipt, identities


def geometry(path):
    """Actual accessor bytes, including type/normalization, not JSON accessor bounds."""
    document, binary, _ = api.glb.parse_glb(path)
    result = {}
    for i, node in enumerate(document.get("nodes", [])):
        if "mesh" not in node:
            continue
        name = node.get("name")
        if not name or name in result:
            raise ValueError("native export requires unique mesh object names")
        primitives = []
        for primitive in document["meshes"][node["mesh"]]["primitives"]:
            values, raw = {}, {}
            for source, target in (("POSITION", "position"), ("NORMAL", "normal"), ("TEXCOORD_0", "uv"),
                                   ("indices", "index")):
                index = primitive.get("indices") if source == "indices" else primitive["attributes"].get(source)
                if index is None:
                    continue
                accessor = document["accessors"][index]
                if "sparse" in accessor or "bufferView" not in accessor:
                    raise ValueError("native sparse accessors need a separate binary parity producer")
                view = document["bufferViews"][accessor["bufferView"]]
                size = api.glb._COMPONENT_FORMATS[accessor["componentType"]][1] * api.glb._TYPE_COMPONENTS[accessor["type"]]
                stride = view.get("byteStride", size)
                start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
                packed = b"".join(binary[start + n * stride:start + n * stride + size]
                                  for n in range(accessor["count"]))
                if len(packed) != accessor["count"] * size:
                    raise ValueError("native geometry accessor exceeds actual bytes")
                raw[target] = {"type": accessor["type"], "componentType": accessor["componentType"],
                               "normalized": accessor.get("normalized", False), "count": accessor["count"],
                               "sha256": api.digest(packed)}
                values[target] = [v for row in api.glb.read_accessor(document, binary, index) for v in row]
            primitives.append({"name": f"node:{i}/primitive:{len(primitives)}",
                               "attributes": {key: value for key, value in values.items() if key != "index"},
                               "index": values.get("index"), "binary": raw})
        result[name] = primitives
    return result


def freeze_export(base, delivery, spec):
    before, after = geometry(base), geometry(delivery)
    if set(before) != set(spec["meshes"]) or set(after) != set(before):
        raise ValueError("native pre/post export mesh roster differs from frozen source")
    frozen = []
    for name in before:
        if len(before[name]) != len(after[name]):
            raise ValueError("binding changed native exported primitive roster")
        for old, new in zip(before[name], after[name]):
            if old["binary"] != new["binary"]:
                raise ValueError("binding changed frozen binary position/normal/UV/index accessors")
            frozen.append({"name": new["name"], "attributes": old["attributes"], "index": old["index"]})
    manifest = api.parity.freeze({"meshes": frozen}).to_dict()
    extracted = api.extract_glb(delivery)
    if not api.parity.verify(api.parity.Manifest.from_dict(manifest), extracted["meshBuffers"]).ok:
        raise ValueError("native export failed pre-bind mesh parity")
    return manifest


def compare_poses(receipt, extracted, runtime):
    """Match by measured rest position; ambiguous coincident deformation is rejected.

    Exporters may split UV/hard-edge vertices. Every delivered split vertex must
    correspond to a real native vertex and its actual evaluated posed position.
    """
    rig = extracted["rig"]
    world = api.glb.rest_world_matrices(rig)
    nodes = rig._document["nodes"]
    height = extracted["bounds"]["max"][1] - extracted["bounds"]["min"][1]
    tolerance = height * NATIVE_PARITY_OVER_H
    if not api.positive(tolerance):
        raise ValueError("native parity has no finite figure height")
    clips = [clip["name"] for clip in extracted["clips"]]
    samples = runtime.get("poseSamples", {})
    if set(samples) != set(clips) or set(receipt["poseSamples"]) != set(clips):
        raise ValueError("native/browser parity clip coverage differs")
    maximum, comparisons = 0., 0
    native_displacement = browser_displacement = 0.
    for mesh in extracted["meshBuffers"]["meshes"]:
        node = int(mesh["name"].split("/")[0].split(":")[1])
        name, matrix = nodes[node]["name"], world[node]
        source = receipt["restWorld"][name]
        positions = mesh["attributes"]["position"]
        # Spatial buckets keep matching linear for normal character vertex distributions.
        buckets = {}
        for index, point in enumerate(source):
            key = tuple(math.floor(v / tolerance) for v in point)
            buckets.setdefault(key, []).append(index)
        matches, world_rest = [], []
        for i in range(0, len(positions), 3):
            p = positions[i:i + 3]
            point = [sum(matrix[c * 4 + a] * p[c] for c in range(3)) + matrix[12 + a] for a in range(3)]
            world_rest.append(point)
            cell = tuple(math.floor(v / tolerance) for v in point)
            candidates = [j for x in (-1, 0, 1) for y in (-1, 0, 1) for z in (-1, 0, 1)
                          for j in buckets.get((cell[0] + x, cell[1] + y, cell[2] + z), ())
                          if math.dist(source[j], point) <= tolerance]
            if not candidates:
                raise ValueError("exported vertex has no native frozen rest correspondence")
            matches.append(candidates)
        for clip in clips:
            native_frames, browser_frames = receipt["poseSamples"][clip], samples[clip]
            if (len(native_frames) != 5 or len(browser_frames) != 5
                    or [f["fraction"] for f in native_frames] != [0, .25, .5, .75, 1]
                    or [f["fraction"] for f in browser_frames] != [0, .25, .5, .75, 1]):
                raise ValueError("native/browser pose parity requires all five matched fractions")
            for native, browser in zip(native_frames, browser_frames):
                actual = browser["meshes"][mesh["name"]]
                expected = native["meshes"][name]
                if len(actual) != len(positions) or len(expected) != len(source):
                    raise ValueError("native/browser vertex coverage differs")
                for i, candidates in enumerate(matches):
                    # Do not pick whichever coincident vertex happens to make the pose pass.
                    if any(math.dist(expected[candidates[0]], expected[j]) > tolerance for j in candidates):
                        raise ValueError("ambiguous native split-vertex deformation correspondence")
                    delta = math.dist(actual[i * 3:i * 3 + 3], expected[candidates[0]])
                    if not math.isfinite(delta) or delta > tolerance:
                        raise ValueError("actual Blender/browser posed vertex parity failed")
                    maximum = max(maximum, delta)
                    native_displacement = max(native_displacement,
                                              math.dist(expected[candidates[0]], source[candidates[0]]))
                    browser_displacement = max(browser_displacement,
                                               math.dist(actual[i * 3:i * 3 + 3], world_rest[i]))
                    comparisons += 1
    return {"maxWorldVertexDelta": maximum, "tolerance": tolerance,
            "toleranceOverH": NATIVE_PARITY_OVER_H, "vertexComparisons": comparisons,
            "maxNativeDisplacement": native_displacement, "maxBrowserDisplacement": browser_displacement,
            "clips": clips, "fractions": [0, .25, .5, .75, 1]}
