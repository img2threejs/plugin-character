"""Inventory of a character GLB: what is in the file, measured from its JSON and buffers.

This is the first of three construction-prior modules (`inventory`, `anatomy`, `construction`).
It answers "what does this asset contain and how big is each part" and nothing about anatomy or
topology quality. Every number under `observed` is read or computed from the file; everything under
`inferred` is a heuristic and carries a `basis` string saying why. `limits` lists what this module
cannot know.

    analyze(glb_path, body_mesh=None, figure_height=None) -> dict

Required top-level keys: `schema`, `observed`, `inferred`, `limits`; plus `warnings` (data the
reader could not decode, never silently dropped).

Conventions
-----------
* Distances are metres. `...Frac` fields are fractions of the figure height H. Y is floor-relative
  (`(y - floorY) / H`, floorY = lowest mesh vertex); X and Z fractions are `value / H` about the
  world origin, because the origin, not a vertex, is the symmetry reference.
* H is measured from the world-space bounds of every mesh in the file (`heightSource`), never
  assumed. If no mesh has vertices H is `None` and every fraction is `None`.
* Skinned meshes are read in their stored (bind) space: glTF ignores the node transform of a skinned
  mesh, and the rest-pose cancellation check in `observed.skins` is what tells the caller whether
  that bind space equals the rest pose. Unskinned meshes are transformed by their node's world matrix.

Pure Python 3.10+ stdlib; reuses the GLB reader in `rig_glb_reference`.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
import sys
import zlib
from pathlib import Path
from typing import Any, Sequence

_TOOLS_DIR = str(Path(__file__).resolve().parent.parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import rig_glb_reference as rgr  # noqa: E402

SCHEMA = "img2.character-prior.inventory/1"

# A vertex "supports" a mask when its strength exceeds this. 0.01 matches the softbody mask contract.
SUPPORT_THRESHOLD = 0.01
# A mask value at or above this counts as saturated (fully on).
SATURATION_THRESHOLD = 0.99
# A skin weight below this is not an influence.
INFLUENCE_EPSILON = 1e-6
# Weight sums within this of 1.0 count as normalised.
WEIGHT_SUM_TOLERANCE = 1e-3
# Rest-pose cancellation: |jointWorld * inverseBind - I| above this means bind pose != rest pose.
REST_CANCELLATION_TOLERANCE = 1e-4
# Plausible human-scale H (metres) for the units sanity check.
PLAUSIBLE_HEIGHT_RANGE_M = (0.3, 3.0)
# Role-classifier geometry thresholds, as fractions of H.
FACE_BAND_MIN_Y = 0.85
FACE_DETAIL_MAX_DIM = 0.15
HAIR_TOP_MIN_Y = 0.95
HAIR_CENTROID_MIN_Y = 0.70
HAIR_MIN_VERTICES = 1000
FOOTWEAR_MAX_Y = 0.15
PROP_MAX_DIM = 0.12
NODE_LIST_CAP = 500
ROUND = 6

_COMPONENT_NAMES = {
    5120: "BYTE", 5121: "UNSIGNED_BYTE", 5122: "SHORT", 5123: "UNSIGNED_SHORT",
    5125: "UNSIGNED_INT", 5126: "FLOAT",
}
_COMPONENT_BYTES = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
_TYPE_COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}
_PRIMITIVE_MODES = {0: "POINTS", 1: "LINES", 2: "LINE_LOOP", 3: "LINE_STRIP", 4: "TRIANGLES",
                    5: "TRIANGLE_STRIP", 6: "TRIANGLE_FAN"}
_FILTERS = {9728: "NEAREST", 9729: "LINEAR", 9984: "NEAREST_MIPMAP_NEAREST",
            9985: "LINEAR_MIPMAP_NEAREST", 9986: "NEAREST_MIPMAP_LINEAR", 9987: "LINEAR_MIPMAP_LINEAR"}
_WRAPS = {33071: "CLAMP_TO_EDGE", 33648: "MIRRORED_REPEAT", 10497: "REPEAT"}
_PNG_COLOR_TYPES = {0: "greyscale", 2: "truecolour", 3: "indexed", 4: "greyscale+alpha", 6: "truecolour+alpha"}
_PNG_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
_MATERIAL_TEXTURE_SLOTS = (
    ("baseColorTexture", ("pbrMetallicRoughness", "baseColorTexture")),
    ("metallicRoughnessTexture", ("pbrMetallicRoughness", "metallicRoughnessTexture")),
    ("normalTexture", ("normalTexture",)),
    ("occlusionTexture", ("occlusionTexture",)),
    ("emissiveTexture", ("emissiveTexture",)),
)

_FACE_WORDS = {"brow", "eyebrow", "lash", "eyelash", "eye", "iris", "pupil", "cornea", "sclera", "teeth",
               "tooth", "tongue", "mouth", "lip", "nose", "ear", "face", "gum", "eyelid"}
_HAIR_WORDS = {"hair", "fringe", "bang", "ponytail", "braid", "bun", "wig"}
_FOOTWEAR_WORDS = {"shoe", "boot", "feet", "foot", "sandal", "sock", "heel", "sneaker", "slipper"}
_GARMENT_WORDS = {"jean", "pant", "trouser", "skirt", "short", "shirt", "top", "bikini", "bra", "dress",
                  "jacket", "coat", "cloth", "clothe", "glove", "sleeve", "vest", "hoodie", "sweater",
                  "tight", "stocking", "swimsuit", "bodysuit", "legging", "blouse", "robe", "kimono"}
_PROP_WORDS = {"belt", "charm", "bag", "weapon", "sword", "staff", "hat", "cap", "glass", "jewel",
               "earring", "necklace", "bracelet", "watch", "prop", "chain", "crown", "ribbon", "bow",
               "scarf", "tie", "accessory", "pendant"}
_SKIN_MATERIAL_WORDS = {"skin", "body", "dielectric", "flesh"}


# --------------------------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------------------------


def _r(value: float | None, digits: int = ROUND) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(float(value), digits) + 0.0


def _rv(vector: Sequence[float] | None) -> list[float | None] | None:
    return None if vector is None else [_r(v) for v in vector]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tokens(*names: str | None) -> list[str]:
    """Lower-case word tokens from names, splitting camelCase and punctuation, digits dropped."""
    out: list[str] = []
    for name in names:
        if not name:
            continue
        spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(name))
        for token in re.split(r"[^A-Za-z]+", spaced):
            if token:
                out.append(token.lower())
    return out


def _token_hit(tokens: Sequence[str], words: set[str]) -> str | None:
    for token in tokens:
        stems = {token, token.rstrip("s")}
        if token.endswith("es"):
            stems.add(token[:-2])
        if stems & words:
            return token
        # compound names written without a case boundary ("beltcharm"): longer role words match inside
        for word in words:
            if len(word) >= 4 and word in token:
                return token
    return None


class _Frame:
    """Fractions of H about the floor. Everything degrades to None when H is unknown."""

    def __init__(self, height: float | None, floor_y: float | None) -> None:
        self.height = height
        self.floor_y = floor_y

    def point(self, p: Sequence[float] | None) -> list[float | None] | None:
        if p is None or not self.height or self.floor_y is None:
            return None
        return [_r(p[0] / self.height), _r((p[1] - self.floor_y) / self.height), _r(p[2] / self.height)]

    def length(self, value: float | None) -> float | None:
        if value is None or not self.height:
            return None
        return _r(value / self.height)

    def vector(self, v: Sequence[float]) -> list[float | None] | None:
        if not self.height:
            return None
        return [_r(c / self.height) for c in v]


def _box(frame: _Frame, lo: Sequence[float] | None, hi: Sequence[float] | None) -> dict[str, Any] | None:
    if lo is None or hi is None:
        return None
    size = [hi[i] - lo[i] for i in range(3)]
    return {
        "minM": _rv(lo), "maxM": _rv(hi), "sizeM": _rv(size),
        "minFrac": frame.point(lo), "maxFrac": frame.point(hi), "sizeFrac": frame.vector(size),
    }


def _bounds(points: Sequence[Sequence[float]]) -> tuple[list[float], list[float]] | None:
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return [min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]


def _mean_point(points: Sequence[Sequence[float]]) -> list[float] | None:
    if not points:
        return None
    n = len(points)
    return [sum(p[0] for p in points) / n, sum(p[1] for p in points) / n, sum(p[2] for p in points) / n]


# --------------------------------------------------------------------------------------------
# image headers
# --------------------------------------------------------------------------------------------


def decode_png_header(data: bytes) -> dict[str, Any]:
    """PNG IHDR plus the ancillary chunk names present. Never raises: failures become `error`."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return {"format": "unknown", "error": "missing PNG signature"}
    if len(data) < 33 or data[12:16] != b"IHDR":
        return {"format": "png", "error": "IHDR chunk missing or truncated"}
    length, = struct.unpack_from(">I", data, 8)
    width, height, depth, color, compression, filt, interlace = struct.unpack_from(">IIBBBBB", data, 16)
    crc_stored, = struct.unpack_from(">I", data, 29)
    crc_ok = (zlib.crc32(data[12:29]) & 0xFFFFFFFF) == crc_stored if length == 13 else False
    chunk_names: list[str] = []
    cursor = 8
    while cursor + 8 <= len(data) and len(chunk_names) < 1000:
        chunk_length, = struct.unpack_from(">I", data, cursor)
        name = data[cursor + 4:cursor + 8].decode("latin-1")
        if name not in chunk_names:
            chunk_names.append(name)
        cursor += 12 + chunk_length
        if name == "IEND":
            break
    channels = _PNG_CHANNELS.get(color)
    return {
        "format": "png", "width": width, "height": height, "bitDepth": depth,
        "colorType": color, "colorTypeName": _PNG_COLOR_TYPES.get(color, "unknown"),
        "channels": channels, "hasAlphaChannel": color in (4, 6) or "tRNS" in chunk_names,
        "interlaceMethod": interlace, "ihdrCrcOk": crc_ok, "chunkNames": chunk_names,
        "compressionMethod": compression, "filterMethod": filt,
    }


