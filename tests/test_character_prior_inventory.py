#!/usr/bin/env python3
"""Tests for the construction-prior inventory module and its CLI.

Every GLB here is synthesised in-process with the stdlib (real 12-byte header, JSON chunk, BIN
chunk), so the suite depends on no external asset, except ONE test that reads the delivered Nami
GLB and skips with a stated reason when it is absent (path from env IMG2_NAMI_GLB).

The synthetic figure is a 1.0 m tall tube "body" with two joints, a left-sided `_SOFT_CHEST_LEFT`
mask whose support/max/mean are known by construction, hair and a face detail, so the numbers the
module reports can be checked against numbers chosen here rather than against its own output. The
counter-examples are the point: a GLB with no skin, no meshes, weights that do not sum to one, a bind
pose that is not the rest pose, a mirrored mask layout, and a corrupt image header must each come out
different from the happy path.

Pure Python 3.10+ stdlib.
"""

from __future__ import annotations

import io
import json
import math
import os
import struct
import sys
import tempfile
import unittest
import zlib
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from character_prior import inventory  # noqa: E402
import extract_construction_prior as cli  # noqa: E402

NAMI_GLB = Path(os.environ.get("IMG2_NAMI_GLB") or Path.home() / ".img2/jobs/nami-sketchfab-8e496e5a/native/export/character.glb")

FLOAT, UBYTE, USHORT = 5126, 5121, 5123


# --------------------------------------------------------------------------------------------
# minimal GLB builder
# --------------------------------------------------------------------------------------------


def png_bytes(width: int, height: int, color_type: int = 2, bad_crc: bool = False) -> bytes:
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[color_type]
    raw = b"".join(b"\x00" + bytes(width * channels) for _ in range(height))

    def chunk(name: bytes, payload: bytes, corrupt: bool = False) -> bytes:
        crc = zlib.crc32(name + payload) & 0xFFFFFFFF
        if corrupt:
            crc ^= 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + name + payload + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr, bad_crc) + chunk(b"sRGB", b"\x00")
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def jpeg_bytes(width: int, height: int, progressive: bool = False) -> bytes:
    sof = struct.pack(">BHHB", 8, height, width, 3) + bytes([1, 0x22, 0, 2, 0x11, 1, 3, 0x11, 1])
    marker = 0xC2 if progressive else 0xC0
    return b"\xff\xd8" + b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + bytes(9) \
        + bytes([0xFF, marker]) + struct.pack(">H", 2 + len(sof)) + sof + b"\xff\xd9"


class Glb:
    """Accumulates accessors into one BIN chunk and renders a GLB."""

    def __init__(self) -> None:
        self.bin = bytearray()
        self.views: list[dict[str, Any]] = []
        self.accessors: list[dict[str, Any]] = []

    def view(self, data: bytes, target: int | None = None) -> int:
        while len(self.bin) % 4:
            self.bin.append(0)
        entry: dict[str, Any] = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(data)}
        if target:
            entry["target"] = target
        self.bin.extend(data)
        self.views.append(entry)
        return len(self.views) - 1

    def accessor(self, values: Sequence[Sequence[float]], ctype: int, kind: str, normalized: bool = False,
                 bounds: bool = False) -> int:
        fmt = {FLOAT: "f", UBYTE: "B", USHORT: "H"}[ctype]
        width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[kind]
        data = b"".join(struct.pack(f"<{width}{fmt}", *v) for v in values)
        entry: dict[str, Any] = {"bufferView": self.view(data), "componentType": ctype, "count": len(values), "type": kind}
        if normalized:
            entry["normalized"] = True
        if bounds and values:
            entry["min"] = [min(v[i] for v in values) for i in range(width)]
            entry["max"] = [max(v[i] for v in values) for i in range(width)]
        self.accessors.append(entry)
        return len(self.accessors) - 1

    def indices(self, tris: Sequence[tuple[int, int, int]]) -> int:
        return self.accessor([(i,) for tri in tris for i in tri], USHORT, "SCALAR")

    def render(self, document: dict[str, Any]) -> bytes:
        document = dict(document)
        document.setdefault("asset", {"version": "2.0", "generator": "test-builder"})
        document["accessors"] = self.accessors
        document["bufferViews"] = self.views
        document["buffers"] = [{"byteLength": len(self.bin)}]
        payload = json.dumps(document).encode("utf-8")
        payload += b" " * (-len(payload) % 4)
        bin_chunk = bytes(self.bin) + b"\x00" * (-len(self.bin) % 4)
        body = struct.pack("<II", len(payload), 0x4E4F534A) + payload
        if bin_chunk:
            body += struct.pack("<II", len(bin_chunk), 0x004E4942) + bin_chunk
        return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


