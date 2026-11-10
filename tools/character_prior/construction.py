#!/usr/bin/env python3
"""Construction analysis of a rigged character GLB: HOW the model is built, as numbers.

Where `inventory` says what is in the file and `anatomy` says where the face and body landmarks
are, this module measures the *construction* of the delivered mesh set so a later character
can be built from the same template:

  1. parts and layering   -- which meshes are separate objects over the skin, and by what offset
  2. garment clearance    -- signed point-to-skin-surface distance distribution per garment mesh
  3. density / topology   -- vertices per m^2 and edge length per height band, valence, angle
                             quality, quad pairing, and whether the mesh looks linearly subdivided
  4. symmetry             -- x-mirror correspondence error and UV mirroring
  5. UV / atlas           -- island count, seam share, coverage, overlap, texel density
  6. skin weights / masks -- bone usage, influence histogram, `_SOFT_*` mask smoothness and support
  7. hair                 -- card / ribbon / tube / shell classification, strand count, scalp cover

Everything under `observed` is measured from the GLB. Everything under `inferred` is a heuristic
classification and carries a `basis` string saying what it was derived from. `limits` states what
this module cannot know. A feature that cannot be found is `null` with the reason recorded; no
value is invented.

Pure Python 3.10+ stdlib, no numpy. All neighbour searches use uniform spatial hashes, so the work
stays near-linear in the vertex count (a 38k-vertex body analyses in seconds).

Public API: `analyze(glb_path, *, body_mesh=None, hair_mesh=None, figure_height=None,
max_garment_samples=12000) -> dict`.
"""

from __future__ import annotations

import math
import struct
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

_TOOLS_DIR = str(Path(__file__).resolve().parent.parent)
if _TOOLS_DIR not in sys.path:
    sys.path.append(_TOOLS_DIR)

import rig_glb_reference as glbref  # noqa: E402  (needs the tools dir on sys.path first)

SCHEMA = "img2.character-prior.construction/1"

# Clearance bands the cloth-contact runtime clamps to (metres).
CLEARANCE_CLAMP_MIN_M = 0.0008
CLEARANCE_CLAMP_MAX_M = 0.020
CLEARANCE_NEAR_THRESHOLDS_M = (0.0008, 0.0025)

# Tolerance for "the same position" between welded vertices.
WELD_SCALE = 1e6
MIRROR_MATCH_M = 0.0005
UV_MATCH = 3e-4
MIDPOINT_TOL_M = 2e-6
ATLAS_GRID = 256
BAND_COUNT = 20


# --------------------------------------------------------------------------------------------
# Small numeric helpers
# --------------------------------------------------------------------------------------------


def _pct(sorted_values: Sequence[float], p: float) -> float | None:
    """Linear-interpolated percentile `p` (0..100) of an already sorted sequence."""
    n = len(sorted_values)
    if n == 0:
        return None
    if n == 1:
        return float(sorted_values[0])
    k = (n - 1) * p / 100.0
    lo = int(math.floor(k))
    hi = min(lo + 1, n - 1)
    return float(sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo))


def _r(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    if not math.isfinite(value):
        return None
    return round(float(value), digits)


def _summary(values: Sequence[float], scale: float = 1.0, digits: int = 4) -> dict[str, float | None] | None:
    """min, p1, p5, p25, median, p75, p95, max of `values` (scaled), or None when empty."""
    if not values:
        return None
    ordered = sorted(values)
    out: dict[str, float | None] = {}
    for key, p in (("min", 0), ("p1", 1), ("p5", 5), ("p25", 25), ("median", 50), ("p75", 75), ("p95", 95), ("max", 100)):
        value = _pct(ordered, p)
        out[key] = _r(None if value is None else value * scale, digits)
    return out


def _wide_summary(values: Sequence[float], scale: float = 1.0, digits: int = 4) -> dict[str, float | None] | None:
    """Like `_summary` but adds p50-adjacent tail points used for error distributions."""
    if not values:
        return None
    ordered = sorted(values)
    out: dict[str, float | None] = {}
    for key, p in (("min", 0), ("p50", 50), ("p90", 90), ("p95", 95), ("p99", 99), ("max", 100)):
        value = _pct(ordered, p)
        out[key] = _r(None if value is None else value * scale, digits)
    out["mean"] = _r(sum(ordered) / len(ordered) * scale, digits)
    return out


def _stride_sample(count: int, limit: int) -> list[int]:
    """Deterministic, evenly spaced sample of range(count) with at most `limit` entries."""
    if count <= limit:
        return list(range(count))
    step = count / float(limit)
    return [int(i * step) for i in range(limit)]


def _bbox(points: Iterable[Sequence[float]]) -> tuple[list[float], list[float]] | None:
    lo = [math.inf, math.inf, math.inf]
    hi = [-math.inf, -math.inf, -math.inf]
    seen = False
    for p in points:
        seen = True
        for k in range(3):
            v = p[k]
            if v < lo[k]:
                lo[k] = v
            if v > hi[k]:
                hi[k] = v
    return (lo, hi) if seen else None


# --------------------------------------------------------------------------------------------
# GLB -> mesh objects
# --------------------------------------------------------------------------------------------


_FAST_FORMATS = {5126: ("f", 4), 5123: ("H", 2), 5125: ("I", 4), 5121: ("B", 1)}
_FAST_WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def _read_accessor(doc: dict[str, Any], binp: bytes, index: int) -> list[tuple[float, ...]]:
    """`glbref.read_accessor`, with a bulk-unpack path for the common tightly packed layout.

    The fast path covers non-sparse, non-normalised FLOAT / UNSIGNED_SHORT / UNSIGNED_INT /
    UNSIGNED_BYTE accessors whose bufferView is not interleaved; it returns exactly the values the
    reference reader would (integer components come back as ints, which every caller here converts
    with int()). Anything else is delegated unchanged, so the reference reader stays the authority.
    """
    accessors = doc.get("accessors") or []
    if 0 <= index < len(accessors) and isinstance(accessors[index], dict):
        acc = accessors[index]
        fmt = _FAST_FORMATS.get(int(acc.get("componentType", 5126)))
        width = _FAST_WIDTH.get(str(acc.get("type")))
        view_index = acc.get("bufferView")
        views = doc.get("bufferViews") or []
        if fmt and width and "sparse" not in acc and not acc.get("normalized") and isinstance(view_index, int) and 0 <= view_index < len(views):
            view = views[view_index]
            element = fmt[1] * width
            stride = int(view.get("byteStride", element) or element)
            count = int(acc.get("count", 0))
            start = int(view.get("byteOffset", 0)) + int(acc.get("byteOffset", 0))
            end = start + count * element
            if stride == element and int(view.get("buffer", 0)) == 0 and count >= 0 and end <= int(view.get("byteOffset", 0)) + int(view.get("byteLength", 0)) and end <= len(binp):
                return list(struct.iter_unpack(f"<{width}{fmt[0]}", memoryview(binp)[start:end]))
    return glbref.read_accessor(doc, binp, index)


class _Mesh:
    """One mesh instance (a node that references a mesh), all primitives merged.

    Positions and triangles are loaded eagerly; every other attribute is decoded on first use and
    cached, so a section that does not need weights never pays for them. Skinned nodes keep their
    bind-space positions untouched (glTF ignores a skinned node's own transform); an unskinned
    node's positions are moved by its rest world matrix.
    """

    def __init__(self, doc: dict[str, Any], binp: bytes, node_index: int, node: dict[str, Any], world: Sequence[float] | None) -> None:
        self.doc = doc
        self.binp = binp
        self.node_index = node_index
        self.node_name = str(node.get("name", f"node-{node_index}"))
        self.mesh_index = int(node["mesh"])
        mesh = doc["meshes"][self.mesh_index]
        self.name = str(mesh.get("name") or self.node_name)
        skin = node.get("skin")
        self.skin_index: int | None = int(skin) if isinstance(skin, int) else None
        self.warnings: list[str] = []
        self._cache: dict[str, Any] = {}

        self.prims = [
            p for p in (mesh.get("primitives") or [])
            if isinstance(p, dict) and isinstance(p.get("attributes"), dict) and "POSITION" in p["attributes"] and p.get("mode", 4) in (4, 5, 6)
        ]
        self.material_indices = [p.get("material") for p in self.prims]
        self.positions: list[tuple[float, float, float]] = []
        self.tris: list[tuple[int, int, int]] = []
        self._prim_ranges: list[tuple[int, int]] = []
        self._world = world if (world is not None and self.skin_index is None and not _is_identity(world)) else None

        for prim in self.prims:
            base = len(self.positions)
            raw = _read_accessor(doc, binp, int(prim["attributes"]["POSITION"]))
            for p in raw:
                self.positions.append((p[0], p[1], p[2]))
            count = len(raw)
            self._prim_ranges.append((base, count))
            if "indices" in prim:
                idx = [int(t[0]) for t in _read_accessor(doc, binp, int(prim["indices"]))]
            else:
                idx = list(range(count))
            self.tris.extend(_triangulate(idx, int(prim.get("mode", 4)), base, count))

        if self._world is not None:
            m = self._world
            self.positions = [
                (m[0] * x + m[4] * y + m[8] * z + m[12], m[1] * x + m[5] * y + m[9] * z + m[13], m[2] * x + m[6] * y + m[10] * z + m[14])
                for (x, y, z) in self.positions
            ]

    # -- attributes --------------------------------------------------------------------------

    def _attribute(self, key: str) -> list[tuple[float, ...]] | None:
        if key in self._cache:
            return self._cache[key]
        parts: list[list[tuple[float, ...]] | None] = []
        width = 0
        for prim, (_, count) in zip(self.prims, self._prim_ranges):
            accessor = prim["attributes"].get(key)
            if accessor is None:
                parts.append(None)
                continue
            data = _read_accessor(self.doc, self.binp, int(accessor))
            if len(data) != count:
                self.warnings.append(f"attribute {key} count {len(data)} != POSITION count {count}; ignored")
                parts.append(None)
                continue
            width = max(width, len(data[0]) if data else 0)
            parts.append(data)
        if width == 0:
            self._cache[key] = None
            return None
        merged: list[tuple[float, ...]] = []
        for part, (_, count) in zip(parts, self._prim_ranges):
            if part is None:
                merged.extend([tuple([0.0] * width)] * count)
            else:
                merged.extend(part)
        self._cache[key] = merged
        return merged

    @property
    def normals(self) -> list[tuple[float, ...]] | None:
        data = self._attribute("NORMAL")
        if data is None or self._world is None:
            return data
        key = "NORMAL:world"
        if key not in self._cache:
            m = self._world
            # Inverse transpose of the world linear transform, including non-uniform scale.
            a, b, c = m[0], m[4], m[8]
            d, e, f = m[1], m[5], m[9]
            g, h, i = m[2], m[6], m[10]
            cofactor = (e*i-f*h, f*g-d*i, d*h-e*g,
                        c*h-b*i, a*i-c*g, b*g-a*h,
                        b*f-c*e, c*d-a*f, a*e-b*d)
            det = a*cofactor[0] + b*cofactor[1] + c*cofactor[2]
            if abs(det) < 1e-15:
                self.warnings.append("singular world transform; normals recomputed from transformed triangles")
                self._cache[key] = None
                return None
            out = []
            for (x, y, z) in data:
                nx = (cofactor[0]*x + cofactor[1]*y + cofactor[2]*z) / det
                ny = (cofactor[3]*x + cofactor[4]*y + cofactor[5]*z) / det
                nz = (cofactor[6]*x + cofactor[7]*y + cofactor[8]*z) / det
                ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
                out.append((nx / ln, ny / ln, nz / ln))
            self._cache[key] = out
        return self._cache[key]

    @property
    def uvs(self) -> list[tuple[float, ...]] | None:
        return self._attribute("TEXCOORD_0")

    def joint_sets(self) -> list[tuple[list[tuple[float, ...]], list[tuple[float, ...]]]]:
        sets = []
        n = 0
        while True:
            joints = self._attribute(f"JOINTS_{n}")
            weights = self._attribute(f"WEIGHTS_{n}")
            if joints is None or weights is None:
                break
            sets.append((joints, weights))
            n += 1
        return sets

    def soft_masks(self) -> dict[str, list[float]]:
        key = "soft-masks"
        if key not in self._cache:
            masks: dict[str, list[float]] = {}
            names: list[str] = []
            for prim in self.prims:
                for attr in prim["attributes"]:
                    if attr.startswith("_SOFT_") and attr not in names:
                        names.append(attr)
            for attr in names:
                data = self._attribute(attr)
                if data is not None:
                    masks[attr] = [float(t[0]) for t in data]
            self._cache[key] = masks
        return self._cache[key]

    # -- derived -----------------------------------------------------------------------------

    @property
    def vertex_count(self) -> int:
        return len(self.positions)

    @property
    def has_joints(self) -> bool:
        return any("JOINTS_0" in p["attributes"] for p in self.prims)

    def soft_mask_names(self) -> list[str]:
        names: list[str] = []
        for prim in self.prims:
            for attr in prim["attributes"]:
                if attr.startswith("_SOFT_") and attr not in names:
                    names.append(attr)
        return names

    def material(self) -> dict[str, Any] | None:
        for index in self.material_indices:
            if isinstance(index, int):
                return _material_info(self.doc, self.binp, index)
        return None

    def surface_area(self) -> float:
        total = 0.0
        p = self.positions
        for a, b, c in self.tris:
            total += _tri_area(p[a], p[b], p[c])
        return total


def _is_identity(m: Sequence[float]) -> bool:
    ident = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
    return all(abs(m[i] - ident[i]) < 1e-12 for i in range(16))


def _triangulate(idx: list[int], mode: int, base: int, count: int) -> list[tuple[int, int, int]]:
    out: list[tuple[int, int, int]] = []
    if mode == 4:
        for i in range(0, len(idx) - len(idx) % 3, 3):
            a, b, c = idx[i], idx[i + 1], idx[i + 2]
            out.append((a + base, b + base, c + base))
    elif mode == 5:
        for i in range(len(idx) - 2):
            a, b, c = (idx[i], idx[i + 1], idx[i + 2]) if i % 2 == 0 else (idx[i + 1], idx[i], idx[i + 2])
            out.append((a + base, b + base, c + base))
    elif mode == 6:
        for i in range(1, len(idx) - 1):
            out.append((idx[0] + base, idx[i] + base, idx[i + 1] + base))
    return [t for t in out if t[0] != t[1] and t[1] != t[2] and t[0] != t[2] and max(t) < base + count]


def _material_info(doc: dict[str, Any], binp: bytes, index: int) -> dict[str, Any] | None:
    materials = doc.get("materials") or []
    if not 0 <= index < len(materials) or not isinstance(materials[index], dict):
        return None
    mat = materials[index]
    pbr = mat.get("pbrMetallicRoughness") or {}
    ext = mat.get("extensions") or {}
    texture = (pbr.get("baseColorTexture") or {}).get("index")
    source = None
    if isinstance(texture, int) and 0 <= texture < len(doc.get("textures") or []):
        source = doc["textures"][texture].get("source")
    info: dict[str, Any] = {
        "index": index,
        "name": mat.get("name"),
        "unlit": "KHR_materials_unlit" in ext,
        "metallic": float(pbr.get("metallicFactor", 1.0)),
        "roughness": float(pbr.get("roughnessFactor", 1.0)),
        "baseColorTexture": texture,
        "imageSource": source if isinstance(source, int) else None,
    }
    info["atlasPx"] = _image_size(doc, binp, info["imageSource"])
    return info


def _image_size(doc: dict[str, Any], binp: bytes, image_index: int | None) -> list[int] | None:
    """Pixel size of an embedded PNG/JPEG without decoding it, or None."""
    if image_index is None:
        return None
    images = doc.get("images") or []
    if not 0 <= image_index < len(images):
        return None
    view_index = images[image_index].get("bufferView")
    views = doc.get("bufferViews") or []
    if not isinstance(view_index, int) or not 0 <= view_index < len(views):
        return None
    view = views[view_index]
    start = int(view.get("byteOffset", 0))
    length = int(view.get("byteLength", 0))
    data = binp[start:start + min(length, 1 << 20)]
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        w, h = struct.unpack(">II", data[16:24])
        return [int(w), int(h)]
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return [int(w), int(h)]
            seg = struct.unpack(">H", data[i + 2:i + 4])[0]
            i += 2 + seg
    return None


def _load_meshes(doc: dict[str, Any], binp: bytes, world: Sequence[Sequence[float]]) -> tuple[list[_Mesh], list[str]]:
    meshes: list[_Mesh] = []
    skipped: list[str] = []
    nodes = doc.get("nodes") or []
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or "mesh" not in node:
            continue
        mesh_index = node["mesh"]
        if not isinstance(mesh_index, int) or not 0 <= mesh_index < len(doc.get("meshes") or []):
            skipped.append(f"node {index}: mesh reference {mesh_index!r} is out of range")
            continue
        m = _Mesh(doc, binp, index, node, world[index] if index < len(world) else None)
        if m.vertex_count == 0:
            skipped.append(f"node {index} ({m.node_name}): mesh {m.name!r} has no triangle POSITION data")
            continue
        meshes.append(m)
    return meshes, skipped


# --------------------------------------------------------------------------------------------
# Geometry primitives
# --------------------------------------------------------------------------------------------


def _tri_area(a: Sequence[float], b: Sequence[float], c: Sequence[float]) -> float:
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    cx = uy * vz - uz * vy
    cy = uz * vx - ux * vz
    cz = ux * vy - uy * vx
    return 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)