def decode_jpeg_header(data: bytes) -> dict[str, Any]:
    """JPEG start-of-frame header. Never raises: failures become `error`."""
    if data[:2] != b"\xff\xd8":
        return {"format": "unknown", "error": "missing JPEG SOI"}
    cursor = 2
    while cursor + 4 <= len(data):
        if data[cursor] != 0xFF:
            cursor += 1
            continue
        marker = data[cursor + 1]
        if marker in (0xFF,):
            cursor += 1
            continue
        if marker == 0xD8 or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            cursor += 2
            continue
        length, = struct.unpack_from(">H", data, cursor + 2)
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            precision, height, width, components = struct.unpack_from(">BHHB", data, cursor + 4)
            return {
                "format": "jpeg", "width": width, "height": height, "bitDepth": precision,
                "channels": components, "progressive": marker in (0xC2, 0xC6, 0xCA, 0xCE),
                "sofMarker": f"0x{marker:02X}",
            }
        cursor += 2 + length
    return {"format": "jpeg", "error": "no SOF marker found"}


def _sniff_image(data: bytes) -> dict[str, Any]:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return decode_png_header(data)
    if data[:2] == b"\xff\xd8":
        return decode_jpeg_header(data)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return {"format": "webp", "error": "header not decoded (WebP)"}
    if data[:12] == b"\xabKTX 20\xbb\r\n\x1a\n":
        width, height = struct.unpack_from("<II", data, 20) if len(data) >= 28 else (None, None)
        return {"format": "ktx2", "width": width, "height": height}
    return {"format": "unknown", "error": "unrecognised image magic"}


# --------------------------------------------------------------------------------------------
# buffers
# --------------------------------------------------------------------------------------------


def _view_slice(document: dict[str, Any], bin_payload: bytes, view_index: int) -> bytes:
    view = document["bufferViews"][view_index]
    start = int(view.get("byteOffset", 0))
    return bin_payload[start:start + int(view.get("byteLength", 0))]


def _image_bytes(document: dict[str, Any], bin_payload: bytes, image: dict[str, Any], base: Path) -> tuple[bytes | None, str]:
    """(bytes, origin). Origin names where the bytes came from, or why there are none."""
    if isinstance(image.get("bufferView"), int):
        try:
            return _view_slice(document, bin_payload, image["bufferView"]), "bufferView"
        except (IndexError, KeyError, TypeError):
            return None, "bufferView missing"
    uri = image.get("uri")
    if isinstance(uri, str):
        if uri.startswith("data:"):
            head, _, payload = uri.partition(",")
            if ";base64" in head:
                import base64
                try:
                    return base64.b64decode(payload), "data-uri"
                except ValueError:
                    return None, "data-uri undecodable"
            return None, "data-uri not base64"
        target = (base / uri)
        if target.is_file():
            return target.read_bytes(), "external-file"
        return None, "external-uri not found"
    return None, "no source"


# --------------------------------------------------------------------------------------------
# geometry reading
# --------------------------------------------------------------------------------------------


def _read(document: dict[str, Any], bin_payload: bytes, index: Any, warnings: list[str], what: str) -> list[tuple[float, ...]] | None:
    if not isinstance(index, int):
        return None
    try:
        return rgr.read_accessor(document, bin_payload, index)
    except (ValueError, KeyError, IndexError, TypeError, struct.error) as exc:
        warnings.append(f"{what}: accessor {index} not decoded ({exc})")
        return None


def _mat_apply(matrix: Sequence[float], p: Sequence[float]) -> tuple[float, float, float]:
    x, y, z = p[0], p[1], p[2]
    return (
        matrix[0] * x + matrix[4] * y + matrix[8] * z + matrix[12],
        matrix[1] * x + matrix[5] * y + matrix[9] * z + matrix[13],
        matrix[2] * x + matrix[6] * y + matrix[10] * z + matrix[14],
    )


def _is_identity(matrix: Sequence[float], tol: float = 1e-9) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(matrix, rgr.IDENTITY_MATRIX))


def _triangles(mode: int, indices: list[int]) -> list[tuple[int, int, int]]:
    if mode == 4:
        return [(indices[i], indices[i + 1], indices[i + 2]) for i in range(0, len(indices) - 2, 3)]
    if mode == 5:
        out = []
        for i in range(len(indices) - 2):
            a, b, c = indices[i], indices[i + 1], indices[i + 2]
            out.append((a, b, c) if i % 2 == 0 else (b, a, c))
        return out
    if mode == 6:
        return [(indices[0], indices[i], indices[i + 1]) for i in range(1, len(indices) - 1)]
    return []


def _surface_stats(tris: list[tuple[int, int, int]], positions: Sequence[Sequence[float]]) -> dict[str, Any]:
    area = 0.0
    degenerate = 0
    out_of_range = 0
    count = len(positions)
    for a, b, c in tris:
        if a >= count or b >= count or c >= count:
            out_of_range += 1
            continue
        pa, pb, pc = positions[a], positions[b], positions[c]
        ux, uy, uz = pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]
        vx, vy, vz = pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2]
        cx, cy, cz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        twice = math.sqrt(cx * cx + cy * cy + cz * cz)
        if a == b or b == c or a == c or twice < 1e-14:
            degenerate += 1
        area += 0.5 * twice
    return {"surfaceAreaM2": area, "degenerateTriangles": degenerate, "indicesOutOfRangeTriangles": out_of_range}


class _MeshAcc:
    """Everything gathered for one mesh across its primitives, in metres."""

    def __init__(self, index: int, mesh: dict[str, Any]) -> None:
        self.index = index
        self.name = str(mesh.get("name") or f"mesh-{index}")
        self.positions: list[tuple[float, float, float]] = []
        self.primitives: list[dict[str, Any]] = []
        self.custom: dict[str, tuple[list[tuple[float, ...]], list[tuple[float, float, float]], dict[str, Any]]] = {}
        self.colors: dict[str, tuple[list[tuple[float, ...]], dict[str, Any]]] = {}
        self.uvs: list[tuple[float, ...]] = []
        self.triangles = 0
        self.surface = {"surfaceAreaM2": 0.0, "degenerateTriangles": 0, "indicesOutOfRangeTriangles": 0}
        self.morph_targets = 0
        self.nodes: list[int] = []
        self.skin_index: int | None = None
        self.materials: list[int | None] = []
        self.influence: dict[str, Any] | None = None


