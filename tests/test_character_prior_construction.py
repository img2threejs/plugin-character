#!/usr/bin/env python3
"""Tests for tools/character_prior/construction.py.

Every behaviour is pinned twice: once on a synthetic GLB whose right answer is known by
construction (a polygonal tube "body", offset tube "garments", ...) and once on a counter-example
that must give a DIFFERENT answer (an asymmetric mesh, a mesh with the wrong diagonal pattern, a
garment inside the skin, a GLB with no skin, an empty mesh). A test that only checked the good case
would pass against a module that returned the same numbers for everything.

The synthetic GLBs are written in-process with the stdlib (real 12-byte header, JSON chunk, BIN
chunk). One test reads the real delivered character; it is skipped, with its reason, when that
file is absent (override the path with IMG2_NAMI_GLB).

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
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from character_prior import construction  # noqa: E402

REAL_GLB = Path(os.environ.get("IMG2_NAMI_GLB") or Path.home() / ".img2/jobs/nami-sketchfab-8e496e5a/native/export/character.glb")

BODY_HEIGHT = 1.7
BODY_RADIUS = 0.10


# --------------------------------------------------------------------------------------------
# A tiny GLB builder and mesh generators
# --------------------------------------------------------------------------------------------


def tube(
    radius: float,
    y0: float,
    y1: float,
    *,
    around: int = 16,
    along: int = 40,
    cx: float = 0.0,
    alternate: bool = False,
    uv_mode: str = "unwrap",
    uv_scale: float = 1.0,
) -> dict[str, Any]:
    """A polygonal tube with outward vertex normals and a duplicated seam column.

    uv_mode: 'unwrap' (u by angle index, v by height), 'shared' (u = |x|/r so x-mirrored vertices
    share a UV), 'mirrored' (u = 0.5 + x/2r so x-mirrored vertices are mirrored in u).
    """
    positions: list[tuple[float, float, float]] = []
    normals: list[tuple[float, float, float]] = []
    uvs: list[tuple[float, float]] = []
    for j in range(along + 1):
        y = y0 + (y1 - y0) * j / along
        for k in range(around + 1):
            th = 2.0 * math.pi * k / around
            c, s = math.cos(th), math.sin(th)
            positions.append((cx + radius * c, y, radius * s))
            normals.append((c, 0.0, s))
            v = j / along
            if uv_mode == "unwrap":
                u = k / around
            elif uv_mode == "shared":
                u = abs(c)
            elif uv_mode == "mirrored":
                u = 0.5 + 0.5 * c
            else:
                raise ValueError(uv_mode)
            uvs.append((u * uv_scale, v * uv_scale))
    indices: list[int] = []
    for j in range(along):
        for k in range(around):
            a = j * (around + 1) + k
            b = a + 1
            c = a + around + 1
            d = c + 1
            if alternate and (j + k) % 2:
                indices += [a, c, d, a, d, b]
            else:
                indices += [a, c, b, b, c, d]
    return {"positions": positions, "normals": normals, "uvs": uvs, "indices": indices}


def merge(*parts: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"positions": [], "normals": [], "uvs": [], "indices": []}
    for p in parts:
        base = len(out["positions"])
        out["positions"] += p["positions"]
        out["normals"] += p["normals"]
        out["uvs"] += p["uvs"]
        out["indices"] += [i + base for i in p["indices"]]
    return out


def sphere(radius: float, centre: tuple[float, float, float], *, around: int = 24, rings: int = 12) -> dict[str, Any]:
    positions, normals, uvs = [], [], []
    for r in range(rings + 1):
        phi = math.pi * r / rings
        for k in range(around):
            th = 2.0 * math.pi * k / around
            n = (math.sin(phi) * math.cos(th), math.cos(phi), math.sin(phi) * math.sin(th))
            positions.append((centre[0] + radius * n[0], centre[1] + radius * n[1], centre[2] + radius * n[2]))
            normals.append(n)
            uvs.append((k / around, r / rings))
    indices = []
    for r in range(rings):
        for k in range(around):
            a = r * around + k
            b = r * around + (k + 1) % around
            c = (r + 1) * around + k
            d = (r + 1) * around + (k + 1) % around
            indices += [a, c, b, b, c, d]
    return {"positions": positions, "normals": normals, "uvs": uvs, "indices": indices}


def strip(origin: tuple[float, float, float], length: float, width: float, segments: int) -> dict[str, Any]:
    """A flat ribbon hanging down from `origin`, `segments` quads long."""
    positions, normals, uvs = [], [], []
    for s in range(segments + 1):
        y = origin[1] - length * s / segments
        positions += [(origin[0] - width / 2, y, origin[2]), (origin[0] + width / 2, y, origin[2])]
        normals += [(0.0, 0.0, 1.0), (0.0, 0.0, 1.0)]
        uvs += [(0.0, s / segments), (1.0, s / segments)]
    indices = []
    for s in range(segments):
        a = 2 * s
        indices += [a, a + 2, a + 1, a + 1, a + 2, a + 3]
    return {"positions": positions, "normals": normals, "uvs": uvs, "indices": indices}


def _pad(data: bytes, fill: bytes = b"\0") -> bytes:
    return data + fill * ((4 - len(data) % 4) % 4)


def build_glb(
    meshes: list[dict[str, Any]],
    *,
    with_skin: bool = True,
    image_size: tuple[int, int] | None = None,
) -> bytes:
    """Write a GLB. Each mesh dict: name, geometry keys of `tube`, optional joints/weights/masks/material."""
    blob = bytearray()
    views: list[dict[str, Any]] = []
    accessors: list[dict[str, Any]] = []

    def add_view(data: bytes) -> int:
        offset = len(blob)
        blob.extend(_pad(data))
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(data)})
        return len(views) - 1

    def add_accessor(data: bytes, component: int, count: int, kind: str, bounds: bool = False, values: list | None = None) -> int:
        acc: dict[str, Any] = {"bufferView": add_view(data), "componentType": component, "count": count, "type": kind}
        if bounds and values:
            acc["min"] = [min(v[k] for v in values) for k in range(3)]
            acc["max"] = [max(v[k] for v in values) for k in range(3)]
        accessors.append(acc)
        return len(accessors) - 1

    gltf_meshes: list[dict[str, Any]] = []
    materials: list[dict[str, Any]] = []
    for spec in meshes:
        pos = spec["positions"]
        attrs: dict[str, int] = {}
        attrs["POSITION"] = add_accessor(struct.pack(f"<{3 * len(pos)}f", *[c for p in pos for c in p]), 5126, len(pos), "VEC3", True, pos)
        if spec.get("normals"):
            attrs["NORMAL"] = add_accessor(struct.pack(f"<{3 * len(pos)}f", *[c for p in spec["normals"] for c in p]), 5126, len(pos), "VEC3")
        if spec.get("uvs"):
            attrs["TEXCOORD_0"] = add_accessor(struct.pack(f"<{2 * len(pos)}f", *[c for p in spec["uvs"] for c in p]), 5126, len(pos), "VEC2")
        if spec.get("joints"):
            attrs["JOINTS_0"] = add_accessor(struct.pack(f"<{4 * len(pos)}H", *[c for p in spec["joints"] for c in p]), 5123, len(pos), "VEC4")
            attrs["WEIGHTS_0"] = add_accessor(struct.pack(f"<{4 * len(pos)}f", *[c for p in spec["weights"] for c in p]), 5126, len(pos), "VEC4")
        for mask_name, values in (spec.get("masks") or {}).items():
            attrs[mask_name] = add_accessor(struct.pack(f"<{len(pos)}f", *values), 5126, len(pos), "SCALAR")
        idx = spec["indices"]
        prim: dict[str, Any] = {"attributes": attrs, "indices": add_accessor(struct.pack(f"<{len(idx)}I", *idx), 5125, len(idx), "SCALAR")}
        material = spec.get("material")
        if material is not None:
            materials.append(material)
            prim["material"] = len(materials) - 1
        gltf_meshes.append({"name": spec["name"], "primitives": [prim]})

    doc: dict[str, Any] = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}]}
    nodes: list[dict[str, Any]] = [{"name": "Rig", "children": []}]
    if with_skin:
        nodes.append({"name": "Root", "children": [2]})
        nodes.append({"name": "Pelvis"})
        nodes[0]["children"] += [1]
        ibm = add_accessor(struct.pack("<32f", *([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] * 2)), 5126, 2, "MAT4")
        doc["skins"] = [{"joints": [1, 2], "inverseBindMatrices": ibm, "name": "Skin"}]
    for mi, spec in enumerate(meshes):
        node: dict[str, Any] = {"name": f"{spec['name']}-node", "mesh": mi}
        if with_skin:
            node["skin"] = 0
        nodes.append(node)
        nodes[0]["children"].append(len(nodes) - 1)
    doc["nodes"] = nodes
    doc["meshes"] = gltf_meshes
    if materials:
        doc["materials"] = materials
    if image_size is not None:
        png = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", *image_size) + b"\x08\x06\x00\x00\x00"
        view = add_view(png)
        doc["images"] = [{"bufferView": view, "mimeType": "image/png"}]
        doc["textures"] = [{"source": 0}]
    doc["accessors"] = accessors
    doc["bufferViews"] = views
    doc["buffers"] = [{"byteLength": len(blob)}]
    json_bytes = _pad(json.dumps(doc).encode("utf-8"), b" ")
    bin_bytes = _pad(bytes(blob))
    total = 12 + 8 + len(json_bytes) + 8 + len(bin_bytes)
    return (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<II", len(json_bytes), 0x4E4F534A) + json_bytes
        + struct.pack("<II", len(bin_bytes), 0x004E4942) + bin_bytes
    )


SKIN_MATERIAL = {"name": "skin", "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 0.5}}
CLOTH_MATERIAL = {"name": "cloth", "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 0.9}, "extensions": {"KHR_materials_unlit": {}}}


def rig_body(geom: dict[str, Any], *, masks: dict[str, list[float]] | None = None, weights_error_first: bool = False) -> dict[str, Any]:
    """Body mesh dict: two-joint weights blending 0.5..0.9 m, skin-like material."""
    joints, weights = [], []
    for (_, y, _) in geom["positions"]:
        t = min(1.0, max(0.0, (y - 0.5) / 0.4))
        if t <= 0.0:
            joints.append((0, 0, 0, 0))
            weights.append((1.0, 0.0, 0.0, 0.0))
        elif t >= 1.0:
            joints.append((1, 0, 0, 0))
            weights.append((1.0, 0.0, 0.0, 0.0))
        else:
            joints.append((0, 1, 0, 0))
            weights.append((1.0 - t, t, 0.0, 0.0))
    if weights_error_first:
        joints[0], weights[0] = (0, 1, 0, 0), (0.5, 0.4, 0.0, 0.0)
    spec = dict(geom)
    spec.update({"name": "Body", "joints": joints, "weights": weights, "material": SKIN_MATERIAL, "masks": masks or {}})
    return spec


def cloth(name: str, geom: dict[str, Any]) -> dict[str, Any]:
    spec = dict(geom)
    spec.update({"name": name, "material": CLOTH_MATERIAL})
    return spec


def analyze_bytes(data: bytes, **options: Any) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "t.glb"
        path.write_bytes(data)
        return construction.analyze(path, **options)


def standard_body(**kwargs: Any) -> dict[str, Any]:
    return rig_body(tube(BODY_RADIUS, 0.0, BODY_HEIGHT), **kwargs)


# --------------------------------------------------------------------------------------------
# Accessor reading
# --------------------------------------------------------------------------------------------


class AccessorReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        import rig_glb_reference as ref

        self.ref = ref
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.glb"
            path.write_bytes(build_glb([standard_body(masks={"_SOFT_X": [0.25] * (17 * 41)})]))
            self.doc, self.binp, _ = ref.parse_glb(path)

    def test_fast_path_matches_the_reference_reader_on_every_accessor(self) -> None:
        for index in range(len(self.doc["accessors"])):
            expected = self.ref.read_accessor(self.doc, self.binp, index)
            got = construction._read_accessor(self.doc, self.binp, index)
            self.assertEqual(len(expected), len(got), index)
            for a, b in zip(expected, got):
                self.assertEqual(tuple(float(x) for x in a), tuple(float(x) for x in b), index)

    def test_normalised_accessor_is_delegated_not_misread(self) -> None:
        # Counter-example: a normalised ushort accessor must come back scaled to 0..1.
        index = next(i for i, a in enumerate(self.doc["accessors"]) if a["componentType"] == 5123)
        self.doc["accessors"][index]["normalized"] = True
        got = construction._read_accessor(self.doc, self.binp, index)
        self.assertEqual(got, self.ref.read_accessor(self.doc, self.binp, index))
        self.assertTrue(all(0.0 <= c <= 1.0 for row in got for c in row))

    def test_interleaved_view_is_delegated(self) -> None:
        index = next(i for i, a in enumerate(self.doc["accessors"]) if a["type"] == "VEC3")
        view = self.doc["bufferViews"][self.doc["accessors"][index]["bufferView"]]
        view["byteStride"] = 12  # equal to the element size: still tight
        self.assertEqual(construction._read_accessor(self.doc, self.binp, index), self.ref.read_accessor(self.doc, self.binp, index))
        view["byteStride"] = 16  # a gap after each element runs past this view: the reference reader's error must surface
        with self.assertRaises(ValueError):
            self.ref.read_accessor(self.doc, self.binp, index)
        with self.assertRaises(ValueError):
            construction._read_accessor(self.doc, self.binp, index)


# --------------------------------------------------------------------------------------------
# Contract
# --------------------------------------------------------------------------------------------


class ContractTests(unittest.TestCase):
    def test_required_keys_json_and_basis_strings(self) -> None:
        result = analyze_bytes(build_glb([standard_body(), cloth("Shirt", tube(BODY_RADIUS + 0.005, 0.6, 1.2, along=15))]))
        for key in ("schema", "observed", "inferred", "limits"):
            self.assertIn(key, result)
        self.assertEqual(result["schema"], "img2.character-prior.construction/1")
        json.dumps(result, allow_nan=False)  # strictly serialisable: no NaN/inf anywhere
        self.assertIsInstance(result["limits"], list)
        self.assertTrue(result["limits"])
        self.assertEqual(result["source"]["heightSource"], "meshPositionBoundsYExtent")
        self.assertAlmostEqual(result["source"]["heightM"], BODY_HEIGHT, places=5)
        # every inferred classification states its basis
        self.assertIn("basis", result["inferred"]["densityTopology"]["subdivision"])
        self.assertIn("basis", result["inferred"]["symmetry"]["geometricSymmetry"])
        self.assertIn("basis", result["inferred"]["layering"])
        self.assertTrue(all("basis" in r for r in result["inferred"]["roles"].values()))

    def test_height_override_scales_fractions(self) -> None:
        data = build_glb([standard_body(), cloth("Shirt", tube(BODY_RADIUS + 0.005, 0.6, 1.2, along=15))])
        base = analyze_bytes(data)
        scaled = analyze_bytes(data, figure_height=3.4)
        self.assertEqual(scaled["source"]["heightSource"], "caller-supplied")
        self.assertAlmostEqual(scaled["source"]["heightM"], 3.4)
        a = base["observed"]["garmentClearance"]["Shirt"]["signedFrac"]["median"]
        b = scaled["observed"]["garmentClearance"]["Shirt"]["signedFrac"]["median"]
        self.assertAlmostEqual(a / b, 2.0, places=2)

    def test_body_override_and_unknown_name(self) -> None:
        data = build_glb([standard_body(), cloth("Shirt", tube(BODY_RADIUS + 0.005, 0.6, 1.2, along=15))])
        auto = analyze_bytes(data)
        self.assertEqual(auto["source"]["bodyMesh"]["name"], "Body")
        self.assertEqual(auto["source"]["bodyMesh"]["method"], "autodetect")
        forced = analyze_bytes(data, body_mesh="Shirt")
        self.assertEqual(forced["source"]["bodyMesh"]["name"], "Shirt")
        self.assertEqual(forced["source"]["bodyMesh"]["method"], "override")
        by_node = analyze_bytes(data, body_mesh="Shirt-node")
        self.assertEqual(by_node["source"]["bodyMesh"]["name"], "Shirt")
        with self.assertRaises(ValueError):
            analyze_bytes(data, body_mesh="NoSuchMesh")


# --------------------------------------------------------------------------------------------
# Garment clearance and layering
# --------------------------------------------------------------------------------------------


class ClearanceTests(unittest.TestCase):
    def test_known_five_millimetre_offset_is_measured(self) -> None:
        result = analyze_bytes(build_glb([standard_body(), cloth("Shirt", tube(BODY_RADIUS + 0.005, 0.6, 1.2, along=15))]))
        c = result["observed"]["garmentClearance"]["Shirt"]
        self.assertEqual(result["inferred"]["roles"]["Shirt"]["role"], "garment")
        for key in ("min", "p1", "p5", "p25", "median", "p75", "p95", "max"):
            self.assertAlmostEqual(c["signedMm"][key], 5.0, delta=0.05, msg=key)
        self.assertEqual(c["negativeCount"], 0)
        self.assertEqual(c["nearShare"]["closerThan0.8mm"], 0.0)
        self.assertEqual(c["nearShare"]["closerThan2.5mm"], 0.0)
        self.assertAlmostEqual(c["clampBandShare"]["within0.8to20mm"], 1.0)

    def test_garment_inside_the_skin_is_negative(self) -> None:
        # Counter-example: the same garment shrunk inside the body must come out NEGATIVE,
        # so the sign is real and not an absolute value.
        result = analyze_bytes(build_glb([standard_body(), cloth("Inner", tube(BODY_RADIUS - 0.003, 0.6, 1.2, along=15))]))
        c = result["observed"]["garmentClearance"]["Inner"]
        self.assertEqual(c["negativeCount"], c["sampledVertices"])
        self.assertEqual(c["negativeShare"], 1.0)
        self.assertTrue(-3.0 <= c["signedMm"]["median"] <= -2.8, c["signedMm"])
        self.assertAlmostEqual(c["clampBandShare"]["below0.8mm"], 1.0)

    def test_tight_garment_counts_against_the_clamp_thresholds(self) -> None:
        result = analyze_bytes(build_glb([standard_body(), cloth("Tight", tube(BODY_RADIUS + 0.0005, 0.6, 1.2, along=15))]))
        c = result["observed"]["garmentClearance"]["Tight"]
        self.assertAlmostEqual(c["signedMm"]["median"], 0.5, delta=0.02)
        self.assertEqual(c["nearShare"]["closerThan0.8mm"], 1.0)
        self.assertEqual(c["nearShare"]["closerThan2.5mm"], 1.0)
        self.assertEqual(c["clampBandShare"]["below0.8mm"], 1.0)

    def test_detached_object_is_not_given_a_clearance(self) -> None:
        # Counter-example: a tube 1 m beside the body is a prop, not a garment.
        result = analyze_bytes(build_glb([standard_body(), cloth("Prop", tube(0.1, 0.6, 1.2, along=15, cx=1.0))]))
        self.assertEqual(result["inferred"]["roles"]["Prop"]["role"], "detached-or-prop")
        self.assertNotIn("Prop", result["observed"]["garmentClearance"] or {})

    def test_layering_orders_meshes_by_offset(self) -> None:
        result = analyze_bytes(build_glb([
            standard_body(),
            cloth("Outer", tube(BODY_RADIUS + 0.015, 0.6, 1.2, along=15)),
            cloth("Inner", tube(BODY_RADIUS + 0.004, 0.6, 1.2, along=15)),
        ]))
        order = [row["mesh"] for row in result["observed"]["layering"]["overSkinMeshesByMedianOffset"]]
        self.assertEqual(order, ["Inner", "Outer"])
        self.assertEqual(result["observed"]["layering"]["separateNonSkinObjectCount"], 2)

    def test_garment_far_outside_the_search_cap_is_not_a_garment(self) -> None:
        result = analyze_bytes(build_glb([standard_body(), cloth("Loose", tube(BODY_RADIUS + 0.2, 0.6, 1.2, along=15))]), body_mesh="Body")
        # 20 cm away: outside the 6 cm role-guess window, so it is a detached object, not a garment
        self.assertEqual(result["inferred"]["roles"]["Loose"]["role"], "detached-or-prop")
        self.assertNotIn("Loose", result["observed"]["garmentClearance"] or {})

    def test_nonuniform_static_scale_preserves_clearance_side_at_a_boundary(self) -> None:
        # Plane x+y=0, stretched 10x in X. Transforming normals like positions
        # flips the sign near the edge even though the point is above the plane.
        n = math.sqrt(0.5)
        geometry = {"positions": [(-1, 1, 0), (1, -1, 0), (0, 0, 1)],
                    "normals": [(n, n, 0)] * 3, "indices": [0, 1, 2]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scaled.glb"
            path.write_bytes(build_glb([cloth("Plane", geometry)], with_skin=False))
            doc, binp, _ = construction.glbref.parse_glb(path)
            world = (10, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
            mesh = construction._Mesh(doc, binp, 1, doc["nodes"][1], world)
            ctx = construction._Ctx(doc, binp, [mesh], mesh, 2.0, -1.0, 1.0)
            ctx.skin_grid = construction._TriGrid(mesh.positions, mesh.tris, 1.0)
            query = construction._SkinQuery(ctx)
            norm = math.hypot(0.1, 1.0)
            base = (-10.01, 1.001, 0)  # just beyond the triangle along its plane
            for side in (-1, 1):
                point = (base[0] + side * 0.001 * 0.1 / norm,
                         base[1] + side * 0.001 / norm, 0)
                distance, _ = query.signed(point, 0.1)
                self.assertGreater(side * distance, 0.0)


# --------------------------------------------------------------------------------------------
# Topology, density
# --------------------------------------------------------------------------------------------


class TopologyTests(unittest.TestCase):
    def topo(self, geom: dict[str, Any]) -> dict[str, Any]:
        return analyze_bytes(build_glb([rig_body(geom)]))["observed"]["densityTopology"]

    def test_regular_diagonal_grid_is_valence_six(self) -> None:
        t = self.topo(tube(BODY_RADIUS, 0.0, BODY_HEIGHT))
        self.assertGreater(t["valence"]["interiorValence6Share"], 0.95)
        self.assertEqual(t["weldedVertices"], 16 * 41)  # the duplicated seam column welds away
        self.assertEqual(t["triangles"], 16 * 40 * 2)
        self.assertEqual(t["nonManifoldEdges"], 0)

    def test_alternating_diagonals_are_not_valence_six(self) -> None:
        # Counter-example: flipping every other diagonal gives valence 4/8, not 6.
        t = self.topo(tube(BODY_RADIUS, 0.0, BODY_HEIGHT, alternate=True))
        self.assertLess(t["valence"]["interiorValence6Share"], 0.3)
        hist = t["valence"]["interiorHistogram"]
        self.assertIn("4", hist)
        self.assertIn("8", hist)

    def test_sliver_triangles_fail_the_angle_quality_share(self) -> None:
        good = self.topo(tube(BODY_RADIUS, 0.0, BODY_HEIGHT, around=16, along=16))
        sliver = self.topo(tube(BODY_RADIUS, 0.0, BODY_HEIGHT, around=64, along=4))
        self.assertLess(good["shareTrianglesMinAngleBelow10Deg"], 0.05)
        self.assertGreater(sliver["shareTrianglesMinAngleBelow10Deg"], 0.9)

    def test_edge_and_area_percentiles_match_the_grid(self) -> None:
        t = self.topo(tube(BODY_RADIUS, 0.0, BODY_HEIGHT, around=16, along=34))
        # vertical edges are 1.7/34 = 50 mm; circumferential 2*0.1*sin(pi/16) = 39.0 mm
        self.assertAlmostEqual(t["edgeLengthMm"]["min"], 39.0, delta=0.2)
        self.assertAlmostEqual(t["edgeLengthMm"]["max"], math.hypot(50.0, 39.0), delta=0.3)
        self.assertAlmostEqual(t["triangleAreaMm2"]["p50"], 0.5 * 50.0 * 39.0, delta=2.0)

    def test_density_bands_cover_the_height(self) -> None:
        t = self.topo(tube(BODY_RADIUS, 0.0, BODY_HEIGHT))
        bands = t["density"]["bandsOfHeight"]
        self.assertEqual(len(bands), construction.BAND_COUNT)
        self.assertEqual(sum(b["vertices"] for b in bands), t["weldedVertices"])
        self.assertAlmostEqual(sum(b["areaM2"] for b in bands), t["surfaceAreaM2"], places=3)

    def test_pairing_of_a_diagonal_split_grid(self) -> None:
        t = self.topo(tube(BODY_RADIUS, 0.0, BODY_HEIGHT, around=16, along=34))
        q = t["quadPairing"]
        self.assertGreater(q["pairedTriangleShare"], 0.95)
        self.assertGreater(q["nearPlanarPairShareOfPairs"], 0.99)

    def test_subdivision_inference_distinguishes_lattice_from_alternating(self) -> None:
        regular = analyze_bytes(build_glb([rig_body(tube(BODY_RADIUS, 0.0, BODY_HEIGHT))]))["inferred"]["densityTopology"]["subdivision"]
        alt = analyze_bytes(build_glb([rig_body(tube(BODY_RADIUS, 0.0, BODY_HEIGHT, alternate=True))]))["inferred"]["densityTopology"]["subdivision"]
        self.assertTrue(regular["valenceConsistentWithRegularRefinement"])
        self.assertFalse(alt["valenceConsistentWithRegularRefinement"])
        self.assertIn("basis", regular)
        # Valence and midpoint counts cannot recover a modifier stack from an exported mesh.
        self.assertIsNone(regular["linearSubdivision"])
        self.assertIsNone(alt["linearSubdivision"])

    def test_region_density_ratios_follow_a_denser_head(self) -> None:
        # A dense cap on top of a coarse tube: head triangles per m^2 must exceed the torso's.
        body = merge(tube(BODY_RADIUS, 0.0, 1.5, around=12, along=15), tube(0.06, 1.55, 1.7, around=24, along=12))
        result = analyze_bytes(build_glb([rig_body(body)]))
        regions = result["regions"]
        self.assertGreater(regions["headStartFrac"], 0.8)
        ratios = result["observed"]["densityTopology"]["density"]["regions"]["ratiosTrianglesPerM2VsTorso"]
        self.assertGreater(ratios["head"], 2.0)


# --------------------------------------------------------------------------------------------
# Symmetry
# --------------------------------------------------------------------------------------------


class SymmetryTests(unittest.TestCase):
    def sym(self, geom: dict[str, Any]) -> dict[str, Any]:
        return analyze_bytes(build_glb([rig_body(geom)]))["observed"]["symmetry"]

    def test_mirrored_mesh_has_zero_error(self) -> None:
        s = self.sym(tube(BODY_RADIUS, 0.0, BODY_HEIGHT))
        self.assertLess(s["mirrorErrorMm"]["allVertices"]["p95"], 0.01)
        self.assertGreater(s["exactMirrorShare"], 0.99)

    def test_asymmetric_mesh_has_a_larger_error(self) -> None:
        # Counter-example: push the +x half 4 mm along z. Mirror partners no longer coincide.
        geom = tube(BODY_RADIUS, 0.0, BODY_HEIGHT)
        geom["positions"] = [(x, y, z + (0.004 if x > 1e-9 else 0.0)) for (x, y, z) in geom["positions"]]
        s = self.sym(geom)
        self.assertGreater(s["mirrorErrorMm"]["allVertices"]["p95"], 3.0)
        self.assertLess(s["mirrorErrorMm"]["allVertices"]["p95"], 5.0)
        self.assertLess(s["exactMirrorShare"], 0.6)

    def test_uv_sharing_and_mirroring_are_told_apart(self) -> None:
        shared = self.sym(tube(BODY_RADIUS, 0.0, BODY_HEIGHT, uv_mode="shared"))["uvMirroring"]
        mirrored = self.sym(tube(BODY_RADIUS, 0.0, BODY_HEIGHT, uv_mode="mirrored"))["uvMirroring"]
        unwrapped = self.sym(tube(BODY_RADIUS, 0.0, BODY_HEIGHT, uv_mode="unwrap"))["uvMirroring"]
        self.assertGreater(shared["sharedUvShare"], 0.95)
        self.assertGreater(mirrored["mirroredUvShare"], 0.95)
        self.assertAlmostEqual(mirrored["mirrorAxisUSum"], 1.0, places=4)
        self.assertLess(shared["mirroredUvShare"], 0.05)
        self.assertLess(mirrored["sharedUvShare"], 0.05)
        # the angle unwrap neither shares nor mirrors for most pairs
        self.assertLess(unwrapped["sharedUvShare"], 0.2)

    def test_inference_reports_the_symmetry_verdict(self) -> None:
        geom = tube(BODY_RADIUS, 0.0, BODY_HEIGHT)
        good = analyze_bytes(build_glb([rig_body(geom)]))["inferred"]["symmetry"]["geometricSymmetry"]["verdict"]
        geom["positions"] = [(x, y, z + (0.004 if x > 1e-9 else 0.0)) for (x, y, z) in geom["positions"]]
        bad = analyze_bytes(build_glb([rig_body(geom)]))["inferred"]["symmetry"]["geometricSymmetry"]["verdict"]
        self.assertEqual(good, "bilaterally symmetric (x-mirror)")
        self.assertNotEqual(bad, good)


# --------------------------------------------------------------------------------------------
# UV / atlas
# --------------------------------------------------------------------------------------------


class UvTests(unittest.TestCase):
    def uv(self, geom: dict[str, Any], **kw: Any) -> dict[str, Any]:
        return analyze_bytes(build_glb([rig_body(geom)], **kw))["observed"]["uvAtlas"]

    def test_full_unwrap_covers_the_atlas_without_overlap(self) -> None:
        u = self.uv(tube(BODY_RADIUS, 0.0, BODY_HEIGHT, around=24, along=24))
        self.assertGreater(u["coverage"]["coveredPixelShare"], 0.97)
        self.assertLess(u["coverage"]["overlapFractionOfCovered"], 0.02)
        self.assertEqual(u["islandCount"], 1)
        self.assertEqual(u["seams"]["seamEdges"], 24)  # the welded seam column: one edge per row

    def test_quarter_unwrap_covers_a_quarter(self) -> None:
        u = self.uv(tube(BODY_RADIUS, 0.0, BODY_HEIGHT, around=24, along=24, uv_scale=0.5))
        self.assertAlmostEqual(u["coverage"]["coveredPixelShare"], 0.25, delta=0.03)

    def test_mirrored_layout_overlaps(self) -> None:
        # Counter-example: front and back project to the same UV, so every covered pixel is hit twice.
        u = self.uv(tube(BODY_RADIUS, 0.0, BODY_HEIGHT, around=24, along=24, uv_mode="shared"))
        self.assertGreater(u["coverage"]["overlapFractionOfCovered"], 0.9)
        self.assertGreater(u["coverage"]["meanLayersWhereCovered"], 1.5)

    def test_two_disjoint_tubes_are_two_islands(self) -> None:
        body = merge(tube(0.05, 0.0, BODY_HEIGHT, cx=-0.15), tube(0.05, 0.0, BODY_HEIGHT, cx=0.15))
        self.assertEqual(self.uv(body)["islandCount"], 2)

    def test_atlas_size_is_read_from_the_embedded_png(self) -> None:
        spec = standard_body()
        spec["material"] = {"name": "skin", "pbrMetallicRoughness": {"metallicFactor": 0.0, "baseColorTexture": {"index": 0}}}
        u = analyze_bytes(build_glb([spec], image_size=(512, 256)))["observed"]["uvAtlas"]
        self.assertEqual(u["atlasPx"], [512, 256])
        self.assertEqual(u["texelDensity"]["unit"], "texelsPerMetre")
        none = analyze_bytes(build_glb([standard_body()]))["observed"]["uvAtlas"]
        self.assertIsNone(none["atlasPx"])
        self.assertIn("uvUnitsPerMetre", none["texelDensity"]["unit"])

    def test_texel_density_scales_with_atlas_size(self) -> None:
        def median(size: tuple[int, int]) -> float:
            spec = standard_body()
            spec["material"] = {"name": "skin", "pbrMetallicRoughness": {"metallicFactor": 0.0, "baseColorTexture": {"index": 0}}}
            u = analyze_bytes(build_glb([spec], image_size=size))["observed"]["uvAtlas"]
            return u["texelDensity"]["perTriangle"]["median"]

        self.assertAlmostEqual(median((1024, 1024)) / median((512, 512)), 2.0, places=1)

    def test_no_uv_attribute_is_reported_as_a_limit(self) -> None:
        geom = tube(BODY_RADIUS, 0.0, BODY_HEIGHT)
        geom["uvs"] = []
        result = analyze_bytes(build_glb([rig_body(geom)]))
        self.assertIsNone(result["observed"]["uvAtlas"])
        self.assertTrue(any("TEXCOORD_0" in line for line in result["limits"]))


# --------------------------------------------------------------------------------------------
# Weights and masks
# --------------------------------------------------------------------------------------------


class WeightTests(unittest.TestCase):
    def test_bone_usage_and_influence_histogram(self) -> None:
        result = analyze_bytes(build_glb([standard_body()]))
        w = result["observed"]["weights"]
        row = next(r for r in w["meshes"] if r["mesh"] == "Body")
        self.assertEqual(w["skins"][0]["joints"], ["Root", "Pelvis"])
        self.assertEqual(row["maxInfluences"], 2)
        self.assertEqual(sum(row["influencesPerVertexHistogram"].values()), 17 * 41)
        self.assertEqual({j["joint"] for j in row["jointsUsed"]}, {"Root", "Pelvis"})
        self.assertEqual(row["weightSumError"]["verticesOver1e-3"], 0)
        self.assertLess(row["weightSumError"]["max"], 1e-6)

    def test_unnormalised_weights_are_flagged(self) -> None:
        # Counter-example: one vertex whose weights sum to 0.9.
        result = analyze_bytes(build_glb([rig_body(tube(BODY_RADIUS, 0.0, BODY_HEIGHT), weights_error_first=True)]))
        err = next(r for r in result["observed"]["weights"]["meshes"] if r["mesh"] == "Body")["weightSumError"]
        self.assertAlmostEqual(err["max"], 0.1, places=6)
        self.assertEqual(err["verticesOver1e-3"], 1)

    def test_glb_without_a_skin_has_no_weights(self) -> None:
        result = analyze_bytes(build_glb([dict(standard_body(), joints=None, weights=None)], with_skin=False))
        self.assertIsNone(result["observed"]["weights"])
        self.assertTrue(any("no skin" in line for line in result["limits"]))
        # the geometry sections still work without a skeleton
        self.assertIsNotNone(result["observed"]["densityTopology"])


class MaskTests(unittest.TestCase):
    def masked(self, values_for_y: Any, name: str = "_SOFT_TEST", extra: dict[str, Any] | None = None) -> dict[str, Any]:
        geom = tube(BODY_RADIUS, 0.0, BODY_HEIGHT)
        masks = {name: [values_for_y(p[1]) for p in geom["positions"]]}
        for other_name, fn in (extra or {}).items():
            masks[other_name] = [fn(p[1]) for p in geom["positions"]]
        return analyze_bytes(build_glb([rig_body(geom, masks=masks)]))

    def test_smooth_ramp_has_a_known_gradient(self) -> None:
        result = self.masked(lambda y: min(1.0, max(0.0, (y - 0.8) / 0.2)))
        m = result["observed"]["masks"]["perMask"]["_SOFT_TEST"]
        self.assertAlmostEqual(m["maxGradientPerM"]["max"], 5.0, delta=0.05)  # 1 / 0.2 m along y
        self.assertGreater(m["centroidYFrac"], 0.55)
        self.assertEqual(m["seamInconsistentVertices"], 0)

    def test_hard_edge_has_a_much_larger_gradient(self) -> None:
        # Counter-example: a step is 1 / edge length = ~23 per metre on the 42.5 mm grid.
        result = self.masked(lambda y: 1.0 if y > 0.85 else 0.0)
        m = result["observed"]["masks"]["perMask"]["_SOFT_TEST"]
        self.assertGreater(m["maxGradientPerM"]["max"], 20.0)

    def test_centroid_and_support_area_follow_the_painted_band(self) -> None:
        result = self.masked(lambda y: 1.0 if 0.4 <= y <= 0.6 else 0.0)
        m = result["observed"]["masks"]["perMask"]["_SOFT_TEST"]
        self.assertAlmostEqual(m["centroidM"][1], 0.5, delta=0.03)
        self.assertAlmostEqual(m["centroidYFrac"], 0.5 / BODY_HEIGHT, delta=0.02)
        # support is a band of height ~0.2 around a 0.1 m radius tube: 2*pi*0.1*0.2 = 0.126 m^2, plus one ring of partial triangles
        self.assertTrue(0.10 < m["supportAreaM2"] < 0.20, m["supportAreaM2"])

    def test_overlapping_masks_that_sum_above_one_are_flagged(self) -> None:
        stacked = self.masked(lambda y: 0.7 if 0.4 <= y <= 0.8 else 0.0, extra={"_SOFT_OTHER": lambda y: 0.7 if 0.6 <= y <= 1.0 else 0.0})
        shared = self.masked(lambda y: 0.5 if 0.4 <= y <= 0.8 else 0.0, extra={"_SOFT_OTHER": lambda y: 0.5 if 0.6 <= y <= 1.0 else 0.0})
        self.assertGreater(stacked["observed"]["masks"]["sums"]["maxSumWhereMasksOverlap"], 1.0)
        self.assertFalse(stacked["inferred"]["masks"]["normalisation"]["masksSumBelowOneWhereTheyOverlap"])
        self.assertTrue(shared["inferred"]["masks"]["normalisation"]["masksSumBelowOneWhereTheyOverlap"])

    def test_no_masks_is_a_limit_not_a_crash(self) -> None:
        result = analyze_bytes(build_glb([standard_body()]))
        self.assertIsNone(result["observed"]["masks"])
        self.assertTrue(any("_SOFT_" in line for line in result["limits"]))


# --------------------------------------------------------------------------------------------
# Hair
# --------------------------------------------------------------------------------------------


def _ring_of(count: int, make: Any) -> dict[str, Any]:
    parts = []
    for i in range(count):
        a = 2.0 * math.pi * i / count
        parts.append(make(0.09 * math.cos(a), 0.09 * math.sin(a)))
    return merge(*parts)


class HairTests(unittest.TestCase):
    def hair(self, geom: dict[str, Any]) -> dict[str, Any]:
        result = analyze_bytes(build_glb([standard_body(), cloth("Hair", geom)]), hair_mesh="Hair")
        return result

    def test_cards(self) -> None:
        geom = _ring_of(16, lambda x, z: strip((x, 1.72, z), 0.20, 0.03, 1))
        result = self.hair(geom)
        self.assertEqual(result["inferred"]["hair"]["hairType"], "cards")
        self.assertEqual(result["observed"]["hair"]["connectedComponents"], 16)
        self.assertEqual(result["inferred"]["hair"]["strandOrCardCountEstimate"], 16)

    def test_ribbon_strips(self) -> None:
        geom = _ring_of(16, lambda x, z: strip((x, 1.72, z), 0.30, 0.02, 20))
        self.assertEqual(self.hair(geom)["inferred"]["hair"]["hairType"], "ribbon strips")

    def test_tube_strands(self) -> None:
        geom = _ring_of(12, lambda x, z: _shift(tube(0.005, 1.42, 1.72, around=10, along=10), x, z))
        result = self.hair(geom)
        self.assertEqual(result["inferred"]["hair"]["hairType"], "tube strands")
        self.assertAlmostEqual(result["observed"]["hair"]["componentWidthMm"]["median"], 10.0, delta=1.0)
        self.assertIsNone(result["inferred"]["hair"]["clumpNote"])  # 10 mm wide: strand scale, not a clump

    def test_solid_shell(self) -> None:
        result = self.hair(sphere(0.13, (0.0, 1.6, 0.0)))
        self.assertEqual(result["inferred"]["hair"]["hairType"], "solid shell")
        self.assertEqual(result["observed"]["hair"]["connectedComponents"], 1)
        self.assertLess(result["observed"]["hair"]["boundaryEdgeShare"], 0.01)

    def test_types_differ_between_constructions(self) -> None:
        cards = self.hair(_ring_of(16, lambda x, z: strip((x, 1.72, z), 0.20, 0.03, 1)))["inferred"]["hair"]["hairType"]
        shell = self.hair(sphere(0.13, (0.0, 1.6, 0.0)))["inferred"]["hair"]["hairType"]
        self.assertNotEqual(cards, shell)

    def test_no_hair_mesh_is_reported(self) -> None:
        result = analyze_bytes(build_glb([standard_body()]))
        self.assertIsNone(result["observed"]["hair"])
        self.assertTrue(any(line.startswith("hair:") for line in result["limits"]))

    def test_unknown_hair_override_raises(self) -> None:
        with self.assertRaises(ValueError):
            analyze_bytes(build_glb([standard_body()]), hair_mesh="Nope")

    def test_scalp_coverage_is_partial_for_a_few_cards(self) -> None:
        few = self.hair(_ring_of(3, lambda x, z: strip((x, 1.62, z), 0.2, 0.03, 1)))["observed"]["hair"]["scalp"]
        shell = self.hair(sphere(0.13, (0.0, 1.62, 0.0)))["observed"]["hair"]["scalp"]
        self.assertIsNotNone(few)
        self.assertLess(few["coverageShare"], shell["coverageShare"])


def _shift(geom: dict[str, Any], dx: float, dz: float) -> dict[str, Any]:
    out = dict(geom)
    out["positions"] = [(x + dx, y, z + dz) for (x, y, z) in geom["positions"]]
    return out


# --------------------------------------------------------------------------------------------
# Degenerate inputs
# --------------------------------------------------------------------------------------------


class DegenerateInputTests(unittest.TestCase):
    def test_glb_with_no_meshes_raises(self) -> None:
        data = build_glb([])
        with self.assertRaises(ValueError):
            analyze_bytes(data)

    def test_empty_mesh_does_not_crash_and_says_so(self) -> None:
        # Three vertices, zero indices: a mesh with positions but no triangles.
        empty = {"name": "Empty", "positions": [(0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.5, 0.1)], "normals": [], "uvs": [], "indices": []}
        result = analyze_bytes(build_glb([empty]))
        self.assertIsNone(result["observed"]["densityTopology"])
        self.assertIsNone(result["observed"]["symmetry"])
        self.assertIsNone(result["observed"]["garmentClearance"])
        self.assertTrue(any("no triangles" in line or "no skin mesh" in line for line in result["limits"]))

    def test_mesh_without_skin_still_measures_geometry(self) -> None:
        result = analyze_bytes(build_glb([dict(standard_body(), joints=None, weights=None)], with_skin=False))
        self.assertEqual(result["source"]["bodyMesh"]["name"], "Body")
        self.assertGreater(result["observed"]["densityTopology"]["weldedVertices"], 0)


# --------------------------------------------------------------------------------------------
# The real delivered character
# --------------------------------------------------------------------------------------------


@unittest.skipUnless(REAL_GLB.is_file(), f"real character GLB not found at {REAL_GLB} (set IMG2_NAMI_GLB to override)")
class RealCharacterTests(unittest.TestCase):
    def test_measured_construction_of_the_delivered_character(self) -> None:
        result = construction.analyze(REAL_GLB, max_garment_samples=3000)
        obs = result["observed"]
        # figure and body detection
        self.assertAlmostEqual(result["source"]["heightM"], 1.75, places=3)
        self.assertEqual(result["source"]["bodyMesh"]["name"], "Cube.020")
        self.assertEqual(result["source"]["bodyMesh"]["vertices"], 37771)
        self.assertEqual(result["source"]["bodyMesh"]["triangles"], 72144)
        self.assertEqual(result["source"]["meshInstances"], 23)

        # facial-feature-scale parts sit in the head band (y > 1.5 m = 0.857 H)
        roles = result["inferred"]["roles"]
        faces = [p for p in obs["parts"] if roles.get(p["mesh"], {}).get("role") == "face-detail"]
        self.assertGreaterEqual(len(faces), 4)
        self.assertTrue(all(p["bboxM"]["min"][1] > 1.5 for p in faces))

        # hair: one mesh found from geometry, built from tube-like clumps
        self.assertEqual(roles["NurbsPath.002"]["role"], "hair")
        self.assertEqual(obs["hair"]["connectedComponents"], 33)
        self.assertEqual(result["inferred"]["hair"]["hairType"], "tube strands")

        # bikini top sits a few millimetres off the skin, never inside it
        top = obs["garmentClearance"]["Vert.005"]
        self.assertEqual(top["negativeCount"], 0)
        self.assertTrue(2.5 < top["signedMm"]["median"] < 4.5, top["signedMm"])

        # the body mesh is bilaterally symmetric and its UVs are shared left/right
        self.assertLess(obs["symmetry"]["mirrorErrorMm"]["allVertices"]["p95"], 0.01)
        self.assertGreater(obs["symmetry"]["uvMirroring"]["sharedUvShare"], 0.9)

        # topology: a valence-6 dominated lattice
        t = obs["densityTopology"]
        self.assertTrue(0.80 < t["valence"]["interiorValence6Share"] < 0.87)
        self.assertEqual(t["weldedVertices"], 36076)

        # atlas and masks
        self.assertEqual(obs["uvAtlas"]["atlasPx"], [2048, 1024])
        self.assertEqual(len(obs["masks"]["maskNames"]), 9)
        self.assertLessEqual(obs["masks"]["sums"]["maxSumOfMasksAtAnyVertex"], 1.0 + 1e-4)
        self.assertEqual(obs["weights"]["skins"][0]["joints"], ["Root", "Pelvis", "Spine", "Head"])
        json.dumps(result, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
