#!/usr/bin/env python3
"""Tests for tools/character_prior/anatomy.py: proportions, silhouette, face layout and atlas mapping.

Every GLB here is synthesised in-process with the stdlib: a boxy figure (legs, pelvis, waist, chest
with a bust, shoulders, neck, head with a nose) built from coarse grids -- deliberately coarse, like a
real limb mesh, so the silhouette bands only work because the module densifies triangle edges -- plus
an eye/brow detail mesh, a hair mesh and a 4-quadrant PNG atlas whose filters cycle through all five
PNG row filters. Expected heights are the box dimensions chosen below, so each assertion compares the
module against a number written down here, not against its own output.

Counter-examples:
  * no skin                       -> still measured, flagged as unskinned, rest pose not evaluated
  * empty mesh / no mesh          -> ValueError
  * mirrored vs asymmetric head   -> very different symmetry error
  * no face-detail meshes         -> eye line, mouth and brow are absent, with reasons in `limits`
  * decoy mesh with more vertices -> the skinned, mask-carrying mesh still wins body autodetection
  * A-pose / T-pose / no arms     -> three different pose classes
  * 16-bit PNG                    -> reported as undecodable, never decoded wrongly

One test reads the real delivered character (path from IMG2_NAMI_GLB) and is skipped when absent.

Pure Python 3.10+ stdlib.
"""

from __future__ import annotations

import json
import math
import os
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from typing import Any, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from character_prior import anatomy  # noqa: E402

REAL_GLB = Path(
    os.environ.get("IMG2_NAMI_GLB") or Path.home() / ".img2/jobs/nami-sketchfab-8e496e5a/native/export/character.glb"
)

GLB_MAGIC = b"glTF"
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942

SKIN_RGB = (240, 200, 170)  # top-left quadrant: the face
BODY_RGB = (30, 60, 200)  # bottom-right quadrant: the body
OTHER_RGB = ((10, 10, 10), (90, 160, 90))  # top-right, bottom-left

# Geometry of the synthetic figure (metres). H is the hair top, the floor is the leg bottoms at y = 0.
HAIR_TOP = 1.78
HEAD_TOP = 1.74
CHIN_Y = 1.52
EYE_Y = 1.64
CROTCH_Y = 0.80
PELVIS = (0.80, 0.95)
WAIST = (0.95, 1.15)
HEAD_WIDTH = 0.18
NOSE_FRONT_Z = 0.125


# ---------------------------------------------------------------------------------------------
# PNG writer (all five row filters) and GLB writer
# ---------------------------------------------------------------------------------------------


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def _filter_row(ftype: int, row: bytes, prev: bytes, bpp: int) -> bytes:
    out = bytearray(len(row))
    for i, value in enumerate(row):
        left = row[i - bpp] if i >= bpp else 0
        up = prev[i]
        up_left = prev[i - bpp] if i >= bpp else 0
        if ftype == 0:
            predictor = 0
        elif ftype == 1:
            predictor = left
        elif ftype == 2:
            predictor = up
        elif ftype == 3:
            predictor = (left + up) >> 1
        else:
            predictor = _paeth(left, up, up_left)
        out[i] = (value - predictor) & 255
    return bytes(out)


def _png(width: int, height: int, rows: Sequence[bytes], color_type: int = 2, depth: int = 8,
         filters: Sequence[int] = (1, 2, 3, 4, 0)) -> bytes:
    channels = 3 if color_type == 2 else 4
    bpp = channels * (depth // 8)
    raw = bytearray()
    prev = bytes(len(rows[0]))
    for y, row in enumerate(rows):
        ftype = filters[y % len(filters)]
        raw.append(ftype)
        raw.extend(_filter_row(ftype, row, prev, bpp))
        prev = row

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, depth, color_type, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw)))
        + chunk(b"IEND", b"")
    )


def _quadrant_atlas(width: int = 32, height: int = 16) -> bytes:
    """Four colour quadrants: TL face skin, TR dark, BL green, BR body blue."""
    rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            top, left = y < height // 2, x < width // 2
            colour = SKIN_RGB if top and left else (OTHER_RGB[0] if top else (OTHER_RGB[1] if left else BODY_RGB))
            row.extend(colour)
        rows.append(bytes(row))
    return _png(width, height, rows)


class _Bin:
    def __init__(self) -> None:
        self.data = bytearray()
        self.views: list[dict[str, Any]] = []
        self.accessors: list[dict[str, Any]] = []

    def view(self, payload: bytes) -> int:
        while len(self.data) % 4:
            self.data.append(0)
        self.views.append({"buffer": 0, "byteOffset": len(self.data), "byteLength": len(payload)})
        self.data.extend(payload)
        return len(self.views) - 1

    def accessor(self, payload: bytes, ctype: int, atype: str, count: int, **extra: Any) -> int:
        entry = {"bufferView": self.view(payload), "componentType": ctype, "count": count, "type": atype}
        entry.update(extra)
        self.accessors.append(entry)
        return len(self.accessors) - 1