def _weld(positions: Sequence[Sequence[float]]) -> tuple[list[int], list[tuple[float, float, float]]]:
    """Weld by position at 1e-6 m. Returns (welded id per raw vertex, one position per welded id)."""
    table: dict[tuple[int, int, int], int] = {}
    wid: list[int] = []
    wpos: list[tuple[float, float, float]] = []
    for p in positions:
        key = (round(p[0] * WELD_SCALE), round(p[1] * WELD_SCALE), round(p[2] * WELD_SCALE))
        got = table.get(key)
        if got is None:
            got = len(wpos)
            table[key] = got
            wpos.append((p[0], p[1], p[2]))
        wid.append(got)
    return wid, wpos


def _closest_on_triangle(px: float, py: float, pz: float, t: tuple[float, ...]) -> tuple[float, float, float]:
    """Squared distance from p to triangle t plus the (v, w) barycentric weights of the closest point.

    Ericson, Real-Time Collision Detection 5.1.5. The closest point is a + ab*v + ac*w and the
    weight of vertex a is 1 - v - w.
    """
    ax, ay, az, abx, aby, abz, acx, acy, acz = t
    apx, apy, apz = px - ax, py - ay, pz - az
    d1 = abx * apx + aby * apy + abz * apz
    d2 = acx * apx + acy * apy + acz * apz
    if d1 <= 0.0 and d2 <= 0.0:
        v = w = 0.0
    else:
        bpx, bpy, bpz = apx - abx, apy - aby, apz - abz
        d3 = abx * bpx + aby * bpy + abz * bpz
        d4 = acx * bpx + acy * bpy + acz * bpz
        if d3 >= 0.0 and d4 <= d3:
            v, w = 1.0, 0.0
        else:
            vc = d1 * d4 - d3 * d2
            if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
                v, w = d1 / (d1 - d3), 0.0
            else:
                cpx, cpy, cpz = apx - acx, apy - acy, apz - acz
                d5 = abx * cpx + aby * cpy + abz * cpz
                d6 = acx * cpx + acy * cpy + acz * cpz
                if d6 >= 0.0 and d5 <= d6:
                    v, w = 0.0, 1.0
                else:
                    vb = d5 * d2 - d1 * d6
                    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
                        v, w = 0.0, d2 / (d2 - d6)
                    else:
                        va = d3 * d6 - d5 * d4
                        if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:
                            w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
                            v = 1.0 - w
                        else:
                            total = va + vb + vc
                            if total == 0.0:
                                v = w = 0.0
                            else:
                                inv = 1.0 / total
                                v, w = vb * inv, vc * inv
    qx = ax + abx * v + acx * w - px
    qy = ay + aby * v + acy * w - py
    qz = az + abz * v + acz * w - pz
    return qx * qx + qy * qy + qz * qz, v, w


def _axis_gap2(q: float, c: int, d: int, cs: float) -> float:
    """Squared gap along one axis from coordinate q (in cell c) to the cell at offset d."""
    if d > 0:
        g = (c + d) * cs - q
    elif d < 0:
        g = q - (c + d + 1) * cs
    else:
        return 0.0
    return g * g


class _TriGrid:
    """Uniform grid over triangles for exact nearest-surface-point queries."""

    def __init__(self, positions: Sequence[Sequence[float]], tris: Sequence[tuple[int, int, int]], cell: float) -> None:
        self.cell = cell
        self.inv = 1.0 / cell
        self.tris = []
        self.data: list[tuple[float, ...]] = []
        cells: dict[tuple[int, int, int], list[int]] = {}
        inv = self.inv
        floor = math.floor
        for tri in tris:
            a, b, c = positions[tri[0]], positions[tri[1]], positions[tri[2]]
            if _tri_area(a, b, c) < 1e-14:
                continue
            index = len(self.data)
            self.tris.append(tri)
            self.data.append((a[0], a[1], a[2], b[0] - a[0], b[1] - a[1], b[2] - a[2], c[0] - a[0], c[1] - a[1], c[2] - a[2]))
            lo = [int(floor(min(a[k], b[k], c[k]) * inv)) for k in range(3)]
            hi = [int(floor(max(a[k], b[k], c[k]) * inv)) for k in range(3)]
            for ix in range(lo[0], hi[0] + 1):
                for iy in range(lo[1], hi[1] + 1):
                    for iz in range(lo[2], hi[2] + 1):
                        cells.setdefault((ix, iy, iz), []).append(index)
        self.cells = cells

    def nearest(self, q: Sequence[float], cap: float) -> tuple[float, int, float, float] | None:
        """(distance, triangle index, v, w) of the closest surface point within `cap`, else None."""
        inv = self.inv
        cs = self.cell
        qx, qy, qz = q[0], q[1], q[2]
        fx, fy, fz = qx * inv, qy * inv, qz * inv
        cx, cy, cz = int(math.floor(fx)), int(math.floor(fy)), int(math.floor(fz))
        # distance from q to the faces of its own cell: a lower bound on anything outside radius 0
        m0 = min(fx - cx, cx + 1 - fx, fy - cy, cy + 1 - fy, fz - cz, cz + 1 - fz) * cs
        best = math.inf
        best_t = -1
        best_v = best_w = 0.0
        seen: set[int] = set()
        cells = self.cells
        data = self.data
        ring = 0
        max_ring = int(cap * inv) + 1
        while ring <= max_ring:
            if ring == 0:
                buckets = (cells.get((cx, cy, cz)),)
            else:
                # skip every cell whose box is already farther than the best hit; the per-axis
                # squared gap from q to cell offset d is shared by all cells with that offset
                exs = [_axis_gap2(qx, cx, d, cs) for d in range(-ring, ring + 1)]
                eys = [_axis_gap2(qy, cy, d, cs) for d in range(-ring, ring + 1)]
                ezs = [_axis_gap2(qz, cz, d, cs) for d in range(-ring, ring + 1)]
                buckets = [
                    cells.get((cx + dx, cy + dy, cz + dz))
                    for dx, dy, dz in _ring_offsets(ring)
                    if exs[dx + ring] + eys[dy + ring] + ezs[dz + ring] <= best
                ]
            for bucket in buckets:
                if bucket is None:
                    continue
                for ti in bucket:
                    if ti in seen:
                        continue
                    seen.add(ti)
                    d2, v, w = _closest_on_triangle(qx, qy, qz, data[ti])
                    if d2 < best:
                        best, best_t, best_v, best_w = d2, ti, v, w
            bound = ring * cs + m0
            if best_t >= 0 and math.sqrt(best) <= bound:
                break
            if bound > cap:
                break
            ring += 1
        if best_t < 0:
            return None
        d = math.sqrt(best)
        if d > cap:
            return None
        return d, best_t, best_v, best_w


_RING_OFFSETS: dict[int, list[tuple[int, int, int]]] = {}


def _ring_offsets(r: int) -> list[tuple[int, int, int]]:
    """Cell offsets at Chebyshev distance exactly r (cached; r >= 1)."""
    cached = _RING_OFFSETS.get(r)
    if cached is None:
        cached = [
            (dx, dy, dz)
            for dx in range(-r, r + 1)
            for dy in range(-r, r + 1)
            for dz in range(-r, r + 1)
            if max(abs(dx), abs(dy), abs(dz)) == r
        ]
        _RING_OFFSETS[r] = cached
    return cached


class _PointGrid:
    """Uniform grid over points for bounded nearest-neighbour queries."""

    def __init__(self, points: Sequence[Sequence[float]], cell: float, ids: Sequence[int] | None = None) -> None:
        self.cell = cell
        self.inv = 1.0 / cell
        self.points = points
        cells: dict[tuple[int, int, int], list[int]] = {}
        inv = self.inv
        floor = math.floor
        for i in (range(len(points)) if ids is None else ids):
            p = points[i]
            cells.setdefault((int(floor(p[0] * inv)), int(floor(p[1] * inv)), int(floor(p[2] * inv))), []).append(i)
        self.cells = cells

    def nearest(self, q: Sequence[float], cap: float, exclude: int = -1) -> tuple[float, int] | None:
        inv = self.inv
        cs = self.cell
        fx, fy, fz = q[0] * inv, q[1] * inv, q[2] * inv
        cx, cy, cz = int(math.floor(fx)), int(math.floor(fy)), int(math.floor(fz))
        m0 = min(fx - cx, cx + 1 - fx, fy - cy, cy + 1 - fy, fz - cz, cz + 1 - fz) * cs
        best = math.inf
        best_i = -1
        pts = self.points
        cells = self.cells
        ring = 0
        max_ring = int(cap * inv) + 1
        while ring <= max_ring:
            buckets = (cells.get((cx, cy, cz)),) if ring == 0 else [cells.get((cx + dx, cy + dy, cz + dz)) for dx, dy, dz in _ring_offsets(ring)]
            for bucket in buckets:
                if bucket is None:
                    continue
                for i in bucket:
                    if i == exclude:
                        continue
                    p = pts[i]
                    d2 = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2
                    if d2 < best:
                        best, best_i = d2, i
            bound = ring * cs + m0
            if best_i >= 0 and math.sqrt(best) <= bound:
                break
            if bound > cap:
                break
            ring += 1
        if best_i < 0:
            return None
        d = math.sqrt(best)
        return (d, best_i) if d <= cap else None


# --------------------------------------------------------------------------------------------
# Context shared by every section
# --------------------------------------------------------------------------------------------


class _Regions:
    """Body regions of the skin mesh, derived from its own geometry (never from names)."""

    def __init__(self, ymin: float, height: float, skin: _Mesh) -> None:
        self.ymin = ymin
        self.height = height
        self.notes: list[str] = []
        pos = skin.positions
        bands: dict[int, list[float]] = {}
        for (x, y, z) in pos:
            bands.setdefault(int((y - ymin) / height * 100.0), []).append(abs(x))

        # neck = narrowest horizontal extent between 0.80 H and 0.95 H
        candidates = []
        for b in range(80, 96):
            xs = bands.get(b)
            if xs and len(xs) >= 8:
                xs = sorted(xs)
                candidates.append((_pct(xs, 98), b))
        self.neck_found = bool(candidates)
        if candidates:
            self.neck_band = min(candidates)[1]
            self.head_start_frac = (self.neck_band + 1) / 100.0
            self.neck_basis = "narrowest p98(|x|) band of the skin mesh between 0.80H and 0.95H; head starts at that band's upper edge"
        else:
            self.neck_band = None
            self.head_start_frac = 0.87
            self.neck_basis = "no usable neck band found; head start ASSUMED at 0.87H"
            self.notes.append("head start is assumed (0.87H): the skin mesh has no measurable neck band")

        # crotch = highest band (scanning down from 0.58 H) with no vertices at the body centre line
        centre_half = 0.004 * height
        self.crotch_frac: float | None = None
        for b in range(58, 15, -1):
            xs = bands.get(b)
            if not xs or len(xs) < 10:
                continue
            central = sum(1 for v in xs if v < centre_half)
            if central == 0:
                self.crotch_frac = (b + 1) / 100.0
                break
        self.crotch_basis = (
            "highest 0.01H band below 0.58H whose skin vertices leave the centre line (|x|<0.004H) empty, i.e. the legs have separated"
            if self.crotch_frac is not None else "legs never separate at the centre line; crotch not found"
        )
        if self.crotch_frac is None:
            self.notes.append("crotch height not found: leg region is empty and everything below the head is torso/arm")

        if self.crotch_frac is not None:
            lo = int(round(self.crotch_frac * 100)) - 15
            hi = int(round(self.crotch_frac * 100)) - 5
            xs = sorted(v for b in range(lo, hi + 1) for v in bands.get(b, ()))
            hip_half = _pct(xs, 98) if xs else None
        else:
            hip_half = None
        if hip_half is not None:
            self.arm_x = max(1.15 * hip_half, 0.075 * height)
            self.arm_basis = "1.15 x p98(|x|) of the 0.01H bands 0.05H-0.15H below the crotch (leg/hip half-width, clear of hands at hip height), floor 0.075H"
        else:
            self.arm_x = 0.09 * height
            self.arm_basis = "ASSUMED 0.09H half-width (no leg band to measure from)"
        self.hip_half_width = hip_half

    @property
    def head_start_y(self) -> float:
        return self.ymin + self.head_start_frac * self.height

    @property
    def crotch_y(self) -> float | None:
        return None if self.crotch_frac is None else self.ymin + self.crotch_frac * self.height

    def of(self, x: float, y: float, z: float) -> str:
        f = (y - self.ymin) / self.height
        if f >= self.head_start_frac:
            return "head"
        if abs(x) > self.arm_x:
            return "arm"
        if self.crotch_frac is not None and f < self.crotch_frac:
            return "leg"
        return "torso"

    def to_dict(self) -> dict[str, Any]:
        return {
            "headStartFrac": _r(self.head_start_frac, 4),
            "headStartBasis": self.neck_basis,
            "crotchFrac": _r(self.crotch_frac, 4),
            "crotchBasis": self.crotch_basis,
            "armHalfWidthM": _r(self.arm_x),
            "armHalfWidthFrac": _r(self.arm_x / self.height, 4),
            "armBasis": self.arm_basis,
            "hipHalfWidthM": _r(self.hip_half_width),
            "definition": "head: y>=headStart; arm: |x|>armHalfWidth; leg: y<crotch; torso: the rest (arm test precedes leg/torso)",
            "notes": list(self.notes),
        }


