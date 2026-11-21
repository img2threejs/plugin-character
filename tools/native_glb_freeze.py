"""Preserve authored pre-bind normals through bpy's extra skin-normal normalization.

No tolerant comparison: positions, UVs, index values, formats and vertex order must
already be byte-identical. Only NORMAL payload bytes are restored from the actual
pre-bind export. JSON, rig, inverse binds, skin weights/indices and clips stay exact.
Actual native/browser world-vertex parity is independently required by the caller.
"""
import hashlib
from pathlib import Path
import struct

from prepare_softbody import read_glb


def sha(data):
    return hashlib.sha256(data).hexdigest()


def accessor(document, binary, index):
    value = document["accessors"][index]
    if "sparse" in value or "bufferView" not in value:
        raise ValueError("native frozen export requires dense embedded accessors")
    view = document["bufferViews"][value["bufferView"]]
    if view.get("buffer", 0) != 0:
        raise ValueError("native frozen export requires its embedded buffer")
    sizes = {5121: 1, 5123: 2, 5125: 4, 5126: 4}
    components = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
    size = sizes[value["componentType"]] * components[value["type"]]
    stride = view.get("byteStride", size)
    start = view.get("byteOffset", 0) + value.get("byteOffset", 0)
    ranges = [(start + i * stride, start + i * stride + size) for i in range(value["count"])]
    if any(a < 0 or b > len(binary) for a, b in ranges):
        raise ValueError("native accessor exceeds actual binary")
    packed = b"".join(binary[a:b] for a, b in ranges)
    metadata = (value["componentType"], value["type"], value["count"], value.get("normalized", False))
    return metadata, packed, ranges


def primitives(document):
    result = {}
    for node in document["nodes"]:
        if "mesh" not in node:
            continue
        name = node.get("name")
        if not name or name in result:
            raise ValueError("native freeze requires unique mesh identities")
        result[name] = document["meshes"][node["mesh"]]["primitives"]
    return result


def overlaps(left, right):
    i = j = 0
    while i < len(left) and j < len(right):
        a, b = left[i]
        c, d = right[j]
        if a < d and c < b:
            return True
        if b <= c:
            i += 1
        else:
            j += 1
    return False


def preserve_normals(base_path, bound_path, delivery_path):
    before, base_binary = read_glb(base_path)
    after, bound_binary = read_glb(bound_path)
    base, bound = primitives(before), primitives(after)
    if set(base) != set(bound):
        raise ValueError("binding changed frozen mesh roster")
    data = bytearray(Path(bound_path).read_bytes())
    cursor, bin_start = 12, None
    while cursor < len(data):
        length, kind = struct.unpack_from("<II", data, cursor)
        if kind == 0x004E4942:
            bin_start = cursor + 8
            break
        cursor += 8 + length
    if bin_start is None:
        raise ValueError("native bound export has no embedded binary")
    restored = []
    for name in base:
        if len(base[name]) != len(bound[name]):
            raise ValueError("binding changed frozen primitive order/count")
        for i, (old, new) in enumerate(zip(base[name], bound[name])):
            for semantic in ("POSITION", "TEXCOORD_0", "indices"):
                a = old.get("indices") if semantic == "indices" else old["attributes"].get(semantic)
                b = new.get("indices") if semantic == "indices" else new["attributes"].get(semantic)
                if (a is None) != (b is None):
                    raise ValueError("binding changed frozen accessor roster")
                if a is not None and accessor(before, base_binary, a)[:2] != accessor(after, bound_binary, b)[:2]:
                    raise ValueError("binding changed exact frozen position/UV/index bytes or vertex order")
            a, b = old["attributes"].get("NORMAL"), new["attributes"].get("NORMAL")
            if (a is None) != (b is None):
                raise ValueError("binding changed authored normal roster")
            if a is None:
                continue
            meta, payload, _ = accessor(before, base_binary, a)
            other_meta, other_payload, ranges = accessor(after, bound_binary, b)
            if meta != other_meta or meta[0:2] != (5126, "VEC3"):
                raise ValueError("binding changed authored normal format/count")
            # A normal correction must not alias any rig/skin/animation/other accessor.
            for index in range(len(after["accessors"])):
                if index == b:
                    continue
                _, _, other_ranges = accessor(after, bound_binary, index)
                if overlaps(ranges, other_ranges):
                    raise ValueError("normal payload aliases non-normal accessor bytes")
            for j, (start, end) in enumerate(ranges):
                data[bin_start + start:bin_start + end] = payload[j * 12:(j + 1) * 12]
            restored.append({"mesh": name, "primitive": i, "beforeSha256": sha(other_payload),
                             "frozenSha256": sha(payload), "changed": other_payload != payload})
    Path(delivery_path).write_bytes(data)
    return {"kind": "img2.character-frozen-normal-preservation", "version": 1,
            "baseGlbSha256": sha(Path(base_path).read_bytes()),
            "rawBoundGlbSha256": sha(Path(bound_path).read_bytes()),
            "deliveryGlbSha256": sha(data), "accessors": restored}