def _box(centre: Sequence[float], size: Sequence[float], uv_box: Sequence[float], step: float = 0.03):
    """A box surface as separate face grids: (vertices, uvs, triangles)."""
    verts: list[tuple[float, float, float]] = []
    uvs: list[tuple[float, float]] = []
    tris: list[tuple[int, int, int]] = []
    for axis in range(3):
        a1, a2 = [i for i in range(3) if i != axis]
        n1 = max(1, round(size[a1] / step))
        n2 = max(1, round(size[a2] / step))
        for sign in (-1, 1):
            base = len(verts)
            for i in range(n1 + 1):
                for j in range(n2 + 1):
                    p = [0.0, 0.0, 0.0]
                    p[axis] = centre[axis] + sign * size[axis] / 2
                    p[a1] = centre[a1] - size[a1] / 2 + size[a1] * i / n1
                    p[a2] = centre[a2] - size[a2] / 2 + size[a2] * j / n2
                    verts.append((p[0], p[1], p[2]))
                    uvs.append((uv_box[0] + (uv_box[2] - uv_box[0]) * i / n1, uv_box[1] + (uv_box[3] - uv_box[1]) * j / n2))
            for i in range(n1):
                for j in range(n2):
                    a = base + i * (n2 + 1) + j
                    b, c = a + 1, a + n2 + 1
                    tris += [(a, b, c), (b, c + 1, c)]
    return verts, uvs, tris


def _merge(*meshes):
    verts, uvs, tris = [], [], []
    for v, u, t in meshes:
        base = len(verts)
        verts += v
        uvs += u
        tris += [(a + base, b + base, c + base) for a, b, c in t]
    return verts, uvs, tris


FACE_UV = (0.05, 0.05, 0.40, 0.40)
BODY_UV = (0.60, 0.60, 0.95, 0.95)
DARK_UV = (0.60, 0.05, 0.95, 0.40)


def _rotate_arm(mesh, pivot: tuple[float, float], theta_deg: float, mirror: bool):
    """Rotate a horizontal arm about `pivot` (x, y) so it points `theta_deg` from straight down."""
    verts, uvs, tris = mesh
    phi = math.radians(theta_deg - 90.0)
    c, s = math.cos(phi), math.sin(phi)
    out = []
    for x, y, z in verts:
        vx, vy = x - pivot[0], y - pivot[1]
        rx, ry = vx * c - vy * s + pivot[0], vx * s + vy * c + pivot[1]
        out.append((-rx if mirror else rx, ry, z))
    return out, uvs, tris


def _humanoid(*, arms: str | None = "T", arm_angle: float = 90.0, eyes: bool = True, hair: bool = True,
              asym_head: bool = False, decoy: bool = False) -> list[dict[str, Any]]:
    """Parts of the synthetic figure. `arms` is "T"/"A" (angle from `arm_angle`) or None for no arms."""
    legs = [_box((sx * 0.10, 0.40, 0.0), (0.12, 0.80, 0.12), BODY_UV) for sx in (-1, 1)]
    torso = [
        _box((0.0, 0.875, 0.0), (0.34, 0.15, 0.16), BODY_UV),  # pelvis, widest
        _box((0.0, 1.05, 0.0), (0.24, 0.20, 0.12), BODY_UV),  # waist, narrowest
        _box((0.0, 1.25, 0.0), (0.32, 0.20, 0.14), BODY_UV),  # chest
        _box((0.0, 1.26, 0.09), (0.20, 0.08, 0.06), BODY_UV),  # bust: front z 0.12
        _box((0.0, 1.40, 0.0), (0.40, 0.10, 0.14), BODY_UV),  # shoulders
        _box((0.0, 1.48, 0.0), (0.08, 0.06, 0.08), BODY_UV),  # neck, top 1.51: a hair's breadth under the chin
    ]
    head = _box((0.0, (CHIN_Y + HEAD_TOP) / 2, 0.0), (HEAD_WIDTH, HEAD_TOP - CHIN_Y, 0.20), FACE_UV)
    if asym_head:
        # push the x > 0 half of the head forward: a deliberately asymmetric skull
        head = (
            [(x, y, z + 0.02) if x > 0.02 else (x, y, z) for x, y, z in head[0]],
            head[1],
            head[2],
        )
    nose = _box((0.0, 1.60, 0.11), (0.02, 0.03, 0.03), FACE_UV, step=0.01)
    pieces = legs + torso + [head, nose]
    if arms:
        for mirror in (False, True):
            arm = _box((0.2 + 0.275, 1.40, 0.0), (0.55, 0.08, 0.08), BODY_UV)
            pieces.append(_rotate_arm(arm, (0.2, 1.40), arm_angle, mirror))
    body = _merge(*pieces)
    parts: list[dict[str, Any]] = [
        {"name": "Cube.020", "node": "Body", "mesh": body, "material": 0, "soft": ["_SOFT_CHEST_LEFT", "_SOFT_CHEST_RIGHT"],
         "skinned": True}
    ]
    if eyes:
        eye_boxes = [_box((sx * 0.045, EYE_Y, 0.097), (0.03, 0.012, 0.01), DARK_UV, step=0.01) for sx in (-1, 1)]
        brow_boxes = [_box((sx * 0.045, 1.67, 0.097), (0.034, 0.006, 0.01), DARK_UV, step=0.01) for sx in (-1, 1)]
        parts.append({"name": "Cube.021", "node": "Eyes", "mesh": _merge(*eye_boxes), "material": 1, "skinned": True})
        parts.append({"name": "Cube.023", "node": "Brows", "mesh": _merge(*brow_boxes), "material": 1, "skinned": True})
    if hair:
        parts.append({"name": "NurbsPath.002", "node": "Hair",
                      "mesh": _box((0.0, 1.63, 0.0), (0.28, 0.30, 0.30), DARK_UV), "material": 1, "skinned": True})
    if decoy:
        parts.append({"name": "Decoy", "node": "Decoy", "mesh": _box((0.6, 0.3, 0.0), (0.1, 0.1, 0.1), DARK_UV, step=0.003),
                      "material": 1, "skinned": False})
    return parts