class _Ctx:
    def __init__(self, doc: dict[str, Any], binp: bytes, meshes: list[_Mesh], skin: _Mesh | None, height: float, ymin: float, ymax: float) -> None:
        self.doc = doc
        self.binp = binp
        self.meshes = meshes
        self.skin = skin
        self.height = height
        self.ymin = ymin
        self.ymax = ymax
        self.regions: _Regions | None = None
        self.skin_grid: _TriGrid | None = None
        self.limits: list[str] = []
        self.timings: dict[str, float] = {}

    def frac(self, y: float) -> float:
        return (y - self.ymin) / self.height


# --------------------------------------------------------------------------------------------
# Body mesh detection
# --------------------------------------------------------------------------------------------


def _pick_body(meshes: list[_Mesh], override: str | None) -> tuple[_Mesh | None, dict[str, Any]]:
    if override is not None:
        for m in meshes:
            if m.name == override or m.node_name == override:
                return m, {"method": "override", "basis": f"body_mesh={override!r} matched mesh {m.name!r} / node {m.node_name!r}"}
        names = sorted({n for m in meshes for n in (m.name, m.node_name)})
        raise ValueError(f"body_mesh {override!r} matches no mesh or node name; available: {names}")
    scored = []
    for m in meshes:
        if not m.tris:
            continue
        mat = m.material()
        skin_like = bool(mat and not mat["unlit"] and mat["metallic"] <= 0.1)
        n_soft = len(m.soft_mask_names())
        score = (1 if m.has_joints else 0, 1 if skin_like else 0, m.vertex_count, n_soft)
        scored.append((score, m, n_soft, skin_like))
    if not scored:
        return None, {"method": "none", "basis": "no mesh with triangles"}
    scored.sort(key=lambda s: s[0], reverse=True)
    top = scored[0]
    return top[1], {
        "method": "autodetect",
        "basis": (
            "ranking key (has JOINTS_0, lit dielectric material metallic<=0.1, vertex count, number of _SOFT_* attributes); highest wins. "
            "Vertex count outranks the mask count because garments carry _SOFT_* masks too while some bodies carry none"
        ),
        "candidates": [
            {"mesh": s[1].name, "node": s[1].node_name, "vertices": s[1].vertex_count, "softMaskAttributes": s[2], "skinLikeMaterial": s[3], "hasJoints": s[1].has_joints}
            for s in scored[:5]
        ],
    }


# --------------------------------------------------------------------------------------------
# Section: parts, roles, layering, garment clearance
# --------------------------------------------------------------------------------------------


def _vertex_normals(mesh: _Mesh) -> list[tuple[float, float, float]]:
    """The mesh's NORMAL attribute, or area-weighted vertex normals computed from its triangles."""
    given = mesh.normals
    if given is not None and len(given) == mesh.vertex_count:
        return [(n[0], n[1], n[2]) for n in given]
    acc = [[0.0, 0.0, 0.0] for _ in range(mesh.vertex_count)]
    p = mesh.positions
    for a, b, c in mesh.tris:
        ux, uy, uz = p[b][0] - p[a][0], p[b][1] - p[a][1], p[b][2] - p[a][2]
        vx, vy, vz = p[c][0] - p[a][0], p[c][1] - p[a][1], p[c][2] - p[a][2]
        n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
        for i in (a, b, c):
            acc[i][0] += n[0]
            acc[i][1] += n[1]
            acc[i][2] += n[2]
    out = []
    for n in acc:
        ln = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) or 1.0
        out.append((n[0] / ln, n[1] / ln, n[2] / ln))
    return out


class _SkinQuery:
    """Signed nearest-surface distance from arbitrary points to the skin mesh."""

    def __init__(self, ctx: _Ctx) -> None:
        skin = ctx.skin
        assert skin is not None
        grid = ctx.skin_grid
        assert grid is not None
        self.grid = grid
        self.normals = _vertex_normals(skin)
        self.tris = grid.tris

    def signed(self, q: Sequence[float], cap: float) -> tuple[float, bool] | None:
        """(signed distance, ok) with + outside the skin; None when the skin is farther than `cap`."""
        hit = self.grid.nearest(q, cap)
        if hit is None:
            return None
        d, ti, v, w = hit
        ia, ib, ic = self.tris[ti]
        na, nb, nc = self.normals[ia], self.normals[ib], self.normals[ic]
        u = 1.0 - v - w
        nx = u * na[0] + v * nb[0] + w * nc[0]
        ny = u * na[1] + v * nb[1] + w * nc[1]
        nz = u * na[2] + v * nb[2] + w * nc[2]
        t = self.grid.data[ti]
        cx = t[0] + t[3] * v + t[6] * w
        cy = t[1] + t[4] * v + t[7] * w
        cz = t[2] + t[5] * v + t[8] * w
        dot = (q[0] - cx) * nx + (q[1] - cy) * ny + (q[2] - cz) * nz
        return (d if dot >= 0.0 or d < 1e-9 else -d), True


def _mesh_features(ctx: _Ctx, mesh: _Mesh, query: _SkinQuery, sample: int = 200) -> dict[str, Any]:
    """Geometry-only features used by the light role guess."""
    pos = mesh.positions
    bb = _bbox(pos) or ([0.0] * 3, [0.0] * 3)
    lo, hi = bb
    centroid = [sum(p[k] for p in pos) / len(pos) for k in range(3)]
    extents = [hi[k] - lo[k] for k in range(3)]
    ids = _stride_sample(len(pos), sample)
    cap = 0.06
    dists: list[float] = []
    inside = 0
    beyond = 0
    for i in ids:
        res = query.signed(pos[i], cap)
        if res is None:
            beyond += 1
            continue
        dists.append(res[0])
        if res[0] < 0.0:
            inside += 1
    n = len(ids)
    ordered = sorted(abs(d) for d in dists)
    regions = ctx.regions
    return {
        "bboxLo": lo,
        "bboxHi": hi,
        "extents": extents,
        "maxExtent": max(extents),
        "centroid": centroid,
        "centroidYFrac": ctx.frac(centroid[1]),
        "topYFrac": ctx.frac(hi[1]),
        "bottomYFrac": ctx.frac(lo[1]),
        "centroidRegion": regions.of(*centroid) if regions else None,
        "sampled": n,
        "nearSkinShare": len(dists) / n if n else 0.0,
        "within1cmShare": sum(1 for d in ordered if d <= 0.01) / n if n else 0.0,
        "medianAbsToSkinM": _pct(ordered, 50) if ordered else None,
        "insideShare": inside / n if n else 0.0,
    }


def _guess_roles(ctx: _Ctx, features: dict[str, dict[str, Any]], keys: dict[int, str], hair_override: str | None) -> dict[str, dict[str, Any]]:
    """Geometry-only role guess per mesh label. Rules are explicit and ordered; each result has a basis."""
    H = ctx.height
    skin = ctx.skin
    regions = ctx.regions
    head_start = regions.head_start_frac if regions else 0.87
    roles: dict[str, dict[str, Any]] = {}
    hair_candidates: list[tuple[int, str]] = []
    for m in ctx.meshes:
        f = features.get(keys[id(m)])
        if f is None:
            continue
        if hair_override is not None and (m.name == hair_override or m.node_name == hair_override):
            hair_candidates.append((10 ** 9, keys[id(m)]))
            continue
        if skin is not None and m is skin:
            continue
        head_wide = 0.30 * H
        touches_top = f["topYFrac"] >= 0.95
        in_head = f["centroidYFrac"] >= head_start - 0.10 and f["bboxHi"][0] - f["bboxLo"][0] <= head_wide
        if touches_top and in_head and f["within1cmShare"] < 0.5 and m.vertex_count >= 500:
            hair_candidates.append((m.vertex_count, keys[id(m)]))
    hair_key = max(hair_candidates)[1] if hair_candidates else None

    for m in ctx.meshes:
        key = keys[id(m)]
        f = features.get(key)
        if f is None:
            continue
        if skin is not None and m is skin:
            roles[key] = {"role": "skin-body", "confidence": "high", "basis": "chosen main skin mesh (see source.bodyMesh)"}
            continue
        near = f["nearSkinShare"]
        small = f["maxExtent"] < 0.06 * H
        in_head_band = f["centroidYFrac"] >= head_start
        if key == hair_key:
            roles[key] = {
                "role": "hair", "confidence": "medium",
                "basis": ("hair_mesh override" if hair_override is not None else
                          f"reaches the top 5% of the figure (topYFrac={f['topYFrac']:.3f}), centroid in the head/upper-neck band, "
                          f"narrower than 0.30H, <50% of sampled vertices within 1 cm of skin, >=500 vertices"),
            }
        elif in_head_band and f["maxExtent"] <= 0.09 * H and near >= 0.5:
            roles[key] = {
                "role": "face-detail", "confidence": "low",
                "basis": f"small (max extent {f['maxExtent']:.3f} m <= 0.09H) and in the head band, {near:.0%} of sampled vertices within 6 cm of skin: brow/lash/eye/mouth-scale part; which one cannot be told from geometry alone",
            }
        elif near >= 0.5 and not small:
            roles[key] = {
                "role": "garment", "confidence": "medium",
                "basis": f"{near:.0%} of sampled vertices within 6 cm of the skin surface, extent {f['maxExtent']:.3f} m; worn over region {f['centroidRegion']}",
            }
        elif near >= 0.5:
            roles[key] = {
                "role": "accessory", "confidence": "low",
                "basis": f"small (max extent {f['maxExtent']:.3f} m < 0.06H) and {near:.0%} of sampled vertices within 6 cm of skin",
            }
        else:
            roles[key] = {
                "role": "detached-or-prop", "confidence": "low",
                "basis": f"only {near:.0%} of sampled vertices within 6 cm of skin: separate attachment (footwear on a body part not in the skin mesh, prop, or floating detail)",
            }
    return roles


def _unique_keys(meshes: list[_Mesh]) -> dict[int, str]:
    """A stable unique label per mesh instance: the mesh name, with the node index added on a clash."""
    counts: dict[str, int] = {}
    for m in meshes:
        counts[m.name] = counts.get(m.name, 0) + 1
    return {id(m): (m.name if counts[m.name] == 1 else f"{m.name}#node{m.node_index}") for m in meshes}


def _garment_clearance(ctx: _Ctx, mesh: _Mesh, query: _SkinQuery, max_samples: int, cap: float) -> dict[str, Any]:
    pos = mesh.positions
    ids = _stride_sample(len(pos), max_samples)
    signed: list[float] = []
    beyond = 0
    H = ctx.height
    for i in ids:
        res = query.signed(pos[i], cap)
        if res is None:
            beyond += 1
        else:
            signed.append(res[0])
    n = len(ids)
    out: dict[str, Any] = {
        "vertexCount": mesh.vertex_count,
        "sampledVertices": n,
        "sampling": "all vertices" if n == mesh.vertex_count else f"every {mesh.vertex_count / n:.2f}-th vertex (deterministic stride)",
        "searchCapM": cap,
        "beyondCapCount": beyond,
        "beyondCapShare": _r(beyond / n if n else 0.0, 5),
    }
    if not signed:
        out.update({"signedMm": None, "signedFrac": None, "unsignedMm": None, "nearShare": None, "negativeCount": 0, "negativeShare": None, "clampBandShare": None})
        out["note"] = f"every sampled vertex is farther than {cap} m from the skin surface"
        return out
    out["signedMm"] = _summary(signed, 1000.0)
    out["signedFrac"] = _summary(signed, 1.0 / H, digits=6)
    out["unsignedMm"] = _summary([abs(d) for d in signed], 1000.0)
    m = len(signed)
    out["nearShare"] = {
        f"closerThan{int(round(t * 10000)) / 10}mm": _r(sum(1 for d in signed if abs(d) < t) / m, 5)
        for t in CLEARANCE_NEAR_THRESHOLDS_M
    }
    neg = sum(1 for d in signed if d < 0.0)
    out["negativeCount"] = neg
    out["negativeShare"] = _r(neg / m, 5)
    out["clampBandShare"] = {
        "description": "signed offset against the cloth-contact clearance clamp 0.8-20 mm",
        "below0.8mm": _r(sum(1 for d in signed if d < CLEARANCE_CLAMP_MIN_M) / m, 5),
        "within0.8to20mm": _r(sum(1 for d in signed if CLEARANCE_CLAMP_MIN_M <= d <= CLEARANCE_CLAMP_MAX_M) / m, 5),
        "above20mm": _r(sum(1 for d in signed if d > CLEARANCE_CLAMP_MAX_M) / m, 5),
    }
    return out