def _accessor_meta(document: dict[str, Any], index: int) -> dict[str, Any]:
    accessor = document.get("accessors", [])[index]
    ctype = int(accessor.get("componentType", 5126))
    return {
        "accessor": index, "type": accessor.get("type"), "componentType": _COMPONENT_NAMES.get(ctype, ctype),
        "normalized": bool(accessor.get("normalized", False)), "count": int(accessor.get("count", 0)),
    }


def _value_stats(values: list[tuple[float, ...]], positions: Sequence[Sequence[float]] | None,
                 frame_ready: bool = True) -> dict[str, Any]:
    """Per-component min/max/sum/mean plus support statistics for a custom attribute."""
    n = len(values)
    if n == 0:
        return {"count": 0}
    width = len(values[0])
    comps = []
    for c in range(width):
        col = [v[c] for v in values]
        total = math.fsum(col)
        comps.append({"min": _r(min(col)), "max": _r(max(col)), "sum": _r(total, 4), "mean": _r(total / n)})
    strength = [max(abs(c) for c in v) for v in values] if width > 1 else [v[0] for v in values]
    support_idx = [i for i, s in enumerate(strength) if s > SUPPORT_THRESHOLD]
    support_vals = [strength[i] for i in support_idx]
    out: dict[str, Any] = {
        "count": n, "components": width,
        "perComponent": comps,
        "supportThreshold": SUPPORT_THRESHOLD,
        "supportCount": len(support_idx),
        "supportFraction": _r(len(support_idx) / n),
        "max": _r(max(strength)),
        "meanOverSupport": _r(math.fsum(support_vals) / len(support_vals)) if support_vals else None,
        "sum": _r(math.fsum(strength), 4),
        "saturatedCount": sum(1 for s in strength if s >= SATURATION_THRESHOLD),
        "nonFiniteCount": sum(1 for v in values if not all(math.isfinite(c) for c in v)),
    }
    if positions is not None and len(positions) == n and support_idx:
        weight_total = math.fsum(support_vals)
        if weight_total > 0:
            centroid = [
                math.fsum(strength[i] * positions[i][axis] for i in support_idx) / weight_total
                for axis in range(3)
            ]
            lo, hi = _bounds([positions[i] for i in support_idx])  # type: ignore[misc]
            out["_centroidM"] = centroid
            out["_supportBoundsM"] = (lo, hi)
    return out


def _finish_value_stats(stats: dict[str, Any], frame: _Frame) -> dict[str, Any]:
    centroid = stats.pop("_centroidM", None)
    bounds = stats.pop("_supportBoundsM", None)
    if centroid is not None:
        stats["weightedCentroidM"] = _rv(centroid)
        stats["weightedCentroidFrac"] = frame.point(centroid)
    if bounds is not None:
        stats["supportBounds"] = _box(frame, bounds[0], bounds[1])
    return stats


def _color_stats(values: list[tuple[float, ...]]) -> dict[str, Any]:
    n = len(values)
    if n == 0:
        return {"count": 0}
    width = len(values[0])
    comps = []
    for c in range(width):
        col = [v[c] for v in values]
        comps.append({"min": _r(min(col)), "max": _r(max(col)), "mean": _r(math.fsum(col) / n)})
    return {"count": n, "components": width, "perComponent": comps,
            "constant": all(c["min"] == c["max"] for c in comps)}


def _influence_stats(sets: list[tuple[list[tuple[float, ...]], list[tuple[float, ...]]]], joint_count: int) -> dict[str, Any]:
    """Skin influence statistics over every JOINTS_n/WEIGHTS_n pair of one primitive."""
    n = len(sets[0][0])
    sums = [0.0] * n
    nonzero = [0] * n
    mass: dict[int, float] = {}
    verts: dict[int, int] = {}
    dominant: dict[int, int] = {}
    out_of_range = 0
    negative = 0
    for joints, weights in sets:
        for v in range(min(n, len(joints), len(weights))):
            for jv, wv in zip(joints[v], weights[v]):
                if wv < 0:
                    negative += 1
                if wv > INFLUENCE_EPSILON:
                    j = int(jv)
                    sums[v] += wv
                    nonzero[v] += 1
                    mass[j] = mass.get(j, 0.0) + wv
                    verts[j] = verts.get(j, 0) + 1
                    if j >= joint_count:
                        out_of_range += 1
    # dominant joint = highest weight across sets
    for v in range(n):
        best_w, best_j = 0.0, None
        for joints, weights in sets:
            if v < len(joints):
                for jv, wv in zip(joints[v], weights[v]):
                    if wv > best_w:
                        best_w, best_j = wv, int(jv)
        if best_j is not None:
            dominant[best_j] = dominant.get(best_j, 0) + 1
    return {
        "vertexCount": n, "sums": sums, "nonzero": nonzero, "mass": mass, "vertices": verts,
        "dominant": dominant, "outOfRange": out_of_range, "negative": negative,
    }


def _merge_influence(into: dict[str, Any] | None, part: dict[str, Any]) -> dict[str, Any]:
    if into is None:
        return part
    into["vertexCount"] += part["vertexCount"]
    into["sums"].extend(part["sums"])
    into["nonzero"].extend(part["nonzero"])
    for key in ("mass", "vertices", "dominant"):
        for j, value in part[key].items():
            into[key][j] = into[key].get(j, 0) + value
    into["outOfRange"] += part["outOfRange"]
    into["negative"] += part["negative"]
    return into


# --------------------------------------------------------------------------------------------
# skin / rig
# --------------------------------------------------------------------------------------------


def _skin_sections(rig: rgr.GlbRig, world: list[Any] | None, frame: _Frame,
                   meshes: list[_MeshAcc], warnings: list[str]) -> list[dict[str, Any]]:
    document = rig._document
    out: list[dict[str, Any]] = []
    nodes = document.get("nodes", [])
    for skin in rig.skins:
        joint_nodes = {j.node_index: j.skin_joint_index for j in skin.joints}
        positions: dict[int, list[float] | None] = {}
        for joint in skin.joints:
            if world is not None and 0 <= joint.node_index < len(world):
                positions[joint.skin_joint_index] = list(rgr.matrix_translation(world[joint.node_index]))
            else:
                positions[joint.skin_joint_index] = None

        # inverse-bind sanity: world(joint) * inverseBind == identity iff bind pose is the rest pose
        cancellation: list[dict[str, Any]] = []
        worst = 0.0
        if world is not None:
            for joint, ibm in zip(skin.joints, skin.inverse_bind_matrices):
                if not 0 <= joint.node_index < len(world):
                    continue
                product = rgr.multiply(world[joint.node_index], tuple(ibm))
                error = max(abs(a - b) for a, b in zip(product, rgr.IDENTITY_MATRIX))
                worst = max(worst, error)
                cancellation.append({"skinJointIndex": joint.skin_joint_index, "joint": joint.node_name,
                                     "maxAbsError": _r(error, 9)})

        # skeleton depth (within the skin's joint set) and in-skin children
        parent_in_skin: dict[int, int | None] = {}
        for joint in skin.joints:
            parent = joint.parent_node_index
            parent_in_skin[joint.skin_joint_index] = joint_nodes.get(parent) if parent is not None else None
        children: dict[int, list[int]] = {j.skin_joint_index: [] for j in skin.joints}
        for child, parent in parent_in_skin.items():
            if parent is not None:
                children[parent].append(child)

        def depth(slot: int, seen: frozenset[int] = frozenset()) -> int:
            parent = parent_in_skin.get(slot)
            return 0 if parent is None or slot in seen else 1 + depth(parent, seen | {slot})

        carried: dict[int, list[dict[str, Any]]] = {j.skin_joint_index: [] for j in skin.joints}
        for mesh in meshes:
            if mesh.skin_index != skin.skin_index or mesh.influence is None:
                continue
            for slot, count in sorted(mesh.influence["vertices"].items()):
                if slot in carried:
                    carried[slot].append({"mesh": mesh.name, "vertices": count,
                                          "weightMass": _r(mesh.influence["mass"].get(slot, 0.0), 3),
                                          "dominantVertices": mesh.influence["dominant"].get(slot, 0)})

        joints_out = []
        for joint in skin.joints:
            slot = joint.skin_joint_index
            pos = positions.get(slot)
            parent_slot = parent_in_skin.get(slot)
            parent_pos = positions.get(parent_slot) if parent_slot is not None else None
            local = None
            bone_length = None
            if pos is not None and parent_pos is not None:
                local = [pos[i] - parent_pos[i] for i in range(3)]
                bone_length = math.sqrt(sum(c * c for c in local))
            joints_out.append({
                "skinJointIndex": slot, "node": joint.node_index, "name": joint.node_name,
                "parentSkinJointIndex": parent_slot,
                "parentName": skin.joints[parent_slot].node_name if parent_slot is not None else None,
                "depthInSkin": depth(slot),
                "childSkinJointIndices": sorted(children[slot]),
                "restPositionM": _rv(pos), "restPositionFrac": frame.point(pos) if pos else None,
                "offsetFromParentM": _rv(local), "offsetFromParentFrac": frame.vector(local) if local else None,
                "boneLengthM": _r(bone_length), "boneLengthFrac": frame.length(bone_length),
                "carriesMeshes": carried[slot],
            })

        out.append({
            "skinIndex": skin.skin_index, "name": skin.name, "jointCount": len(skin.joints),
            "jointOrderAuthority": "skin.joints",
            "skeletonNode": skin.skeleton_node_index,
            "skeletonNodeName": nodes[skin.skeleton_node_index].get("name") if skin.skeleton_node_index is not None and skin.skeleton_node_index < len(nodes) else None,
            "joints": joints_out,
            "inverseBindSource": skin.inverse_bind_source,
            "restCancellation": {
                "basis": "max |world(joint) * inverseBind - I| over 16 entries; ~0 means the bind pose equals the node rest pose",
                "maxAbsError": _r(worst, 9) if cancellation else None,
                "tolerance": REST_CANCELLATION_TOLERANCE,
                "bindPoseEqualsRestPose": (worst <= REST_CANCELLATION_TOLERANCE) if cancellation else None,
                "perJoint": cancellation,
            },
        })
    return out