def _build_glb(path: Path, parts: Sequence[dict[str, Any]], *, skin: bool = True, png: bytes | None = None,
               empty: bool = False) -> Path:
    bin_ = _Bin()
    meshes: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = [{"name": "Root"}, {"name": "Rig", "children": [0]}]
    for part in parts:
        verts, uvs, tris = part["mesh"]
        attributes: dict[str, int] = {}
        if empty:
            attributes["POSITION"] = len(bin_.accessors)
            bin_.accessors.append({"componentType": 5126, "count": 0, "type": "VEC3"})
            meshes.append({"name": part["name"], "primitives": [{"attributes": attributes}]})
        else:
            lo = [min(v[k] for v in verts) for k in range(3)]
            hi = [max(v[k] for v in verts) for k in range(3)]
            attributes["POSITION"] = bin_.accessor(
                b"".join(struct.pack("<3f", *v) for v in verts), 5126, "VEC3", len(verts), min=lo, max=hi
            )
            attributes["TEXCOORD_0"] = bin_.accessor(
                b"".join(struct.pack("<2f", *u) for u in uvs), 5126, "VEC2", len(uvs)
            )
            if skin and part.get("skinned"):
                attributes["JOINTS_0"] = bin_.accessor(struct.pack("<4H", 0, 0, 0, 0) * len(verts), 5123, "VEC4", len(verts))
                attributes["WEIGHTS_0"] = bin_.accessor(struct.pack("<4f", 1, 0, 0, 0) * len(verts), 5126, "VEC4", len(verts))
            for soft in part.get("soft", []):
                attributes[soft] = bin_.accessor(struct.pack("<f", 0.5) * len(verts), 5126, "SCALAR", len(verts))
            indices = bin_.accessor(
                b"".join(struct.pack("<3I", *t) for t in tris), 5125, "SCALAR", 3 * len(tris)
            )
            meshes.append({"name": part["name"],
                           "primitives": [{"attributes": attributes, "indices": indices, "material": part["material"]}]})
        node: dict[str, Any] = {"name": part["node"], "mesh": len(meshes) - 1}
        if skin and part.get("skinned"):
            node["skin"] = 0
        nodes.append(node)
        nodes[1]["children"].append(len(nodes) - 1)
    document: dict[str, Any] = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [1]}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": [
            {"name": "skin", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "metallicFactor": 0, "roughnessFactor": 0.5}},
            {"name": "unlit", "extensions": {"KHR_materials_unlit": {}},
             "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "metallicFactor": 0}},
        ],
    }
    if skin:
        ibm = bin_.accessor(struct.pack("<16f", 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1), 5126, "MAT4", 1)
        document["skins"] = [{"joints": [0], "inverseBindMatrices": ibm}]
    if png is not None:
        document["images"] = [{"bufferView": bin_.view(png), "mimeType": "image/png"}]
        document["textures"] = [{"source": 0}]
    document["accessors"] = bin_.accessors
    document["bufferViews"] = bin_.views
    document["buffers"] = [{"byteLength": len(bin_.data)}]

    json_bytes = json.dumps(document).encode("utf-8")
    json_bytes += b" " * (-len(json_bytes) % 4)
    bin_bytes = bytes(bin_.data) + b"\x00" * (-len(bin_.data) % 4)
    total = 12 + 8 + len(json_bytes) + 8 + len(bin_bytes)
    blob = (
        struct.pack("<4sII", GLB_MAGIC, 2, total)
        + struct.pack("<II", len(json_bytes), JSON_CHUNK) + json_bytes
        + struct.pack("<II", len(bin_bytes), BIN_CHUNK) + bin_bytes
    )
    path.write_bytes(blob)
    return path


def _band_index(result: dict[str, Any], y: float) -> int:
    return int(y / result["figure"]["heightM"] * result["silhouette"]["bandCount"])