def _contacts(ctx: _Ctx, keys: dict[int, str], roles: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """For each non-skin mesh: which other non-skin meshes touch it (vertex within 1 cm of >=10% of samples)."""
    others = [m for m in ctx.meshes if m is not ctx.skin]
    points: list[tuple[float, float, float]] = []
    owner: list[int] = []
    for oi, m in enumerate(others):
        for p in m.positions:
            points.append(p)
            owner.append(oi)
    if not points:
        return {}
    grid = _PointGrid(points, 0.01)
    result: dict[str, list[dict[str, Any]]] = {}
    for oi, m in enumerate(others):
        ids = _stride_sample(m.vertex_count, 150)
        counts: dict[int, int] = {}
        for i in ids:
            q = m.positions[i]
            # nearest vertex of a DIFFERENT mesh: query a few rings and skip own vertices
            best = _nearest_other(grid, points, owner, q, oi, 0.01)
            if best is not None:
                counts[best] = counts.get(best, 0) + 1
        rows = [
            {"mesh": keys[id(others[o])], "share": _r(c / len(ids), 3)}
            for o, c in sorted(counts.items(), key=lambda kv: -kv[1]) if c / len(ids) >= 0.10
        ]
        result[keys[id(m)]] = rows
    return result


def _nearest_other(grid: _PointGrid, points: Sequence[Sequence[float]], owner: Sequence[int], q: Sequence[float], own: int, cap: float) -> int | None:
    inv = grid.inv
    cx, cy, cz = int(math.floor(q[0] * inv)), int(math.floor(q[1] * inv)), int(math.floor(q[2] * inv))
    best = math.inf
    best_owner = None
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                bucket = grid.cells.get((cx + dx, cy + dy, cz + dz))
                if not bucket:
                    continue
                for i in bucket:
                    if owner[i] == own:
                        continue
                    p = points[i]
                    d2 = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2
                    if d2 < best:
                        best, best_owner = d2, owner[i]
    return best_owner if best <= cap * cap else None


def _parts_section(ctx: _Ctx, keys: dict[int, str], max_samples: int, hair_override: str | None) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Returns (parts, roles inferred, layering observed, layering inferred, clearance observed, role features)."""
    parts: list[dict[str, Any]] = []
    features: dict[str, dict[str, Any]] = {}
    query: _SkinQuery | None = None
    if ctx.skin is not None and ctx.skin_grid is not None and ctx.regions is not None:
        query = _SkinQuery(ctx)

    for m in ctx.meshes:
        key = keys[id(m)]
        mat = m.material()
        bb = _bbox(m.positions)
        part: dict[str, Any] = {
            "mesh": key,
            "node": m.node_name,
            "vertices": m.vertex_count,
            "triangles": len(m.tris),
            "skinned": m.skin_index is not None,
            "hasJointsAttribute": m.has_joints,
            "softMaskAttributes": m.soft_mask_names(),
            "material": None if mat is None else {k: mat[k] for k in ("name", "unlit", "metallic", "roughness", "imageSource", "atlasPx")},
        }
        if bb:
            lo, hi = bb
            part["bboxM"] = {"min": [_r(v) for v in lo], "max": [_r(v) for v in hi]}
            part["bboxYFrac"] = [_r(ctx.frac(lo[1]), 4), _r(ctx.frac(hi[1]), 4)]
            part["extentsM"] = [_r(hi[k] - lo[k]) for k in range(3)]
        part["surfaceAreaM2"] = _r(m.surface_area(), 5)
        parts.append(part)
        if query is not None:
            features[key] = _mesh_features(ctx, m, query)
            part["nearSkinShare6cm"] = _r(features[key]["nearSkinShare"], 3)

    roles: dict[str, dict[str, Any]] = {}
    if query is not None:
        roles = _guess_roles(ctx, features, keys, hair_override)
    else:
        ctx.limits.append("no skin mesh with triangles: roles, layering and garment clearance were not computed")

    clearance: dict[str, Any] = {}
    cap = 0.10
    if query is not None:
        for m in ctx.meshes:
            key = keys[id(m)]
            role = roles.get(key, {}).get("role")
            if role in ("garment", "accessory") and m.vertex_count >= 30:
                clearance[key] = _garment_clearance(ctx, m, query, max_samples, cap)
                clearance[key]["role"] = role

    layering_obs: dict[str, Any] = {}
    layering_inf: dict[str, Any] = {}
    if query is not None:
        contacts = _contacts(ctx, keys, roles)
        over = []
        for key, c in clearance.items():
            sm = c.get("signedMm")
            over.append({
                "mesh": key,
                "role": roles[key]["role"],
                "medianOffsetMm": None if sm is None else sm["median"],
                "p5OffsetMm": None if sm is None else sm["p5"],
                "p95OffsetMm": None if sm is None else sm["p95"],
                "negativeShare": c.get("negativeShare"),
            })
        over.sort(key=lambda r: (r["medianOffsetMm"] is None, r["medianOffsetMm"] if r["medianOffsetMm"] is not None else 0.0))
        layering_obs = {
            "skinMesh": keys[id(ctx.skin)],
            "separateObjectCount": len(ctx.meshes),
            "separateNonSkinObjectCount": len(ctx.meshes) - 1,
            "overSkinMeshesByMedianOffset": over,
            "meshContacts": contacts,
            "contactDefinition": "other non-skin meshes whose vertex lies within 1 cm of >=10% of 150 sampled vertices of this mesh",
        }
        counts: dict[str, int] = {}
        for r in roles.values():
            counts[r["role"]] = counts.get(r["role"], 0) + 1
        offs = [r["medianOffsetMm"] for r in over if r["medianOffsetMm"] is not None]
        layering_inf = {
            "roleCounts": counts,
            "structure": ("every garment/accessory is a SEPARATE mesh object floating over a single skin mesh"
                          if over else "no garment-like mesh found over the skin"),
            "medianOffsetRangeMm": None if not offs else [min(offs), max(offs)],
            "basis": "roles come from geometry only (distance to the skin surface, position in the figure, size); see inferred.roles for each rule",
        }
    return parts, roles, layering_obs, layering_inf, clearance, features


# --------------------------------------------------------------------------------------------
# Section: density and topology (skin mesh)
# --------------------------------------------------------------------------------------------


class _Topology:
    """Welded triangle graph of the skin mesh and every per-triangle / per-edge measurement on it."""

    def __init__(self, mesh: _Mesh) -> None:
        self.mesh = mesh
        self.wid, self.wpos = _weld(mesh.positions)
        nw = len(self.wpos)
        self.nw = nw
        wtris = []
        raw_tri_ids = []
        for ti, (a, b, c) in enumerate(mesh.tris):
            wa, wb, wc = self.wid[a], self.wid[b], self.wid[c]
            if wa != wb and wb != wc and wa != wc:
                wtris.append((wa, wb, wc))
                raw_tri_ids.append(ti)
        self.wtris = wtris
        self.raw_tri_ids = raw_tri_ids
        self.degenerate = len(mesh.tris) - len(wtris)

        # edges
        edge_index: dict[int, int] = {}
        edge_a: list[int] = []
        edge_b: list[int] = []
        edge_faces: list[list[int]] = []
        tri_edges: list[tuple[int, int, int]] = []
        for fi, (a, b, c) in enumerate(wtris):
            ids = []
            for (u, v) in ((a, b), (b, c), (c, a)):
                lo, hi = (u, v) if u < v else (v, u)
                key = lo * nw + hi
                ei = edge_index.get(key)
                if ei is None:
                    ei = len(edge_a)
                    edge_index[key] = ei
                    edge_a.append(lo)
                    edge_b.append(hi)
                    edge_faces.append([])
                edge_faces[ei].append(fi)
                ids.append(ei)
            tri_edges.append((ids[0], ids[1], ids[2]))
        self.edge_a, self.edge_b, self.edge_faces, self.tri_edges = edge_a, edge_b, edge_faces, tri_edges
        wp = self.wpos
        self.edge_len = [math.sqrt((wp[a][0] - wp[b][0]) ** 2 + (wp[a][1] - wp[b][1]) ** 2 + (wp[a][2] - wp[b][2]) ** 2) for a, b in zip(edge_a, edge_b)]

        adj: list[list[int]] = [[] for _ in range(nw)]
        for a, b in zip(edge_a, edge_b):
            adj[a].append(b)
            adj[b].append(a)
        self.adj = adj
        boundary = [False] * nw
        self.boundary_edges = 0
        self.nonmanifold_edges = 0
        for ei, faces in enumerate(edge_faces):
            if len(faces) == 1:
                boundary[edge_a[ei]] = True
                boundary[edge_b[ei]] = True
                self.boundary_edges += 1
            elif len(faces) > 2:
                self.nonmanifold_edges += 1
        self.boundary = boundary

        # per-triangle measurements
        self.tri_area: list[float] = []
        self.tri_min_angle: list[float] = []
        self.tri_centroid: list[tuple[float, float, float]] = []
        self.tri_normal: list[tuple[float, float, float]] = []
        el = self.edge_len
        for fi, (a, b, c) in enumerate(wtris):
            pa, pb, pc = wp[a], wp[b], wp[c]
            ux, uy, uz = pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]
            vx, vy, vz = pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            ln = math.sqrt(nx * nx + ny * ny + nz * nz)
            self.tri_area.append(0.5 * ln)
            self.tri_normal.append((nx / ln, ny / ln, nz / ln) if ln > 0 else (0.0, 0.0, 0.0))
            self.tri_centroid.append(((pa[0] + pb[0] + pc[0]) / 3.0, (pa[1] + pb[1] + pc[1]) / 3.0, (pa[2] + pb[2] + pc[2]) / 3.0))
            e0, e1, e2 = (el[i] for i in tri_edges[fi])
            # min angle sits opposite the shortest edge
            s, p, q = sorted((e0, e1, e2))
            if p > 0 and q > 0:
                cosv = (p * p + q * q - s * s) / (2.0 * p * q)
                self.tri_min_angle.append(math.degrees(math.acos(max(-1.0, min(1.0, cosv)))))
            else:
                self.tri_min_angle.append(0.0)


def _density_bands(topo: _Topology, ctx: _Ctx) -> list[dict[str, Any]]:
    n = BAND_COUNT
    verts = [0] * n
    area = [0.0] * n
    tri_count = [0] * n
    edge_len_sum = [0.0] * n
    edge_cnt = [0] * n
    wp = topo.wpos

    def band(y: float) -> int:
        return max(0, min(n - 1, int(ctx.frac(y) * n)))

    for p in wp:
        verts[band(p[1])] += 1
    for fi, c in enumerate(topo.tri_centroid):
        b = band(c[1])
        area[b] += topo.tri_area[fi]
        tri_count[b] += 1
    for ei, (a, b) in enumerate(zip(topo.edge_a, topo.edge_b)):
        k = band((wp[a][1] + wp[b][1]) * 0.5)
        edge_len_sum[k] += topo.edge_len[ei]
        edge_cnt[k] += 1
    rows = []
    for k in range(n):
        rows.append({
            "yFracLo": _r(k / n, 3), "yFracHi": _r((k + 1) / n, 3),
            "vertices": verts[k], "triangles": tri_count[k], "areaM2": _r(area[k], 5),
            "verticesPerM2": _r(verts[k] / area[k], 1) if area[k] > 0 else None,
            "meanEdgeMm": _r(edge_len_sum[k] / edge_cnt[k] * 1000.0, 3) if edge_cnt[k] else None,
        })
    return rows


def _region_density(topo: _Topology, ctx: _Ctx) -> dict[str, Any]:
    regions = ctx.regions
    assert regions is not None
    names = ["head", "torso", "arm", "leg"]
    stats = {k: {"vertices": 0, "triangles": 0, "area": 0.0, "edgeLenSum": 0.0, "edges": 0} for k in names}
    wp = topo.wpos
    for p in wp:
        stats[regions.of(*p)]["vertices"] += 1
    for fi, c in enumerate(topo.tri_centroid):
        s = stats[regions.of(*c)]
        s["triangles"] += 1
        s["area"] += topo.tri_area[fi]
    for ei, (a, b) in enumerate(zip(topo.edge_a, topo.edge_b)):
        mid = ((wp[a][0] + wp[b][0]) * 0.5, (wp[a][1] + wp[b][1]) * 0.5, (wp[a][2] + wp[b][2]) * 0.5)
        s = stats[regions.of(*mid)]
        s["edgeLenSum"] += topo.edge_len[ei]
        s["edges"] += 1
    limbs = {"vertices": stats["arm"]["vertices"] + stats["leg"]["vertices"], "triangles": stats["arm"]["triangles"] + stats["leg"]["triangles"],
             "area": stats["arm"]["area"] + stats["leg"]["area"], "edgeLenSum": stats["arm"]["edgeLenSum"] + stats["leg"]["edgeLenSum"],
             "edges": stats["arm"]["edges"] + stats["leg"]["edges"]}
    stats["limbs"] = limbs

    out: dict[str, Any] = {}
    for k, s in stats.items():
        out[k] = {
            "vertices": s["vertices"], "triangles": s["triangles"], "areaM2": _r(s["area"], 5),
            "verticesPerM2": _r(s["vertices"] / s["area"], 1) if s["area"] > 0 else None,
            "trianglesPerM2": _r(s["triangles"] / s["area"], 1) if s["area"] > 0 else None,
            "meanEdgeMm": _r(s["edgeLenSum"] / s["edges"] * 1000.0, 3) if s["edges"] else None,
        }
    torso = out["torso"]["trianglesPerM2"]
    ratios: dict[str, Any] = {}
    for k in ("head", "torso", "arm", "leg", "limbs"):
        d = out[k]["trianglesPerM2"]
        ratios[k] = _r(d / torso, 4) if (d is not None and torso) else None
    out["ratiosTrianglesPerM2VsTorso"] = ratios
    edge_t = out["torso"]["meanEdgeMm"]
    out["ratiosMeanEdgeVsTorso"] = {k: (_r(out[k]["meanEdgeMm"] / edge_t, 4) if (out[k]["meanEdgeMm"] is not None and edge_t) else None) for k in ("head", "torso", "arm", "leg", "limbs")}
    out["definition"] = "vertex region from its position, triangle region from its centroid, edge region from its midpoint (see regions)"
    return out


def _topology_section(topo: _Topology, ctx: _Ctx) -> tuple[dict[str, Any], dict[str, Any]]:
    wp = topo.wpos
    nw = topo.nw
    n_tri = len(topo.wtris)
    areas = sorted(topo.tri_area)
    edge_len = sorted(topo.edge_len)
    min_angles = sorted(topo.tri_min_angle)
    total_area = sum(areas)

    # valence
    valence = [len(a) for a in topo.adj]
    boundary = topo.boundary
    interior_hist: dict[int, int] = {}
    for v, deg in enumerate(valence):
        if not boundary[v]:
            interior_hist[deg] = interior_hist.get(deg, 0) + 1
    n_interior = sum(interior_hist.values())
    n_boundary = nw - n_interior
    six = interior_hist.get(6, 0)
    hist_all: dict[int, int] = {}
    for d in valence:
        hist_all[d] = hist_all.get(d, 0) + 1

    # extraordinary-vertex isolation: non-6 interior vertices with no non-6 interior neighbour
    isolated = 0
    non_six = 0
    for v, deg in enumerate(valence):
        if boundary[v] or deg == 6:
            continue
        non_six += 1
        if all(boundary[u] or valence[u] == 6 for u in topo.adj[v]):
            isolated += 1

    # exact-midpoint vertices: p equals the midpoint of two of its own neighbours
    tol2 = MIDPOINT_TOL_M * 2.0
    midpoint = 0
    mid_by_valence: dict[int, int] = {}
    for v in range(nw):
        nbrs = topo.adj[v]
        if len(nbrs) < 2 or len(nbrs) > 14:
            continue
        px, py, pz = wp[v][0] * 2.0, wp[v][1] * 2.0, wp[v][2] * 2.0
        found = False
        pts = [wp[u] for u in nbrs]
        for i in range(len(pts)):
            ai = pts[i]
            tx, ty, tz = px - ai[0], py - ai[1], pz - ai[2]
            for j in range(i + 1, len(pts)):
                bj = pts[j]
                if abs(bj[0] - tx) < tol2 and abs(bj[1] - ty) < tol2 and abs(bj[2] - tz) < tol2:
                    found = True
                    break
            if found:
                break
        if found:
            midpoint += 1
            if not boundary[v]:
                mid_by_valence[len(nbrs)] = mid_by_valence.get(len(nbrs), 0) + 1

    # what do the neighbours of the most common valences look like?
    signature_counts: dict[int, dict[tuple[int, ...], int]] = {}
    for v in range(nw):
        if boundary[v] or valence[v] not in interior_hist or interior_hist[valence[v]] < 0.01 * max(n_interior, 1):
            continue
        sig = tuple(sorted(valence[u] for u in topo.adj[v]))
        bucket = signature_counts.setdefault(valence[v], {})
        bucket[sig] = bucket.get(sig, 0) + 1
    signatures = {
        str(k): [{"neighbourValences": list(sig), "vertices": c} for sig, c in sorted(bucket.items(), key=lambda kv: -kv[1])[:3]]
        for k, bucket in sorted(signature_counts.items())
    }

    # quad pairing: triangles whose longest edge is shared with a triangle that has the same longest edge
    longest: list[int] = []
    for fi in range(n_tri):
        es = topo.tri_edges[fi]
        longest.append(max(es, key=lambda e: topo.edge_len[e]))
    paired = 0
    planar_pairs = 0
    quad_like = 0
    pairs = 0
    for ei, faces in enumerate(topo.edge_faces):
        if len(faces) != 2:
            continue
        f0, f1 = faces
        if longest[f0] == ei and longest[f1] == ei:
            pairs += 1
            n0, n1 = topo.tri_normal[f0], topo.tri_normal[f1]
            dot = n0[0] * n1[0] + n0[1] * n1[1] + n0[2] * n1[2]
            planar = dot >= math.cos(math.radians(5.0))
            if planar:
                planar_pairs += 1
                if _quad_like(topo, f0, f1, ei):
                    quad_like += 1
    paired = pairs * 2

    # texture of angle quality
    low_angle = sum(1 for a in topo.tri_min_angle if a < 10.0)

    observed = {
        "weldedVertices": nw,
        "rawVertices": topo.mesh.vertex_count,
        "triangles": n_tri,
        "degenerateTrianglesDropped": topo.degenerate,
        "uniqueEdges": len(topo.edge_a),
        "boundaryEdges": topo.boundary_edges,
        "nonManifoldEdges": topo.nonmanifold_edges,
        "surfaceAreaM2": _r(total_area, 5),
        "verticesPerM2": _r(nw / total_area, 1) if total_area > 0 else None,
        "meanEdgeLengthMm": _r(sum(edge_len) / len(edge_len) * 1000.0, 3) if edge_len else None,
        "edgeLengthMm": _wide_summary(edge_len, 1000.0, 3),
        "triangleAreaMm2": _wide_summary(areas, 1e6, 3),
        "triangleMinAngleDeg": _wide_summary(min_angles, 1.0, 3),
        "shareTrianglesMinAngleBelow10Deg": _r(low_angle / n_tri, 5) if n_tri else None,
        "valence": {
            "interiorHistogram": {str(k): v for k, v in sorted(interior_hist.items())},
            "allHistogram": {str(k): v for k, v in sorted(hist_all.items())},
            "interiorVertices": n_interior,
            "boundaryVertices": n_boundary,
            "interiorValence6Share": _r(six / n_interior, 5) if n_interior else None,
            "interiorNonSixShare": _r((n_interior - six) / n_interior, 5) if n_interior else None,
            "meanInteriorValence": _r(sum(k * v for k, v in interior_hist.items()) / n_interior, 4) if n_interior else None,
            "nonSixInteriorVertices": non_six,
            "nonSixWithOnlyValence6Neighbours": isolated,
            "nonSixIsolationShare": _r(isolated / non_six, 4) if non_six else None,
        },
        "exactMidpointVertices": midpoint,
        "exactMidpointShare": _r(midpoint / nw, 5) if nw else None,
        "neighbourValenceSignatures": signatures,
        "quadPairing": {
            "mutualLongestEdgePairs": pairs,
            "pairedTriangleShare": _r(paired / n_tri, 5) if n_tri else None,
            "nearPlanarPairShareOfPairs": _r(planar_pairs / pairs, 5) if pairs else None,
            "nearPlanarPairedTriangleShare": _r(planar_pairs * 2 / n_tri, 5) if n_tri else None,
            "quadLikePairShareOfPairs": _r(quad_like / pairs, 5) if pairs else None,
            "definition": "two triangles pair when their shared edge is the longest edge of both; near-planar = dihedral < 5 degrees; quad-like = planar and every merged-quad angle in 60-120 degrees",
        },
        "density": {
            "bandsOfHeight": _density_bands(topo, ctx),
            "bandDefinition": f"{BAND_COUNT} equal bands of figure height; vertices by position, area by triangle centroid, edges by midpoint",
            "regions": _region_density(topo, ctx) if ctx.regions else None,
        },
    }

    # inference: refinement structure
    six_share = observed["valence"]["interiorValence6Share"]
    mid_share = observed["exactMidpointShare"]
    iso = observed["valence"]["nonSixIsolationShare"]
    inferred: dict[str, Any] = {}
    if six_share is not None and mid_share is not None:
        lattice = six_share >= 0.80 and (iso is None or iso >= 0.95)  # iso is None: no irregular vertex at all
        midpoint_majority = mid_share >= 0.60
        extraordinary = sum(c for k, c in interior_hist.items() if k not in (4, 6))
        parts = []
        if lattice:
            parts.append(
                f"valence statistics are consistent with a regular refinement lattice: {six_share:.1%} of interior vertices have valence 6 and "
                + ("there is no irregular vertex" if iso is None else f"{'every' if iso == 1.0 else f'{iso:.1%} of the'} irregular vertex sits only among valence-6 neighbours")
            )
        else:
            parts.append("valence statistics do NOT show a regular refinement lattice")
        parts.append(
            f"{mid_share:.1%} of welded vertices are exact (2 um) midpoints of two triangle-graph neighbours; "
            "this adjacency statistic cannot establish or exclude linear subdivision, smoothing or projection. "
            "Triangulated quad refinement and diagonal choices change the neighbour pairs; consult authoring source"
        )
        inferred["subdivision"] = {
            "valenceConsistentWithRegularRefinement": lattice,
            "midpointMajority": midpoint_majority,
            "linearSubdivision": None,
            "irregularVertexCount": extraordinary,
            "irregularVertexCountNote": "interior vertices with valence other than 4 or 6; not an estimate of the original control-cage vertex count without a known refinement algorithm",
            "verdict": "; ".join(parts),
            "evidence": {
                "interiorValence6Share": six_share,
                "exactMidpointShare": mid_share,
                "nonSixIsolationShare": iso,
                "exactMidpointByValence": {str(k): [mid_by_valence.get(k, 0), c] for k, c in sorted(interior_hist.items())},
            },
            "basis": (
                "regular lattice = interior valence-6 share >= 0.80 AND >= 95% of non-6 interior vertices have only valence-6 neighbours; "
                "midpointMajority = >= 60% of welded vertices lie within 2 um of the midpoint of two triangle-graph neighbours. "
                "Neither statistic determines construction history: regular grids, quad triangulation and different refinements can overlap. "
                "The original cage and modifier stack are not stored in the GLB; linearSubdivision remains null."
            ),
        }
    else:
        inferred["subdivision"] = {"valenceConsistentWithRegularRefinement": None, "basis": "no interior vertices to measure valence on"}
    pair_share = observed["quadPairing"]["pairedTriangleShare"]
    inferred["faceStructure"] = {
        "trianglePairing": None if pair_share is None else ("few-mutual-longest-edge-pairs" if pair_share < 0.5 else "many-mutual-longest-edge-pairs"),
        "basis": f"pairedTriangleShare={pair_share}; this measures exported triangles, not original quads or authoring history; planarity is reported separately",
    }
    return observed, inferred


def _quad_like(topo: _Topology, f0: int, f1: int, shared_edge: int) -> bool:
    """Is the union of two triangles a convex quad with all angles in 60-120 degrees?"""
    wp = topo.wpos
    a, b = topo.edge_a[shared_edge], topo.edge_b[shared_edge]
    c0 = next(v for v in topo.wtris[f0] if v != a and v != b)
    c1 = next(v for v in topo.wtris[f1] if v != a and v != b)
    ring = [a, c0, b, c1]
    for i in range(4):
        p, q, r = wp[ring[i - 1]], wp[ring[i]], wp[ring[(i + 1) % 4]]
        ux, uy, uz = p[0] - q[0], p[1] - q[1], p[2] - q[2]
        vx, vy, vz = r[0] - q[0], r[1] - q[1], r[2] - q[2]
        lu = math.sqrt(ux * ux + uy * uy + uz * uz)
        lv = math.sqrt(vx * vx + vy * vy + vz * vz)
        if lu == 0 or lv == 0:
            return False
        ang = math.degrees(math.acos(max(-1.0, min(1.0, (ux * vx + uy * vy + uz * vz) / (lu * lv)))))
        if not 60.0 <= ang <= 120.0:
            return False
    return True


# --------------------------------------------------------------------------------------------
# Section: symmetry
# --------------------------------------------------------------------------------------------


def _mirror_match(topo: _Topology, x0: float, cell: float, cap: float) -> tuple[list[float], list[int]]:
    """Per welded vertex: distance to the nearest welded vertex at its mirror position, and that vertex."""
    wp = topo.wpos
    grid = _PointGrid(wp, cell)
    dists: list[float] = []
    partner: list[int] = []
    for p in wp:
        q = (2.0 * x0 - p[0], p[1], p[2])
        hit = grid.nearest(q, cap)
        if hit is None:
            dists.append(cap)
            partner.append(-1)
        else:
            dists.append(hit[0])
            partner.append(hit[1])
    return dists, partner


def _symmetry_section(topo: _Topology, ctx: _Ctx) -> tuple[dict[str, Any], dict[str, Any]]:
    wp = topo.wpos
    regions = ctx.regions
    assert regions is not None
    H = ctx.height
    el = sorted(topo.edge_len)
    median_edge = _pct(el, 50) or 0.005
    cell = max(median_edge, 0.002)
    cap = max(4.0 * cell, 0.01)
    bb = _bbox(wp)
    assert bb is not None
    centre_x = (bb[0][0] + bb[1][0]) / 2.0

    candidates = [0.0] if abs(centre_x) < 1e-6 else [0.0, centre_x]
    best: tuple[float, float, list[float], list[int]] | None = None
    for x0 in candidates:
        d, partner = _mirror_match(topo, x0, cell, cap)
        med = _pct(sorted(d), 50) or 0.0
        if best is None or med < best[0]:
            best = (med, x0, d, partner)
    assert best is not None
    _, x0, dists, partner = best

    reg = [regions.of(*p) for p in wp]
    arm_idx = [i for i, r in enumerate(reg) if r == "arm"]
    nonarm_idx = [i for i, r in enumerate(reg) if r != "arm"]
    centre_line = sum(1 for p in wp if abs(p[0] - x0) < 1e-5)

    def block(ids: list[int]) -> dict[str, Any] | None:
        if not ids:
            return None
        vals = [dists[i] for i in ids]
        s = _wide_summary(vals, 1000.0, 4)
        s["vertices"] = len(ids)
        s["frac"] = {"p95": _r(_pct(sorted(vals), 95) / H, 7), "max": _r(max(vals) / H, 7)}
        s["unmatchedAtCap"] = sum(1 for i in ids if partner[i] < 0)
        return s

    observed: dict[str, Any] = {
        "mirrorPlaneX": _r(x0, 7),
        "mirrorPlaneCandidatesTried": [_r(c, 7) for c in candidates],
        "searchCapMm": _r(cap * 1000.0, 3),
        "cellMm": _r(cell * 1000.0, 3),
        "centreLineVertices": centre_line,
        "mirrorErrorMm": {"allVertices": block(list(range(len(wp)))), "excludingArms": block(nonarm_idx), "armsOnly": block(arm_idx)},
        "exactMirrorShare": _r(sum(1 for d in dists if d <= MIRROR_MATCH_M) / len(dists), 5),
        "exactMirrorToleranceMm": MIRROR_MATCH_M * 1000.0,
    }

    # UV mirroring
    uv = ctx.skin.uvs if ctx.skin is not None else None
    uv_obs: dict[str, Any] | None = None
    if uv is None:
        ctx.limits.append("symmetry: the skin mesh has no TEXCOORD_0, so UV mirroring was not evaluated")
    else:
        copies: list[list[int]] = [[] for _ in wp]
        for raw, w in enumerate(topo.wid):
            copies[w].append(raw)
        pair_sum_samples: list[float] = []
        pending: list[tuple[int, int]] = []
        for w, p in enumerate(wp):
            m = partner[w]
            if m < 0 or m == w or abs(p[0] - x0) < 1e-5 or dists[w] > MIRROR_MATCH_M:
                continue
            if p[0] < x0:  # visit each mirrored pair once
                continue
            pending.append((w, m))
        for w, m in pending:
            for i in copies[w]:
                for j in copies[m]:
                    du = abs(uv[i][0] - uv[j][0])
                    dv = abs(uv[i][1] - uv[j][1])
                    if dv < UV_MATCH and du > UV_MATCH:
                        pair_sum_samples.append(uv[i][0] + uv[j][0])
        axis_sum = _pct(sorted(pair_sum_samples), 50) if pair_sum_samples else None
        shared = mirrored = independent = 0
        for w, m in pending:
            kind = "independent"
            for i in copies[w]:
                for j in copies[m]:
                    du = abs(uv[i][0] - uv[j][0])
                    dv = abs(uv[i][1] - uv[j][1])
                    if du < UV_MATCH and dv < UV_MATCH:
                        kind = "shared"
                        break
                    if axis_sum is not None and dv < UV_MATCH and abs(uv[i][0] + uv[j][0] - axis_sum) < UV_MATCH:
                        kind = "mirrored"
                if kind == "shared":
                    break
            if kind == "shared":
                shared += 1
            elif kind == "mirrored":
                mirrored += 1
            else:
                independent += 1
        total = shared + mirrored + independent
        uv_obs = {
            "mirroredVertexPairsExamined": total,
            "sharedUvShare": _r(shared / total, 5) if total else None,
            "mirroredUvShare": _r(mirrored / total, 5) if total else None,
            "independentUvShare": _r(independent / total, 5) if total else None,
            "mirrorAxisUSum": _r(axis_sum, 6),
            "uvToleranceUnits": UV_MATCH,
            "definition": "pairs are welded vertices whose x-mirror partner lies within 0.5 mm; shared = any copy has the same UV, mirrored = same v and u+u' equal to one constant, else independent",
        }
    observed["uvMirroring"] = uv_obs

    ex = observed["mirrorErrorMm"]["excludingArms"]
    allv = observed["mirrorErrorMm"]["allVertices"]
    arms = observed["mirrorErrorMm"]["armsOnly"]
    inferred: dict[str, Any] = {}
    p95_all = allv["p95"] if allv else None
    inferred["geometricSymmetry"] = {
        "verdict": None if p95_all is None else (
            "bilaterally symmetric (x-mirror)" if p95_all <= 1.0 else
            "mostly symmetric with local deviations" if (allv["p50"] <= 1.0) else "not mirror symmetric"),
        "armsDifferFromRest": None if not (ex and arms) else bool(arms["p95"] > max(2.0 * ex["p95"], 1.0)),
        "basis": "all-vertex p95 mirror error <= 1.0 mm => symmetric; median <= 1 mm but p95 larger => local deviations; arms compared with the rest at 2x p95",
    }
    if uv_obs and uv_obs["mirroredVertexPairsExamined"]:
        s, mi = uv_obs["sharedUvShare"], uv_obs["mirroredUvShare"]
        inferred["uvSymmetry"] = {
            "layout": "mirrored halves share one UV layout (overlapping)" if s >= 0.5 else
                      ("mirrored UV islands (u reflected, not overlapping)" if mi >= 0.5 else "independent UV islands for left and right"),
            "basis": f"sharedUvShare={s}, mirroredUvShare={mi} over matched mirror pairs",
        }
    return observed, inferred


# --------------------------------------------------------------------------------------------
# Section: UV / atlas
# --------------------------------------------------------------------------------------------

_JX = 0.0137
_JY = 0.0071


def _rasterise(tri_uvs: Sequence[tuple[float, float, float, float, float, float]], n: int, owners: Sequence[int] | None = None) -> tuple[bytearray, list[int], dict[int, list[int]]]:
    """Point-sample UV triangles on an n x n grid (sample = pixel centre + a fixed irrational jitter).

    Returns (hit count per pixel saturating at 255, first owner per pixel, per-owner [self-overlap
    pixels, cross-owner overlap pixels]). Centre sampling is unbiased on aggregate coverage even
    when triangles are smaller than a pixel.
    """
    counts = bytearray(n * n)
    owner_of = [-1] * (n * n)
    overlap: dict[int, list[int]] = {}
    floor, ceil = math.floor, math.ceil
    for ti, (u0, v0, u1, v1, u2, v2) in enumerate(tri_uvs):
        x0, y0, x1, y1, x2, y2 = u0 * n, v0 * n, u1 * n, v1 * n, u2 * n, v2 * n
        area2 = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area2) < 1e-12:
            continue
        i0 = max(0, int(ceil(min(x0, x1, x2) - 0.5 - _JX)))
        i1 = min(n - 1, int(floor(max(x0, x1, x2) - 0.5 - _JX)))
        j0 = max(0, int(ceil(min(y0, y1, y2) - 0.5 - _JY)))
        j1 = min(n - 1, int(floor(max(y0, y1, y2) - 0.5 - _JY)))
        if i0 > i1 or j0 > j1:
            continue
        inv = 1.0 / area2
        who = owners[ti] if owners is not None else 0
        for j in range(j0, j1 + 1):
            sy = j + 0.5 + _JY
            row = j * n
            for i in range(i0, i1 + 1):
                sx = i + 0.5 + _JX
                w0 = ((x1 - sx) * (y2 - sy) - (x2 - sx) * (y1 - sy)) * inv
                if w0 < 0.0:
                    continue
                w1 = ((x2 - sx) * (y0 - sy) - (x0 - sx) * (y2 - sy)) * inv
                if w1 < 0.0:
                    continue
                if 1.0 - w0 - w1 < 0.0:
                    continue
                px = row + i
                c = counts[px]
                if c == 0:
                    owner_of[px] = who
                else:
                    rec = overlap.setdefault(who, [0, 0])
                    if owner_of[px] == who:
                        rec[0] += 1
                    else:
                        rec[1] += 1
                if c < 255:
                    counts[px] = c + 1
    return counts, owner_of, overlap


def _uv_islands(mesh: _Mesh, uv: Sequence[Sequence[float]]) -> tuple[list[int], int]:
    """Island id per triangle via union-find over (position, uv) welded vertices."""
    table: dict[tuple[int, int, int, int, int], int] = {}
    vid: list[int] = []
    for p, t in zip(mesh.positions, uv):
        key = (round(p[0] * WELD_SCALE), round(p[1] * WELD_SCALE), round(p[2] * WELD_SCALE), round(t[0] * WELD_SCALE), round(t[1] * WELD_SCALE))
        got = table.get(key)
        if got is None:
            got = len(table)
            table[key] = got
        vid.append(got)
    parent = list(range(len(table)))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b, c in mesh.tris:
        ra, rb, rc = find(vid[a]), find(vid[b]), find(vid[c])
        if ra != rb:
            parent[rb] = ra
        rc = find(vid[c])
        ra = find(vid[a])
        if rc != ra:
            parent[rc] = ra
    roots: dict[int, int] = {}
    island_of_tri: list[int] = []
    for a, _, _ in mesh.tris:
        r = find(vid[a])
        island_of_tri.append(roots.setdefault(r, len(roots)))
    return island_of_tri, len(roots)


def _uv_section(topo: _Topology, ctx: _Ctx) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    mesh = topo.mesh
    uv = mesh.uvs
    if uv is None:
        ctx.limits.append("uv/atlas: the skin mesh has no TEXCOORD_0")
        return None, {}
    mat = mesh.material()
    atlas = mat["atlasPx"] if mat else None
    pos = mesh.positions

    tri_uvs = []
    out_of_unit = 0
    for a, b, c in mesh.tris:
        ta, tb, tc = uv[a], uv[b], uv[c]
        tri_uvs.append((ta[0], ta[1], tb[0], tb[1], tc[0], tc[1]))
        if any(not 0.0 <= t <= 1.0 for t in (ta[0], ta[1], tb[0], tb[1], tc[0], tc[1])):
            out_of_unit += 1

    island_of_tri, island_count = _uv_islands(mesh, uv)
    isl_tris = [0] * island_count
    isl_area3d = [0.0] * island_count
    isl_area_uv = [0.0] * island_count
    isl_bbox = [[math.inf, math.inf, -math.inf, -math.inf] for _ in range(island_count)]
    isl_cent = [[0.0, 0.0, 0.0] for _ in range(island_count)]
    tri_density: list[float] = []
    w_px, h_px = (atlas if atlas else (None, None))
    px_scale = (w_px * h_px) if atlas else 1.0
    for ti, (a, b, c) in enumerate(mesh.tris):
        k = island_of_tri[ti]
        a3 = _tri_area(pos[a], pos[b], pos[c])
        t = tri_uvs[ti]
        a_uv = 0.5 * abs((t[2] - t[0]) * (t[5] - t[1]) - (t[4] - t[0]) * (t[3] - t[1]))
        isl_tris[k] += 1
        isl_area3d[k] += a3
        isl_area_uv[k] += a_uv
        bb = isl_bbox[k]
        for (u, v) in ((t[0], t[1]), (t[2], t[3]), (t[4], t[5])):
            bb[0] = min(bb[0], u)
            bb[1] = min(bb[1], v)
            bb[2] = max(bb[2], u)
            bb[3] = max(bb[3], v)
        for q in (pos[a], pos[b], pos[c]):
            isl_cent[k][0] += q[0] * a3 / 3.0
            isl_cent[k][1] += q[1] * a3 / 3.0
            isl_cent[k][2] += q[2] * a3 / 3.0
        if a3 > 1e-12:
            tri_density.append(math.sqrt(a_uv * px_scale / a3))

    # seams: welded edges whose sides disagree on UV
    seam_len = 0.0
    seam_edges = 0
    total_len = sum(topo.edge_len)
    side_uv: dict[int, list[tuple[tuple[int, int], tuple[int, int]]]] = {}
    nw = topo.nw
    for fi, ti in enumerate(topo.raw_tri_ids):
        raw = mesh.tris[ti]
        for k in range(3):
            ra, rb = raw[k], raw[(k + 1) % 3]
            wa, wb = topo.wid[ra], topo.wid[rb]
            ua = (round(uv[ra][0] * WELD_SCALE), round(uv[ra][1] * WELD_SCALE))
            ub = (round(uv[rb][0] * WELD_SCALE), round(uv[rb][1] * WELD_SCALE))
            if wa > wb:
                wa, wb, ua, ub = wb, wa, ub, ua
            side_uv.setdefault(wa * nw + wb, []).append((ua, ub))
    edge_key_len = {topo.edge_a[e] * nw + topo.edge_b[e]: topo.edge_len[e] for e in range(len(topo.edge_a))}
    for key, sides in side_uv.items():
        if len(sides) >= 2 and len(set(sides)) > 1:
            seam_edges += 1
            seam_len += edge_key_len.get(key, 0.0)

    # coverage / overlap
    counts, _, _ = _rasterise(tri_uvs, ATLAS_GRID)
    covered = sum(1 for c in counts if c > 0)
    overlapped = sum(1 for c in counts if c > 1)

    # texel density per island group (region of island centroid)
    regions = ctx.regions
    groups: dict[str, list[float]] = {}
    unit = "texelsPerMetre" if atlas else "uvUnitsPerMetre (atlas size unknown)"
    for k in range(island_count):
        if isl_area3d[k] <= 1e-12 or isl_area_uv[k] <= 0:
            continue
        cen = [isl_cent[k][d] / isl_area3d[k] for d in range(3)]
        g = regions.of(*cen) if regions else "all"
        groups.setdefault(g, []).append(math.sqrt(isl_area_uv[k] * px_scale / isl_area3d[k]))
    order = sorted(range(island_count), key=lambda k: -isl_tris[k])[:12]
    observed = {
        "atlasPx": atlas,
        "atlasSizeSource": "embedded PNG/JPEG header of the material's base-colour image" if atlas else "unavailable",
        "uvTrianglesOutsideUnitSquare": out_of_unit,
        "islandCount": island_count,
        "islandsLargestTwelve": [
            {"triangles": isl_tris[k], "areaM2": _r(isl_area3d[k], 5), "uvAreaShare": _r(isl_area_uv[k], 5),
             "uvBbox": [_r(v, 4) for v in isl_bbox[k]]}
            for k in order
        ],
        "islandTrianglesSummary": _summary(sorted(float(t) for t in isl_tris), 1.0, 1),
        "seams": {
            "seamEdges": seam_edges, "seamLengthM": _r(seam_len, 4),
            "seamLengthShare": _r(seam_len / total_len, 5) if total_len > 0 else None,
            "seamEdgeShare": _r(seam_edges / len(topo.edge_a), 5) if topo.edge_a else None,
            "definition": "welded-by-position edges whose two sides carry different UV coordinates (open mesh boundaries are not seams)",
        },
        "coverage": {
            "grid": f"{ATLAS_GRID}x{ATLAS_GRID}", "coveredPixelShare": _r(covered / (ATLAS_GRID * ATLAS_GRID), 5),
            "overlapFractionOfCovered": _r(overlapped / covered, 5) if covered else None,
            "overlappedPixels": overlapped,
            "sumOfUvTriangleAreaShare": _r(sum(isl_area_uv), 5),
            "meanLayersWhereCovered": _r(sum(isl_area_uv) / (covered / (ATLAS_GRID * ATLAS_GRID)), 4) if covered else None,
            "samplingNote": "pixel-centre point sampling with a fixed jitter; unbiased in aggregate, so small triangles are not rounded up to whole pixels",
        },
        "texelDensity": {
            "unit": unit,
            "perTriangle": _summary(tri_density, 1.0, 2),
            "perIslandByRegion": {g: dict(_summary(v, 1.0, 2) or {}, islands=len(v)) for g, v in sorted(groups.items())},
        },
    }
    inferred = {}
    if covered:
        inferred["atlasUse"] = {
            "packing": "dense" if covered / (ATLAS_GRID * ATLAS_GRID) >= 0.6 else ("moderate" if covered / (ATLAS_GRID * ATLAS_GRID) >= 0.3 else "sparse"),
            "hasUvOverlap": overlapped / covered > 0.01,
            "basis": f"coveredPixelShare={covered / (ATLAS_GRID * ATLAS_GRID):.3f} (>=0.6 dense, >=0.3 moderate); overlap share of covered pixels {overlapped / covered:.3f} (>0.01 = overlapping layout)",
        }
    return observed, inferred


def _atlas_groups(ctx: _Ctx, keys: dict[int, str]) -> dict[str, Any] | None:
    """Meshes that sample the same base-colour image, rasterised together so cross-mesh overlap shows."""
    groups: dict[int, list[_Mesh]] = {}
    for m in ctx.meshes:
        mat = m.material()
        if mat is None or mat["imageSource"] is None or m.uvs is None:
            continue
        groups.setdefault(mat["imageSource"], []).append(m)
    if not groups:
        return None
    out: dict[str, Any] = {}
    for image, members in groups.items():
        tri_uvs = []
        owners = []
        for oi, m in enumerate(members):
            uv = m.uvs
            for a, b, c in m.tris:
                ta, tb, tc = uv[a], uv[b], uv[c]
                tri_uvs.append((ta[0], ta[1], tb[0], tb[1], tc[0], tc[1]))
                owners.append(oi)
        counts, owner_of, overlap = _rasterise(tri_uvs, ATLAS_GRID, owners)
        per_mesh_px = [0] * len(members)
        for o in owner_of:
            if o >= 0:
                per_mesh_px[o] += 1
        covered = sum(1 for c in counts if c > 0)
        out[str(image)] = {
            "imageSource": image,
            "atlasPx": members[0].material()["atlasPx"],
            "meshCount": len(members),
            "unionCoveredPixelShare": _r(covered / (ATLAS_GRID ** 2), 5),
            "perMesh": [
                {"mesh": keys[id(m)], "firstClaimedPixelShare": _r(per_mesh_px[i] / (ATLAS_GRID ** 2), 5),
                 "selfOverlapPixels": overlap.get(i, [0, 0])[0], "overlapWithOtherMeshesPixels": overlap.get(i, [0, 0])[1]}
                for i, m in enumerate(members)
            ],
            "note": "pixel claimed by the first mesh rasterised; overlap counted when a later triangle hits an occupied pixel",
        }
    return out


# --------------------------------------------------------------------------------------------
# Section: skin weights and soft masks
# --------------------------------------------------------------------------------------------


def _joint_names(doc: dict[str, Any], skin_index: int | None) -> list[str]:
    if skin_index is None:
        return []
    skins = doc.get("skins") or []
    nodes = doc.get("nodes") or []
    if not 0 <= skin_index < len(skins):
        return []
    names = []
    for j in skins[skin_index].get("joints") or []:
        names.append(str(nodes[j].get("name", f"node-{j}")) if isinstance(j, int) and 0 <= j < len(nodes) else f"node-{j}")
    return names


def _weights_for(mesh: _Mesh, doc: dict[str, Any]) -> dict[str, Any] | None:
    sets = mesh.joint_sets()
    if not sets:
        return None
    names = _joint_names(doc, mesh.skin_index)
    n = mesh.vertex_count
    usage: dict[int, list[float]] = {}
    infl_hist: dict[int, int] = {}
    sum_err: list[float] = []
    zero_sum = 0
    for v in range(n):
        total = 0.0
        active = 0
        for joints, weights in sets:
            for slot in range(len(weights[v])):
                w = weights[v][slot]
                if w > 1e-6:
                    active += 1
                    total += w
                    rec = usage.setdefault(int(joints[v][slot]), [0, 0.0])
                    rec[0] += 1
                    rec[1] += w
        infl_hist[active] = infl_hist.get(active, 0) + 1
        sum_err.append(abs(total - 1.0))
        if total == 0.0:
            zero_sum += 1
    sum_err_sorted = sorted(sum_err)
    return {
        "mesh": mesh.name,
        "skinIndex": mesh.skin_index,
        "jointSets": len(sets),
        "jointsUsed": [
            {"joint": names[j] if 0 <= j < len(names) else f"joint-{j}", "jointIndex": j, "vertices": int(rec[0]), "weightMass": _r(rec[1], 3)}
            for j, rec in sorted(usage.items(), key=lambda kv: -kv[1][1])
        ],
        "influencesPerVertexHistogram": {str(k): v for k, v in sorted(infl_hist.items())},
        "maxInfluences": max(infl_hist) if infl_hist else 0,
        "weightSumError": {
            "max": _r(sum_err_sorted[-1], 8), "mean": _r(sum(sum_err) / n, 8), "p99": _r(_pct(sum_err_sorted, 99), 8),
            "verticesOver1e-3": sum(1 for e in sum_err if e > 1e-3), "zeroSumVertices": zero_sum,
        },
    }


def _weights_section(ctx: _Ctx, keys: dict[int, str]) -> dict[str, Any] | None:
    rows = []
    for m in ctx.meshes:
        r = _weights_for(m, ctx.doc)
        if r is not None:
            r["mesh"] = keys[id(m)]
            rows.append(r)
    skins = ctx.doc.get("skins") or []
    if not skins:
        ctx.limits.append("weights: the GLB has no skin, so bone usage, influence and weight-sum statistics do not exist")
        return None
    return {
        "skinCount": len(skins),
        "skins": [{"index": i, "joints": _joint_names(ctx.doc, i)} for i in range(len(skins))],
        "meshes": rows,
        "meshesWithoutJoints": [keys[id(m)] for m in ctx.meshes if not m.has_joints],
    }


def _mask_section(topo: _Topology, ctx: _Ctx, face_detail: list[_Mesh]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    mesh = topo.mesh
    masks = mesh.soft_masks()
    if not masks:
        ctx.limits.append("masks: the skin mesh carries no _SOFT_* attributes")
        return None, {}
    regions = ctx.regions
    assert regions is not None
    wp = topo.wpos
    nw = topo.nw
    H = ctx.height

    # welded per-vertex mask value (max over the raw copies) and consistency across copies
    wvals: dict[str, list[float]] = {}
    inconsistent: dict[str, int] = {}
    for name, vals in masks.items():
        w = [0.0] * nw
        lo = [math.inf] * nw
        for raw, wi in enumerate(topo.wid):
            v = vals[raw]
            if v > w[wi]:
                w[wi] = v
            if v < lo[wi]:
                lo[wi] = v
        inconsistent[name] = sum(1 for i in range(nw) if w[i] - lo[i] > 1e-4)
        wvals[name] = w

    # per-welded-vertex area share (1/3 of each incident triangle)
    varea = [0.0] * nw
    for fi, (a, b, c) in enumerate(topo.wtris):
        share = topo.tri_area[fi] / 3.0
        varea[a] += share
        varea[b] += share
        varea[c] += share

    # head and torso boxes from the skin vertices in each region
    head_pts = [p for p in wp if regions.of(*p) == "head"]
    torso_pts = [p for p in wp if regions.of(*p) == "torso"]
    head_bb = _bbox(head_pts)
    torso_bb = _bbox(torso_pts)

    def rel(point: Sequence[float], bb: tuple[list[float], list[float]] | None) -> list[float | None] | None:
        if bb is None:
            return None
        lo, hi = bb
        out = []
        for k in range(3):
            span = hi[k] - lo[k]
            out.append(_r((point[k] - (lo[k] + hi[k]) / 2.0) / span, 4) if span > 0 else None)
        return out

    per: dict[str, Any] = {}
    for name, w in wvals.items():
        mass = sum(w[i] * varea[i] for i in range(nw))
        nz = [i for i in range(nw) if w[i] > 0.0]
        support = 0.0
        for fi, (a, b, c) in enumerate(topo.wtris):
            k = (w[a] > 0) + (w[b] > 0) + (w[c] > 0)
            if k:
                support += topo.tri_area[fi] * k / 3.0
        if mass > 0:
            cen = [sum(wp[i][d] * w[i] * varea[i] for i in nz) / mass for d in range(3)]
        else:
            cen = None
        grads = []
        for ei in range(len(topo.edge_a)):
            a, b = topo.edge_a[ei], topo.edge_b[ei]
            if w[a] > 0 or w[b] > 0:
                ln = topo.edge_len[ei]
                if ln > 1e-9:
                    grads.append(abs(w[a] - w[b]) / ln)
        grads.sort()
        per[name] = {
            "nonzeroVertices": len(nz),
            "nonzeroShareOfBody": _r(len(nz) / nw, 5),
            "maxValue": _r(max(w), 5),
            "supportAreaM2": _r(support, 5),
            "weightedAreaM2": _r(mass, 5),
            "centroidM": None if cen is None else [_r(c) for c in cen],
            "centroidYFrac": None if cen is None else _r(ctx.frac(cen[1]), 4),
            "centroidXFrac": None if cen is None else _r(cen[0] / H, 4),
            "centroidRegion": None if cen is None else regions.of(*cen),
            "centroidHeadRelative": None if cen is None else rel(cen, head_bb),
            "centroidTorsoRelative": None if cen is None else rel(cen, torso_bb),
            "maxGradientPerM": _wide_summary(grads, 1.0, 3),
            "activeEdges": len(grads),
            "seamInconsistentVertices": inconsistent[name],
        }

    sums = [0.0] * nw
    active = [0] * nw
    for w in wvals.values():
        for i in range(nw):
            if w[i] > 0.0:
                sums[i] += w[i]
                active[i] += 1
    overlap_idx = [i for i in range(nw) if active[i] >= 2]
    max_sum = max(sums) if sums else 0.0
    sum_obs = {
        "maxSumOfMasksAtAnyVertex": _r(max_sum, 5),
        "verticesWithTwoOrMoreMasks": len(overlap_idx),
        "maxSumWhereMasksOverlap": _r(max((sums[i] for i in overlap_idx), default=0.0), 5),
        "verticesWhereSumExceeds1": sum(1 for s in sums if s > 1.0 + 1e-4),
        "verticesWithAnyMask": sum(1 for a in active if a),
    }

    # protected zeros: skin vertices around the face-detail meshes should carry no mask
    protected: dict[str, Any] | None = None
    if face_detail:
        fpts = [p for m in face_detail for p in m.positions]
        grid = _PointGrid(fpts, 0.01)
        radius = 0.008
        region_ids = [i for i, p in enumerate(wp) if grid.nearest(p, radius) is not None]
        zero = [i for i in region_ids if active[i] == 0]
        touched: dict[str, int] = {}
        for name, w in wvals.items():
            c = sum(1 for i in region_ids if w[i] > 0.0)
            if c:
                touched[name] = c
        protected = {
            "regionDefinition": f"skin vertices within {radius * 1000:.0f} mm of any vertex of the small head-band parts (face-detail guess)",
            "faceDetailMeshes": [m.name for m in face_detail],
            "regionVertices": len(region_ids),
            "allMasksZeroVertices": len(zero),
            "allMasksZeroShare": _r(len(zero) / len(region_ids), 4) if region_ids else None,
            "masksTouchingRegion": touched,
        }
    else:
        ctx.limits.append("masks: no face-detail parts were identified, so protected zeros around eyes/lips were not measured")

    observed = {
        "maskNames": sorted(masks),
        "weldingNote": "mask value per welded vertex = max over raw copies; copies differing by >1e-4 are counted per mask as seamInconsistentVertices",
        "relativeFrameDefinition": "centroidHeadRelative / centroidTorsoRelative = (centroid - box centre) / box size per axis, box = bbox of the skin vertices in that region; 0 is the box centre, +-0.5 its faces; x is character-left positive",
        "perMask": per,
        "sums": sum_obs,
        "protectedZeros": protected,
        "headBboxM": None if head_bb is None else {"min": [_r(v) for v in head_bb[0]], "max": [_r(v) for v in head_bb[1]]},
        "torsoBboxM": None if torso_bb is None else {"min": [_r(v) for v in torso_bb[0]], "max": [_r(v) for v in torso_bb[1]]},
    }
    inferred = {
        "normalisation": {
            "masksSumBelowOneWhereTheyOverlap": None if not overlap_idx else bool(sum_obs["maxSumWhereMasksOverlap"] <= 1.0 + 1e-4),
            "basis": f"maximum summed mask value at vertices where >=2 masks are non-zero is {sum_obs['maxSumWhereMasksOverlap']}; <=1 means overlapping regions share rather than stack weight",
        },
        "smoothness": {
            "worstMaxGradientPerM": _r(max((p["maxGradientPerM"]["max"] for p in per.values() if p["maxGradientPerM"]), default=None), 3) if per else None,
            "basis": "max |delta mask| / edge length over welded edges touching the mask support; a hard-edged mask would show a gradient of 1/edge_length",
        },
    }
    return observed, inferred


# --------------------------------------------------------------------------------------------
# Section: hair
# --------------------------------------------------------------------------------------------


def _jacobi_eigen(c: list[list[float]]) -> tuple[list[float], list[list[float]]]:
    """Eigenvalues and eigenvectors (columns) of a symmetric 3x3 matrix, cyclic Jacobi."""
    a = [row[:] for row in c]
    v = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    for _ in range(30):
        off = abs(a[0][1]) + abs(a[0][2]) + abs(a[1][2])
        if off < 1e-18:
            break
        for p, q in ((0, 1), (0, 2), (1, 2)):
            if abs(a[p][q]) < 1e-30:
                continue
            theta = (a[q][q] - a[p][p]) / (2.0 * a[p][q])
            t = (1.0 if theta >= 0 else -1.0) / (abs(theta) + math.sqrt(theta * theta + 1.0))
            cs = 1.0 / math.sqrt(t * t + 1.0)
            sn = t * cs
            for k in range(3):
                akp, akq = a[k][p], a[k][q]
                a[k][p] = cs * akp - sn * akq
                a[k][q] = sn * akp + cs * akq
            for k in range(3):
                apk, aqk = a[p][k], a[q][k]
                a[p][k] = cs * apk - sn * aqk
                a[q][k] = sn * apk + cs * aqk
            for k in range(3):
                vkp, vkq = v[k][p], v[k][q]
                v[k][p] = cs * vkp - sn * vkq
                v[k][q] = sn * vkp + cs * vkq
    return [a[0][0], a[1][1], a[2][2]], v


def _component_axes(points: Sequence[Sequence[float]]) -> tuple[list[float], list[list[float]], list[float]]:
    """Principal-axis extents (largest first), the axes themselves, and the centroid."""
    n = len(points)
    cx = sum(p[0] for p in points) / n
    cy = sum(p[1] for p in points) / n
    cz = sum(p[2] for p in points) / n
    cov = [[0.0] * 3 for _ in range(3)]
    for p in points:
        d = (p[0] - cx, p[1] - cy, p[2] - cz)
        for i in range(3):
            for j in range(i, 3):
                cov[i][j] += d[i] * d[j]
    for i in range(3):
        for j in range(i, 3):
            cov[i][j] /= n
            cov[j][i] = cov[i][j]
    values, vecs = _jacobi_eigen(cov)
    order = sorted(range(3), key=lambda k: -values[k])
    axes = [[vecs[r][k] for r in range(3)] for k in order]
    extents = []
    for ax in axes:
        proj = [(p[0] - cx) * ax[0] + (p[1] - cy) * ax[1] + (p[2] - cz) * ax[2] for p in points]
        extents.append(max(proj) - min(proj))
    return extents, axes, [cx, cy, cz]


def _hair_section(ctx: _Ctx, hair: _Mesh, topo: _Topology | None) -> tuple[dict[str, Any], dict[str, Any]]:
    regions = ctx.regions
    wid, wpos = _weld(hair.positions)
    nw = len(wpos)
    parent = list(range(nw))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    edge_count: dict[int, int] = {}
    tri_w = []
    for a, b, c in hair.tris:
        wa, wb, wc = wid[a], wid[b], wid[c]
        if wa == wb or wb == wc or wa == wc:
            continue
        tri_w.append((wa, wb, wc))
        for u, v in ((wa, wb), (wb, wc), (wc, wa)):
            lo, hi = (u, v) if u < v else (v, u)
            key = lo * nw + hi
            edge_count[key] = edge_count.get(key, 0) + 1
        ra, rb, rc = find(wa), find(wb), find(wc)
        if ra != rb:
            parent[rb] = ra
        rc, ra = find(wc), find(wa)
        if rc != ra:
            parent[rc] = ra
    comp_of_vertex = [find(i) for i in range(nw)]
    comps: dict[int, list[int]] = {}
    for i, r in enumerate(comp_of_vertex):
        comps.setdefault(r, []).append(i)
    comp_tris: dict[int, int] = {}
    comp_area: dict[int, float] = {}
    for wa, wb, wc in tri_w:
        r = comp_of_vertex[wa]
        comp_tris[r] = comp_tris.get(r, 0) + 1
        comp_area[r] = comp_area.get(r, 0.0) + _tri_area(wpos[wa], wpos[wb], wpos[wc])
    boundary_edges = sum(1 for c in edge_count.values() if c == 1)
    total_edges = len(edge_count)
    total_area = sum(comp_area.values())

    rows = []
    for r, ids in comps.items():
        if comp_tris.get(r, 0) == 0:
            continue
        pts = [wpos[i] for i in ids]
        if len(pts) < 3:
            continue
        ext, axes, cen = _component_axes(pts)
        rows.append({"root": r, "ids": ids, "tris": comp_tris[r], "area": comp_area[r], "L1": ext[0], "L2": ext[1], "L3": ext[2], "axes": axes, "centroid": cen})

    # classify every component, weighted by triangle count
    votes: dict[str, int] = {"tube": 0, "ribbon": 0, "card": 0, "shell": 0, "blob-or-other": 0}
    for row in rows:
        l1, l2, l3 = row["L1"], max(row["L2"], 1e-9), row["L3"]
        aspect = l1 / l2
        flat = l3 / l2
        if aspect >= 3.0 and flat >= 0.45:
            kind = "tube"
        elif flat < 0.25 and aspect >= 4.0 and row["tris"] >= 24:
            kind = "ribbon"
        elif flat < 0.25:
            kind = "card"
        elif row["area"] >= 0.6 * total_area and aspect < 3.0 and boundary_edges / max(total_edges, 1) < 0.02:
            kind = "shell"
        else:
            kind = "blob-or-other"
        row["kind"] = kind
        row["aspect"] = aspect
        row["flat"] = flat
        votes[kind] += row["tris"]
    total_votes = sum(votes.values()) or 1
    winner = max(votes, key=lambda k: votes[k]) if rows else None
    names = {"tube": "tube strands", "ribbon": "ribbon strips", "card": "cards", "shell": "solid shell", "blob-or-other": "thick clumps / unclassified"}

    # head geometry from the skin
    skin = ctx.skin
    scalp: dict[str, Any] | None = None
    roots_obs: dict[str, Any] | None = None
    head_notes: list[str] = []
    if skin is not None and regions is not None:
        head_pts = [p for p in skin.positions if regions.of(*p) == "head"]
        if head_pts:
            lo, hi = _bbox(head_pts)  # type: ignore[misc]
            centre = ((lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0, (lo[2] + hi[2]) / 2.0)
            skull = {}
            # equal-solid-angle bins: 24 azimuth x 6 sin(elevation) in the upper hemisphere
            def bin_of(p: Sequence[float]) -> tuple[int, int] | None:
                dx, dy, dz = p[0] - centre[0], p[1] - centre[1], p[2] - centre[2]
                r = math.sqrt(dx * dx + dy * dy + dz * dz)
                if r == 0 or dy < 0:
                    return None
                el = min(5, int(dy / r * 6))
                az = int(((math.atan2(dx, dz) + math.pi) / (2 * math.pi)) * 24) % 24
                return az, el

            for p in head_pts:
                k = bin_of(p)
                if k is not None:
                    skull.setdefault(k, []).append(math.dist(p, centre))
            skull_r = {k: _pct(sorted(v), 50) for k, v in skull.items() if len(v) >= 2}
            covered_bins = 0
            offsets: list[float] = []
            samples = list(hair.positions)
            for a, b, c in hair.tris[:: max(1, len(hair.tris) // 20000)]:
                pa, pb, pc = hair.positions[a], hair.positions[b], hair.positions[c]
                samples.append(((pa[0] + pb[0] + pc[0]) / 3.0, (pa[1] + pb[1] + pc[1]) / 3.0, (pa[2] + pb[2] + pc[2]) / 3.0))
            best: dict[tuple[int, int], float] = {}
            for p in samples:
                k = bin_of(p)
                if k is None or k not in skull_r:
                    continue
                rr = math.dist(p, centre)
                if rr >= 0.95 * skull_r[k] and rr <= skull_r[k] + 0.10:
                    cur = best.get(k)
                    if cur is None or rr < cur:
                        best[k] = rr
            for k, rr in best.items():
                covered_bins += 1
                offsets.append(rr - skull_r[k])
            scalp = {
                "headCentreM": [_r(v) for v in centre],
                "upperHemisphereBinsWithSkin": len(skull_r),
                "binsCoveredByHair": covered_bins,
                "coverageShare": _r(covered_bins / len(skull_r), 4) if skull_r else None,
                "hairLayerOffsetFromSkullMm": _summary(offsets, 1000.0, 2),
                "binning": "24 azimuth x 6 equal-solid-angle elevation bins above the head-box centre; a bin is covered when a hair vertex or triangle centroid lies 0.95x..skull radius+10 cm out along it",
            }
            # roots
            roots = []
            for row in rows:
                ax = row["axes"][0]
                ids = row["ids"]
                pts = [wpos[i] for i in ids]
                cen = row["centroid"]
                proj = [((p[0] - cen[0]) * ax[0] + (p[1] - cen[1]) * ax[1] + (p[2] - cen[2]) * ax[2]) for p in pts]
                pmin, pmax = min(proj), max(proj)
                if row["aspect"] >= 2.0 and (pmax - pmin) > 0:
                    near_lo = [p for p, s in zip(pts, proj) if s <= pmin + 0.08 * (pmax - pmin)]
                    near_hi = [p for p, s in zip(pts, proj) if s >= pmax - 0.08 * (pmax - pmin)]
                    clo = [sum(p[k] for p in near_lo) / len(near_lo) for k in range(3)]
                    chi = [sum(p[k] for p in near_hi) / len(near_hi) for k in range(3)]
                    root = clo if math.dist(clo, centre) <= math.dist(chi, centre) else chi
                else:
                    root = min(pts, key=lambda p: math.dist(p, centre))
                roots.append(root)
            if roots:
                els = []
                az_bins = set()
                off_skin = []
                for rt in roots:
                    dx, dy, dz = rt[0] - centre[0], rt[1] - centre[1], rt[2] - centre[2]
                    rr = math.sqrt(dx * dx + dy * dy + dz * dz) or 1e-9
                    els.append(math.degrees(math.asin(max(-1.0, min(1.0, dy / rr)))))
                    az_bins.add(int(((math.atan2(dx, dz) + math.pi) / (2 * math.pi)) * 12) % 12)
                    k = bin_of(rt)
                    if k is not None and k in skull_r:
                        off_skin.append(rr - skull_r[k])
                roots_obs = {
                    "rootCount": len(roots),
                    "rootElevationDeg": _summary(els, 1.0, 1),
                    "rootsAboveHeadCentreShare": _r(sum(1 for e in els if e >= 0.0) / len(els), 4),
                    "azimuthSectorsOf12WithARoot": len(az_bins),
                    "rootOffsetFromSkullMm": _summary(off_skin, 1000.0, 2),
                    "rootDefinition": "per component: the end of its principal axis nearer the head-box centre (mean of the end 8% of vertices); non-elongated components use their vertex nearest the head centre",
                    "rootsM": [[_r(c, 4) for c in rt] for rt in roots[:200]],
                    "rootsMTruncatedTo": 200 if len(roots) > 200 else None,
                }
        else:
            head_notes.append("the skin mesh has no vertices above the detected neck: scalp coverage and roots were not measured")
    else:
        head_notes.append("no skin mesh/regions: scalp coverage and roots were not measured")
    ctx.limits.extend(head_notes)

    lo, hi = _bbox(hair.positions) or ([0.0] * 3, [0.0] * 3)
    widths = sorted(r["L2"] for r in rows)
    thick = sorted(r["L3"] for r in rows)
    lens = sorted(r["L1"] for r in rows)
    observed = {
        "mesh": hair.name,
        "vertices": hair.vertex_count,
        "weldedVertices": nw,
        "triangles": len(hair.tris),
        "surfaceAreaM2": _r(total_area, 5),
        "bboxM": {"min": [_r(v) for v in lo], "max": [_r(v) for v in hi]},
        "bboxYFrac": [_r(ctx.frac(lo[1]), 4), _r(ctx.frac(hi[1]), 4)],
        "connectedComponents": len(rows),
        "componentTriangles": _summary([float(r["tris"]) for r in rows], 1.0, 1),
        "componentLengthMm": _summary(lens, 1000.0, 1),
        "componentWidthMm": _summary(widths, 1000.0, 1),
        "componentThicknessMm": _summary(thick, 1000.0, 1),
        "componentAspectLengthOverWidth": _summary(sorted(r["aspect"] for r in rows), 1.0, 2),
        "componentFlatnessThicknessOverWidth": _summary(sorted(r["flat"] for r in rows), 1.0, 3),
        "boundaryEdgeShare": _r(boundary_edges / total_edges, 4) if total_edges else None,
        "classVotesByTriangles": {k: _r(v / total_votes, 4) for k, v in votes.items()},
        "scalp": scalp,
        "roots": roots_obs,
    }
    med_width = _pct(widths, 50)
    clump_note = None
    if winner in ("tube", "ribbon", "card") and med_width is not None and med_width >= 0.015:
        clump_note = (
            f"median component width {med_width * 1000:.0f} mm: each component is a thick clump/lock, not an individual hair strand; "
            "the true strand count is not recoverable from this mesh"
        )
    inferred = {
        "hairType": None if winner is None else names[winner],
        "clumpNote": clump_note,
        "typeConfidenceShare": None if winner is None else _r(votes[winner] / total_votes, 3),
        "strandOrCardCountEstimate": len(rows),
        "meanWidthMm": _r(sum(widths) / len(widths) * 1000.0, 2) if widths else None,
        "meanThicknessMm": _r(sum(thick) / len(thick) * 1000.0, 2) if thick else None,
        "basis": (
            "each connected component (welded by position) is measured on its principal axes (length L1 >= width L2 >= thickness L3); "
            "tube = L1/L2>=3 and L3/L2>=0.45; ribbon = L3/L2<0.25, L1/L2>=4 and >=24 triangles; card = L3/L2<0.25 otherwise; "
            "shell = a dominant low-aspect closed component; the type is the class holding most triangles. Counts are components, so strands merged at the root count as one."
        ),
    }
    return observed, inferred


# --------------------------------------------------------------------------------------------
# analyze
# --------------------------------------------------------------------------------------------


def analyze(
    glb_path: str | Path,
    *,
    body_mesh: str | None = None,
    hair_mesh: str | None = None,
    figure_height: float | None = None,
    max_garment_samples: int = 8000,
    **_ignored: Any,
) -> dict[str, Any]:
    """Measure the construction of the GLB at `glb_path`. See the module docstring for the contract."""
    t_start = time.perf_counter()
    path = Path(glb_path)
    doc, binp, _info = glbref.parse_glb(path)
    rig = glbref.read_rig(path)
    world = glbref.rest_world_matrices(rig)
    meshes, skipped = _load_meshes(doc, binp, world)
    if not meshes:
        raise ValueError(f"{path}: no node references a mesh with triangle POSITION data; nothing to analyse")

    limits: list[str] = []
    height_source: str
    if figure_height is not None:
        if not figure_height > 0:
            raise ValueError("figure_height must be positive")
        height, height_source = float(figure_height), "caller-supplied"
    else:
        try:
            height, height_source = glbref.derive_figure_height(rig)
        except ValueError:
            bb_all = _bbox(p for m in meshes for p in m.positions)
            assert bb_all is not None
            height = bb_all[1][1] - bb_all[0][1]
            height_source = "loadedPositionsYExtent"
            if not height > 0:
                raise ValueError(f"{path}: figure height measured as zero; pass figure_height explicitly")
    ymin = min(p[1] for m in meshes for p in m.positions)
    ymax = max(p[1] for m in meshes for p in m.positions)

    skin, body_basis = _pick_body(meshes, body_mesh)
    if skipped:
        limits.append("skipped nodes: " + "; ".join(skipped))
    ctx = _Ctx(doc, binp, meshes, skin, height, ymin, ymax)
    ctx.limits = limits
    keys = _unique_keys(meshes)
    if not doc.get("skins"):
        limits.append("the GLB has no skin: skeleton-dependent facts (bone usage, rest-pose joints) are absent")

    observed: dict[str, Any] = {}
    inferred: dict[str, Any] = {}

    def lap(name: str, t0: float) -> None:
        ctx.timings[name] = round(time.perf_counter() - t0, 3)

    topo: _Topology | None = None
    if skin is not None and skin.tris:
        t0 = time.perf_counter()
        ctx.regions = _Regions(ymin, height, skin)
        topo = _Topology(skin)
        lap("topology", t0)
        t0 = time.perf_counter()
        # ~4 median edges per cell: measured fastest for clearance queries 0.5-60 mm from the skin
        med_edge = _pct(sorted(topo.edge_len), 50) or 0.005
        ctx.skin_grid = _TriGrid(skin.positions, skin.tris, max(4.0 * med_edge, 0.008))
        lap("skinGrid", t0)
    elif skin is not None:
        limits.append(f"body mesh {skin.name!r} has no triangles: every skin-relative section was skipped")

    t0 = time.perf_counter()
    parts, roles, layering_obs, layering_inf, clearance, features = _parts_section(ctx, keys, max_garment_samples, hair_mesh)
    lap("partsAndClearance", t0)
    observed["parts"] = parts
    observed["layering"] = layering_obs or None
    observed["garmentClearance"] = clearance or None
    inferred["roles"] = roles or None
    inferred["layering"] = layering_inf or None
    inferred["roles_note"] = "geometry-only guesses; inventory uses name/geometry heuristics too, not authoritative artist labels"

    if topo is not None:
        t0 = time.perf_counter()
        topo_obs, topo_inf = _topology_section(topo, ctx)
        lap("densityTopology", t0)
        observed["densityTopology"] = topo_obs
        inferred["densityTopology"] = topo_inf

        t0 = time.perf_counter()
        sym_obs, sym_inf = _symmetry_section(topo, ctx)
        lap("symmetry", t0)
        observed["symmetry"] = sym_obs
        inferred["symmetry"] = sym_inf

        t0 = time.perf_counter()
        uv_obs, uv_inf = _uv_section(topo, ctx)
        lap("uvAtlas", t0)
        observed["uvAtlas"] = uv_obs
        if uv_obs is not None:
            t0 = time.perf_counter()
            uv_obs["atlasGroups"] = _atlas_groups(ctx, keys)
            lap("atlasGroups", t0)
        inferred["uvAtlas"] = uv_inf

        face_detail = [m for m in meshes if roles.get(keys[id(m)], {}).get("role") == "face-detail"]
        t0 = time.perf_counter()
        mask_obs, mask_inf = _mask_section(topo, ctx, face_detail)
        lap("masks", t0)
        observed["masks"] = mask_obs
        inferred["masks"] = mask_inf
    else:
        for key in ("densityTopology", "symmetry", "uvAtlas", "masks"):
            observed[key] = None
            inferred[key] = None

    t0 = time.perf_counter()
    observed["weights"] = _weights_section(ctx, keys)
    lap("weights", t0)

    hair = None
    if hair_mesh is not None:
        hair = next((m for m in meshes if m.name == hair_mesh or m.node_name == hair_mesh), None)
        if hair is None:
            raise ValueError(f"hair_mesh {hair_mesh!r} matches no mesh or node name")
    else:
        hair = next((m for m in meshes if roles.get(keys[id(m)], {}).get("role") == "hair"), None)
    if hair is not None and hair.tris:
        t0 = time.perf_counter()
        h_obs, h_inf = _hair_section(ctx, hair, topo)
        lap("hair", t0)
        observed["hair"] = h_obs
        inferred["hair"] = h_inf
    else:
        observed["hair"] = None
        inferred["hair"] = None
        limits.append("hair: no mesh was recognised as hair from geometry (pass hair_mesh= to force one)")

    limits.extend([
        "all roles are geometry-only guesses; names, materials and node hierarchy are not used except for the body-mesh ranking and atlas lookup",
        "garment clearance uses stored bind-pose skin positions (static meshes use rest-world transforms); no skin animation was evaluated, so this is not a runtime clearance result",
        "clearance is measured from the garment vertices to the skin only; garment-over-garment offsets are reported as contacts, not distances",
        "density regions (head/torso/arm/leg) come from silhouette heuristics on the skin mesh, not from the skeleton; the upper arm near the shoulder falls into 'torso'",
        "valence and exact-midpoint statistics describe exported connectivity only; they do not identify subdivision, smoothing, projection or the original control cage",
        "UV coverage uses a 256x256 point-sampled raster; overlap below that resolution (sub-pixel overlap) is not detected",
        "texture CONTENT (paint, skin tones, makeup) is not analysed: only UV layout and the image size are",
        "no animation was evaluated: weights and masks are read at the bind pose",
    ])

    return {
        "schema": SCHEMA,
        "source": {
            "path": str(path),
            "heightM": _r(height, 6),
            "heightSource": height_source,
            "yMinM": _r(ymin, 6),
            "yMaxM": _r(ymax, 6),
            "meshInstances": len(meshes),
            "bodyMesh": None if skin is None else {"name": skin.name, "node": skin.node_name, "vertices": skin.vertex_count, "triangles": len(skin.tris), **body_basis},
        },
        "regions": ctx.regions.to_dict() if ctx.regions else None,
        "observed": observed,
        "inferred": inferred,
        "limits": limits,
        "diagnostics": {"timingsS": dict(ctx.timings), "totalS": round(time.perf_counter() - t_start, 3), "python": sys.version.split()[0]},
    }


def main(argv: list[str]) -> int:  # pragma: no cover - thin convenience wrapper
    import json

    if len(argv) < 2:
        print("usage: construction.py GLB [--body-mesh NAME]", file=sys.stderr)
        return 2
    body = argv[argv.index("--body-mesh") + 1] if "--body-mesh" in argv else None
    result = analyze(argv[1], body_mesh=body)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