def _animation_section(rig: rgr.GlbRig) -> list[dict[str, Any]]:
    joint_nodes = {j.node_index for skin in rig.skins for j in skin.joints}
    clips = []
    for clip in rig.clips:
        per_node: dict[int | None, dict[str, Any]] = {}
        for ch in clip.channels:
            entry = per_node.setdefault(ch.target_node_index, {
                "node": ch.target_node_index,
                "name": rig.node_name(ch.target_node_index) if ch.target_node_index is not None else None,
                "isSkinJoint": ch.target_node_index in joint_nodes, "paths": {},
            })
            entry["paths"][ch.path] = {"keys": ch.key_count, "interpolation": ch.interpolation,
                                       "timeMin": _r(ch.time_min), "timeMax": _r(ch.time_max)}
        duration = clip.duration
        max_keys = max((c.key_count for c in clip.channels), default=0)
        clips.append({
            "animationIndex": clip.animation_index, "name": clip.name, "durationS": _r(duration),
            "channelCount": len(clip.channels), "targetedNodeCount": len(per_node),
            "targetedNonJointNodeCount": sum(1 for e in per_node.values() if not e["isSkinJoint"]),
            "interpolations": list(clip.interpolations),
            "maxKeysPerChannel": max_keys,
            "approxKeyRateHz": _r(max_keys / duration, 3) if duration > 0 and max_keys > 1 else None,
            "perBone": list(per_node.values()),
        })
    return clips


# --------------------------------------------------------------------------------------------
# roles
# --------------------------------------------------------------------------------------------


def _material_summary(document: dict[str, Any], index: int | None) -> dict[str, Any]:
    materials = document.get("materials", [])
    if index is None or not isinstance(index, int) or not 0 <= index < len(materials):
        return {"name": None, "metallic": None, "roughness": None}
    material = materials[index]
    pbr = material.get("pbrMetallicRoughness", {}) or {}
    return {"name": material.get("name"), "metallic": pbr.get("metallicFactor", 1.0),
            "roughness": pbr.get("roughnessFactor", 1.0),
            "unlit": "KHR_materials_unlit" in (material.get("extensions") or {})}


def _skin_material_hint(document: dict[str, Any], mesh: _MeshAcc) -> str | None:
    for index in mesh.materials:
        summary = _material_summary(document, index)
        words = set(_tokens(summary["name"]))
        if words & _SKIN_MATERIAL_WORDS:
            return str(summary["name"])
    return None


def _detect_body(document: dict[str, Any], meshes: list[_MeshAcc], frame: _Frame,
                 override: str | None) -> tuple[_MeshAcc | None, dict[str, Any]]:
    if override is not None:
        for mesh in meshes:
            if mesh.name == override or any(
                str(document.get("nodes", [{}])[n].get("name")) == override for n in mesh.nodes
            ):
                return mesh, {"mesh": mesh.name, "override": True,
                              "basis": f"caller passed body_mesh={override!r}"}
        names = [m.name for m in meshes]
        raise ValueError(f"body_mesh {override!r} matches no mesh; available: {names}")
    best: tuple[float, _MeshAcc, dict[str, Any]] | None = None
    for mesh in meshes:
        if not mesh.positions:
            continue
        soft = sum(1 for name in mesh.custom if name.startswith("_SOFT_"))
        skinned = mesh.skin_index is not None and mesh.influence is not None
        hint = _skin_material_hint(document, mesh)
        lo, hi = _bounds(mesh.positions)  # type: ignore[misc]
        y_frac = ((hi[1] - lo[1]) / frame.height) if frame.height else 0.0
        score = len(mesh.positions) * (1 + 0.5 * soft) * (2.0 if hint else 1.0) * (1.0 + y_frac) * (1.5 if skinned else 1.0)
        detail = {"mesh": mesh.name, "override": False, "score": _r(score, 2), "softMaskCount": soft,
                  "skinned": skinned, "skinMaterialHint": hint, "vertexCount": len(mesh.positions),
                  "yExtentFrac": _r(y_frac)}
        if best is None or score > best[0]:
            best = (score, mesh, detail)
    if best is None:
        return None, {"mesh": None, "override": False, "basis": "no mesh has vertices"}
    detail = best[2]
    detail["basis"] = (
        "highest score = vertices x (1 + 0.5 x _SOFT_* attribute count) x 2 if the material name says "
        "skin/body/dielectric x (1 + Y extent as fraction of H) x 1.5 if skinned"
    )
    return best[1], detail