class _Workdir(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def analyze(self, parts, name: str = "fig.glb", png: bytes | None = None, **kwargs: Any) -> dict[str, Any]:
        build_keys = {k: kwargs.pop(k) for k in ("skin", "empty") if k in kwargs}
        glb = _build_glb(self.dir / name, parts, png=png if png is not None else _quadrant_atlas(), **build_keys)
        return anatomy.analyze(glb, **kwargs)


# ---------------------------------------------------------------------------------------------
# PNG decoding
# ---------------------------------------------------------------------------------------------


class PngDecodeTests(unittest.TestCase):
    def _rows(self, width: int, height: int, channels: int) -> list[bytes]:
        return [bytes((x * 7 + y * 13 + c * 29 + (x * y) % 11) & 255 for x in range(width) for c in range(channels))
                for y in range(height)]

    def test_all_five_filters_round_trip_rgb_and_rgba(self) -> None:
        for ctype, channels in ((2, 3), (6, 4)):
            rows = self._rows(23, 10, channels)
            png = anatomy._decode_png(_png(23, 10, rows, color_type=ctype))
            self.assertEqual(png.rows, rows, f"colour type {ctype}")
            self.assertEqual((png.width, png.height, png.channels), (23, 10, channels))

    def test_each_filter_alone_round_trips(self) -> None:
        rows = self._rows(17, 6, 3)
        for ftype in range(5):
            decoded = anatomy._decode_png(_png(17, 6, rows, filters=(ftype,)))
            self.assertEqual(decoded.rows, rows, f"filter {ftype}")

    def test_cropped_decode_equals_top_left_of_full_decode(self) -> None:
        rows = self._rows(40, 20, 3)
        data = _png(40, 20, rows)
        crop = anatomy._decode_png(data, max_rows=9, max_cols=13)
        self.assertEqual(len(crop.rows), 9)
        self.assertEqual(crop.cols, 13)
        for y in range(9):
            self.assertEqual(crop.rows[y], rows[y][: 13 * 3])

    def test_unsupported_images_raise_instead_of_decoding_wrongly(self) -> None:
        sixteen = _png(4, 2, [bytes(4 * 6)] * 2, depth=16)
        with self.assertRaises(ValueError):
            anatomy._decode_png(sixteen)
        with self.assertRaises(ValueError):
            anatomy._decode_png(b"not a png at all")
        interlaced = bytearray(_png(4, 2, [bytes(12)] * 2))
        # IHDR payload starts at byte 16: width(4) height(4) depth colour compression filter interlace
        interlaced[16 + 12] = 1
        with self.assertRaises(ValueError):
            anatomy._decode_png(bytes(interlaced))


class ColourTests(unittest.TestCase):
    def test_lstar_of_black_white_and_mid_grey(self) -> None:
        self.assertAlmostEqual(anatomy._lstar(0, 0, 0), 0.0, places=6)
        self.assertAlmostEqual(anatomy._lstar(255, 255, 255), 100.0, places=3)
        # sRGB 119 is 18.4% linear luminance: L* ~ 50.
        self.assertAlmostEqual(anatomy._lstar(119, 119, 119), 50.0, delta=0.5)

    def test_palette_is_deterministic_and_fractions_are_real_cluster_sizes(self) -> None:
        colours = [SKIN_RGB] * 70 + [BODY_RGB] * 30
        first = anatomy._palette(colours, 5)
        self.assertEqual(first, anatomy._palette(list(reversed(colours)), 5))
        self.assertEqual(first[0]["hex"], "#f0c8aa")
        self.assertAlmostEqual(first[0]["fraction"], 0.7, places=6)
        self.assertAlmostEqual(sum(p["fraction"] for p in first), 1.0, places=6)
        self.assertEqual(anatomy._palette([], 5), [])


class GeometryHelperTests(unittest.TestCase):
    def test_texel_density_of_a_known_quad(self) -> None:
        points = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
        uvs = [(0, 0), (0.5, 0), (0.5, 0.5), (0, 0.5)]
        tris = [(0, 1, 2), (0, 2, 3)]
        out = anatomy._texel_density(tris, points, uvs, (64, 32), lambda j: True, 1.0)
        # 1 m^2 of surface covers 0.25 of a 64 x 32 atlas = 512 texels^2 -> sqrt(512) texels per metre.
        self.assertAlmostEqual(out["texelsPerMetre"], math.sqrt(512.0), places=6)
        self.assertAlmostEqual(out["surfaceAreaM2"], 1.0, places=9)
        self.assertIsNone(anatomy._texel_density(tris, points, uvs, (64, 32), lambda j: False, 1.0))

    def test_mirror_error_separates_symmetric_from_asymmetric_points(self) -> None:
        sym = [(x, y, 0.1 * y) for x in (-0.05, -0.02, 0.02, 0.05) for y in (0.0, 0.01, 0.02)]
        shifted = [(x, y, z + (0.03 if x > 0 else 0.0)) for x, y, z in sym]
        a = anatomy._mirror_error(sym, 0.0, 0.004)
        b = anatomy._mirror_error(shifted, 0.0, 0.004)
        self.assertLess(a["meanErrM"], 1e-9)
        self.assertEqual(a["matchedFraction"], 1.0)
        self.assertAlmostEqual(b["meanErrM"], 0.004, places=9)  # every point unmatched: capped at one cell
        self.assertEqual(b["matchedFraction"], 0.0)
        self.assertIsNone(anatomy._mirror_error([], 0.0, 0.004))

    def test_uv_clusters_split_scattered_uvs(self) -> None:
        uvs = [(0.10 + 0.001 * i, 0.10) for i in range(5)] + [(0.90, 0.80 + 0.001 * i) for i in range(3)]
        clusters = anatomy._uv_clusters(uvs, (100, 100))
        self.assertEqual([c["vertexCount"] for c in clusters], [5, 3])
        self.assertLess(clusters[0]["uvAreaFraction"], 1e-3)


# ---------------------------------------------------------------------------------------------
# Whole-figure measurements on the synthetic T-pose figure
# ---------------------------------------------------------------------------------------------


class SyntheticFigureTests(_Workdir):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp_cls = tempfile.TemporaryDirectory()
        glb = _build_glb(Path(cls._tmp_cls.name) / "t.glb", _humanoid(), png=_quadrant_atlas())
        cls.result = anatomy.analyze(glb)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp_cls.cleanup()

    def test_contract_keys_json_and_basis_on_every_inferred_landmark(self) -> None:
        r = self.result
        for key in ("schema", "observed", "inferred", "limits"):
            self.assertIn(key, r)
        self.assertEqual(r["schema"], anatomy.SCHEMA)
        self.assertTrue(all(isinstance(item, str) for item in r["limits"]))
        json.dumps(r, allow_nan=False)  # strict JSON: no NaN/Infinity, no tuples needed
        for name, entry in r["inferred"]["landmarks"].items():
            if entry is not None:
                self.assertTrue(entry["basis"], name)
                self.assertIn(entry["confidence"], ("high", "medium", "low"), name)
        self.assertEqual(r["observed"]["figure"]["heightSource"], "meshWorldBoundsYExtent")

    def test_figure_height_floor_and_body_detection(self) -> None:
        o = self.result["observed"]
        self.assertAlmostEqual(o["figure"]["heightM"], HAIR_TOP, places=5)
        self.assertAlmostEqual(o["figure"]["floorY"], 0.0, places=6)
        self.assertEqual(o["bodyMesh"]["meshName"], "Cube.020")
        self.assertEqual(o["bodyMesh"]["nodeName"], "Body")
        self.assertTrue(o["bodyMesh"]["skinned"])
        self.assertEqual(o["bodyMesh"]["softAttributes"], ["_SOFT_CHEST_LEFT", "_SOFT_CHEST_RIGHT"])
        self.assertTrue(o["restPose"]["restPoseEqualsBindPose"])
        self.assertEqual(o["restPose"]["jointCount"], 1)

    def test_t_pose_is_detected_and_arm_span_measured(self) -> None:
        pose = self.result["inferred"]["pose"]
        self.assertEqual(pose["class"], "T-pose")
        self.assertGreaterEqual(pose["armAngleFromVerticalDeg"], 75.0)
        span = self.result["observed"]["armSpan"]
        self.assertAlmostEqual(span["spanM"], 1.5, places=3)
        self.assertAlmostEqual(span["spanOverH"], 1.5 / HAIR_TOP, places=3)

    def test_landmark_heights(self) -> None:
        lm = self.result["inferred"]["landmarks"]
        h = HAIR_TOP
        band = 1.0 / 100 * h
        self.assertAlmostEqual(lm["chin"]["yM"], CHIN_Y, delta=0.005)
        self.assertAlmostEqual(lm["headTopSkin"]["yM"], HEAD_TOP, delta=1e-5)
        self.assertAlmostEqual(lm["headTopWithHair"]["yM"], HAIR_TOP, delta=1e-5)
        self.assertAlmostEqual(lm["crotch"]["yM"], CROTCH_Y, delta=1.5 * band)
        self.assertTrue(1.44 <= lm["neck"]["yM"] <= 1.53, lm["neck"])
        self.assertTrue(PELVIS[0] - band <= lm["hips"]["yM"] <= PELVIS[1] + band, lm["hips"])
        self.assertTrue(WAIST[0] <= lm["waist"]["yM"] <= WAIST[1], lm["waist"])
        self.assertTrue(1.20 <= lm["chest"]["yM"] <= 1.32, lm["chest"])
        self.assertAlmostEqual(lm["chin"]["yFrac"], CHIN_Y / h, places=2)

    def test_torso_widths_at_hips_and_waist(self) -> None:
        ex = self.result["observed"]["extrema"]
        self.assertAlmostEqual(ex["hipsMaxWidth"]["widthM"], 0.34, delta=0.01)
        self.assertAlmostEqual(ex["waistMinWidth"]["widthM"], 0.24, delta=0.01)
        self.assertAlmostEqual(self.result["observed"]["torsoWidthRatios"]["waistOverHips"], 0.24 / 0.34, delta=0.03)

    def test_proportions_heads_tall_and_segments_sum_to_one(self) -> None:
        pr = self.result["inferred"]["proportions"]
        self.assertAlmostEqual(pr["headsTall"], HAIR_TOP / (HEAD_TOP - CHIN_Y), delta=0.03)
        self.assertGreater(pr["headsTallWithHair"], 0)
        fracs = pr["segmentsFracOfH"]
        self.assertAlmostEqual(sum(fracs.values()), 1.0, places=5)
        self.assertAlmostEqual(pr["legToTorsoToHead"][2], 1.0)
        self.assertGreater(pr["legToTorsoToHead"][0], pr["legToTorsoToHead"][1] * 0.5)

    def test_t_pose_arms_are_excluded_from_the_torso_series(self) -> None:
        s = self.result["silhouette"]
        trimmed = [i for i, flag in enumerate(s["armTrimmed"]) if flag]
        self.assertTrue(trimmed, "the T-pose arm bands must be trimmed")
        for i in trimmed:
            self.assertLess(s["torsoWidth"][i], 0.5, f"band {i}")
            self.assertAlmostEqual(s["width"][i], 1.5, delta=0.02, msg=f"band {i}: full silhouette keeps the arms")
            self.assertTrue(s["armsMerged"][i])

    def test_silhouette_arrays_cover_the_requested_bands(self) -> None:
        s = self.result["silhouette"]
        n = s["bandCount"]
        self.assertEqual(n, 100)
        for key in ("yFracCentre", "vertexCount", "minX", "maxX", "minZ", "maxZ", "width", "depth", "torsoWidth", "region"):
            self.assertEqual(len(s[key]), n, key)
        self.assertEqual(s["region"][5], "legs")
        self.assertEqual(s["region"][95], "head")
        # the leg band is two 0.12 m legs 0.2 m apart centre to centre: 0.32 m wide
        self.assertAlmostEqual(s["width"][20], 0.32, delta=0.01)

    def test_head_dimensions(self) -> None:
        h = self.result["head"]["observed"]
        self.assertAlmostEqual(h["widthM"], HEAD_WIDTH, places=4)
        self.assertAlmostEqual(h["heightM"], HEAD_TOP - CHIN_Y, delta=0.005)
        self.assertAlmostEqual(h["depthM"], 0.10 + NOSE_FRONT_Z, delta=0.002)
        self.assertGreater(h["withAllMeshesBounds"]["widthM"], h["widthM"], "hair adds width")

    def test_face_detail_meshes_found_with_roles(self) -> None:
        face = self.result["face"]
        names = {f["name"] for f in face["features"]}
        self.assertEqual(names, {"Cube.021", "Cube.023"}, "the hair mesh must not be a face detail")
        roles = {r["name"]: r for r in self.result["inferred"]["faceFeatureRoles"]}
        self.assertEqual(roles["Cube.021"]["role"], "eye")
        self.assertEqual(roles["Cube.023"]["role"], "brow")
        for r in roles.values():
            self.assertTrue(r["basis"])
            self.assertIn(r["confidence"], ("high", "medium", "low"))
        eye = next(f for f in face["features"] if f["name"] == "Cube.021")
        self.assertEqual(eye["layout"], "paired")
        self.assertAlmostEqual(eye["centreM"][1], EYE_Y, places=5)
        self.assertAlmostEqual(eye["headRel"]["centre"]["y"], (EYE_Y - CHIN_Y) / (HEAD_TOP - CHIN_Y), delta=0.01)
        self.assertAlmostEqual(eye["headRel"]["centre"]["x"], 0.0, places=6)
        self.assertEqual(self.result["inferred"]["landmarks"]["chin"]["confidence"], "medium")

    def test_eye_line_interocular_and_nose(self) -> None:
        layout = self.result["face"]["layout"]
        self.assertAlmostEqual(layout["eyeLineHeadFrac"], (EYE_Y - CHIN_Y) / (HEAD_TOP - CHIN_Y), delta=0.01)
        self.assertAlmostEqual(layout["eyeWidthM"], 0.03, places=5)
        self.assertAlmostEqual(layout["eyeWidthOverHeadWidth"], 0.03 / HEAD_WIDTH, delta=1e-3)
        self.assertAlmostEqual(layout["interocularInnerGapM"], 0.06, places=5)
        self.assertAlmostEqual(layout["interocularCentreDistanceM"], 0.09, places=5)
        self.assertAlmostEqual(layout["interocularCentreOverHeadWidth"], 0.09 / HEAD_WIDTH, delta=1e-3)
        self.assertAlmostEqual(layout["faceWidthAtEyeLineM"], HEAD_WIDTH, delta=0.002)
        nose = self.result["face"]["noseTip"]
        self.assertAlmostEqual(nose["positionM"][2], NOSE_FRONT_Z, places=5)
        self.assertTrue(1.58 <= nose["positionM"][1] <= 1.62)
        self.assertAlmostEqual(nose["headRel"]["x"], 0.0, places=6)
        thirds = layout["thirds"]
        self.assertAlmostEqual(thirds["noseToChinM"], nose["positionM"][1] - CHIN_Y, places=5)
        self.assertGreater(thirds["browToNoseM"], 0.0)

    def test_hairline_is_measured_from_the_hair_mesh_above_the_eyes(self) -> None:
        layout = self.result["face"]["layout"]
        self.assertEqual(layout["hairMesh"]["name"], "NurbsPath.002")
        self.assertGreaterEqual(layout["thirds"]["hairlineYM"], EYE_Y - 1e-6)

    def test_mouth_is_null_with_a_reason_when_there_is_no_mouth_mesh(self) -> None:
        self.assertIsNone(self.result["face"]["mouth"])
        self.assertTrue(any(l.startswith("mouth:") for l in self.result["limits"]))

    def test_mirrored_figure_has_zero_symmetry_error_and_faces_forward(self) -> None:
        sym = self.result["face"]["symmetry"]
        self.assertLess(sym["skinHead"]["meanErrM"], 1e-6)
        self.assertEqual(sym["skinHead"]["matchedFraction"], 1.0)
        self.assertLess(sym["pairedFeaturesMeanErrM"], 1e-6)
        self.assertTrue(self.result["face"]["facing"]["consistent"])

    def test_atlas_face_uv_box_and_texel_density(self) -> None:
        atlas = self.result["atlas"]
        self.assertEqual((atlas["image"]["widthPx"], atlas["image"]["heightPx"]), (32, 16))
        box = atlas["faceUv"]["uvBox"]
        self.assertGreaterEqual(box[0], FACE_UV[0] - 1e-6)
        self.assertLessEqual(box[2], FACE_UV[2] + 1e-6)
        self.assertLessEqual(box[3], FACE_UV[3] + 1e-6)
        density = atlas["texelDensity"]
        for region in ("face", "body", "all"):
            self.assertGreater(density[region]["texelsPerMetre"], 0.0, region)
        self.assertIsNotNone(density["faceOverBody"])
        eye_uv = next(d for d in atlas["faceDetailMeshes"] if d["name"] == "Cube.021")
        self.assertGreaterEqual(eye_uv["uvBox"][0], DARK_UV[0] - 1e-6)
        self.assertTrue(eye_uv["sameImageAsSkin"])

    def test_atlas_colours_come_from_the_right_quadrants(self) -> None:
        colours = self.result["atlas"]["colours"]
        self.assertTrue(colours["decoded"])
        face = colours["regions"]["face"]
        for stats in (face["box"], face["vertexSampled"]):
            for got, want in zip(stats["meanSrgb"], SKIN_RGB):
                self.assertAlmostEqual(got, want, delta=0.5)
            self.assertEqual(stats["medianHex"], "#f0c8aa")
        body = colours["regions"]["body"]
        for got, want in zip(body["vertexSampled"]["meanSrgb"], BODY_RGB):
            self.assertAlmostEqual(got, want, delta=0.5)
        self.assertEqual(face["paletteK5"][0]["hex"], "#f0c8aa")
        expected_l = anatomy._lstar(*SKIN_RGB)
        self.assertAlmostEqual(face["vertexSampled"]["meanLstar"], expected_l, places=6)
        self.assertGreater(face["vertexSampled"]["meanLstar"], body["vertexSampled"]["meanLstar"])


# ---------------------------------------------------------------------------------------------
# Counter-examples
# ---------------------------------------------------------------------------------------------


class CounterExampleTests(_Workdir):
    def test_no_skin_is_measured_but_flagged_unskinned(self) -> None:
        r = self.analyze(_humanoid(), skin=False)
        body = r["observed"]["bodyMesh"]
        self.assertFalse(body["skinned"])
        self.assertIn("no skinned mesh", body["selection"])
        self.assertFalse(r["observed"]["restPose"]["evaluated"])
        self.assertEqual(body["meshName"], "Cube.020", "largest mesh by vertex count")
        self.assertAlmostEqual(r["inferred"]["landmarks"]["chin"]["yM"], CHIN_Y, delta=0.005)

    def test_empty_mesh_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.analyze(_humanoid(), empty=True)

    def test_no_mesh_at_all_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.analyze([], skin=False)

    def test_unknown_body_mesh_override_raises_and_known_one_is_used(self) -> None:
        with self.assertRaises(ValueError):
            self.analyze(_humanoid(), body_mesh="NoSuchMesh")
        r = self.analyze(_humanoid(), body_mesh="Hair")
        self.assertEqual(r["observed"]["bodyMesh"]["meshName"], "NurbsPath.002")
        self.assertIn("override", r["observed"]["bodyMesh"]["selection"])

    def test_body_autodetection_prefers_the_skinned_mask_mesh_over_a_bigger_decoy(self) -> None:
        parts = _humanoid(decoy=True)
        self.assertGreater(len(parts[-1]["mesh"][0]), len(parts[0]["mesh"][0]), "the decoy must have more vertices")
        r = self.analyze(parts)
        self.assertEqual(r["observed"]["bodyMesh"]["meshName"], "Cube.020")
        self.assertEqual(r["observed"]["bodyMesh"]["candidates"][0]["mesh"], "Cube.020")

    def test_asymmetric_head_has_a_much_larger_symmetry_error_than_a_mirrored_one(self) -> None:
        mirrored = self.analyze(_humanoid(), name="m.glb")
        skewed = self.analyze(_humanoid(asym_head=True), name="a.glb")
        e_m = mirrored["face"]["symmetry"]["skinHead"]["meanErrM"]
        e_a = skewed["face"]["symmetry"]["skinHead"]["meanErrM"]
        self.assertLess(e_m, 1e-6)
        self.assertGreater(e_a, 5e-4)
        self.assertGreater(e_a, 1000 * max(e_m, 1e-9))
        self.assertLess(skewed["face"]["symmetry"]["skinHead"]["matchedFraction"], 1.0)

    def test_no_face_detail_meshes_means_no_eye_line_and_a_stated_reason(self) -> None:
        r = self.analyze(_humanoid(eyes=False, hair=False))
        face = r["face"]
        self.assertEqual(face["features"], [])
        self.assertNotIn("eyeLineYM", face["layout"])
        self.assertIsNone(face["mouth"])
        self.assertTrue(any(l.startswith("eyes:") for l in r["limits"]))
        self.assertTrue(any(l.startswith("mouth:") for l in r["limits"]))
        self.assertTrue(any(l.startswith("hairline:") for l in r["limits"]))
        self.assertEqual(r["inferred"]["faceFeatureRoles"], [])
        # the nose is still measurable from the skin mesh, with lower confidence as no eye line bounds it
        self.assertEqual(face["noseTip"]["confidence"], "low")

    def test_a_pose_t_pose_and_no_arms_give_three_different_classes(self) -> None:
        t = self.analyze(_humanoid(arms="T", arm_angle=90.0), name="t.glb")
        a = self.analyze(_humanoid(arms="A", arm_angle=35.0), name="a.glb")
        none = self.analyze(_humanoid(arms=None), name="n.glb")
        self.assertEqual(t["inferred"]["pose"]["class"], "T-pose")
        self.assertEqual(a["inferred"]["pose"]["class"], "A-pose")
        self.assertAlmostEqual(a["inferred"]["pose"]["armAngleFromVerticalDeg"], 35.0, delta=8.0)
        self.assertEqual(none["inferred"]["pose"]["class"], "arms-at-sides-or-absent")
        self.assertIsNone(none["inferred"]["pose"]["armAngleFromVerticalDeg"])
        self.assertLess(a["observed"]["armSpan"]["spanOverH"], t["observed"]["armSpan"]["spanOverH"])
        self.assertAlmostEqual(none["observed"]["armSpan"]["spanM"], 0.4, delta=0.01)
        self.assertFalse(any(a["silhouette"]["armTrimmed"]), "A-pose arms are separated by a gap, not trimmed")

    def test_sixteen_bit_atlas_is_reported_not_decoded(self) -> None:
        sixteen = _png(4, 2, [bytes(4 * 3 * 2)] * 2, depth=16)
        r = self.analyze(_humanoid(), png=sixteen)
        self.assertFalse(r["atlas"]["colours"]["decoded"])
        self.assertTrue(any("atlas" in l and "8-bit" in l for l in r["limits"]), r["limits"])
        self.assertIsNotNone(r["atlas"]["faceUv"], "UV boxes do not need the pixels")
        self.assertGreater(r["atlas"]["texelDensity"]["face"]["texelsPerMetre"], 0.0)

    def test_figure_height_override_is_recorded(self) -> None:
        r = self.analyze(_humanoid(), figure_height=1.5)
        self.assertEqual(r["observed"]["figure"]["heightSource"], "caller")
        self.assertEqual(r["observed"]["figure"]["heightM"], 1.5)
        self.assertAlmostEqual(r["observed"]["figure"]["measuredHeightM"], HAIR_TOP, places=5)

    def test_bands_option_changes_the_array_length(self) -> None:
        r = self.analyze(_humanoid(), bands=50)
        self.assertEqual(len(r["silhouette"]["width"]), 50)
        with self.assertRaises(ValueError):
            self.analyze(_humanoid(), bands=3, name="b.glb")


# ---------------------------------------------------------------------------------------------
# The real delivered character
# ---------------------------------------------------------------------------------------------


class RealCharacterTests(unittest.TestCase):
    @unittest.skipUnless(REAL_GLB.is_file(), f"real character GLB not present at {REAL_GLB} (set IMG2_NAMI_GLB)")
    def test_real_character_facts(self) -> None:
        r = anatomy.analyze(REAL_GLB)
        o = r["observed"]
        self.assertEqual(o["bodyMesh"]["meshName"], "Cube.020")
        self.assertEqual(o["bodyMesh"]["vertexCount"], 37771)
        self.assertAlmostEqual(o["figure"]["heightM"], 1.75, delta=1e-3)
        self.assertTrue(o["restPose"]["restPoseEqualsBindPose"])
        # The file is NOT a T-pose: arms hang about 30-40 degrees from vertical (an A-pose).
        self.assertEqual(r["inferred"]["pose"]["class"], "A-pose")
        self.assertTrue(20.0 < r["inferred"]["pose"]["armAngleFromVerticalDeg"] < 50.0)
        self.assertAlmostEqual(o["armSpan"]["spanOverH"], 0.5485, delta=0.005)
        # Face-detail meshes sit in the head, above 1.5 m.
        face = r["face"]
        self.assertEqual(face["detailMeshCount"], 7)
        self.assertEqual(
            {f["name"] for f in face["features"]},
            {"Cube.021", "Cube.023", "Cube.024", "Cube.025", "Circle.005", "Vert.007", "Sphere.001"},
        )
        for feature in face["features"]:
            self.assertGreater(feature["centreM"][1], 1.5, feature["name"])
        roles = {x["name"]: x["role"] for x in r["inferred"]["faceFeatureRoles"]}
        self.assertEqual(roles["Cube.021"], "eye")
        self.assertEqual(roles["Cube.023"], "brow")
        self.assertIsNone(face["mouth"], "no mouth mesh: the mouth is painted or modelled in the skin")
        self.assertTrue(0.35 < face["layout"]["eyeLineHeadFrac"] < 0.55)
        self.assertTrue(7.0 < r["inferred"]["proportions"]["headsTall"] < 9.0)
        self.assertLess(face["symmetry"]["skinHead"]["meanErrM"], 1e-4, "the real mesh is an exact mirror")
        # the face lives in the right-hand strip of the atlas and is sampled ~3x denser than the body
        self.assertGreater(r["atlas"]["faceUv"]["uvBox"][0], 0.8)
        self.assertGreater(r["atlas"]["texelDensity"]["faceOverBody"], 2.0)
        self.assertTrue(r["atlas"]["colours"]["decoded"])
        json.dumps(r, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
