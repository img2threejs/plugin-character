"""Anatomy of a character GLB: proportions, silhouette, face layout and atlas mapping, measured.

Second of the three construction-prior modules (`inventory`, `anatomy`, `construction`). It reads the
main skin mesh and the small face-detail meshes and answers "how is this figure proportioned and
where does the face sit on the head and in the texture atlas".

    analyze(glb_path, body_mesh=None, figure_height=None, bands=100) -> dict

Required top-level keys: `schema`, `observed` (measured numbers), `inferred` (heuristic
classifications, each with a `basis` and a `confidence`), `limits` (what silhouette-only geometry
cannot establish). Module-specific keys: `figure`, `silhouette`, `head`, `face`, `atlas`.

Conventions
-----------
* Metres, Y-up. `...Frac` is a fraction of the figure height H; Y fractions are floor-relative
  `(y - floorY) / H`, floorY being the lowest vertex of any mesh in the file.
* The figure is assumed to face +Z (glTF's forward). With that, character-left is +X. The assumption
  is cross-checked against the face-detail meshes and recorded in `observed.facing`.
* Positions come from the buffers. A skinned mesh is read in its stored (bind) space -- glTF ignores
  the node transform of a skinned mesh -- and `observed.restPose` says whether that space equals the
  rest pose (`jointWorld * inverseBind == I`). Unskinned meshes use their node's world matrix.
* Head-relative face coordinates: x = (X - midline) / headWidth, y = (Y - chin) / headHeight (0 chin,
  1 head top), z = (Z - headBackZ) / headDepth. Head dimensions are those of the skin mesh above the
  chin, i.e. WITHOUT hair; the hair-inclusive bounds are reported separately.

Heuristics are never reported as observations. Everything found by a rule (chin, shoulder line, knee,
feature roles) sits under `inferred` with the rule written out; a feature that cannot be found is
`None`, with the reason in `limits`.

Pure Python 3.10+ stdlib, no numpy. Spatial hashing keeps every neighbour query O(1).
"""

from __future__ import annotations

import base64
import math
import struct
import sys
import zlib
from dataclasses import dataclass, field
from itertools import accumulate
from pathlib import Path
from typing import Any, Sequence

_TOOLS_DIR = str(Path(__file__).resolve().parent.parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import rig_glb_reference as rgr  # noqa: E402

SCHEMA = "img2.character-prior.anatomy/1"

DEFAULT_BANDS = 100
# Torso/arm separation: consecutive |x - midline| values in a height band further apart than this
# (as a fraction of H) start a new lateral cluster (an arm). 0.0075 H = 1.3 cm on a 1.75 m figure.
ARM_GAP_FRAC = 0.0075
# A band whose nearest vertex to the midline is further than this (fraction of H) has a visible
# gap between the legs.
LEG_GAP_FRAC = 0.003
# Minimum vertices beyond the torso cluster for a band to count as having a separate arm.
LATERAL_MIN_COUNT = 5
# The neck is searched for between these floor-relative fractions of H and (skin top - this).
NECK_SEARCH_LOW_FRAC = 0.65
NECK_SEARCH_TOP_MARGIN_FRAC = 0.06
# Chin = lowest central vertex whose z exceeds the neck's front by this multiple of the neck width.
CHIN_FORWARD_NECK_WIDTHS = 0.5
# Knee hollow must stand this far (fraction of H) above the calf's rear bulge to be accepted.
KNEE_PROMINENCE_FRAC = 0.012
# Ankle: a lower band must be at least this much larger in cross-section than the narrowest one.
ANKLE_FLARE_RATIO = 1.15
# T-pose arm trimming: a band belongs to the arms when its half-width is at least this multiple of the
# shoulder half-width; such bands are cut at TRIM_SHOULDER_RATIO x the shoulder half-width.
ARM_BAND_HALF_WIDTH_RATIO = 1.5
TRIM_SHOULDER_RATIO = 1.05
# Pose classes by arm angle from vertical (degrees).
T_POSE_MIN_DEG = 75.0
A_POSE_MIN_DEG = 20.0
# A detail mesh is "in the head" when its bbox lies in the head box grown by this fraction.
HEAD_BOX_MARGIN = 0.15
# Two halves of a feature are "separate" (a pair) when the gap about the midline exceeds this
# fraction of head width.
PAIR_GAP_HEAD_FRAC = 0.03
# Mirror-match search cell, fractions of H.
BODY_MIRROR_CELL_FRAC = 0.0025
FEATURE_MIRROR_CELL_FRAC = 0.0012
# Pixel sampling budget per region, and palette size.
PIXEL_SAMPLE_BUDGET = 40000
PALETTE_SIZE = 5


# --------------------------------------------------------------------------------------------
# Small numeric helpers
# --------------------------------------------------------------------------------------------


def _frac(value: float | None, height: float) -> float | None:
    return None if value is None or not height else value / height


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0


def _percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))]


def _bbox(points: Sequence[Sequence[float]]) -> tuple[list[float], list[float]] | None:
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return [min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]


def _jsonable(value: Any) -> Any:
    """Round floats, drop non-finite numbers and tuples so the result is strict JSON."""
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        return round(value, 6) if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return str(value)


def _lm(y: float | None, floor: float, height: float, basis: str, confidence: str) -> dict[str, Any] | None:
    """A landmark entry: height in metres and as a floor-relative fraction of H."""
    if y is None:
        return None
    return {"yM": y, "yFrac": (y - floor) / height, "basis": basis, "confidence": confidence}


# --------------------------------------------------------------------------------------------
# Geometry collection
# --------------------------------------------------------------------------------------------


@dataclass
class _Part:
    """One mesh primitive instance, with positions in the space the figure is measured in."""

    mesh_name: str
    node_name: str
    node_index: int
    mesh_index: int
    prim_index: int
    skinned: bool
    material: int | None
    attributes: dict[str, int]
    indices_accessor: int | None
    mode: int | None
    positions: list[tuple[float, float, float]]
    soft_attributes: tuple[str, ...] = ()
    lit_dielectric: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return self.mesh_name


def _is_identity(matrix: Sequence[float], tolerance: float = 1e-9) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(matrix, rgr.IDENTITY_MATRIX))


def _material_is_lit_dielectric(document: dict[str, Any], index: int | None) -> bool:
    materials = document.get("materials", [])
    if index is None or not isinstance(materials, list) or not 0 <= index < len(materials):
        return False
    material = materials[index] if isinstance(materials[index], dict) else {}
    extensions = material.get("extensions", {})
    if isinstance(extensions, dict) and "KHR_materials_unlit" in extensions:
        return False
    pbr = material.get("pbrMetallicRoughness", {})
    metallic = pbr.get("metallicFactor", 1.0) if isinstance(pbr, dict) else 1.0
    return float(metallic) <= 0.1


def _collect_parts(
    document: dict[str, Any], bin_payload: bytes, world: Sequence[Sequence[float]], limits: list[str]
) -> list[_Part]:
    nodes = document.get("nodes", [])
    nodes = nodes if isinstance(nodes, list) else []
    meshes = document.get("meshes", [])
    meshes = meshes if isinstance(meshes, list) else []
    parts: list[_Part] = []
    for node_index, node in enumerate(nodes):
        if not isinstance(node, dict) or "mesh" not in node:
            continue
        mesh_index = int(node["mesh"])
        if not 0 <= mesh_index < len(meshes) or not isinstance(meshes[mesh_index], dict):
            continue
        mesh = meshes[mesh_index]
        primitives = mesh.get("primitives", []) or []
        skinned = "skin" in node
        matrix = world[node_index] if node_index < len(world) else rgr.IDENTITY_MATRIX
        for prim_index, primitive in enumerate(primitives):
            if not isinstance(primitive, dict):
                continue
            attributes = primitive.get("attributes", {})
            if not isinstance(attributes, dict) or "POSITION" not in attributes:
                continue
            name = str(mesh.get("name") or f"mesh{mesh_index}")
            if len(primitives) > 1:
                name = f"{name}#{prim_index}"
            try:
                raw = rgr.read_accessor(document, bin_payload, int(attributes["POSITION"]))
            except ValueError as err:
                limits.append(f"mesh {name!r}: POSITION accessor unreadable ({err}); excluded")
                continue
            if not skinned and not _is_identity(matrix):
                m = matrix
                raw = [
                    (
                        m[0] * p[0] + m[4] * p[1] + m[8] * p[2] + m[12],
                        m[1] * p[0] + m[5] * p[1] + m[9] * p[2] + m[13],
                        m[2] * p[0] + m[6] * p[1] + m[10] * p[2] + m[14],
                    )
                    for p in raw
                ]
            material = primitive.get("material")
            material = int(material) if isinstance(material, int) else None
            parts.append(
                _Part(
                    mesh_name=name,
                    node_name=str(node.get("name", f"node{node_index}")),
                    node_index=node_index,
                    mesh_index=mesh_index,
                    prim_index=prim_index,
                    skinned=skinned,
                    material=material,
                    attributes={k: int(v) for k, v in attributes.items() if isinstance(v, int)},
                    indices_accessor=primitive.get("indices") if isinstance(primitive.get("indices"), int) else None,
                    mode=primitive.get("mode"),
                    positions=[(p[0], p[1], p[2]) for p in raw],
                    soft_attributes=tuple(sorted(k for k in attributes if k.startswith("_SOFT_"))),
                    lit_dielectric=_material_is_lit_dielectric(document, material),
                )
            )
    return parts


def _select_body(parts: Sequence[_Part], body_mesh: str | None) -> tuple[_Part, str, list[dict[str, Any]]]:
    candidates = [p for p in parts if p.positions]
    if not candidates:
        raise ValueError("GLB has no mesh with vertices; nothing to measure")
    scoreboard = sorted(
        candidates,
        key=lambda p: (p.skinned, len(p.soft_attributes), p.lit_dielectric, len(p.positions)),
        reverse=True,
    )
    board = [
        {
            "mesh": p.mesh_name,
            "node": p.node_name,
            "skinned": p.skinned,
            "softAttributeCount": len(p.soft_attributes),
            "litDielectricMaterial": p.lit_dielectric,
            "vertexCount": len(p.positions),
        }
        for p in scoreboard[:5]
    ]
    if body_mesh is not None:
        for p in candidates:
            if body_mesh in (p.mesh_name, p.node_name):
                return p, f"caller override body_mesh={body_mesh!r}", board
        names = sorted({p.mesh_name for p in candidates})
        raise ValueError(f"body_mesh {body_mesh!r} matches no mesh or node name; meshes: {names}")
    best = scoreboard[0]
    if best.skinned:
        basis = (
            "autodetected: skinned mesh ranked by (number of _SOFT_* mask attributes, lit dielectric "
            "material, vertex count)"
        )
    else:
        basis = "autodetected: the file has no skinned mesh, so the largest mesh by vertex count"
    return best, basis, board


# --------------------------------------------------------------------------------------------
# Silhouette bands and landmarks
# --------------------------------------------------------------------------------------------


def _band_of(y: float, floor: float, height: float, n: int) -> int:
    i = int((y - floor) / height * n)
    return 0 if i < 0 else (n - 1 if i >= n else i)


def _central_run(items: list[tuple[float, float, float]], gap: float) -> tuple[int, int]:
    """Half-open index range of the cluster nearest the midline in |dx|-sorted items.

    Runs are maximal stretches whose consecutive |dx| differ by at most `gap`. The first run with
    three or more members wins, so a lone seam vertex at the midline does not stand in for the torso.
    """
    start = 0
    for i in range(1, len(items) + 1):
        if i == len(items) or items[i][0] - items[i - 1][0] > gap:
            if i - start >= 3 or i == len(items):
                return start, i
            start = i
    return 0, len(items)