def _classify_roles(document: dict[str, Any], meshes: list[_MeshAcc], body: _MeshAcc | None,
                    frame: _Frame) -> list[dict[str, Any]]:
    nodes = document.get("nodes", [])
    out: list[dict[str, Any]] = []
    for mesh in meshes:
        node_names = [str(nodes[n].get("name")) for n in mesh.nodes if 0 <= n < len(nodes)]
        tokens = _tokens(mesh.name, *node_names)
        evidence: list[str] = []
        role = "unknown"
        if not mesh.positions:
            out.append({"mesh": mesh.name, "meshIndex": mesh.index, "role": "unknown",
                        "basis": "mesh has no vertices"})
            continue
        lo, hi = _bounds(mesh.positions)  # type: ignore[misc]
        dims = [hi[i] - lo[i] for i in range(3)]
        centroid = _mean_point(mesh.positions)
        geo = None
        if frame.height and frame.floor_y is not None:
            cy = (centroid[1] - frame.floor_y) / frame.height  # type: ignore[index]
            top = (hi[1] - frame.floor_y) / frame.height
            max_dim = max(dims) / frame.height
            wide_x = dims[0] / frame.height
            soft = any(name.startswith("_SOFT_") for name in mesh.custom)
            if cy >= FACE_BAND_MIN_Y and max_dim <= FACE_DETAIL_MAX_DIM:
                geo = ("face-detail", f"small (max extent {max_dim:.3f}H <= {FACE_DETAIL_MAX_DIM}H) mesh in the head band (centroid y {cy:.3f}H >= {FACE_BAND_MIN_Y}H)")
            elif top >= HAIR_TOP_MIN_Y and cy >= HAIR_CENTROID_MIN_Y and len(mesh.positions) >= HAIR_MIN_VERTICES and wide_x >= 0.08:
                geo = ("hair", f"{len(mesh.positions)} vertices topping out at {top:.3f}H with centroid y {cy:.3f}H")
            elif top <= FOOTWEAR_MAX_Y + 0.05 and cy <= FOOTWEAR_MAX_Y:
                geo = ("footwear", f"mesh confined to the lowest {FOOTWEAR_MAX_Y}H (centroid y {cy:.3f}H, top {top:.3f}H)")
            elif soft or any(name.startswith("COLOR_") for name in mesh.colors):
                geo = ("garment", "carries _SOFT_* mask attributes or vertex colours but is not the body mesh")
            elif max_dim <= PROP_MAX_DIM:
                geo = ("prop", f"small (max extent {max_dim:.3f}H) mesh outside the head band")
            elif 0.1 <= cy <= 0.75 and max_dim >= 0.2:
                geo = ("garment", f"large mesh covering torso/leg height (centroid y {cy:.3f}H, max extent {max_dim:.3f}H)")

        name_hit: tuple[str, str] | None = None
        for candidate, words in (("face-detail", _FACE_WORDS), ("hair", _HAIR_WORDS),
                                 ("footwear", _FOOTWEAR_WORDS), ("garment", _GARMENT_WORDS),
                                 ("prop", _PROP_WORDS)):
            hit = _token_hit(tokens, words)
            if hit:
                name_hit = (candidate, hit)
                break

        if body is not None and mesh is body:
            role = "skin-body"
            evidence.append("selected as the body mesh (see inferred.bodyMesh)")
        elif name_hit is not None:
            role = name_hit[0]
            evidence.append(f"name token {name_hit[1]!r} in mesh/node names {[mesh.name, *node_names]}")
            if geo is not None:
                evidence.append(f"geometry says {geo[0]}: {geo[1]}" if geo[0] != role else f"geometry agrees: {geo[1]}")
        elif geo is not None:
            role = geo[0]
            evidence.append(geo[1])
            evidence.append(f"no role word in names {[mesh.name, *node_names]}")
        else:
            evidence.append(f"no role word in names {[mesh.name, *node_names]} and no geometry rule matched")
        mats = [_material_summary(document, m)["name"] for m in mesh.materials]
        out.append({"mesh": mesh.name, "meshIndex": mesh.index, "nodes": node_names, "role": role,
                    "basis": "; ".join(evidence), "material": mats, "vertexCount": len(mesh.positions),
                    "triangleCount": mesh.triangles})
    return out


# --------------------------------------------------------------------------------------------
# main entry
# --------------------------------------------------------------------------------------------


def _bytes_by_semantic(document: dict[str, Any]) -> dict[str, int]:
    """Accessor payload bytes grouped by what they feed. Counts accessors once each."""
    usage: dict[int, str] = {}
    for mesh in document.get("meshes", []):
        for prim in mesh.get("primitives", []):
            for name, idx in (prim.get("attributes") or {}).items():
                if isinstance(idx, int):
                    usage.setdefault(idx, re.sub(r"_\d+$", "", name) if not name.startswith("_") else "custom(_*)")
            if isinstance(prim.get("indices"), int):
                usage.setdefault(prim["indices"], "indices")
            for target in prim.get("targets") or []:
                for name, idx in target.items():
                    if isinstance(idx, int):
                        usage.setdefault(idx, f"morphTarget:{name}")
    for skin in document.get("skins", []):
        if isinstance(skin.get("inverseBindMatrices"), int):
            usage.setdefault(skin["inverseBindMatrices"], "inverseBindMatrices")
    for anim in document.get("animations", []):
        for sampler in anim.get("samplers", []):
            for key in ("input", "output"):
                if isinstance(sampler.get(key), int):
                    usage.setdefault(sampler[key], "animation")
    totals: dict[str, int] = {}
    for idx, label in usage.items():
        accessor = document["accessors"][idx]
        size = int(accessor.get("count", 0)) * _TYPE_COMPONENTS.get(accessor.get("type", ""), 0) * _COMPONENT_BYTES.get(int(accessor.get("componentType", 5126)), 0)
        totals[label] = totals.get(label, 0) + size
    images = 0
    for image in document.get("images", []):
        if isinstance(image.get("bufferView"), int):
            images += int(document["bufferViews"][image["bufferView"]].get("byteLength", 0))
    if images:
        totals["images(embedded)"] = images
    return dict(sorted(totals.items(), key=lambda kv: -kv[1]))