def tube(y0: float, y1: float, rings: int, radius: float, cx: float = 0.0, cz: float = 0.0, sides: int = 4):
    """Closed-side tube: (positions, triangles). Vertices are ring-major."""
    pos = []
    for r in range(rings):
        y = y0 + (y1 - y0) * r / (rings - 1)
        for s in range(sides):
            a = 2 * math.pi * s / sides
            pos.append((cx + radius * math.cos(a), y, cz + radius * math.sin(a)))
    tris = []
    for r in range(rings - 1):
        for s in range(sides):
            a = r * sides + s
            b = r * sides + (s + 1) % sides
            c = a + sides
            d = b + sides
            tris += [(a, b, c), (b, d, c)]
    return pos, tris


def figure_glb(*, with_skin: bool = True, weight_sum: float = 1.0, mirror_mask: bool = False,
               bind_equals_rest: bool = True, png: bytes | None = None, extra_node_translation: bool = False) -> bytes:
    """A 1.0 m figure: body tube (0..0.95) + hair tube (0.80..1.0) + a small face detail at y ~0.9.

    Joints: Root at y=0, Spine at y=0.5 (child of Root). Tube vertices at ring r are 4 per ring; only the
    angle-0 vertex has x > 0 and only the angle-180 vertex has x < 0. `_SOFT_CHEST_LEFT` is 1.0 on the x > 0
    vertex of rings 18 and 19 and 0.5 on ring 17 (so support 3, max 1, mean over support 5/6, sum 2.5);
    `_SOFT_CHEST_RIGHT` is the mirror image on x < 0. `mirror_mask` swaps which side each name sits on.
    """
    g = Glb()
    body_pos, body_tris = tube(0.0, 0.95, 20, 0.1, sides=4)   # 80 vertices, 19*4*2 = 152 triangles

    def side_mask(positive_x: bool) -> list[tuple[float]]:
        values = []
        for i, (x, _y, _z) in enumerate(body_pos):
            ring = i // 4
            on_side = x > 1e-6 if positive_x else x < -1e-6
            values.append((1.0 if on_side and ring >= 18 else 0.5 if on_side and ring == 17 else 0.0,))
        return values

    mask_attr = {
        "_SOFT_CHEST_LEFT": g.accessor(side_mask(positive_x=mirror_mask is False), FLOAT, "SCALAR"),
        "_SOFT_CHEST_RIGHT": g.accessor(side_mask(positive_x=mirror_mask is True), FLOAT, "SCALAR"),
    }

    def skinned_attrs(pos: list[tuple[float, float, float]], joint_of) -> dict[str, int]:
        attrs = {"POSITION": g.accessor(pos, FLOAT, "VEC3", bounds=True),
                 "NORMAL": g.accessor([(0.0, 1.0, 0.0)] * len(pos), FLOAT, "VEC3"),
                 "TEXCOORD_0": g.accessor([(0.25, 0.25)] * len(pos), FLOAT, "VEC2")}
        if with_skin:
            attrs["JOINTS_0"] = g.accessor([(joint_of(p), 0, 0, 0) for p in pos], UBYTE, "VEC4")
            attrs["WEIGHTS_0"] = g.accessor([(weight_sum, 0.0, 0.0, 0.0)] * len(pos), FLOAT, "VEC4")
        return attrs

    body_attrs = {**mask_attr, **skinned_attrs(body_pos, lambda p: 0 if p[1] < 0.5 else 1)}
    hair_pos, hair_tris = tube(0.80, 1.0, 6, 0.12, sides=8)
    face_pos, face_tris = tube(0.88, 0.92, 2, 0.02, cz=0.1, sides=4)

    materials = [
        {"name": "Body skin dielectric", "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 0.5,
                                                                    "baseColorTexture": {"index": 0}}, "doubleSided": True},
        {"name": "Plain", "alphaMode": "BLEND"},
    ]
    meshes = [
        {"name": "BodyMesh", "primitives": [{"attributes": body_attrs, "indices": g.indices(body_tris), "material": 0}]},
        {"name": "HairMesh", "primitives": [{"attributes": skinned_attrs(hair_pos, lambda p: 1), "indices": g.indices(hair_tris), "material": 1}]},
        {"name": "Detail", "primitives": [{"attributes": skinned_attrs(face_pos, lambda p: 1), "indices": g.indices(face_tris), "material": 1}]},
    ]
    nodes: list[dict[str, Any]] = []
    scene_nodes = []
    mesh_node_base = 0
    if with_skin:
        nodes = [{"name": "Root", "children": [1]}, {"name": "Spine", "translation": [0, 0.5, 0]}]
        mesh_node_base = 2
    for i, mesh in enumerate(meshes):
        node: dict[str, Any] = {"name": ["Body", "Hair", "Detail"][i], "mesh": i}
        if with_skin:
            node["skin"] = 0
        nodes.append(node)
    scene_nodes = ([0] if with_skin else []) + list(range(mesh_node_base, mesh_node_base + 3))
    if extra_node_translation and not with_skin:
        nodes[mesh_node_base + 2]["translation"] = [0.0, 0.5, 0.0]

    doc: dict[str, Any] = {
        "scene": 0, "scenes": [{"nodes": scene_nodes}], "nodes": nodes, "meshes": meshes, "materials": materials,
        "extensionsUsed": ["KHR_materials_unlit"],
    }
    if png is not None:
        view = g.view(png)
        doc["images"] = [{"bufferView": view, "mimeType": "image/png", "name": "atlas"}]
        doc["samplers"] = [{"magFilter": 9729, "minFilter": 9987, "wrapS": 33071}]
        doc["textures"] = [{"source": 0, "sampler": 0}]
    else:
        materials[0]["pbrMetallicRoughness"].pop("baseColorTexture")
    if with_skin:
        ibm = [
            (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
            (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, -0.5 if bind_equals_rest else 0.0, 0, 1),
        ]
        doc["skins"] = [{"name": "Rig", "joints": [0, 1], "inverseBindMatrices": g.accessor(ibm, FLOAT, "MAT4")}]
        times = g.accessor([(0.0,), (1.0,), (2.0,)], FLOAT, "SCALAR", bounds=True)
        values = g.accessor([(0, 0, 0), (0, 0.1, 0), (0, 0, 0)], FLOAT, "VEC3")
        doc["animations"] = [{"name": "Bob", "samplers": [{"input": times, "output": values, "interpolation": "LINEAR"}],
                              "channels": [{"sampler": 0, "target": {"node": 1, "path": "translation"}}]}]
    return g.render(doc)


def write_tmp(data: bytes, suffix: str = ".glb") -> Path:
    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    handle.write(data)
    handle.close()
    return Path(handle.name)


class SyntheticBase(unittest.TestCase):
    def analyze(self, data: bytes, **options: Any) -> dict[str, Any]:
        path = write_tmp(data)
        self.addCleanup(path.unlink)
        return inventory.analyze(path, **options)

    @staticmethod
    def mesh(result: dict[str, Any], name: str) -> dict[str, Any]:
        return next(m for m in result["observed"]["meshes"] if m["name"] == name)

    @staticmethod
    def role(result: dict[str, Any], name: str) -> dict[str, Any]:
        return next(r for r in result["inferred"]["meshRoles"] if r["mesh"] == name)


# --------------------------------------------------------------------------------------------
# contract + happy path
# --------------------------------------------------------------------------------------------


class ContractAndMeasurements(SyntheticBase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.png = png_bytes(16, 8)
        cls.data = figure_glb(png=cls.png)
        path = write_tmp(cls.data)
        cls.path = path
        cls.result = inventory.analyze(path)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.path.unlink()

    def test_required_keys_and_json_serialisable(self) -> None:
        for key in ("schema", "observed", "inferred", "limits"):
            self.assertIn(key, self.result)
        self.assertEqual(self.result["schema"], inventory.SCHEMA)
        self.assertIsInstance(self.result["limits"], list)
        text = json.dumps(self.result, allow_nan=False)  # NaN/inf would raise here
        self.assertGreater(len(text), 1000)

    def test_file_facts_are_measured(self) -> None:
        import hashlib
        file = self.result["observed"]["file"]
        self.assertEqual(file["bytes"], len(self.data))
        self.assertEqual(file["sha256"], hashlib.sha256(self.data).hexdigest())
        self.assertEqual(file["gltfVersion"], "2.0")
        self.assertEqual(file["generator"], "test-builder")
        self.assertEqual(file["extensionsUsed"], ["KHR_materials_unlit"])
        self.assertEqual(file["counts"]["meshes"], 3)
        self.assertEqual(file["counts"]["bufferViews"], len(json.loads(self._json_chunk())["bufferViews"]))

    def _json_chunk(self) -> str:
        length, = struct.unpack_from("<I", self.data, 12)
        return self.data[20:20 + length].decode("utf-8")

    def test_height_comes_from_mesh_bounds_with_source(self) -> None:
        height = self.result["observed"]["figureHeight"]
        self.assertAlmostEqual(height["heightM"], 1.0, places=5)
        self.assertEqual(height["heightSource"], "meshWorldBoundsYExtent")
        self.assertAlmostEqual(height["floorYM"], 0.0, places=5)
        self.assertTrue(height["crossCheck"]["agreesWithHeightM"])
        # caller-supplied H overrides, and says so
        other = self.analyze(self.data, figure_height=2.0)
        self.assertEqual(other["observed"]["figureHeight"]["heightSource"], "callerSupplied")
        self.assertAlmostEqual(self.mesh(other, "BodyMesh")["bounds"]["maxFrac"][1], 0.475, places=4)

    def test_mesh_counts_and_fractions(self) -> None:
        body = self.mesh(self.result, "BodyMesh")
        self.assertEqual(body["vertexCount"], 80)
        self.assertEqual(body["triangleCount"], 152)
        self.assertAlmostEqual(body["bounds"]["maxM"][1], 0.95, places=5)
        self.assertAlmostEqual(body["bounds"]["maxFrac"][1], 0.95, places=5)  # H = 1.0 so frac == metres
        self.assertEqual(body["nodeName"], "Body")
        self.assertTrue(body["skinned"])
        self.assertEqual(body["morphTargetCount"], 0)
        shares = [m["triangleShare"] for m in self.result["observed"]["meshes"]]
        self.assertAlmostEqual(sum(shares), 1.0, places=4)
        total = sum(m["triangleCount"] for m in self.result["observed"]["meshes"])
        self.assertEqual(self.result["observed"]["budgets"]["totalTriangles"], total)
        semantics = {a["semantic"]: a for a in body["primitives"][0]["attributes"]}
        self.assertEqual(semantics["JOINTS_0"]["componentType"], "UNSIGNED_BYTE")
        self.assertEqual(semantics["POSITION"]["type"], "VEC3")
        self.assertGreater(body["surfaceAreaM2"], 0)
        self.assertEqual(body["degenerateTriangles"], 0)

    def test_soft_mask_statistics_match_construction(self) -> None:
        mask = self.mesh(self.result, "BodyMesh")["customAttributes"]["_SOFT_CHEST_LEFT"]
        # ring 19 and 18: x>0 vertices per ring = 1 (4-sided tube: angle 0 only has x>0 strictly) -> computed below
        self.assertEqual(mask["count"], 80)
        self.assertEqual(mask["supportCount"], 3)           # rings 17 (0.5), 18 (1.0), 19 (1.0): one x>0 vertex each
        self.assertAlmostEqual(mask["max"], 1.0)
        self.assertAlmostEqual(mask["meanOverSupport"], (0.5 + 1.0 + 1.0) / 3, places=5)
        self.assertAlmostEqual(mask["sum"], 2.5, places=3)
        self.assertEqual(mask["saturatedCount"], 2)
        self.assertGreater(mask["weightedCentroidM"][0], 0.0)    # left mask sits on +x
        self.assertGreater(mask["weightedCentroidFrac"][1], 0.85)
        self.assertEqual(mask["type"], "SCALAR")

    def test_conventions_come_from_mask_placement(self) -> None:
        conv = self.result["inferred"]["conventions"]
        self.assertEqual(conv["characterLeft"]["value"], "+X")
        self.assertIn("LEFT", conv["characterLeft"]["basis"])
        self.assertEqual(conv["upAxis"]["value"], "+Y")
        self.assertTrue(conv["units"]["heightIsHumanScale"])

    def test_roles_carry_a_basis_and_use_names_then_geometry(self) -> None:
        self.assertEqual(self.role(self.result, "BodyMesh")["role"], "skin-body")
        hair = self.role(self.result, "HairMesh")
        self.assertEqual(hair["role"], "hair")
        self.assertIn("hair", hair["basis"])
        detail = self.role(self.result, "Detail")
        self.assertEqual(detail["role"], "face-detail")          # no name hint: geometry (small, in head band)
        self.assertIn("head band", detail["basis"])
        for rec in self.result["inferred"]["meshRoles"]:
            self.assertTrue(rec["basis"])
        by_role = self.result["inferred"]["budgetsByRole"]["roles"]
        self.assertAlmostEqual(sum(r["triangleShare"] for r in by_role.values()), 1.0, places=4)
        self.assertEqual(self.result["inferred"]["bodyMesh"]["mesh"], "BodyMesh")

    def test_body_override_and_unknown_name(self) -> None:
        other = self.analyze(self.data, body_mesh="HairMesh")
        self.assertEqual(self.role(other, "HairMesh")["role"], "skin-body")
        self.assertTrue(other["inferred"]["bodyMesh"]["override"])
        self.assertNotEqual(self.role(other, "BodyMesh")["role"], "skin-body")
        with self.assertRaises(ValueError) as caught:
            self.analyze(self.data, body_mesh="NoSuchMesh")
        self.assertIn("NoSuchMesh", str(caught.exception))

    def test_materials_textures_images_and_sampler(self) -> None:
        materials = self.result["observed"]["materials"]
        body_mat = materials[0]
        self.assertEqual(body_mat["metallicFactor"], 0.0)
        self.assertEqual(body_mat["roughnessFactor"], 0.5)
        self.assertTrue(body_mat["doubleSided"])
        self.assertEqual(body_mat["alphaMode"], "OPAQUE")
        self.assertEqual(body_mat["textures"]["baseColorTexture"]["image"], 0)
        self.assertEqual(body_mat["usedByMeshes"], ["BodyMesh"])
        self.assertEqual(materials[1]["alphaMode"], "BLEND")
        self.assertFalse(materials[1]["metallicFactorExplicit"])      # glTF default 1.0 is reported as default, not as authored
        image = self.result["observed"]["images"][0]
        self.assertEqual((image["format"], image["width"], image["height"]), ("png", 16, 8))
        self.assertEqual((image["bitDepth"], image["colorType"], image["colorTypeName"]), (8, 2, "truecolour"))
        self.assertTrue(image["ihdrCrcOk"])
        self.assertEqual(image["byteSize"], len(self.png))
        self.assertEqual(image["usedByTextures"], [0])
        sampler = self.result["observed"]["samplers"][0]
        self.assertEqual((sampler["magFilter"], sampler["minFilter"], sampler["wrapS"], sampler["wrapT"]),
                         ("LINEAR", "LINEAR_MIPMAP_LINEAR", "CLAMP_TO_EDGE", "REPEAT"))

    def test_skin_rig_and_animation(self) -> None:
        skin = self.result["observed"]["skin"]
        self.assertEqual(skin["skinCount"], 1)
        rig = skin["skins"][0]
        self.assertEqual([j["name"] for j in rig["joints"]], ["Root", "Spine"])
        spine = rig["joints"][1]
        self.assertEqual(spine["parentName"], "Root")
        self.assertAlmostEqual(spine["restPositionM"][1], 0.5, places=5)
        self.assertAlmostEqual(spine["restPositionFrac"][1], 0.5, places=5)
        self.assertAlmostEqual(spine["boneLengthM"], 0.5, places=5)
        self.assertTrue(rig["restCancellation"]["bindPoseEqualsRestPose"])
        clip = skin["animations"][0]
        self.assertEqual((clip["name"], clip["channelCount"]), ("Bob", 1))
        self.assertAlmostEqual(clip["durationS"], 2.0)
        self.assertEqual(clip["perBone"][0]["name"], "Spine")
        self.assertEqual(clip["perBone"][0]["paths"]["translation"]["keys"], 3)

    def test_influence_statistics(self) -> None:
        inf = self.mesh(self.result, "BodyMesh")["skinInfluence"]
        self.assertEqual(inf["maxInfluencesPerVertex"], 1)
        self.assertEqual(inf["weightSumWithinToleranceOfOneFraction"], 1.0)
        self.assertEqual(inf["unweightedVertexCount"], 0)
        bones = {b["name"]: b["vertices"] for b in inf["bones"]}
        self.assertEqual(sum(bones.values()), 80)
        self.assertEqual(set(bones), {"Root", "Spine"})
        carried = self.result["observed"]["skin"]["skins"][0]["joints"][1]["carriesMeshes"]
        self.assertIn("HairMesh", [c["mesh"] for c in carried])


# --------------------------------------------------------------------------------------------
# counter-examples
# --------------------------------------------------------------------------------------------


class CounterExamples(SyntheticBase):
    def test_no_skin_is_reported_not_invented(self) -> None:
        result = self.analyze(figure_glb(with_skin=False))
        skin = result["observed"]["skin"]
        self.assertEqual(skin["skinCount"], 0)
        self.assertIsNotNone(skin["structuralFailure"])
        body = self.mesh(result, "BodyMesh")
        self.assertFalse(body["skinned"])
        self.assertNotIn("skinInfluence", body)
        self.assertEqual(result["observed"]["budgets"]["jointCount"], 0)
        self.assertTrue(any("no skin" in limit for limit in result["limits"]))
        self.assertEqual(result["observed"]["skin"]["skins"], [])
        # body is still found, from vertices/masks/material rather than from skinning
        self.assertEqual(result["inferred"]["bodyMesh"]["mesh"], "BodyMesh")

    def test_empty_gltf_has_no_height_and_null_fractions(self) -> None:
        data = Glb().render({"scenes": [{"nodes": []}], "nodes": [], "meshes": []})
        result = self.analyze(data)
        self.assertIsNone(result["observed"]["figureHeight"]["heightM"])
        self.assertIsNone(result["observed"]["figureHeight"]["heightSource"])
        self.assertEqual(result["observed"]["meshes"], [])
        self.assertEqual(result["observed"]["budgets"]["totalTriangles"], 0)
        self.assertIsNone(result["observed"]["sceneBounds"])
        self.assertIsNone(result["inferred"]["bodyMesh"]["mesh"])
        self.assertTrue(any("height" in limit.lower() for limit in result["limits"]))
        json.dumps(result, allow_nan=False)

    def test_mesh_without_vertices_is_not_a_body_and_has_null_bounds(self) -> None:
        g = Glb()
        doc = {"scenes": [{"nodes": [0]}], "nodes": [{"name": "Empty", "mesh": 0}],
               "meshes": [{"name": "Hollow", "primitives": [{"attributes": {"POSITION": g.accessor([], FLOAT, "VEC3")}}]}]}
        result = self.analyze(g.render(doc))
        mesh = self.mesh(result, "Hollow")
        self.assertEqual((mesh["vertexCount"], mesh["triangleCount"]), (0, 0))
        self.assertIsNone(mesh["bounds"])
        self.assertIsNone(result["observed"]["figureHeight"]["heightM"])
        self.assertEqual(self.role(result, "Hollow")["role"], "unknown")

    def test_weights_that_do_not_sum_to_one_are_counted(self) -> None:
        result = self.analyze(figure_glb(weight_sum=0.5))
        inf = self.mesh(result, "BodyMesh")["skinInfluence"]
        self.assertEqual(inf["weightSumWithinToleranceOfOneFraction"], 0.0)
        self.assertAlmostEqual(inf["weightSumMax"], 0.5)
        healthy = self.analyze(figure_glb())
        self.assertEqual(self.mesh(healthy, "BodyMesh")["skinInfluence"]["weightSumWithinToleranceOfOneFraction"], 1.0)
        zero = self.analyze(figure_glb(weight_sum=0.0))
        self.assertEqual(self.mesh(zero, "BodyMesh")["skinInfluence"]["unweightedVertexCount"], 80)

    def test_bind_pose_that_is_not_the_rest_pose_is_flagged(self) -> None:
        bad = self.analyze(figure_glb(bind_equals_rest=False))
        cancellation = bad["observed"]["skin"]["skins"][0]["restCancellation"]
        self.assertFalse(cancellation["bindPoseEqualsRestPose"])
        self.assertAlmostEqual(cancellation["maxAbsError"], 0.5, places=5)
        good = self.analyze(figure_glb())
        self.assertTrue(good["observed"]["skin"]["skins"][0]["restCancellation"]["bindPoseEqualsRestPose"])

    def test_mirrored_mask_flips_the_left_axis(self) -> None:
        normal = self.analyze(figure_glb())
        mirrored = self.analyze(figure_glb(mirror_mask=True))
        self.assertEqual(normal["inferred"]["conventions"]["characterLeft"]["value"], "+X")
        self.assertEqual(mirrored["inferred"]["conventions"]["characterLeft"]["value"], "-X")
        left_x = self.mesh(mirrored, "BodyMesh")["customAttributes"]["_SOFT_CHEST_LEFT"]["weightedCentroidM"][0]
        self.assertLess(left_x, 0.0)

    def test_unskinned_mesh_uses_its_node_transform_skinned_does_not(self) -> None:
        moved = self.analyze(figure_glb(with_skin=False, extra_node_translation=True))
        base = self.analyze(figure_glb(with_skin=False))
        d_moved = self.mesh(moved, "Detail")["bounds"]["minM"][1]
        d_base = self.mesh(base, "Detail")["bounds"]["minM"][1]
        self.assertAlmostEqual(d_moved - d_base, 0.5, places=5)
        # H follows the world bounds: the moved detail now tops out at 1.42 m
        self.assertAlmostEqual(moved["observed"]["figureHeight"]["heightM"], 1.42, places=4)
        self.assertAlmostEqual(base["observed"]["figureHeight"]["heightM"], 1.0, places=4)

    def test_not_a_glb_raises(self) -> None:
        path = write_tmp(b"not a glb at all, but longer than twelve bytes")
        self.addCleanup(path.unlink)
        with self.assertRaises(ValueError):
            inventory.analyze(path)

    def test_corrupt_png_crc_and_non_png_are_reported(self) -> None:
        bad = inventory.decode_png_header(png_bytes(4, 4, bad_crc=True))
        self.assertFalse(bad["ihdrCrcOk"])
        self.assertEqual((bad["width"], bad["height"]), (4, 4))
        self.assertEqual(inventory.decode_png_header(b"GIF89a....")["format"], "unknown")
        rgba = inventory.decode_png_header(png_bytes(5, 3, color_type=6))
        self.assertEqual((rgba["colorTypeName"], rgba["channels"], rgba["hasAlphaChannel"]), ("truecolour+alpha", 4, True))
        truncated = inventory.decode_png_header(png_bytes(4, 4)[:20])
        self.assertIn("error", truncated)

    def test_jpeg_header(self) -> None:
        header = inventory.decode_jpeg_header(jpeg_bytes(640, 480))
        self.assertEqual((header["format"], header["width"], header["height"], header["channels"]), ("jpeg", 640, 480, 3))
        self.assertFalse(header["progressive"])
        self.assertTrue(inventory.decode_jpeg_header(jpeg_bytes(8, 8, progressive=True))["progressive"])
        self.assertIn("error", inventory.decode_jpeg_header(b"\xff\xd8\xff\xd9"))
        self.assertEqual(inventory.decode_jpeg_header(b"nope")["format"], "unknown")

    def test_role_words_do_not_fire_on_unrelated_names(self) -> None:
        tokens = inventory._tokens("Cube.020", "Body")
        self.assertIsNone(inventory._token_hit(tokens, inventory._HAIR_WORDS))
        self.assertEqual(inventory._token_hit(inventory._tokens("beltcharm"), inventory._PROP_WORDS), "beltcharm")
        self.assertEqual(inventory._token_hit(inventory._tokens("BikiniTop"), inventory._GARMENT_WORDS), "bikini")


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------


class CommandLine(SyntheticBase):
    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_skipping_two_modules_writes_the_merged_document(self) -> None:
        glb = write_tmp(figure_glb(png=png_bytes(8, 8)))
        self.addCleanup(glb.unlink)
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "nested" / "prior.json"
            code, stdout, stderr = self.run_cli("--glb", str(glb), "--out", str(out_path), "--skip", "anatomy", "--skip", "construction")
            self.assertEqual((code, stderr), (0, ""))
            prior = json.loads(out_path.read_text())
        self.assertLessEqual(len(stdout.strip().splitlines()), 20)
        self.assertEqual(prior["schema"], "img2.character-construction-prior/1")
        for key in ("source", "inventory", "anatomy", "construction", "generatedBy"):
            self.assertIn(key, prior)
        self.assertIsNone(prior["anatomy"])
        self.assertIsNone(prior["construction"])
        self.assertEqual(prior["skipped"], ["anatomy", "construction"])
        self.assertEqual(prior["source"]["bytes"], glb.stat().st_size)
        self.assertEqual(prior["source"]["sha256"], prior["inventory"]["observed"]["file"]["sha256"])
        self.assertAlmostEqual(prior["source"]["heightM"], 1.0, places=5)
        self.assertEqual(prior["source"]["heightSource"], "meshWorldBoundsYExtent")

    def test_output_cannot_overwrite_the_source_or_an_alias(self) -> None:
        original = figure_glb()
        with tempfile.TemporaryDirectory() as tmp:
            glb = Path(tmp) / "source.glb"
            glb.write_bytes(original)
            symlink = Path(tmp) / "symlink.json"
            symlink.symlink_to(glb)
            hardlink = Path(tmp) / "hardlink.json"
            os.link(glb, hardlink)
            for output in (glb, symlink, hardlink):
                code, _, _ = self.run_cli("--glb", str(glb), "--out", str(output),
                                          "--skip", "anatomy", "--skip", "construction")
                self.assertEqual(code, 2)
                self.assertEqual(glb.read_bytes(), original)

    def test_missing_glb_and_bad_glb_exit_2(self) -> None:
        code, _, err = self.run_cli("--glb", "/nonexistent/none.glb", "--skip", "anatomy", "--skip", "construction")
        self.assertEqual(code, 2)
        self.assertIn("not found", err)
        bad = write_tmp(b"definitely not a glb, but more than 12 bytes")
        self.addCleanup(bad.unlink)
        code, _, err = self.run_cli("--glb", str(bad), "--skip", "anatomy", "--skip", "construction")
        self.assertEqual(code, 2)
        self.assertIn("inventory", err)

    def test_missing_module_fails_loudly_by_name(self) -> None:
        with self.assertRaises(RuntimeError) as caught:
            cli.load_module("no_such_analysis_module")
        self.assertIn("no_such_analysis_module", str(caught.exception))
        self.assertIn("missing", str(caught.exception))


# --------------------------------------------------------------------------------------------
# the real subject
# --------------------------------------------------------------------------------------------


@unittest.skipUnless(NAMI_GLB.is_file(), f"delivered Nami GLB not present at {NAMI_GLB} (set IMG2_NAMI_GLB)")
class DeliveredNami(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = inventory.analyze(NAMI_GLB)

    def test_facts_verified_by_running_the_module(self) -> None:
        observed = self.result["observed"]
        self.assertAlmostEqual(observed["figureHeight"]["heightM"], 1.75, places=3)
        self.assertEqual(observed["file"]["counts"]["meshes"], 23)
        self.assertEqual(observed["file"]["counts"]["nodes"], 28)
        self.assertEqual(observed["budgets"]["jointCount"], 4)
        body = next(m for m in observed["meshes"] if m["name"] == "Cube.020")
        self.assertEqual((body["vertexCount"], body["triangleCount"]), (37771, 72144))
        self.assertEqual(self.result["inferred"]["bodyMesh"]["mesh"], "Cube.020")
        self.assertEqual(len([n for n in body["customAttributes"] if n.startswith("_SOFT_")]), 9)
        self.assertEqual(body["skinInfluence"]["maxInfluencesPerVertex"], 2)
        self.assertEqual(observed["images"][0]["width"], 2048)
        self.assertEqual(observed["images"][0]["height"], 1024)
        self.assertEqual(self.result["inferred"]["conventions"]["characterLeft"]["value"], "+X")

    def test_face_detail_meshes_sit_above_1_5_m(self) -> None:
        by_name = {m["name"]: m for m in self.result["observed"]["meshes"]}
        faces = [r for r in self.result["inferred"]["meshRoles"] if r["role"] == "face-detail"]
        self.assertGreaterEqual(len(faces), 4)
        for rec in faces:
            self.assertGreater(by_name[rec["mesh"]]["centroidM"][1], 1.5, rec["mesh"])
        self.assertTrue({"Cube.021", "Cube.023", "Cube.024", "Cube.025"} <= {r["mesh"] for r in faces})

    def test_cli_on_real_glb_skipping_other_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "prior.json"
            out = io.StringIO()
            with redirect_stdout(out):
                code = cli.main(["--glb", str(NAMI_GLB), "--out", str(out_path), "--skip", "anatomy", "--skip", "construction"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out_path.read_text())["source"]["heightM"], 1.75)


if __name__ == "__main__":
    unittest.main()