def _densify(
    points: Sequence[Sequence[float]], triangles: Sequence[tuple[int, int, int]], step: float
) -> list[tuple[float, float, float]]:
    """Vertices plus points along every triangle edge, at most `step` apart.

    Limb meshes are low-poly (rings of a dozen vertices every few centimetres), so a band of raw
    vertices has holes a silhouette does not. Edge samples lie on the mesh surface and fill them, so a
    gap seen in a band is a gap in the figure and not a gap in the tessellation.
    """
    samples: list[tuple[float, float, float]] = [(p[0], p[1], p[2]) for p in points]
    seen: set[tuple[int, int]] = set()
    for a, b, c in triangles:
        for u, v in ((a, b), (b, c), (c, a)):
            key = (u, v) if u < v else (v, u)
            if key in seen:
                continue
            seen.add(key)
            pu, pv = points[key[0]], points[key[1]]
            dx, dy, dz = pv[0] - pu[0], pv[1] - pu[1], pv[2] - pu[2]
            pieces = int(math.sqrt(dx * dx + dy * dy + dz * dz) / step)
            for k in range(1, pieces + 1):
                t = k / (pieces + 1)
                samples.append((pu[0] + dx * t, pu[1] + dy * t, pu[2] + dz * t))
    return samples


def _band_rows(
    points: Sequence[Sequence[float]],
    samples: Sequence[Sequence[float]],
    floor: float,
    height: float,
    n: int,
    mid: float,
    gap: float,
) -> list[dict[str, Any] | None]:
    """Per-band silhouette statistics. `count` is real vertices; every extent comes from `samples`."""
    counts = [0] * n
    for p in points:
        counts[_band_of(p[1], floor, height, n)] += 1
    members: list[list[int]] = [[] for _ in range(n)]
    for j, p in enumerate(samples):
        members[_band_of(p[1], floor, height, n)].append(j)
    rows: list[dict[str, Any] | None] = []
    for band, mem in enumerate(members):
        if not mem:
            rows.append(None)
            continue
        items = sorted(((abs(samples[j][0] - mid), samples[j][0] - mid, samples[j][2]) for j in mem))
        start, end = _central_run(items, gap)
        run = items[start:end]
        rows.append(
            {
                "count": counts[band],
                "sampleCount": len(items),
                "_members": mem,
                "minX": min(it[1] for it in items),
                "maxX": max(it[1] for it in items),
                "minZ": min(it[2] for it in items),
                "maxZ": max(it[2] for it in items),
                "hw": items[-1][0],
                "minAbsX": items[0][0],
                "torsoCount": len(run),
                "torsoMinX": min(it[1] for it in run),
                "torsoMaxX": max(it[1] for it in run),
                "torsoMinZ": min(it[2] for it in run),
                "torsoMaxZ": max(it[2] for it in run),
                "lateralCount": len(items) - end,
                "lateralMinAbs": items[end][0] if end < len(items) else None,
                "lateralMaxAbs": items[-1][0] if end < len(items) else None,
            }
        )
    return rows


def _torso_width(row: dict[str, Any]) -> float:
    return row["torsoMaxX"] - row["torsoMinX"]


def _trim_row(row: dict[str, Any], samples: Sequence[Sequence[float]], mid: float, half_width: float) -> None:
    """Recompute a band's torso extents from the samples within `half_width` of the midline."""
    kept = [samples[j] for j in row["_members"] if abs(samples[j][0] - mid) <= half_width]
    if not kept:
        return
    row["torsoCount"] = len(kept)
    row["torsoMinX"] = min(p[0] for p in kept) - mid
    row["torsoMaxX"] = max(p[0] for p in kept) - mid
    row["torsoMinZ"] = min(p[2] for p in kept)
    row["torsoMaxZ"] = max(p[2] for p in kept)
    row["armTrimmed"] = True


def _smooth3(values: list[float | None]) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(values)):
        window = [v for v in values[max(0, i - 1) : i + 2] if v is not None]
        out.append(_median(window) if values[i] is not None and window else None)
    return out


def _detect_landmarks(
    points: Sequence[Sequence[float]],
    samples: Sequence[Sequence[float]],
    rows: list[dict[str, Any] | None],
    floor: float,
    height: float,
    n: int,
    mid: float,
    limits: list[str],
) -> dict[str, Any]:
    """Silhouette extrema and heuristic landmarks of the body mesh. All y values are absolute metres."""
    band_lo = lambda i: floor + i / n * height  # noqa: E731
    band_hi = lambda i: floor + (i + 1) / n * height  # noqa: E731
    band_c = lambda i: floor + (i + 0.5) / n * height  # noqa: E731
    present = [i for i, r in enumerate(rows) if r is not None]
    out: dict[str, Any] = {}
    top_skin = max(p[1] for p in points)
    bottom_skin = min(p[1] for p in points)
    out["topSkinY"] = top_skin
    out["bottomSkinY"] = bottom_skin

    # Neck: narrowest torso-cluster width between 0.65 H and (top - 0.06 H).
    low = floor + NECK_SEARCH_LOW_FRAC * height
    high = top_skin - NECK_SEARCH_TOP_MARGIN_FRAC * height
    zone = [i for i in present if low <= band_c(i) <= high]
    neck_band = min(zone, key=lambda i: (_torso_width(rows[i]), -i)) if zone else None
    out["neckBand"] = neck_band
    if neck_band is None:
        limits.append("neck: no silhouette bands in the neck search zone; neck, chin and everything head-relative are null")
        out["neck"] = None
    else:
        r = rows[neck_band]
        out["neck"] = {
            "y": band_c(neck_band),
            "widthM": _torso_width(r),
            "depthM": r["torsoMaxZ"] - r["torsoMinZ"],
            "frontZ": r["torsoMaxZ"],
            "searchZoneY": [low, high],
        }

    # Chin: lowest central vertex above the neck whose z is well in front of the neck's front.
    chin = None
    if neck_band is not None:
        neck = out["neck"]
        # The neck band can straddle the jaw (bands are ~1.75 cm), so the neck's front is the smallest
        # central front-z over the neck band and the two bands below it.
        front_ref = min(
            rows[i]["torsoMaxZ"] for i in range(max(0, neck_band - 2), neck_band + 1) if rows[i] is not None
        )
        threshold = front_ref + CHIN_FORWARD_NECK_WIDTHS * neck["widthM"]
        half = 1.5 * neck["widthM"]
        floor_y = band_lo(max(0, neck_band - 2))
        ys = [p[1] for p in samples if p[1] >= floor_y and abs(p[0] - mid) <= half and p[2] >= threshold]
        chin = min(ys) if ys else None
        out["chinForwardThresholdZ"] = threshold
    out["chinY"] = chin
    if neck_band is not None and chin is None:
        limits.append("chin: no central vertex above the neck projects in front of it; chin and head-relative coordinates are null")

    # Crotch: the apex of the gap between the legs (highest band, contiguous from the bottom, with
    # no sample near the midline). The gap must close below 0.65 H, or there is no crotch to report.
    gap_eps = LEG_GAP_FRAC * height
    last_gap = None
    closed = False
    crotch_zone_top = floor + NECK_SEARCH_LOW_FRAC * height
    for i in present:
        if band_c(i) > crotch_zone_top:
            break
        if rows[i]["minAbsX"] > gap_eps:
            last_gap = i
        elif last_gap is not None:
            closed = True
            break
    if last_gap is None:
        limits.append("crotch: the body mesh shows no gap between the legs (fused legs); crotch and leg length are null")
    elif not closed:
        limits.append("crotch: the leg gap never closes below 0.65 H (skirt/dress or very long legs); crotch is null")
        last_gap = None
    out["crotchBand"] = last_gap
    out["crotchY"] = band_hi(last_gap) if last_gap is not None else None

    # Shoulder line: knee of the outer half-width profile between the neck and its widest band. When the
    # profile is a step (arms level with the shoulders, so the widest band IS the knee) the shoulder line
    # is the top of the widest band and the shoulder width is read one band above it.
    shoulder_band = None
    shoulder_hw = None
    shoulder_method = None
    if neck_band is not None:
        profile = [(i, rows[i]["hw"]) for i in present if i <= neck_band]
        if profile:
            hw_max = max(hw for _, hw in profile)
            widest = max(i for i, hw in profile if hw >= 0.97 * hw_max)
            hw_neck = rows[neck_band]["hw"]
            span_y = band_c(neck_band) - band_c(widest)
            span_w = hw_max - hw_neck
            if widest < neck_band and span_y > 0 and span_w > 0:
                best, best_i = None, None
                for i, hw in profile:
                    if i <= widest or i >= neck_band:
                        continue
                    score = (hw - hw_neck) / span_w - (band_c(neck_band) - band_c(i)) / span_y
                    if best is None or score > best:
                        best, best_i = score, i
                if best is not None and best > 0.02:
                    shoulder_band, shoulder_hw, shoulder_method = best_i, rows[best_i]["hw"], "profile-knee"
                else:
                    # The band above the widest one is the shoulder when the widest band is the arms (it is clearly
                    # wider than the neck but narrower than the arms); otherwise the widest band IS the shoulder.
                    above = widest + 1
                    candidate = rows[above]["hw"] if above < neck_band and rows[above] is not None else None
                    shoulder_band = widest
                    shoulder_hw = candidate if candidate is not None and candidate > 2.0 * hw_neck else hw_max
                    shoulder_method = "widest-band-step"
    out["shoulderBand"] = shoulder_band
    out["shoulder"] = (
        None
        if shoulder_band is None
        else {"y": band_c(shoulder_band), "halfWidthM": shoulder_hw, "method": shoulder_method}
    )
    if shoulder_band is None:
        limits.append("shoulder line: the half-width profile below the neck has no widening; shoulder line is null")
    elif shoulder_hw is None:
        limits.append("shoulder width: the shoulder line is the widest band and no band lies above it; width is null")

    # Hand/arm extreme (widest vertex).
    widest_vertex = max(points, key=lambda p: abs(p[0] - mid))
    out["armExtreme"] = {"halfSpanM": abs(widest_vertex[0] - mid), "y": widest_vertex[1]}

    # Armpit: apex of the highest gap between the arm and the torso, searched downward from the shoulder.
    armpit_band = None
    if shoulder_band is not None:
        floor_band = out["crotchBand"] if out["crotchBand"] is not None else (present[0] if present else 0)
        for i in range(shoulder_band, floor_band - 1, -1):
            r = rows[i]
            if r is not None and r["lateralCount"] >= LATERAL_MIN_COUNT:
                armpit_band = i
                break
    # No gap anywhere and the profile is a step: the arms are level with the shoulders (T-pose), joined to the
    # torso in every band they cross. Those bands are cut at the shoulder width so the torso series
    # excludes the arms, and the armpit is the underside of the lowest arm band.
    trimmed: list[int] = []
    if (
        armpit_band is None
        and shoulder_method == "widest-band-step"
        and shoulder_hw
        and out["armExtreme"]["halfSpanM"] > 1.3 * shoulder_hw
    ):
        i = shoulder_band
        while i >= 0 and rows[i] is not None and rows[i]["hw"] >= ARM_BAND_HALF_WIDTH_RATIO * shoulder_hw:
            _trim_row(rows[i], samples, mid, TRIM_SHOULDER_RATIO * shoulder_hw)
            trimmed.append(i)
            i -= 1
        if trimmed and i >= 0 and rows[i] is not None:
            armpit_band = i
    out["armTrimmedBands"] = sorted(trimmed)
    out["armpitBand"] = armpit_band
    out["armpitY"] = band_hi(armpit_band) if armpit_band is not None else None

    # Arm angle from vertical. Preferred: the axis through the centres of the lateral (arm) cluster over
    # consecutive bands below the armpit. Fallback (arm too short in the silhouette, e.g. a T-pose whose
    # arm shows a gap in one band only): torso side at the armpit to the widest vertex.
    arm: dict[str, Any] = {"angleDeg": None, "method": None}
    if armpit_band is not None:
        centres: list[tuple[float, float]] = []
        i = armpit_band
        while i >= 0 and rows[i] is not None and rows[i]["lateralCount"] >= LATERAL_MIN_COUNT:
            centres.append((band_c(i), (rows[i]["lateralMinAbs"] + rows[i]["lateralMaxAbs"]) / 2.0))
            i -= 1
        if len(centres) >= 4:
            (y_top, c_top), (y_bot, c_bot) = centres[0], centres[-1]
            arm = {
                "angleDeg": math.degrees(math.atan2(c_bot - c_top, y_top - y_bot)),
                "method": f"axis through the lateral-cluster centres of {len(centres)} bands below the armpit",
            }
        else:
            side = rows[armpit_band]["torsoMaxX"]
            arm = {
                "angleDeg": math.degrees(math.atan2(out["armExtreme"]["halfSpanM"] - side,
                                                    band_hi(armpit_band) - out["armExtreme"]["y"])),
                "method": "line from the torso side at the armpit apex to the widest vertex",
            }
    out["arm"] = arm

    # Hips / waist / chest on the torso cluster, below the armpit.
    top_torso_band = armpit_band if armpit_band is not None else shoulder_band
    out["hips"] = out["waist"] = out["chest"] = None
    if out["crotchBand"] is not None and top_torso_band is not None and top_torso_band > out["crotchBand"] + 2:
        cb = out["crotchBand"]
        usable = [i for i in range(cb + 1, top_torso_band + 1) if rows[i] is not None]
        if usable:
            mid_band = (cb + top_torso_band) / 2.0
            lower = [i for i in usable if i <= mid_band] or usable
            hips = max(lower, key=lambda i: (_torso_width(rows[i]), -i))
            above = [i for i in usable if i > hips]
            waist = min(above, key=lambda i: (_torso_width(rows[i]), i)) if above else None
            out["hips"] = {"band": hips, "y": band_c(hips), "widthM": _torso_width(rows[hips]),
                           "depthM": rows[hips]["torsoMaxZ"] - rows[hips]["torsoMinZ"]}
            if waist is not None:
                out["waist"] = {"band": waist, "y": band_c(waist), "widthM": _torso_width(rows[waist]),
                                "depthM": rows[waist]["torsoMaxZ"] - rows[waist]["torsoMinZ"]}
            if waist is not None and shoulder_band is not None:
                chest_zone = [i for i in range(waist, shoulder_band + 1) if rows[i] is not None]
                if chest_zone:
                    chest = max(chest_zone, key=lambda i: (rows[i]["torsoMaxZ"], -i))
                    # Above the armpit arm and torso are one silhouette, so the chest WIDTH is read on the
                    # torso cluster just below the armpit; the front-z peak (depth) is unaffected by arms.
                    width_band = armpit_band if armpit_band is not None and rows[armpit_band] is not None else chest
                    out["chest"] = {"band": chest, "y": band_c(chest),
                                    "widthM": _torso_width(rows[width_band]),
                                    "widthBand": width_band,
                                    "frontZ": rows[chest]["torsoMaxZ"],
                                    "depthM": rows[chest]["torsoMaxZ"] - rows[chest]["torsoMinZ"]}
    for key in ("hips", "waist", "chest"):
        if out[key] is None:
            limits.append(f"{key}: could not be located (needs a crotch and an armpit/shoulder line); null")

    # Legs: knee (rear hollow) and ankle (cross-section minimum with a flare below it).
    out["knee"] = out["ankle"] = None
    out["legSkinBottomY"] = bottom_skin
    if out["crotchBand"] is not None:
        cb = out["crotchBand"]
        leg_bands = [i for i in present if i <= cb]
        if len(leg_bands) >= 8:
            length = out["crotchY"] - bottom_skin
            back = _smooth3([rows[i]["torsoMinZ"] if i in leg_bands else None for i in range(cb + 1)])
            k_low, k_high = bottom_skin + 0.3 * length, bottom_skin + 0.85 * length
            k_zone = [i for i in leg_bands if k_low <= band_c(i) <= k_high and back[i] is not None]
            if k_zone:
                knee_band = max(k_zone, key=lambda i: (back[i], -i))
                below = [back[i] for i in leg_bands if i < knee_band and back[i] is not None]
                if below and back[knee_band] - min(below) >= KNEE_PROMINENCE_FRAC * height:
                    out["knee"] = {"y": band_c(knee_band), "rearZ": back[knee_band],
                                   "prominenceM": back[knee_band] - min(below)}
            area = [
                (rows[i]["torsoMaxX"] - rows[i]["torsoMinX"]) * (rows[i]["torsoMaxZ"] - rows[i]["torsoMinZ"])
                if i in leg_bands else None
                for i in range(cb + 1)
            ]
            a_zone = [i for i in leg_bands if band_c(i) <= bottom_skin + 0.3 * length and area[i] is not None]
            if len(a_zone) >= 3:
                narrowest = min(a_zone, key=lambda i: (area[i], i))
                lower = [area[i] for i in a_zone if i < narrowest]
                if lower and max(lower) >= ANKLE_FLARE_RATIO * area[narrowest]:
                    out["ankle"] = {"y": band_c(narrowest), "crossSectionM2": area[narrowest]}
        else:
            limits.append("legs: fewer than 8 silhouette bands below the crotch; knee and ankle are null")
    if out["knee"] is None:
        limits.append("knee: no rear-of-knee hollow with sufficient prominence in the leg silhouette; knee is null")
    if out["ankle"] is None:
        limits.append(
            "ankle: the leg cross-section has no constriction with a flare below it inside the skin mesh "
            "(the skin mesh may end above the ankle and hand over to separate foot/shoe meshes); ankle is null"
        )
    return out