def analyze(glb_path: str | Path, body_mesh: str | None = None, figure_height: float | None = None) -> dict[str, Any]:
    path = Path(glb_path).expanduser().resolve()
    raw = path.read_bytes()
    document, bin_payload, binary = rgr.parse_glb(path)
    rig = rgr.read_rig(path)
    warnings: list[str] = []
    limits: list[str] = [
        "Only the GLB's own data is read: no renders, no source .blend, no textures decoded beyond image headers.",
        "Mesh roles are name/geometry heuristics (inferred.meshRoles), not artist labels.",
        "Each mesh is counted once even if several nodes instance it (instanceCount is reported).",
    ]

    # ---- file -------------------------------------------------------------------------------
    asset = document.get("asset") or {}
    file_section = {
        "path": str(path), "bytes": len(raw), "sha256": _sha256(raw),
        "glbContainerVersion": binary["version"], "gltfVersion": asset.get("version"),
        "generator": asset.get("generator"), "copyright": asset.get("copyright"),
        "extensionsUsed": list(document.get("extensionsUsed") or []),
        "extensionsRequired": list(document.get("extensionsRequired") or []),
        "chunks": binary["chunks"], "jsonChunkBytes": binary["jsonChunkBytes"], "binChunkBytes": binary["binChunkBytes"],
        "counts": {key: len(document.get(key) or []) for key in (
            "scenes", "nodes", "meshes", "materials", "textures", "images", "samplers", "accessors",
            "bufferViews", "buffers", "skins", "animations", "cameras")},
    }

    # ---- world matrices ---------------------------------------------------------------------
    world: list[Any] | None
    try:
        world = rgr.rest_world_matrices(rig)
    except (ValueError, RecursionError) as exc:
        world = None
        warnings.append(f"node world matrices not computed: {exc}")

    nodes = document.get("nodes", []) or []
    mesh_nodes: dict[int, list[int]] = {}
    for index, node in enumerate(nodes):
        if isinstance(node, dict) and isinstance(node.get("mesh"), int):
            mesh_nodes.setdefault(node["mesh"], []).append(index)

    # ---- pass 1: read every mesh ------------------------------------------------------------
    accs: list[_MeshAcc] = []
    raw_meshes = document.get("meshes", []) or []
    skin_joint_counts = {s.skin_index: len(s.joints) for s in rig.skins}
    for mesh_index, mesh in enumerate(raw_meshes):
        acc = _MeshAcc(mesh_index, mesh)
        acc.nodes = mesh_nodes.get(mesh_index, [])
        first_node = acc.nodes[0] if acc.nodes else None
        node_skin = nodes[first_node].get("skin") if first_node is not None else None
        acc.skin_index = node_skin if isinstance(node_skin, int) else None
        matrix = None
        if first_node is not None and world is not None and acc.skin_index is None and not _is_identity(world[first_node]):
            matrix = world[first_node]
        targets_declared = 0
        for prim_index, prim in enumerate(mesh.get("primitives", []) or []):
            attrs = prim.get("attributes") or {}
            what = f"mesh {acc.name} primitive {prim_index}"
            positions_raw = _read(document, bin_payload, attrs.get("POSITION"), warnings, what + " POSITION")
            positions = positions_raw or []
            if matrix is not None:
                positions = [_mat_apply(matrix, p) for p in positions]
            local_offset = len(acc.positions)
            acc.positions.extend((p[0], p[1], p[2]) for p in positions)
            mode = int(prim.get("mode", 4))
            indices: list[int] | None = None
            if isinstance(prim.get("indices"), int):
                decoded = _read(document, bin_payload, prim["indices"], warnings, what + " indices")
                indices = [int(v[0]) for v in decoded] if decoded is not None else None
            elif positions:
                indices = list(range(len(positions)))
            tris = _triangles(mode, indices) if indices is not None else []
            acc.triangles += len(tris)
            surface = _surface_stats(tris, positions)
            for key in acc.surface:
                acc.surface[key] += surface[key]
            targets = prim.get("targets") or []
            targets_declared = max(targets_declared, len(targets))
            acc.materials.append(prim.get("material") if isinstance(prim.get("material"), int) else None)

            attr_list = []
            for name, idx in attrs.items():
                if isinstance(idx, int) and 0 <= idx < len(document.get("accessors", [])):
                    meta = _accessor_meta(document, idx)
                    meta["semantic"] = name
                    attr_list.append(meta)
            attr_list.sort(key=lambda a: a["semantic"])
            acc.primitives.append({
                "index": prim_index, "mode": _PRIMITIVE_MODES.get(mode, mode), "vertexCount": len(positions),
                "triangleCount": len(tris), "indexed": isinstance(prim.get("indices"), int),
                "indexComponentType": _COMPONENT_NAMES.get(int(document["accessors"][prim["indices"]].get("componentType", 5125)))
                if isinstance(prim.get("indices"), int) and prim["indices"] < len(document.get("accessors", [])) else None,
                "material": prim.get("material"), "attributes": attr_list, "morphTargetCount": len(targets),
                "morphTargetAttributes": sorted({k for t in targets for k in t}),
            })

            for name, idx in attrs.items():
                if name.startswith("_"):
                    values = _read(document, bin_payload, idx, warnings, f"{what} {name}")
                    if values is not None:
                        store = acc.custom.setdefault(name, ([], [], _accessor_meta(document, idx)))
                        store[0].extend(values)
                        store[1].extend(acc.positions[local_offset:local_offset + len(values)])
                elif name.startswith("COLOR_"):
                    values = _read(document, bin_payload, idx, warnings, f"{what} {name}")
                    if values is not None:
                        store2 = acc.colors.setdefault(name, ([], _accessor_meta(document, idx)))
                        store2[0].extend(values)
                elif name == "TEXCOORD_0":
                    values = _read(document, bin_payload, idx, warnings, f"{what} {name}")
                    if values is not None:
                        acc.uvs.extend(values)

            # skin influences
            sets = []
            n_set = 0
            while f"JOINTS_{n_set}" in attrs:
                if f"WEIGHTS_{n_set}" not in attrs:
                    warnings.append(f"{what}: JOINTS_{n_set} has no WEIGHTS_{n_set}")
                    break
                joints = _read(document, bin_payload, attrs[f"JOINTS_{n_set}"], warnings, f"{what} JOINTS_{n_set}")
                weights = _read(document, bin_payload, attrs[f"WEIGHTS_{n_set}"], warnings, f"{what} WEIGHTS_{n_set}")
                if joints is not None and weights is not None:
                    sets.append((joints, weights))
                n_set += 1
            if sets:
                jcount = skin_joint_counts.get(acc.skin_index, 0) if acc.skin_index is not None else 0
                acc.influence = _merge_influence(acc.influence, _influence_stats(sets, jcount))
        acc.morph_targets = targets_declared
        accs.append(acc)

    # ---- figure height ----------------------------------------------------------------------
    all_positions = [p for acc in accs for p in acc.positions]
    scene_bounds = _bounds(all_positions)
    height_info: dict[str, Any]
    height: float | None = None
    floor_y: float | None = None
    if figure_height is not None:
        height = float(figure_height)
        floor_y = scene_bounds[0][1] if scene_bounds else 0.0
        height_source = "callerSupplied"
    elif scene_bounds is not None and scene_bounds[1][1] - scene_bounds[0][1] > 0:
        height = scene_bounds[1][1] - scene_bounds[0][1]
        floor_y = scene_bounds[0][1]
        height_source = "meshWorldBoundsYExtent"
    else:
        height_source = None
        limits.append("Figure height could not be measured (no mesh vertices with a positive Y extent); every Frac field is null.")
    cross_check: dict[str, Any] = {}
    try:
        derived, derived_source = rgr.derive_figure_height(rig)
        cross_check = {"deriveFigureHeightM": _r(derived), "source": derived_source,
                       "agreesWithHeightM": height is not None and abs(derived - height) < 1e-6}
    except ValueError as exc:
        cross_check = {"deriveFigureHeightM": None, "reason": str(exc)}
    frame = _Frame(height, floor_y)
    height_info = {
        "heightM": _r(height), "heightSource": height_source, "floorYM": _r(floor_y),
        "ceilingYM": _r(scene_bounds[1][1]) if scene_bounds else None,
        "crossCheck": cross_check,
        "fracConvention": "Y fractions are (y - floorY) / H; X and Z fractions are value / H about the world origin",
    }
    if height is not None:
        limits.append("H is the Y extent of ALL meshes (hair, props and footwear included); a prop above the head would inflate it.")

    # ---- body + roles -----------------------------------------------------------------------
    body, body_info = _detect_body(document, accs, frame, body_mesh)
    roles = _classify_roles(document, accs, body, frame)

    # ---- mesh records -----------------------------------------------------------------------
    total_tris = sum(a.triangles for a in accs)
    total_verts = sum(len(a.positions) for a in accs)
    mesh_records: list[dict[str, Any]] = []
    for acc in accs:
        bounds = _bounds(acc.positions)
        centroid = _mean_point(acc.positions)
        record: dict[str, Any] = {
            "meshIndex": acc.index, "name": acc.name,
            "node": acc.nodes[0] if acc.nodes else None,
            "nodeName": nodes[acc.nodes[0]].get("name") if acc.nodes else None,
            "instanceCount": len(acc.nodes), "nodeIndices": acc.nodes,
            "vertexCount": len(acc.positions), "triangleCount": acc.triangles,
            "triangleShare": _r(acc.triangles / total_tris) if total_tris else None,
            "vertexShare": _r(len(acc.positions) / total_verts) if total_verts else None,
            "primitiveCount": len(acc.primitives),
            "materials": [
                {"index": m, "name": _material_summary(document, m)["name"]} for m in dict.fromkeys(acc.materials)
            ],
            "primitives": acc.primitives,
            "bounds": _box(frame, bounds[0], bounds[1]) if bounds else None,
            "centroidM": _rv(centroid), "centroidFrac": frame.point(centroid) if centroid else None,
            "skinned": acc.skin_index is not None and acc.influence is not None,
            "skinnedByNode": acc.skin_index is not None, "skinIndex": acc.skin_index,
            "hasJoints": acc.influence is not None,
            "morphTargetCount": acc.morph_targets,
            "morphTargetNames": (raw_meshes[acc.index].get("extras") or {}).get("targetNames") if isinstance(raw_meshes[acc.index].get("extras"), dict) else None,
            "surfaceAreaM2": _r(acc.surface["surfaceAreaM2"], 6),
            "trianglesPerM2": _r(acc.triangles / acc.surface["surfaceAreaM2"], 1) if acc.surface["surfaceAreaM2"] > 0 else None,
            "degenerateTriangles": acc.surface["degenerateTriangles"],
            "indicesOutOfRangeTriangles": acc.surface["indicesOutOfRangeTriangles"],
            "uvBounds": None,
            "customAttributes": {}, "vertexColors": {},
        }
        if acc.uvs:
            us = [uv[0] for uv in acc.uvs]
            vs = [uv[1] for uv in acc.uvs]
            record["uvBounds"] = {"uMin": _r(min(us)), "uMax": _r(max(us)), "vMin": _r(min(vs)), "vMax": _r(max(vs)),
                                  "outside01Fraction": _r(sum(1 for u, v in zip(us, vs) if not (0 <= u <= 1 and 0 <= v <= 1)) / len(us))}
        for name, (values, pts, meta) in sorted(acc.custom.items()):
            stats = _finish_value_stats(_value_stats(values, pts), frame)
            stats.update({"type": meta["type"], "componentType": meta["componentType"], "normalized": meta["normalized"]})
            record["customAttributes"][name] = stats
        for name, (values, meta) in sorted(acc.colors.items()):
            stats = _color_stats(values)
            stats.update({"type": meta["type"], "componentType": meta["componentType"], "normalized": meta["normalized"]})
            record["vertexColors"][name] = stats
        if acc.influence is not None:
            inf = acc.influence
            sums = inf["sums"]
            n = max(len(sums), 1)
            skin_joints = rig.skins[acc.skin_index].joints if acc.skin_index is not None and acc.skin_index < len(rig.skins) else ()
            record["skinInfluence"] = {
                "vertexCount": inf["vertexCount"],
                "maxInfluencesPerVertex": max(inf["nonzero"]) if inf["nonzero"] else 0,
                "meanInfluencesPerVertex": _r(sum(inf["nonzero"]) / n, 4),
                "influenceHistogram": {str(k): inf["nonzero"].count(k) for k in sorted(set(inf["nonzero"]))},
                "weightSumMin": _r(min(sums)) if sums else None, "weightSumMax": _r(max(sums)) if sums else None,
                "weightSumWithinToleranceOfOneFraction": _r(sum(1 for s in sums if abs(s - 1.0) <= WEIGHT_SUM_TOLERANCE) / n),
                "weightSumTolerance": WEIGHT_SUM_TOLERANCE,
                "unweightedVertexCount": sum(1 for s in sums if s <= INFLUENCE_EPSILON),
                "jointIndicesOutOfRange": inf["outOfRange"], "negativeWeights": inf["negative"],
                "bones": [
                    {"skinJointIndex": j, "name": skin_joints[j].node_name if j < len(skin_joints) else None,
                     "vertices": inf["vertices"][j], "weightMass": _r(inf["mass"][j], 3),
                     "dominantVertices": inf["dominant"].get(j, 0)}
                    for j in sorted(inf["vertices"])
                ],
            }
        mesh_records.append(record)
    for rec in mesh_records:
        rec["rolePointer"] = "inferred.meshRoles"

    # ---- materials, textures, images --------------------------------------------------------
    mesh_use: dict[int, list[str]] = {}
    for acc in accs:
        for m in dict.fromkeys(acc.materials):
            if m is not None:
                mesh_use.setdefault(m, []).append(acc.name)
    materials_out = []
    for index, material in enumerate(document.get("materials", []) or []):
        pbr = material.get("pbrMetallicRoughness") or {}
        slots: dict[str, Any] = {}
        for label, keys in _MATERIAL_TEXTURE_SLOTS:
            node: Any = material
            for key in keys:
                node = node.get(key) if isinstance(node, dict) else None
            if isinstance(node, dict) and isinstance(node.get("index"), int):
                tex = node["index"]
                texture = (document.get("textures") or [{}])[tex] if tex < len(document.get("textures") or []) else {}
                slots[label] = {"texture": tex, "image": texture.get("source"), "texCoord": node.get("texCoord", 0),
                                **({"scale": node["scale"]} if "scale" in node else {}),
                                **({"strength": node["strength"]} if "strength" in node else {})}
        materials_out.append({
            "index": index, "name": material.get("name"),
            "baseColorFactor": pbr.get("baseColorFactor", [1, 1, 1, 1]),
            "baseColorFactorExplicit": "baseColorFactor" in pbr,
            "metallicFactor": pbr.get("metallicFactor", 1.0), "metallicFactorExplicit": "metallicFactor" in pbr,
            "roughnessFactor": pbr.get("roughnessFactor", 1.0), "roughnessFactorExplicit": "roughnessFactor" in pbr,
            "emissiveFactor": material.get("emissiveFactor", [0, 0, 0]),
            "alphaMode": material.get("alphaMode", "OPAQUE"), "alphaCutoff": material.get("alphaCutoff"),
            "doubleSided": bool(material.get("doubleSided", False)),
            "textures": slots, "extensions": sorted((material.get("extensions") or {}).keys()),
            "usedByMeshes": mesh_use.get(index, []),
        })

    base = path.parent
    images_out = []
    for index, image in enumerate(document.get("images", []) or []):
        data, origin = _image_bytes(document, bin_payload, image, base)
        entry: dict[str, Any] = {"index": index, "name": image.get("name"), "mimeType": image.get("mimeType"),
                                 "origin": origin}
        if data is not None:
            header = _sniff_image(data)
            w, h = header.get("width"), header.get("height")
            entry.update({"byteSize": len(data), "sha256": _sha256(data), **header})
            if w and h:
                entry["pixels"] = w * h
                entry["aspectRatio"] = _r(w / h, 4)
                entry["isPowerOfTwo"] = (w & (w - 1) == 0) and (h & (h - 1) == 0)
                entry["uncompressedRgba8Bytes"] = w * h * 4
        entry["usedByTextures"] = [i for i, t in enumerate(document.get("textures") or [])
                                   if t.get("source") == index or any(
                                       isinstance(ext, dict) and ext.get("source") == index
                                       for ext in (t.get("extensions") or {}).values())]
        images_out.append(entry)
    samplers = document.get("samplers") or []
    samplers_out = [{
        "index": i, "magFilter": _FILTERS.get(s.get("magFilter"), s.get("magFilter")),
        "minFilter": _FILTERS.get(s.get("minFilter"), s.get("minFilter")),
        "wrapS": _WRAPS.get(s.get("wrapS", 10497), s.get("wrapS")), "wrapT": _WRAPS.get(s.get("wrapT", 10497), s.get("wrapT")),
        "wrapDefaulted": "wrapS" not in s and "wrapT" not in s,
    } for i, s in enumerate(samplers)]
    textures_out = [{
        "index": i, "source": t.get("source"), "sampler": t.get("sampler"),
        "samplerResolved": samplers_out[t["sampler"]] if isinstance(t.get("sampler"), int) and t["sampler"] < len(samplers_out) else None,
        "usedByMaterials": [m["index"] for m in materials_out for slot in m["textures"].values() if slot["texture"] == i],
    } for i, t in enumerate(document.get("textures") or [])]

    # ---- nodes ------------------------------------------------------------------------------
    parent_of = rig._parents
    joint_node_set = {j.node_index for skin in rig.skins for j in skin.joints}

    def node_depth(i: int) -> int:
        d, seen = 0, {i}
        while parent_of.get(i) is not None and parent_of[i] not in seen:
            i = parent_of[i]  # type: ignore[assignment]
            seen.add(i)
            d += 1
        return d

    node_rows = []
    for i, node in enumerate(nodes):
        has_trs = any(k in node for k in ("translation", "rotation", "scale", "matrix"))
        node_rows.append({
            "index": i, "name": node.get("name"), "parent": parent_of.get(i), "depth": node_depth(i),
            "childCount": len(node.get("children") or []), "mesh": node.get("mesh"), "skin": node.get("skin"),
            "isSkinJoint": i in joint_node_set, "hasTransform": has_trs,
            "worldIsIdentity": _is_identity(world[i]) if world is not None else None,
        })
    scenes = document.get("scenes") or []
    default_scene = document.get("scene", 0 if scenes else None)
    scene_roots = (scenes[default_scene].get("nodes") if isinstance(default_scene, int) and default_scene < len(scenes) else None) or []
    nodes_section = {
        "count": len(nodes), "sceneCount": len(scenes), "defaultScene": default_scene,
        "sceneRootNodes": [{"index": r, "name": nodes[r].get("name")} for r in scene_roots if r < len(nodes)],
        "maxDepth": max((r["depth"] for r in node_rows), default=0),
        "meshNodeCount": sum(1 for r in node_rows if r["mesh"] is not None),
        "skinnedMeshNodeCount": sum(1 for r in node_rows if r["mesh"] is not None and r["skin"] is not None),
        "jointNodeCount": len(joint_node_set),
        "list": node_rows[:NODE_LIST_CAP], "listTruncated": len(node_rows) > NODE_LIST_CAP,
    }

    # ---- skins / animations -----------------------------------------------------------------
    skins_out = _skin_sections(rig, world, frame, accs, warnings)
    clips_out = _animation_section(rig)
    for message in rig.warnings:
        warnings.append(f"rig: {message}")
    skin_section = {
        "skinCount": len(rig.skins), "structuralFailure": rig.structural_failure,
        "skins": skins_out, "animations": clips_out,
        "skinnedMeshNodes": list(rig.skinned_mesh_nodes),
        "deformVsTechnical": rig.deform_vs_technical,
    }

    # ---- conventions (inferred) -------------------------------------------------------------
    extents = None
    if scene_bounds is not None:
        extents = [scene_bounds[1][i] - scene_bounds[0][i] for i in range(3)]
    conventions = _conventions(accs, skins_out, extents, height)

    # ---- budgets ----------------------------------------------------------------------------
    by_material: dict[str, dict[str, Any]] = {}
    for acc in accs:
        for prim in acc.primitives:
            key = _material_summary(document, prim["material"] if isinstance(prim["material"], int) else None)["name"] or "(no material)"
            entry = by_material.setdefault(str(key), {"vertices": 0, "triangles": 0, "primitives": 0})
            entry["vertices"] += prim["vertexCount"]
            entry["triangles"] += prim["triangleCount"]
            entry["primitives"] += 1
    for entry in by_material.values():
        entry["triangleShare"] = _r(entry["triangles"] / total_tris) if total_tris else None
    texture_bytes = sum(i.get("uncompressedRgba8Bytes", 0) for i in images_out)
    budgets = {
        "totalVertices": total_verts, "totalTriangles": total_tris,
        "meshCount": len(accs), "primitiveCount": sum(len(a.primitives) for a in accs),
        "jointCount": sum(len(s.joints) for s in rig.skins), "materialCount": len(materials_out),
        "textureCount": len(textures_out), "imageCount": len(images_out),
        "imageEncodedBytes": sum(i.get("byteSize", 0) for i in images_out),
        "imageUncompressedRgba8Bytes": texture_bytes,
        "bytesBySemantic": _bytes_by_semantic(document),
        "byMaterial": by_material,
        "perMeshTriangleShare": {rec["name"]: rec["triangleShare"] for rec in mesh_records},
    }
    by_role: dict[str, dict[str, Any]] = {}
    for role_rec in roles:
        entry = by_role.setdefault(role_rec["role"], {"meshes": [], "vertices": 0, "triangles": 0})
        entry["meshes"].append(role_rec["mesh"])
        entry["vertices"] += role_rec.get("vertexCount", 0)
        entry["triangles"] += role_rec.get("triangleCount", 0)
    for entry in by_role.values():
        entry["meshCount"] = len(entry["meshes"])
        entry["triangleShare"] = _r(entry["triangles"] / total_tris) if total_tris else None
        entry["vertexShare"] = _r(entry["vertices"] / total_verts) if total_verts else None

    soft_masks = {
        acc.name: sorted(n for n in acc.custom if n.startswith("_SOFT_")) for acc in accs if any(n.startswith("_SOFT_") for n in acc.custom)
    }
    if not skins_out:
        limits.append("The GLB has no skin: skin/rig sections are empty and influence statistics are absent.")
    if not accs:
        limits.append("The GLB has no meshes: nothing to measure.")
    limits.append("Facing direction and handedness conventions are inferred from mask/joint placement when available, else from the glTF spec.")
    if body is None:
        limits.append("No body mesh could be selected; role classification falls back to names and geometry only.")

    return {
        "schema": SCHEMA,
        "observed": {
            "file": file_section,
            "figureHeight": height_info,
            "nodes": nodes_section,
            "meshes": mesh_records,
            "softMaskAttributesByMesh": soft_masks,
            "materials": materials_out,
            "textures": textures_out,
            "images": images_out,
            "samplers": samplers_out,
            "skin": skin_section,
            "budgets": budgets,
            "sceneBounds": _box(frame, scene_bounds[0], scene_bounds[1]) if scene_bounds else None,
        },
        "inferred": {
            "bodyMesh": body_info,
            "meshRoles": roles,
            "budgetsByRole": {"basis": "sums of observed per-mesh counts grouped by the inferred role", "roles": by_role},
            "conventions": conventions,
        },
        "limits": limits,
        "warnings": warnings,
    }


def _conventions(accs: list[_MeshAcc], skins: list[dict[str, Any]], extents: list[float] | None,
                 height: float | None) -> dict[str, Any]:
    """Up axis, units, left/forward conventions, each with the evidence it rests on."""
    out: dict[str, Any] = {}
    up_basis = ["glTF 2.0 mandates +Y up"]
    if extents is not None:
        longest = "XYZ"[extents.index(max(extents))]
        up_basis.append(f"world extents X/Y/Z = {[_r(e, 3) for e in extents]} m, longest axis {longest}")
    joint_extents = None
    for skin in skins:
        pts = [j["restPositionM"] for j in skin["joints"] if j["restPositionM"] and None not in j["restPositionM"]]
        if len(pts) >= 2:
            joint_extents = [max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3)]
            up_basis.append(f"joint rest extents X/Y/Z = {[_r(e, 3) for e in joint_extents]} m")
            break
    out["upAxis"] = {"value": "+Y", "basis": "; ".join(up_basis),
                     "dataAgrees": (extents is None or extents[1] >= 0.5 * max(extents)) if extents else None}
    if height is None:
        out["units"] = {"value": "metres", "basis": "glTF 2.0 mandates metres; H could not be measured so plausibility is unchecked"}
    else:
        low, high = PLAUSIBLE_HEIGHT_RANGE_M
        out["units"] = {"value": "metres", "basis": f"glTF 2.0 mandates metres; measured H = {height:.3f} m",
                        "heightIsHumanScale": low <= height <= high}
    # left from *_LEFT/*_RIGHT masks
    left_pts: list[list[float]] = []
    right_pts: list[list[float]] = []
    front_z: list[float] = []
    back_z: list[float] = []
    for acc in accs:
        for name, (values, pts, _meta) in acc.custom.items():
            if not name.startswith("_SOFT_") or not values:
                continue
            stats = _value_stats(values, pts)
            centroid = stats.get("_centroidM")
            if centroid is None:
                continue
            upper = name.upper()
            if upper.endswith("_LEFT") or upper.endswith("_L"):
                left_pts.append(centroid)
            elif upper.endswith("_RIGHT") or upper.endswith("_R"):
                right_pts.append(centroid)
            if any(w in upper for w in ("CHEST", "ABDOMEN", "BELLY", "BREAST")):
                front_z.append(centroid[2])
            elif any(w in upper for w in ("CHEEK", "GLUTE", "BUTT")):
                back_z.append(centroid[2])
    if left_pts and right_pts:
        lx = sum(p[0] for p in left_pts) / len(left_pts)
        rx = sum(p[0] for p in right_pts) / len(right_pts)
        side = "+X" if lx > rx else "-X"
        out["characterLeft"] = {"value": side, "basis": f"mean X of *_LEFT mask centroids {lx:.3f} m vs *_RIGHT {rx:.3f} m ({len(left_pts)}/{len(right_pts)} masks)"}
    else:
        out["characterLeft"] = {"value": "+X", "basis": "no left/right-named masks; assumed from glTF convention (asset faces +Z, so its left is +X) - not verified from data"}
    if front_z and back_z:
        fz = sum(front_z) / len(front_z)
        bz = sum(back_z) / len(back_z)
        out["forwardAxis"] = {"value": "+Z" if fz > bz else "-Z",
                              "basis": f"chest/abdomen mask centroid Z {fz:.3f} m vs cheek mask centroid Z {bz:.3f} m"}
    else:
        out["forwardAxis"] = {"value": "+Z", "basis": "no front/back-named masks; assumed from glTF convention (asset front faces +Z) - not verified from data"}
    return out


if __name__ == "__main__":  # pragma: no cover - convenience for ad-hoc runs
    target = sys.argv[1] if len(sys.argv) > 1 else None
    if target is None:
        sys.exit("usage: python inventory.py <glb>")
    json.dump(analyze(target), sys.stdout, indent=2)