# --------------------------------------------------------------------------------------------
# Mirror symmetry
# --------------------------------------------------------------------------------------------


def _mirror_error(points: Sequence[Sequence[float]], mid: float, cell: float) -> dict[str, Any] | None:
    """Mean distance from each point's mirror image (x -> 2*mid - x) to its nearest actual point.

    Nearest neighbours are searched in the 3x3x3 hash cells around the mirror image, so a distance is
    exact up to `cell` and capped at `cell` beyond that (an unmatched point costs `cell`).
    """
    if not points or cell <= 0:
        return None
    grid: dict[tuple[int, int, int], list[Sequence[float]]] = {}
    for p in points:
        grid.setdefault((int(p[0] // cell), int(p[1] // cell), int(p[2] // cell)), []).append(p)
    errors: list[float] = []
    cap2 = cell * cell
    for p in points:
        mx, my, mz = 2.0 * mid - p[0], p[1], p[2]
        cx, cy, cz = int(mx // cell), int(my // cell), int(mz // cell)
        best = cap2
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for q in grid.get((cx + dx, cy + dy, cz + dz), ()):
                        d2 = (q[0] - mx) ** 2 + (q[1] - my) ** 2 + (q[2] - mz) ** 2
                        if d2 < best:
                            best = d2
        errors.append(math.sqrt(best))
    return {
        "pointCount": len(points),
        "meanErrM": sum(errors) / len(errors),
        "p95ErrM": _percentile(errors, 0.95),
        "matchedFraction": sum(1 for e in errors if e < 0.1 * cell) / len(errors),
        "searchCellM": cell,
        "errorCapM": cell,
    }


# --------------------------------------------------------------------------------------------
# PNG decode (stdlib: zlib + filters), 8-bit RGB/RGBA, non-interlaced
# --------------------------------------------------------------------------------------------


@dataclass
class _Png:
    width: int
    height: int
    channels: int
    color_type: int
    rows: list[bytes]  # decoded rows 0..len-1, each cropped to `cols` pixels
    cols: int

    def pixel(self, x: int, y: int) -> tuple[int, int, int]:
        row = self.rows[y]
        o = x * self.channels
        return row[o], row[o + 1], row[o + 2]


def _png_header(data: bytes) -> tuple[int, int, int, int, int, int, int]:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("image is not a PNG (bad signature)")
    pos = 8
    while pos + 8 <= len(data):
        length, kind = struct.unpack_from(">I4s", data, pos)
        if kind == b"IHDR":
            return struct.unpack_from(">IIBBBBB", data, pos + 8)  # type: ignore[return-value]
        pos += 12 + length
    raise ValueError("PNG has no IHDR chunk")


def _decode_png(data: bytes, max_rows: int | None = None, max_cols: int | None = None) -> _Png:
    """Decode rows 0..max_rows and pixel columns 0..max_cols. Row filters only look left and up, so a
    top-left crop of the image is exactly decodable without the rest."""
    width, height, depth, color_type, _comp, _filt, interlace = _png_header(data)
    if depth != 8 or color_type not in (2, 6):
        raise ValueError(f"unsupported PNG (bit depth {depth}, colour type {color_type}); need 8-bit RGB/RGBA")
    if interlace != 0:
        raise ValueError("interlaced PNG is not supported")
    channels = 3 if color_type == 2 else 4
    idat: list[bytes] = []
    pos = 8
    while pos + 8 <= len(data):
        length, kind = struct.unpack_from(">I4s", data, pos)
        if kind == b"IDAT":
            idat.append(data[pos + 8 : pos + 8 + length])
        elif kind == b"IEND":
            break
        pos += 12 + length
    raw = zlib.decompress(b"".join(idat))
    full_stride = width * channels
    if len(raw) < height * (full_stride + 1):
        raise ValueError("PNG pixel data is shorter than its header declares")
    rows_needed = height if max_rows is None else min(height, max_rows)
    cols = width if max_cols is None else min(width, max_cols)
    stride = cols * channels
    bpp = channels
    prev = bytearray(stride)
    rows: list[bytes] = []
    pos = 0
    for _y in range(rows_needed):
        ftype = raw[pos]
        line = bytearray(raw[pos + 1 : pos + 1 + stride])
        pos += full_stride + 1
        if ftype == 1:
            for c in range(bpp):
                line[c::bpp] = bytes([v & 255 for v in accumulate(line[c::bpp])])
        elif ftype == 2:
            line = bytearray([(a + b) & 255 for a, b in zip(line, prev)])
        elif ftype == 3:
            for i in range(min(bpp, stride)):
                line[i] = (line[i] + (prev[i] >> 1)) & 255
            for i in range(bpp, stride):
                line[i] = (line[i] + ((line[i - bpp] + prev[i]) >> 1)) & 255
        elif ftype == 4:
            for i in range(min(bpp, stride)):
                line[i] = (line[i] + prev[i]) & 255
            for i in range(bpp, stride):
                a, b, c = line[i - bpp], prev[i], prev[i - bpp]
                pa = b - c
                pb = a - c
                pc = pa + pb
                if pa < 0:
                    pa = -pa
                if pb < 0:
                    pb = -pb
                if pc < 0:
                    pc = -pc
                if pa <= pb and pa <= pc:
                    pred = a
                elif pb <= pc:
                    pred = b
                else:
                    pred = c
                line[i] = (line[i] + pred) & 255
        elif ftype != 0:
            raise ValueError(f"PNG row has unknown filter type {ftype}")
        rows.append(bytes(line))
        prev = line
    return _Png(width, height, channels, color_type, rows, cols)


_SRGB_TO_LINEAR = [
    (c / 255.0) / 12.92 if c / 255.0 <= 0.04045 else (((c / 255.0) + 0.055) / 1.055) ** 2.4 for c in range(256)
]


def _lstar(r: int, g: int, b: int) -> float:
    y = 0.2126 * _SRGB_TO_LINEAR[r] + 0.7152 * _SRGB_TO_LINEAR[g] + 0.0722 * _SRGB_TO_LINEAR[b]
    f = y ** (1.0 / 3.0) if y > 216.0 / 24389.0 else (24389.0 / 27.0 * y + 16.0) / 116.0
    return 116.0 * f - 16.0


def _hex(rgb: Sequence[float]) -> str:
    return "#%02x%02x%02x" % tuple(int(round(c)) for c in rgb)


def _palette(colors: list[tuple[int, int, int]], k: int) -> list[dict[str, Any]]:
    """Deterministic k-colour palette with meaningful cluster fractions.

    Seeds are the most populated 4-bit-per-channel bins, each at least `separation` apart in RGB
    (relaxed until k seeds exist); then four Lloyd iterations over the distinct colours, weighted by
    their counts. Nothing is random, so equal input gives equal output.
    """
    if not colors:
        return []
    counts: dict[tuple[int, int, int], int] = {}
    for c in colors:
        counts[c] = counts.get(c, 0) + 1
    bins: dict[tuple[int, int, int], int] = {}
    for c, n in counts.items():
        key = (c[0] >> 4, c[1] >> 4, c[2] >> 4)
        bins[key] = bins.get(key, 0) + n
    ranked = sorted(bins.items(), key=lambda kv: (-kv[1], kv[0]))
    seeds: list[tuple[float, float, float]] = []
    for separation in (48.0, 24.0, 8.0, 0.0):
        for key, _n in ranked:
            centre = (key[0] * 16 + 8.0, key[1] * 16 + 8.0, key[2] * 16 + 8.0)
            if len(seeds) >= k:
                break
            if centre not in seeds and all(math.dist(centre, s) >= separation for s in seeds):
                seeds.append(centre)
        if len(seeds) >= k:
            break
    centres = [list(s) for s in seeds[:k]]
    distinct = list(counts.items())
    members: list[list[tuple[tuple[int, int, int], int]]] = [[] for _ in centres]
    for _ in range(4):
        members = [[] for _ in centres]
        for colour, n in distinct:
            best = min(range(len(centres)), key=lambda i: (math.dist(colour, centres[i]), i))
            members[best].append((colour, n))
        for i, group in enumerate(members):
            weight = sum(n for _, n in group)
            if weight:
                centres[i] = [sum(c[ch] * n for c, n in group) / weight for ch in range(3)]
    total = len(colors)
    palette = []
    for centre, group in zip(centres, members):
        weight = sum(n for _, n in group)
        if weight:
            palette.append({"rgb": [round(v, 2) for v in centre], "hex": _hex(centre), "fraction": weight / total})
    palette.sort(key=lambda e: (-e["fraction"], e["hex"]))
    return palette


def _colour_stats(colors: list[tuple[int, int, int]]) -> dict[str, Any] | None:
    if not colors:
        return None
    n = len(colors)
    mean = [sum(c[ch] for c in colors) / n for ch in range(3)]
    median = [_median([c[ch] for c in colors]) for ch in range(3)]
    lstars = [_lstar(*c) for c in colors]
    return {
        "sampleCount": n,
        "meanSrgb": mean,
        "meanHex": _hex(mean),
        "medianSrgb": median,
        "medianHex": _hex(median),
        "meanLstar": sum(lstars) / n,
        "medianLstar": _median(lstars),
    }


def _sample_box(png: _Png, box: Sequence[float], budget: int = PIXEL_SAMPLE_BUDGET) -> list[tuple[int, int, int]]:
    """Pixels inside a UV box (u0, v0, u1, v1), strided to roughly `budget` samples. v runs down."""
    x0 = max(0, int(box[0] * png.width))
    x1 = min(png.cols, int(math.ceil(box[2] * png.width)) + 1)
    y0 = max(0, int(box[1] * png.height))
    y1 = min(len(png.rows), int(math.ceil(box[3] * png.height)) + 1)
    if x1 <= x0 or y1 <= y0:
        return []
    step = max(1, int(math.sqrt((x1 - x0) * (y1 - y0) / float(budget))))
    return [png.pixel(x, y) for y in range(y0, y1, step) for x in range(x0, x1, step)]


# --------------------------------------------------------------------------------------------
# Atlas / UV
# --------------------------------------------------------------------------------------------


def _image_bytes(document: dict[str, Any], bin_payload: bytes, image_index: int, glb_path: Path) -> bytes:
    images = document.get("images", [])
    if not isinstance(images, list) or not 0 <= image_index < len(images):
        raise ValueError(f"image {image_index} does not exist")
    image = images[image_index]
    if "bufferView" in image:
        views = document.get("bufferViews", [])
        view = views[int(image["bufferView"])]
        start = int(view.get("byteOffset", 0))
        return bin_payload[start : start + int(view.get("byteLength", 0))]
    uri = str(image.get("uri", ""))
    if uri.startswith("data:"):
        return base64.b64decode(uri.split(",", 1)[1])
    candidate = glb_path.parent / uri
    if uri and candidate.is_file():
        return candidate.read_bytes()
    raise ValueError(f"image {image_index} has neither an embedded bufferView nor a readable uri")


def _image_of_material(document: dict[str, Any], material: int | None) -> int | None:
    materials = document.get("materials", [])
    if material is None or not isinstance(materials, list) or not 0 <= material < len(materials):
        return None
    pbr = materials[material].get("pbrMetallicRoughness", {}) if isinstance(materials[material], dict) else {}
    tex = pbr.get("baseColorTexture") if isinstance(pbr, dict) else None
    if not isinstance(tex, dict):
        return None
    textures = document.get("textures", [])
    index = tex.get("index")
    if not isinstance(index, int) or not isinstance(textures, list) or not 0 <= index < len(textures):
        return None
    source = textures[index].get("source") if isinstance(textures[index], dict) else None
    return int(source) if isinstance(source, int) else None


def _uv_box(uvs: Sequence[Sequence[float]]) -> list[float] | None:
    if not uvs:
        return None
    us = [u[0] for u in uvs]
    vs = [u[1] for u in uvs]
    return [min(us), min(vs), max(us), max(vs)]


def _uv_descriptor(box: list[float] | None, atlas: tuple[int, int] | None) -> dict[str, Any] | None:
    if box is None:
        return None
    entry: dict[str, Any] = {
        "uvBox": box,
        "uvAreaFraction": max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1]),
    }
    if atlas is not None:
        entry["pixelBox"] = [box[0] * atlas[0], box[1] * atlas[1], box[2] * atlas[0], box[3] * atlas[1]]
    return entry


def _uv_clusters(
    uvs: Sequence[Sequence[float]], atlas: tuple[int, int] | None, cell: float = 0.01, top: int = 6
) -> list[dict[str, Any]]:
    """Connected groups of UV points (8-neighbour hash cells of `cell` UV units), largest first.

    A mesh whose UVs are scattered over the atlas has a huge bounding box; the clusters say where the
    texels really are.
    """
    cells: dict[tuple[int, int], list[int]] = {}
    for i, uv in enumerate(uvs):
        cells.setdefault((int(uv[0] // cell), int(uv[1] // cell)), []).append(i)
    parent = {c: c for c in cells}

    def find(c: tuple[int, int]) -> tuple[int, int]:
        while parent[c] != c:
            parent[c] = parent[parent[c]]
            c = parent[c]
        return c

    for c in cells:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                n = (c[0] + dx, c[1] + dy)
                if n in cells:
                    a, b = find(c), find(n)
                    if a != b:
                        parent[a] = b
    groups: dict[tuple[int, int], list[int]] = {}
    for c, ids in cells.items():
        groups.setdefault(find(c), []).extend(ids)
    out = []
    for ids in sorted(groups.values(), key=lambda g: (-len(g), min(g)))[:top]:
        out.append({"vertexCount": len(ids), **(_uv_descriptor(_uv_box([uvs[i] for i in ids]), atlas) or {})})
    return out


def _triangles(indices: Sequence[int]) -> list[tuple[int, int, int]]:
    return [(indices[i], indices[i + 1], indices[i + 2]) for i in range(0, len(indices) - 2, 3)]


def _islands(vertex_count: int, triangles: Sequence[tuple[int, int, int]]) -> list[int]:
    parent = list(range(vertex_count))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b, c in triangles:
        ra = find(a)
        for other in (b, c):
            ro = find(other)
            if ro != ra:
                parent[ro] = ra
    return [find(i) for i in range(vertex_count)]


def _texel_density(
    triangles: Sequence[tuple[int, int, int]],
    points: Sequence[Sequence[float]],
    uvs: Sequence[Sequence[float]],
    atlas: tuple[int, int],
    keep: Any,
    height: float,
) -> dict[str, Any] | None:
    """Texels per metre of surface: sqrt(sum UV area in texels^2 / sum 3D area), over kept triangles."""
    area3 = 0.0
    area_uv = 0.0
    per_tri: list[float] = []
    scale = atlas[0] * atlas[1]
    for a, b, c in triangles:
        if not (keep(a) and keep(b) and keep(c)):
            continue
        pa, pb, pc = points[a], points[b], points[c]
        ux, uy, uz = pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]
        vx, vy, vz = pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2]
        cx, cy, cz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        t3 = 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)
        ta, tb, tc = uvs[a], uvs[b], uvs[c]
        tuv = 0.5 * abs((tb[0] - ta[0]) * (tc[1] - ta[1]) - (tc[0] - ta[0]) * (tb[1] - ta[1])) * scale
        area3 += t3
        area_uv += tuv
        if t3 > 1e-12:
            per_tri.append(math.sqrt(tuv / t3))
    if area3 <= 0.0 or not per_tri:
        return None
    density = math.sqrt(area_uv / area3)
    return {
        "triangleCount": len(per_tri),
        "surfaceAreaM2": area3,
        "uvAreaTexels2": area_uv,
        "texelsPerMetre": density,
        "texelsPerFigureHeight": density * height,
        "perTriangleMedian": _median(per_tri),
        "perTriangleP10": _percentile(per_tri, 0.10),
        "perTriangleP90": _percentile(per_tri, 0.90),
    }


# --------------------------------------------------------------------------------------------
# Face detail meshes
# --------------------------------------------------------------------------------------------


def _side_summary(pts: Sequence[Sequence[float]]) -> dict[str, Any] | None:
    box = _bbox(pts)
    if box is None:
        return None
    lo, hi = box
    return {
        "count": len(pts),
        "bboxMin": lo,
        "bboxMax": hi,
        "centre": [(lo[i] + hi[i]) / 2.0 for i in range(3)],
        "widthM": hi[0] - lo[0],
        "heightM": hi[1] - lo[1],
        "depthM": hi[2] - lo[2],
    }


@dataclass
class _Head:
    mid: float
    chin: float
    top: float
    width: float
    depth: float
    zmin: float
    zmax: float

    @property
    def height(self) -> float:
        return self.top - self.chin

    def rel(self, p: Sequence[float]) -> dict[str, float]:
        return {
            "x": (p[0] - self.mid) / self.width,
            "y": (p[1] - self.chin) / self.height,
            "z": (p[2] - self.zmin) / self.depth,
        }


def _face_feature(part: _Part, head: _Head, floor_h: float) -> dict[str, Any]:
    pts = part.positions
    lo, hi = _bbox(pts)  # type: ignore[misc]
    centre = [(lo[i] + hi[i]) / 2.0 for i in range(3)]
    plus = [p for p in pts if p[0] - head.mid > 0.0]
    minus = [p for p in pts if p[0] - head.mid <= 0.0]
    sides = {"xPlus": _side_summary(plus), "xMinus": _side_summary(minus)}
    gap = PAIR_GAP_HEAD_FRAC * head.width
    if plus and minus:
        inner_plus = min(p[0] for p in plus) - head.mid
        inner_minus = head.mid - max(p[0] for p in minus)
        layout = "paired" if inner_plus > gap and inner_minus > gap else "central"
    else:
        layout = "one-sided"
    cell = max(1e-6, FEATURE_MIRROR_CELL_FRAC * floor_h)
    return {
        "name": part.mesh_name,
        "nodeName": part.node_name,
        "vertexCount": len(pts),
        "material": part.material,
        "bboxM": {"min": lo, "max": hi},
        "centreM": centre,
        "headRel": {
            "centre": head.rel(centre),
            "bboxMin": head.rel(lo),
            "bboxMax": head.rel(hi),
            "widthFrac": (hi[0] - lo[0]) / head.width,
            "heightFrac": (hi[1] - lo[1]) / head.height,
            "depthFrac": (hi[2] - lo[2]) / head.depth,
        },
        "layout": layout,
        "sides": sides,
        "symmetry": _mirror_error(pts, head.mid, cell),
    }


def _assign_roles(features: list[dict[str, Any]], head: _Head) -> dict[str, dict[str, Any]]:
    """Guess what each detail mesh is from geometry alone (names are generic exports).

    Rules, in order: eye = the paired feature with the largest per-side bbox area (width x height; brows and
    lashes are thin, so they lose even when wider); brow = highest paired feature lying wholly above the
    eye's vertical centre; mouth = a central feature below the eyes; the remaining paired features are
    described relative to the eye (inner disc, lid/lash line, lower lid, lateral/ear-like).
    """
    roles: dict[str, dict[str, Any]] = {}
    paired = [f for f in features if f["layout"] == "paired"]

    def side_area(f: dict[str, Any]) -> float:
        return max(s["widthM"] * s["heightM"] for s in f["sides"].values() if s)

    def yc(f: dict[str, Any]) -> float:
        return f["centreM"][1]

    eye = None
    if paired:
        eye = max(paired, key=lambda f: (side_area(f), f["vertexCount"]))
        eye_ymin, eye_ymax = eye["bboxM"]["min"][1], eye["bboxM"]["max"][1]
        eye_yc = yc(eye)
        confidence = "medium" if len(paired) >= 3 else "low"
        roles[eye["name"]] = {
            "role": "eye",
            "confidence": confidence,
            "basis": "paired (two separate halves about the midline) detail mesh with the largest per-side bbox area "
                     "in the head box; eyes versus brows/irises is decided by size and position, not by name",
        }
        eye_x_inner = min(s["bboxMin"][0] - head.mid if s["centre"][0] > head.mid else head.mid - s["bboxMax"][0]
                          for s in eye["sides"].values() if s)
        eye_x_outer = max(s["bboxMax"][0] - head.mid if s["centre"][0] > head.mid else head.mid - s["bboxMin"][0]
                          for s in eye["sides"].values() if s)
        above = [f for f in paired if f is not eye and f["bboxM"]["min"][1] >= eye_yc]
        brow = max(above, key=yc) if above else None
        if brow is not None:
            roles[brow["name"]] = {
                "role": "brow",
                "confidence": "medium" if len(paired) >= 3 else "low",
                "basis": "highest paired detail mesh lying wholly above the eye's vertical centre",
            }
        for f in paired:
            if f is eye or f is brow:
                continue
            fymin, fymax = f["bboxM"]["min"][1], f["bboxM"]["max"][1]
            fx_inner = min(s["bboxMin"][0] - head.mid if s["centre"][0] > head.mid else head.mid - s["bboxMax"][0]
                           for s in f["sides"].values() if s)
            fx_outer = max(s["bboxMax"][0] - head.mid if s["centre"][0] > head.mid else head.mid - s["bboxMin"][0]
                           for s in f["sides"].values() if s)
            overlaps_eye_y = fymax >= eye_ymin and fymin <= eye_ymax
            inside_eye_x = fx_inner >= eye_x_inner * 0.9 and fx_outer <= eye_x_outer * 1.1
            if fx_inner >= eye_x_outer * 0.95 and f["centreM"][2] <= head.zmin + 0.5 * head.depth + 0.1 * head.depth:
                role, basis = "lateral-detail-ear-like", "paired, entirely outside the eye columns and near mid-depth of the head"
            elif inside_eye_x and overlaps_eye_y:
                role, basis = "eye-inner-detail", "paired, inside the eye's x-range and overlapping its height (iris/pupil/lid fill)"
            elif eye_ymin <= yc(f) <= eye_ymax:
                role, basis = "lid-or-lash-line", "paired, centred within the eye's height band"
            elif yc(f) < eye_ymin:
                role, basis = "lower-lid-lash-or-cheek-detail", "paired, centred below the eye"
            else:
                role, basis = "upper-lid-or-brow-detail", "paired, centred above the eye but not the highest"
            roles[f["name"]] = {"role": role, "confidence": "low", "basis": basis}
    for f in features:
        if f["name"] in roles:
            continue
        if f["layout"] == "central":
            if eye is not None and yc(f) < eye["bboxM"]["min"][1]:
                roles[f["name"]] = {
                    "role": "mouth-or-nose-detail",
                    "confidence": "low",
                    "basis": "central (contiguous across the midline) detail mesh below the eyes",
                }
            else:
                roles[f["name"]] = {
                    "role": "central-detail",
                    "confidence": "low",
                    "basis": "central detail mesh not below the eyes; role not determined",
                }
        else:
            roles[f["name"]] = {
                "role": "one-sided-detail",
                "confidence": "low",
                "basis": "detail mesh with geometry on one side of the midline only",
            }
    return roles


# --------------------------------------------------------------------------------------------
# analyze
# --------------------------------------------------------------------------------------------


def analyze(
    glb_path: str | Path,
    body_mesh: str | None = None,
    figure_height: float | None = None,
    bands: int = DEFAULT_BANDS,
    arm_gap_frac: float = ARM_GAP_FRAC,
) -> dict[str, Any]:
    """Measure proportions, silhouette, face layout and atlas mapping of the character in `glb_path`.

    Raises ValueError when the file has no mesh with vertices, or `body_mesh` names nothing.
    """
    path = Path(glb_path)
    document, bin_payload, _info = rgr.parse_glb(path)
    rig = rgr.read_rig(path)
    limits: list[str] = []
    nodes = document.get("nodes", [])
    world = rgr.rest_world_matrices(rig) if isinstance(nodes, list) and nodes else []
    parts = _collect_parts(document, bin_payload, world, limits)
    body, body_basis, scoreboard = _select_body(parts, body_mesh)
    if bands < 10:
        raise ValueError("bands must be at least 10")

    # ---- figure ------------------------------------------------------------------------
    all_points = [p for part in parts for p in part.positions]
    floor = min(p[1] for p in all_points)
    top = max(p[1] for p in all_points)
    measured_height = top - floor
    if figure_height is not None:
        height, height_source = float(figure_height), "caller"
    else:
        height, height_source = measured_height, "meshWorldBoundsYExtent"
    if height <= 0.0:
        raise ValueError("figure height is zero: every vertex has the same Y")
    try:
        raw_height, _ = rgr.derive_figure_height(rig)
    except ValueError:
        raw_height = None
    figure_bounds = _bbox(all_points)

    P = body.positions
    body_lo, body_hi = _bbox(P)  # type: ignore[misc]
    mid = (body_lo[0] + body_hi[0]) / 2.0
    n_bands = int(bands)
    gap = arm_gap_frac * height

    # ---- rest pose vs bind pose ------------------------------------------------------------
    rest_pose: dict[str, Any]
    if not body.skinned:
        rest_pose = {"evaluated": False, "reason": "the body mesh is not skinned; positions are used as stored"}
    elif rig.primary_skin is None:
        rest_pose = {"evaluated": False, "reason": rig.structural_failure or "no single primary skin"}
    else:
        worlds = rgr.rest_world_matrices(rig)
        worst = 0.0
        for joint, inverse in zip(rig.joints, rig.inverse_bind_matrices):
            if 0 <= joint.node_index < len(worlds):
                product = rgr.multiply(worlds[joint.node_index], inverse)
                worst = max(worst, max(abs(a - b) for a, b in zip(product, rgr.IDENTITY_MATRIX)))
        rest_pose = {
            "evaluated": True,
            "jointCount": len(rig.joints),
            "inverseBindSource": rig.inverse_bind_source,
            "maxDeviationFromIdentity": worst,
            "restPoseEqualsBindPose": worst <= 1e-4,
        }
        if worst > 1e-4:
            limits.append(
                f"the rest pose differs from the bind pose (max |jointWorld*inverseBind - I| = {worst:.4g}); all "
                "measurements use the bind-pose positions stored in the buffers, not the rest-pose deformation"
            )

    # ---- silhouette bands and landmarks ----------------------------------------------------
    triangles = _read_triangles(document, bin_payload, body, len(P), limits)
    sample_step = 0.0025 * height
    samples = _densify(P, triangles, sample_step) if triangles else [tuple(p) for p in P]
    if not triangles:
        limits.append("the body mesh has no usable triangle list; silhouette bands use vertices only and may have holes")
    rows = _band_rows(P, samples, floor, height, n_bands, mid, gap)
    lm = _detect_landmarks(P, samples, rows, floor, height, n_bands, mid, limits)
    band_c = lambda i: floor + (i + 0.5) / n_bands * height  # noqa: E731

    chin = lm["chinY"]
    top_skin = lm["topSkinY"]
    crotch = lm["crotchY"]
    shoulder_y = lm["shoulder"]["y"] if lm["shoulder"] else None

    # ---- head ------------------------------------------------------------------------------
    head: _Head | None = None
    head_points: list[tuple[float, float, float]] = []
    head_block: dict[str, Any] = {}
    if chin is not None:
        head_points = [p for p in P if p[1] >= chin]
        h_lo, h_hi = _bbox(head_points)  # type: ignore[misc]
        head = _Head(
            mid=(h_lo[0] + h_hi[0]) / 2.0,
            chin=chin,
            top=top_skin,
            width=h_hi[0] - h_lo[0],
            depth=h_hi[2] - h_lo[2],
            zmin=h_lo[2],
            zmax=h_hi[2],
        )
        if head.height <= 0 or head.width <= 0 or head.depth <= 0:
            head = None
    if head is None:
        limits.append("head: not measurable (no chin); head dimensions, face layout and atlas face regions are null")
    else:
        # hair-inclusive bounds: every vertex of every mesh above the chin within the head's x span
        around = [
            p for p in all_points if p[1] >= chin and abs(p[0] - head.mid) <= 1.1 * head.width
        ]
        a_lo, a_hi = _bbox(around)  # type: ignore[misc]
        head_block = {
            "observed": {
                "widthM": head.width,
                "depthM": head.depth,
                "heightM": head.height,
                "widthFrac": head.width / height,
                "depthFrac": head.depth / height,
                "heightFrac": head.height / height,
                "midlineX": head.mid,
                "backZ": head.zmin,
                "frontZ": head.zmax,
                "widthOverHeight": head.width / head.height,
                "depthOverHeight": head.depth / head.height,
                "skinVertexCount": len(head_points),
                "withAllMeshesBounds": {"min": a_lo, "max": a_hi, "widthM": a_hi[0] - a_lo[0],
                                        "depthM": a_hi[2] - a_lo[2], "topY": a_hi[1]},
            },
            "basis": "skin-mesh vertices above the chin (no hair); withAllMeshesBounds adds every mesh in the file "
                     "above the chin within 1.1 head widths of the midline",
        }

    # ---- face detail meshes ----------------------------------------------------------------
    features: list[dict[str, Any]] = []
    roles: dict[str, dict[str, Any]] = {}
    detail_parts: list[_Part] = []
    hair_part: _Part | None = None
    if head is not None:
        gx = head.width * (0.5 + HEAD_BOX_MARGIN)
        box_lo = (head.mid - gx, head.chin - HEAD_BOX_MARGIN * head.height, head.zmin - HEAD_BOX_MARGIN * head.depth)
        box_hi = (head.mid + gx, head.top + HEAD_BOX_MARGIN * head.height, head.zmax + HEAD_BOX_MARGIN * head.depth)
        for part in parts:
            if part is body or not part.positions:
                continue
            lo, hi = _bbox(part.positions)  # type: ignore[misc]
            if all(lo[i] >= box_lo[i] and hi[i] <= box_hi[i] for i in range(3)):
                detail_parts.append(part)
        features = [_face_feature(p, head, height) for p in detail_parts]
        features.sort(key=lambda f: -f["centreM"][1])
        roles = _assign_roles(features, head)
        for f in features:
            f["inferredRole"] = roles[f["name"]]["role"]
        # hair: the largest non-body mesh reaching the head top and covering the head's width
        hair_candidates = []
        for part in parts:
            if part is body or not part.positions or part in detail_parts:
                continue
            lo, hi = _bbox(part.positions)  # type: ignore[misc]
            if hi[1] >= head.top - 0.02 * height and (hi[0] - lo[0]) >= 0.9 * head.width and lo[1] < head.top:
                hair_candidates.append(part)
        if hair_candidates:
            hair_part = max(hair_candidates, key=lambda p: len(p.positions))

    # ---- face metrics -----------------------------------------------------------------------
    face: dict[str, Any] = {
        "features": features,
        "detailMeshCount": len(features),
        "coordinateSystem": "x=(X-midline)/headWidth, y=(Y-chin)/headHeight (0 chin, 1 head top), z=(Z-headBackZ)/headDepth",
    }
    inferred_face: dict[str, Any] = {}
    layout: dict[str, Any] = {}
    nose_tip = None
    mouth = None
    eye_feature = next((f for f in features if roles.get(f["name"], {}).get("role") == "eye"), None)
    brow_feature = next((f for f in features if roles.get(f["name"], {}).get("role") == "brow"), None)
    if head is not None:
        eye_y = eye_feature["centreM"][1] if eye_feature else None
        # nose tip: max-z skin vertex in the central face column, up to the eye line
        upper = eye_y if eye_y is not None else head.chin + 0.6 * head.height
        column = [p for p in head_points if abs(p[0] - head.mid) <= 0.15 * head.width and head.chin <= p[1] <= upper]
        if column:
            tip = max(column, key=lambda p: (p[2], -abs(p[0] - head.mid), -p[1]))
            in_nose_band = head.chin + 0.15 * head.height <= tip[1] <= upper
            nose_tip = {
                "positionM": list(tip),
                "headRel": head.rel(tip),
                "yFracOfH": (tip[1] - floor) / height,
                "protrusionFromHeadCentreM": tip[2] - (head.zmin + head.zmax) / 2.0,
                "confidence": "medium" if (in_nose_band and eye_y is not None) else "low",
                "basis": "max-z vertex of the skin mesh in the central face column (|x-midline| <= 0.15 head widths) "
                         "between the chin and the eye line" + ("" if eye_y is not None else " (no eye found: upper bound 0.6 head heights)"),
            }
        else:
            limits.append("nose tip: no skin vertex in the central face column; null")
        mouth_feature = next(
            (f for f in features if roles.get(f["name"], {}).get("role") == "mouth-or-nose-detail"), None
        )
        if mouth_feature is not None:
            mouth_lo, mouth_hi = mouth_feature["bboxM"]["min"], mouth_feature["bboxM"]["max"]
            mouth = {
                "mesh": mouth_feature["name"],
                "centreM": mouth_feature["centreM"],
                "headRel": mouth_feature["headRel"]["centre"],
                "cornersM": [[mouth_lo[0], mouth_feature["centreM"][1], mouth_feature["centreM"][2]],
                             [mouth_hi[0], mouth_feature["centreM"][1], mouth_feature["centreM"][2]]],
                "confidence": "low",
                "basis": "bbox extremes of the central detail mesh below the eyes",
            }
        else:
            limits.append(
                "mouth: no central detail mesh below the eyes; the mouth is probably painted in the texture atlas "
                "or modelled in the skin mesh, so mouth centre and corners are null"
            )
        if eye_feature is not None:
            sides = [s for s in eye_feature["sides"].values() if s]
            eye_w = _mean([s["widthM"] for s in sides])
            eye_h = _mean([s["heightM"] for s in sides])
            centres = sorted(s["centre"][0] for s in sides)
            inner_gap = None
            if len(sides) == 2:
                minus_side, plus_side = eye_feature["sides"]["xMinus"], eye_feature["sides"]["xPlus"]
                inner_gap = plus_side["bboxMin"][0] - minus_side["bboxMax"][0]
            ipd = centres[-1] - centres[0] if len(centres) == 2 else None
            band_h = 0.005 * height
            line = [p for p in head_points if abs(p[1] - eye_y) <= band_h]
            line_w = (max(p[0] for p in line) - min(p[0] for p in line)) if line else None
            layout.update(
                {
                    "eyeMesh": eye_feature["name"],
                    "eyeLineYM": eye_y,
                    "eyeLineYFracOfH": (eye_y - floor) / height,
                    "eyeLineHeadFrac": head.rel([0.0, eye_y, 0.0])["y"],
                    "eyeWidthM": eye_w,
                    "eyeWidthOverHeadWidth": eye_w / head.width,
                    "eyeHeightM": eye_h,
                    "eyeAspectWidthOverHeight": (eye_w / eye_h) if eye_h else None,
                    "interocularInnerGapM": inner_gap,
                    "interocularInnerGapOverHeadWidth": (inner_gap / head.width) if inner_gap is not None else None,
                    "interocularCentreDistanceM": ipd,
                    "interocularCentreOverHeadWidth": (ipd / head.width) if ipd is not None else None,
                    "innerGapOverEyeWidth": (inner_gap / eye_w) if (inner_gap is not None and eye_w) else None,
                    "faceWidthAtEyeLineM": line_w,
                    "faceWidthAtEyeLineOverHeadWidth": (line_w / head.width) if line_w else None,
                    "eyeSamplingBandM": 2 * band_h,
                    "basis": "eye = the widest paired detail mesh (see inferred.faceFeatureRoles); eye line = its bbox "
                             "centre height; face width = skin-mesh x extent within +-0.5% H of the eye line",
                    "confidence": roles[eye_feature["name"]]["confidence"],
                }
            )
        else:
            limits.append("eyes: no paired detail mesh inside the head box; eye line, interocular and eye width are null "
                          "(the eyes may be painted in the texture)")
        # facing check
        if features:
            centre_z = (head.zmin + head.zmax) / 2.0
            forward = sum(1 for f in features if f["centreM"][2] > centre_z)
            facing = {
                "assumedForward": "+z",
                "detailMeshesAheadOfHeadCentre": forward,
                "detailMeshCount": len(features),
                "consistent": forward * 2 > len(features),
            }
        else:
            facing = {"assumedForward": "+z", "consistent": None,
                      "note": "no face-detail meshes to cross-check the +z forward assumption"}
        # thirds
        brow_y = brow_feature["centreM"][1] if brow_feature else None
        hairline_y = None
        if hair_part is not None:
            floor_y = eye_y if eye_y is not None else head.chin + 0.5 * head.height
            front = [
                p for p in hair_part.positions
                if abs(p[0] - head.mid) <= 0.2 * head.width and p[2] >= head.zmin + 0.75 * head.depth and p[1] >= floor_y
            ]
            hairline_y = min(p[1] for p in front) if front else None
        thirds: dict[str, Any] = {
            "hairlineYM": hairline_y,
            "browYM": brow_y,
            "noseTipYM": nose_tip["positionM"][1] if nose_tip else None,
            "chinYM": head.chin,
        }
        nose_y = thirds["noseTipYM"]
        if nose_y is not None:
            thirds["noseToChinM"] = nose_y - head.chin
            thirds["noseToChinHeadFrac"] = (nose_y - head.chin) / head.height
        if brow_y is not None and nose_y is not None:
            thirds["browToNoseM"] = brow_y - nose_y
            thirds["browToNoseHeadFrac"] = (brow_y - nose_y) / head.height
        if hairline_y is not None and brow_y is not None:
            if hairline_y > brow_y:
                thirds["hairlineToBrowM"] = hairline_y - brow_y
                thirds["hairlineToBrowHeadFrac"] = (hairline_y - brow_y) / head.height
            else:
                thirds["hairlineToBrowM"] = None
                thirds["hairlineNote"] = (
                    "the hair fringe's lower edge is at or below the brow line, so the hairline-to-brow third is "
                    "not measurable (the brows are covered or level with the hair)"
                )
        if hairline_y is None:
            limits.append("hairline: no hair mesh with a front fringe above the eye line; hairline-to-brow third is null")
        thirds["basis"] = ("brow = centre of the brow-role detail mesh; nose = max-z skin vertex in the central column; "
                           "hairline = lowest vertex of the hair-like mesh in the front-central column above the eye line")
        layout["thirds"] = thirds
        layout["hairMesh"] = (
            {"name": hair_part.mesh_name, "nodeName": hair_part.node_name, "vertexCount": len(hair_part.positions)}
            if hair_part else None
        )
        # symmetry
        sym_cell = max(1e-6, BODY_MIRROR_CELL_FRAC * height)
        paired_err = [(f["symmetry"]["meanErrM"], f["vertexCount"]) for f in features
                      if f["layout"] == "paired" and f["symmetry"]]
        weighted = (sum(e * c for e, c in paired_err) / sum(c for _, c in paired_err)) if paired_err else None
        face["symmetry"] = {
            "midlineX": head.mid,
            "skinHead": _mirror_error(head_points, head.mid, sym_cell),
            "pairedFeaturesMeanErrM": weighted,
            "pairedFeaturesMeanErrOverHeadWidth": (weighted / head.width) if weighted is not None else None,
            "basis": "mean distance from each vertex's mirror image about the head midline to the nearest vertex; "
                     "per-feature errors are in features[].symmetry",
        }
        face["noseTip"] = nose_tip
        face["mouth"] = mouth
        face["layout"] = layout
        face["facing"] = facing
        inferred_face = {
            "faceFeatureRoles": [
                {"name": f["name"], "role": roles[f["name"]]["role"], "confidence": roles[f["name"]]["confidence"],
                 "basis": roles[f["name"]]["basis"]}
                for f in features
            ]
        }

    # ---- observed numbers --------------------------------------------------------------------
    span = body_hi[0] - body_lo[0]
    observed: dict[str, Any] = {
        "figure": {
            "heightM": height,
            "heightSource": height_source,
            "measuredHeightM": measured_height,
            "rigReferenceHeightM": raw_height,
            "floorY": floor,
            "topY": top,
            "boundsMin": figure_bounds[0] if figure_bounds else None,
            "boundsMax": figure_bounds[1] if figure_bounds else None,
        },
        "bodyMesh": {
            "meshName": body.mesh_name,
            "nodeName": body.node_name,
            "selection": body_basis,
            "vertexCount": len(P),
            "skinned": body.skinned,
            "softAttributes": list(body.soft_attributes),
            "litDielectricMaterial": body.lit_dielectric,
            "material": body.material,
            "boundsMin": body_lo,
            "boundsMax": body_hi,
            "midlineX": mid,
            "candidates": scoreboard,
        },
        "restPose": rest_pose,
        "armSpan": {
            "spanM": span,
            "spanOverH": span / height,
            "halfSpanM": lm["armExtreme"]["halfSpanM"],
            "extremeVertexY": lm["armExtreme"]["y"],
            "extremeVertexYFrac": (lm["armExtreme"]["y"] - floor) / height,
        },
        "extrema": {
            "topSkinYFrac": (top_skin - floor) / height,
            "bottomSkinYFrac": (lm["bottomSkinY"] - floor) / height,
            "neckNarrowest": None if not lm["neck"] else {
                "yM": lm["neck"]["y"], "yFrac": (lm["neck"]["y"] - floor) / height,
                "widthM": lm["neck"]["widthM"], "widthFrac": lm["neck"]["widthM"] / height,
                "depthM": lm["neck"]["depthM"]},
            "crotchApex": None if crotch is None else {"yM": crotch, "yFrac": (crotch - floor) / height},
            "shoulderKnee": None if not lm["shoulder"] else {
                "yM": lm["shoulder"]["y"], "yFrac": (lm["shoulder"]["y"] - floor) / height,
                "method": lm["shoulder"]["method"],
                "widthM": None if lm["shoulder"]["halfWidthM"] is None else 2 * lm["shoulder"]["halfWidthM"],
                "widthFrac": None if lm["shoulder"]["halfWidthM"] is None
                else 2 * lm["shoulder"]["halfWidthM"] / height},
            "armpitApex": None if lm["armpitY"] is None else {
                "yM": lm["armpitY"], "yFrac": (lm["armpitY"] - floor) / height},
            "hipsMaxWidth": None if not lm["hips"] else {
                "yM": lm["hips"]["y"], "yFrac": (lm["hips"]["y"] - floor) / height,
                "widthM": lm["hips"]["widthM"], "widthFrac": lm["hips"]["widthM"] / height,
                "depthM": lm["hips"]["depthM"]},
            "waistMinWidth": None if not lm["waist"] else {
                "yM": lm["waist"]["y"], "yFrac": (lm["waist"]["y"] - floor) / height,
                "widthM": lm["waist"]["widthM"], "widthFrac": lm["waist"]["widthM"] / height,
                "depthM": lm["waist"]["depthM"]},
            "chestMaxDepth": None if not lm["chest"] else {
                "yM": lm["chest"]["y"], "yFrac": (lm["chest"]["y"] - floor) / height,
                "widthM": lm["chest"]["widthM"], "widthFrac": lm["chest"]["widthM"] / height,
                "frontZ": lm["chest"]["frontZ"], "depthM": lm["chest"]["depthM"]},
            "legSkinBottomY": lm["legSkinBottomY"],
            "legSkinBottomYFrac": (lm["legSkinBottomY"] - floor) / height,
        },
        "torsoWidthRatios": {},
        "facing": face.get("facing"),
    }
    ratios = observed["torsoWidthRatios"]
    hips_w = lm["hips"]["widthM"] if lm["hips"] else None
    waist_w = lm["waist"]["widthM"] if lm["waist"] else None
    sh_w = 2 * lm["shoulder"]["halfWidthM"] if lm["shoulder"] and lm["shoulder"]["halfWidthM"] else None
    if waist_w and hips_w:
        ratios["waistOverHips"] = waist_w / hips_w
    if sh_w and hips_w:
        ratios["shoulderOverHips"] = sh_w / hips_w
    if sh_w and waist_w:
        ratios["shoulderOverWaist"] = sh_w / waist_w
    if lm["chest"] and waist_w:
        ratios["chestWidthOverWaist"] = lm["chest"]["widthM"] / waist_w

    # ---- inferred landmarks -----------------------------------------------------------------
    landmarks = {
        "floor": _lm(floor, floor, height, "lowest vertex of any mesh in the file", "high"),
        "headTopSkin": _lm(top_skin, floor, height, "highest vertex of the body (skin) mesh; hair adds above it", "high"),
        "headTopWithHair": _lm(top, floor, height, "highest vertex of any mesh (hair/accessories included)", "high"),
        "neck": None if not lm["neck"] else _lm(
            lm["neck"]["y"], floor, height,
            f"narrowest central silhouette width between {NECK_SEARCH_LOW_FRAC} H and the skin top minus "
            f"{NECK_SEARCH_TOP_MARGIN_FRAC} H (band centre; band height = H/{n_bands})", "medium"),
        "chin": _lm(chin, floor, height,
                    "lowest central vertex above the neck whose z lies >= neck-front + 0.5 neck widths in front of the neck "
                    "(the jaw leaving the neck in side view)", "medium"),
        "shoulderLine": None if not lm["shoulder"] else _lm(
            lm["shoulder"]["y"], floor, height,
            "knee (max of normalised width-gain minus normalised descent) of the outer half-width profile between the "
            f"neck and the widest band, or the widest band itself when the profile is a step (method: {lm['shoulder']['method']})",
            "medium"),
        "armpit": None if lm["armpitY"] is None else _lm(
            lm["armpitY"], floor, height,
            "apex of the highest empty gap between torso cluster and arm cluster searching down from the shoulder line",
            "medium"),
        "chest": None if not lm["chest"] else _lm(
            lm["chest"]["y"], floor, height,
            "band of maximum torso front-z between the waist and the shoulder line (bust/pectoral prominence)", "low"),
        "waist": None if not lm["waist"] else _lm(
            lm["waist"]["y"], floor, height,
            "band of minimum torso-cluster width between the hip maximum and the armpit", "medium"),
        "hips": None if not lm["hips"] else _lm(
            lm["hips"]["y"], floor, height,
            "band of maximum torso-cluster width in the lower half between crotch and armpit", "medium"),
        "crotch": None if crotch is None else _lm(
            crotch, floor, height, "top edge of the highest band, contiguous from the leg bottoms, with no vertex "
            f"within {LEG_GAP_FRAC} H of the midline (apex of the inter-leg gap)", "medium"),
        "knee": None if not lm["knee"] else _lm(
            lm["knee"]["y"], floor, height,
            "peak of the smoothed rear-z profile (popliteal hollow) in the middle of the leg, at least "
            f"{KNEE_PROMINENCE_FRAC} H above the calf bulge", "low"),
        "ankle": None if not lm["ankle"] else _lm(
            lm["ankle"]["y"], floor, height, "minimum leg cross-section with a flare below it", "low"),
    }

    # pose class
    pose: dict[str, Any]
    arm_extreme = lm["armExtreme"]
    arm = lm["arm"]
    sh_half = lm["shoulder"]["halfWidthM"] if lm["shoulder"] else None
    if arm["angleDeg"] is not None:
        angle = arm["angleDeg"]
        cls = "T-pose" if angle >= T_POSE_MIN_DEG else ("A-pose" if angle >= A_POSE_MIN_DEG else "arms-at-sides")
        pose = {
            "class": cls,
            "armAngleFromVerticalDeg": angle,
            "method": arm["method"],
            "basis": f"arm angle from vertical ({arm['method']}); T-pose >= {T_POSE_MIN_DEG:g} deg, "
                     f"A-pose >= {A_POSE_MIN_DEG:g} deg, otherwise arms at the sides. Silhouette estimate, not a bone axis",
            "confidence": "medium",
        }
    elif sh_half and arm_extreme["halfSpanM"] <= 1.3 * sh_half:
        pose = {
            "class": "arms-at-sides-or-absent",
            "armAngleFromVerticalDeg": None,
            "basis": "no gap between arm and torso and the widest vertex is within 1.3x the shoulder half-width",
            "confidence": "medium",
        }
    else:
        pose = {
            "class": None,
            "armAngleFromVerticalDeg": None,
            "basis": "no gap between arm and torso was found below the shoulder line, so the arm angle cannot be measured",
            "confidence": "low",
        }
    # segments
    segments: dict[str, Any] = {}
    head_h = (top_skin - chin) if chin is not None else None
    if head_h:
        segments["headsTall"] = height / head_h
        segments["headsTallBasis"] = "H / (skin top - chin); hair excluded"
        segments["headsTallWithHair"] = height / (top - chin)
    if chin is not None and crotch is not None and shoulder_y is not None:
        legs, torso, neck_len, head_len = crotch - floor, shoulder_y - crotch, chin - shoulder_y, head_h
        crown = top - top_skin
        segments["segmentsM"] = {"legs": legs, "torso": torso, "neck": neck_len, "head": head_len, "crownAboveSkin": crown}
        segments["segmentsFracOfH"] = {k: v / height for k, v in segments["segmentsM"].items()}
        segments["segmentsInHeads"] = {k: v / head_h for k, v in segments["segmentsM"].items()}
        segments["legToTorsoToHead"] = [legs / head_len, torso / head_len, 1.0]
        segments["basis"] = ("legs = floor to crotch apex; torso = crotch to shoulder line; neck = shoulder line to chin; "
                             "head = chin to skin top; crownAboveSkin = hair/accessory height above the skin mesh; "
                             "the five segments sum to H")
    else:
        segments["basis"] = "segment ratios need chin, crotch and shoulder line; at least one is null"
    if sh_w:
        segments["shoulderWidthOverH"] = sh_w / height
    if hips_w:
        segments["hipWidthOverH"] = hips_w / height
    if lm["chest"]:
        segments["chestWidthOverH"] = lm["chest"]["widthM"] / height
    if waist_w:
        segments["waistWidthOverH"] = waist_w / height

    # ---- silhouette arrays ---------------------------------------------------------------------
    def series(key: str, scale: float = 1.0) -> list[float | None]:
        return [None if r is None else r[key] * scale for r in rows]

    region: list[str | None] = []
    armpit_band = lm["armpitBand"]
    neck_band = lm["neckBand"]
    merged: list[bool | None] = []
    for i, r in enumerate(rows):
        if r is None:
            region.append(None)
            merged.append(None)
            continue
        yc = band_c(i)
        if chin is not None and yc >= chin:
            region.append("head")
        elif neck_band is not None and i >= neck_band:
            region.append("neck")
        elif shoulder_y is not None and yc >= shoulder_y:
            region.append("shoulders")
        elif crotch is not None and yc < crotch:
            region.append("legs")
        else:
            region.append("torso")
        merged.append(bool(armpit_band is not None and neck_band is not None and armpit_band < i < neck_band))
    silhouette = {
        "bandCount": n_bands,
        "bandHeightFracOfH": 1.0 / n_bands,
        "yFracCentre": [(i + 0.5) / n_bands for i in range(n_bands)],
        "units": "metres; x relative to the midline; z absolute. Divide by heightM for H-fractions (also given as *Frac).",
        "heightM": height,
        "midlineX": mid,
        "vertexCount": series("count"),
        "minX": series("minX"),
        "maxX": series("maxX"),
        "minZ": series("minZ"),
        "maxZ": series("maxZ"),
        "width": [None if r is None else r["maxX"] - r["minX"] for r in rows],
        "depth": [None if r is None else r["maxZ"] - r["minZ"] for r in rows],
        "widthFrac": [None if r is None else (r["maxX"] - r["minX"]) / height for r in rows],
        "depthFrac": [None if r is None else (r["maxZ"] - r["minZ"]) / height for r in rows],
        "torsoVertexCount": series("torsoCount"),
        "torsoMinX": series("torsoMinX"),
        "torsoMaxX": series("torsoMaxX"),
        "torsoMinZ": series("torsoMinZ"),
        "torsoMaxZ": series("torsoMaxZ"),
        "torsoWidth": [None if r is None else _torso_width(r) for r in rows],
        "torsoWidthFrac": [None if r is None else _torso_width(r) / height for r in rows],
        "torsoDepth": [None if r is None else r["torsoMaxZ"] - r["torsoMinZ"] for r in rows],
        "torsoDepthFrac": [None if r is None else (r["torsoMaxZ"] - r["torsoMinZ"]) / height for r in rows],
        "lateralVertexCount": series("lateralCount"),
        "armsMerged": merged,
        "armTrimmed": [None if r is None else bool(r.get("armTrimmed")) for r in rows],
        "region": region,
        "torsoRule": (
            "Per band, surface samples (vertices plus triangle-edge points, <= H/400 apart) are folded about the midline "
            f"(|x - midline|), sorted, and split wherever consecutive values differ by more than {arm_gap_frac} H "
            f"({gap:.4f} m here). The torso cluster is the first run with >= 3 samples; samples beyond it are the arms "
            "(lateral*). Above the armpit apex (armsMerged = true, up to the neck) arm and torso are connected, so the "
            "torso arrays there report the merged silhouette and are an upper bound. T-pose exception: when no band shows "
            "an arm gap and the half-width profile is a step (arms level with the shoulders), bands whose half-width is "
            f">= {ARM_BAND_HALF_WIDTH_RATIO} x the shoulder half-width (read one band above the arm) are cut at "
            f"{TRIM_SHOULDER_RATIO} x the shoulder half-width (armTrimmed = true), so the arms are excluded. Below the "
            "crotch the cluster is both legs together."
        ),
    }

    # ---- atlas ------------------------------------------------------------------------------
    atlas = _atlas(document, bin_payload, path, body, triangles, detail_parts, P, head, lm, height, limits)

    embedded: list[dict[str, Any]] = []
    if atlas and head is not None:
        for isl in ((atlas.get("regions") or {}).get("head") or {}).get("islands", []):
            if isl.get("mirroredTwin") and isl["vertexCount"] < 0.25 * len(head_points):
                embedded.append(
                    {
                        "vertexCount": isl["vertexCount"],
                        "headRelCentre": isl["headRelCentre"],
                        "yRangeM": isl["yRangeM"],
                        "uvBox": isl["uvBox"],
                        "role": "paired-embedded-island",
                        "confidence": "low",
                        "basis": "a small mesh island of the skin mesh with a twin of identical UV box on the other side of the "
                                 "midline (shared, mirrored texture) inside the head: eyeball/iris/inner-mouth-like geometry "
                                 "embedded in the skin mesh",
                    }
                )
    inferred: dict[str, Any] = {
        "landmarks": landmarks,
        "pose": pose,
        "proportions": segments,
        "statements": [
            {
                "statement": f"Pose class: {pose.get('class')}"
                             + (f" (arms about {pose['armAngleFromVerticalDeg']:.0f} deg from vertical)"
                                if pose.get("armAngleFromVerticalDeg") is not None else ""),
                "basis": pose["basis"],
            },
            {
                "statement": "No sex or gender is inferred. Hip, waist, shoulder and chest dimensions are reported as "
                             "measured ratios (observed.torsoWidthRatios, inferred.proportions) for a template to use "
                             "or ignore.",
                "basis": "silhouette widths and depths do not determine sex; classification would be an assumption",
            },
            {
                "statement": "Stylisation is stated by ratios, not by label: heads tall, head width/height and leg:torso:head "
                             "are in inferred.proportions and head.observed.",
                "basis": "measured from the skin mesh; realistic versus stylised is a judgement left to the consumer",
            },
        ],
        "bodyMeshSelection": {"mesh": body.mesh_name, "basis": body_basis},
        "embeddedPairedIslands": embedded,
        **inferred_face,
    }

    limits.extend(
        [
            "Silhouette bands see only vertex positions and triangle edges: surface detail between them, back detail, "
            "and cavities (inside the mouth, behind the ears) are not measured.",
            "Head depth and shape under hair are those of the skin mesh; hair volume is reported separately "
            "(head.observed.withAllMeshesBounds) and the skull beneath it is not known.",
            "Whether eyes, brows, lashes and mouth are geometry or painted cannot be told from the skin silhouette; "
            "separate detail meshes and mirrored twin islands of the skin mesh (inferred.embeddedPairedIslands) are "
            "reported, and their roles are guesses from size and position.",
            "Landmarks are silhouette heuristics at band resolution (H/%d); they are not anatomical bone landmarks." % n_bands,
            "Arm/torso separation uses a gap rule on folded |x|; arms pressed against the torso are merged into it.",
            "The +z facing is assumed (glTF forward) and only cross-checked against the face-detail meshes.",
            "Texel densities and atlas colours describe the atlas as authored; they do not say how the texture reads "
            "under lighting or what is painted outside the sampled UV boxes.",
        ]
    )
    result = {
        "schema": SCHEMA,
        "observed": observed,
        "inferred": inferred,
        "limits": limits,
        "figure": {
            "heightM": height,
            "heightSource": height_source,
            "floorY": floor,
            "topY": top,
            "poseAssumption": "Y-up metres, facing +z, character-left = +x",
        },
        "silhouette": silhouette,
        "head": head_block or None,
        "face": face if head is not None else None,
        "atlas": atlas,
        "options": {"bands": n_bands, "armGapFrac": arm_gap_frac, "bodyMesh": body_mesh, "figureHeight": figure_height},
    }
    return _jsonable(result)


def _read_triangles(
    document: dict[str, Any], bin_payload: bytes, body: _Part, vertex_count: int, limits: list[str]
) -> list[tuple[int, int, int]]:
    if body.indices_accessor is None or body.mode not in (None, 4):
        return []
    try:
        indices = [int(i[0]) for i in rgr.read_accessor(document, bin_payload, body.indices_accessor)]
    except ValueError as err:
        limits.append(f"body mesh indices unreadable ({err})")
        return []
    triangles = _triangles(indices)
    if any(max(t) >= vertex_count or min(t) < 0 for t in triangles):
        limits.append("body mesh indices reference vertices outside the position accessor; triangles discarded")
        return []
    return triangles


def _atlas(
    document: dict[str, Any],
    bin_payload: bytes,
    glb_path: Path,
    body: _Part,
    triangles: Sequence[tuple[int, int, int]],
    detail_parts: Sequence[_Part],
    P: Sequence[Sequence[float]],
    head: _Head | None,
    lm: dict[str, Any],
    height: float,
    limits: list[str],
) -> dict[str, Any] | None:
    if "TEXCOORD_0" not in body.attributes:
        limits.append("atlas: the body mesh has no TEXCOORD_0; UV boxes, texel density and atlas colours are null")
        return None
    uvs = rgr.read_accessor(document, bin_payload, body.attributes["TEXCOORD_0"])
    if len(uvs) != len(P):
        limits.append("atlas: TEXCOORD_0 and POSITION counts differ; atlas analysis skipped")
        return None
    image_index = _image_of_material(document, body.material)
    png_info: dict[str, Any] = {"imageIndex": image_index}
    png_bytes: bytes | None = None
    atlas_size: tuple[int, int] | None = None
    if image_index is None:
        limits.append("atlas: the body material has no baseColorTexture; atlas colours are null")
    else:
        try:
            png_bytes = _image_bytes(document, bin_payload, image_index, glb_path)
            width, hgt, depth, ctype, _c, _f, inter = _png_header(png_bytes)
            atlas_size = (width, hgt)
            png_info.update({"widthPx": width, "heightPx": hgt, "bitDepth": depth, "colourType": ctype,
                             "interlaced": bool(inter), "bytes": len(png_bytes)})
        except (ValueError, OSError, struct.error) as err:
            png_info["error"] = str(err)
            png_bytes = None
            limits.append(f"atlas: image could not be read ({err}); atlas colours are null")

    regions: dict[str, Any] = {}
    region_vertices: dict[str, list[int]] = {}
    face_ids: set[int] = set()
    if head is not None:
        head_ids = [j for j, p in enumerate(P) if p[1] >= head.chin]
        upper = head.top
        front_mid = head.zmin + 0.5 * head.depth
        face_ids_list = [j for j in head_ids if P[j][2] >= front_mid and P[j][1] <= upper]
        face_ids = set(face_ids_list)
        region_vertices["head"] = head_ids
        region_vertices["face"] = face_ids_list
    neck_y = lm["neck"]["y"] if lm.get("neck") else (head.chin if head is not None else None)
    if neck_y is not None:
        region_vertices["body"] = [j for j, p in enumerate(P) if p[1] < neck_y]

    islands = _islands(len(P), triangles) if triangles else None
    dominant_ids: dict[str, list[int]] = {}
    for name, ids in region_vertices.items():
        entry = _uv_descriptor(_uv_box([uvs[j] for j in ids]), atlas_size) or {}
        entry["vertexCount"] = len(ids)
        if islands is not None and ids:
            groups: dict[int, list[int]] = {}
            for j in ids:
                groups.setdefault(islands[j], []).append(j)
            ranked = sorted(groups.values(), key=lambda g: (-len(g), min(g)))
            listed = []
            for g in ranked[:8]:
                if len(g) < 20:
                    continue
                gbox = _bbox([P[j] for j in g])
                item: dict[str, Any] = {
                    "vertexCount": len(g),
                    **(_uv_descriptor(_uv_box([uvs[j] for j in g]), atlas_size) or {}),
                    "bboxM": {"min": gbox[0], "max": gbox[1]},
                    "yRangeM": [gbox[0][1], gbox[1][1]],
                }
                if head is not None:
                    centre = [(gbox[0][k] + gbox[1][k]) / 2.0 for k in range(3)]
                    item["headRelCentre"] = head.rel(centre)
                listed.append(item)
            # an island that has a twin with the same UV box on the other side of the midline is a
            # mirrored (shared-texture) part: left/right eyeball-like geometry embedded in the skin mesh
            for item in listed:
                if head is None:
                    break
                cx = item["headRelCentre"]["x"]
                twin = [
                    o for o in listed
                    if o is not item
                    and all(abs(a - b) < 1e-4 for a, b in zip(o["uvBox"], item["uvBox"]))
                    and o["headRelCentre"]["x"] * cx < 0
                ]
                item["mirroredTwin"] = bool(twin)
            entry["islands"] = listed
            if listed:
                entry["dominantIslandUvBox"] = listed[0]["uvBox"]
                dominant_ids[name] = ranked[0]
        regions[name] = entry

    density: dict[str, Any] = {}
    if atlas_size is not None and triangles:
        def in_set(ids: set[int]):
            return lambda j: j in ids
        sets = {k: set(v) for k, v in region_vertices.items()}
        for name, ids in sets.items():
            density[name] = _texel_density(triangles, P, uvs, atlas_size, in_set(ids), height)
        density["all"] = _texel_density(triangles, P, uvs, atlas_size, lambda j: True, height)
        face_d = (density.get("face") or {}).get("texelsPerMetre")
        body_d = (density.get("body") or {}).get("texelsPerMetre")
        density["faceOverBody"] = (face_d / body_d) if face_d and body_d else None
    elif atlas_size is not None:
        limits.append("atlas: the body mesh has no triangle indices; texel density is null")

    # detail meshes
    detail_entries = []
    for part in detail_parts:
        entry: dict[str, Any] = {"name": part.mesh_name, "vertexCount": len(part.positions), "material": part.material}
        if "TEXCOORD_0" in part.attributes:
            try:
                duv = rgr.read_accessor(document, bin_payload, part.attributes["TEXCOORD_0"])
                entry.update(_uv_descriptor(_uv_box(duv), atlas_size) or {})
                entry["uvClusters"] = _uv_clusters(duv, atlas_size, top=4)
            except ValueError as err:
                entry["error"] = str(err)
        part_image = _image_of_material(document, part.material)
        entry["imageIndex"] = part_image
        entry["sameImageAsSkin"] = (part_image == image_index) if part_image is not None else None
        detail_entries.append(entry)

    # colours: the face is the dominant face island (the union box also spans unrelated islands), the body is its
    # region's UV box
    colours: dict[str, Any] = {"decoded": False}
    if png_bytes is not None and atlas_size is not None:
        boxes: dict[str, list[float]] = {}
        sample_ids: dict[str, list[int]] = {}
        if "face" in dominant_ids:
            boxes["face"] = (regions["face"].get("islands") or [{}])[0].get("uvBox")
            sample_ids["face"] = dominant_ids["face"]
        elif (regions.get("face") or {}).get("uvBox"):
            boxes["face"] = regions["face"]["uvBox"]
            sample_ids["face"] = region_vertices["face"]
        if (regions.get("body") or {}).get("uvBox"):
            boxes["body"] = regions["body"]["uvBox"]
            sample_ids["body"] = region_vertices["body"]
        if boxes:
            max_u = max(b[2] for b in boxes.values())
            max_v = max(b[3] for b in boxes.values())
            try:
                png = _decode_png(
                    png_bytes,
                    max_rows=min(atlas_size[1], int(math.ceil(max_v * atlas_size[1])) + 2),
                    max_cols=min(atlas_size[0], int(math.ceil(max_u * atlas_size[0])) + 2),
                )
                colours = {
                    "decoded": True,
                    "decodedRows": len(png.rows),
                    "decodedColumns": png.cols,
                    "note": "sRGB values 0-255; L* is CIE 1976 from linearised sRGB (D65). `box` statistics include every "
                            "texel inside the UV bounding box (neighbouring islands, painted features); `vertexSampled` "
                            "uses only the texel under each region vertex's UV and is the better skin-colour estimate. "
                            "face = dominant face island, body = skin vertices below the neck.",
                    "regions": {},
                }
                for name, box in boxes.items():
                    pixels = _sample_box(png, box)
                    colours["regions"][name] = {
                        "uvBox": box,
                        "box": _colour_stats(pixels),
                        "paletteK5": _palette(pixels, PALETTE_SIZE),
                    }
                    ids = sample_ids[name]
                    step = max(1, len(ids) // PIXEL_SAMPLE_BUDGET)
                    sampled = []
                    for j in ids[::step]:
                        x = min(png.cols - 1, max(0, int(uvs[j][0] * png.width)))
                        y = min(len(png.rows) - 1, max(0, int(uvs[j][1] * png.height)))
                        sampled.append(png.pixel(x, y))
                    colours["regions"][name]["vertexSampled"] = _colour_stats(sampled)
                    colours["regions"][name]["vertexSampledPaletteK5"] = _palette(sampled, PALETTE_SIZE)
            except (ValueError, zlib.error, struct.error) as err:
                colours = {"decoded": False, "error": str(err)}
                limits.append(f"atlas: PNG could not be decoded ({err}); atlas colours are null")
    face_uv = None
    face_islands = (regions.get("face") or {}).get("islands") or []
    if face_islands:
        main = face_islands[0]
        face_uv = {
            "uvBox": main["uvBox"],
            "pixelBox": main.get("pixelBox"),
            "uvAreaFraction": main["uvAreaFraction"],
            "vertexCount": main["vertexCount"],
            "basis": "UV bounding box of the largest mesh island among the skin vertices that are above the chin, "
                     "in the front half of the head; other islands (eyeball-like pieces, hair-cap) are in regions.face.islands",
        }
    else:
        limits.append("atlas: no UV island found for the face region; faceUv is null")
    return {
        "image": png_info,
        "textureCoordinateConvention": "glTF: origin top-left, v grows downward; pixel row = v * height",
        "regions": regions,
        "texelDensity": density,
        "faceDetailMeshes": detail_entries,
        "faceUv": face_uv,
        "colours": colours,
    }
