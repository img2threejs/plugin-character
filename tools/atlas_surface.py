#!/usr/bin/env python3
"""Head-atlas layout, neck-strip blending and bounded colour-line repair.

This module is the numpy-only core of the head-atlas recipe distilled from the
``robin-bikini-transfer-01`` case study. It contains no bpy calls, no file IO
and no subject-specific defaults: every measurement enters as an explicit
argument.

The rules encoded here, and the case that produced each one:

* **Atlas phase boundary** -- the original body occupies the bottom ``4/9`` of
  the composite, the donor face and donor neck occupy the middle ``4/9`` as two
  half-width tiles, and the neck bridge owns the top ``1/9``. Body UV is
  ``(u, 4v/9)``, face UV is ``(u/2, 4/9 + 4v/9)``, and neck UV adds ``0.5`` to
  U (``native/transplant_head.py:447-472,759-773``). The measured composites in
  that job are ``2048x2304`` and ``4096x4608`` -- the same normalised layout at
  two resolutions.
* **Resolution-scaled bridge padding** -- the strip is padded by
  ``4 * width / 2048`` pixels and blended with ``smoothstep`` in linear light,
  which keeps the bridge V endpoints identical at 2048 and 4096
  (``native/transplant_head.py:37,475-488``).
* **Bounded nape repair** -- the repair projects only onto the measured
  shadow-to-skin colour line, feathers inside the declared box and changes no
  pixel outside it (``native/nape_atlas.py:10-37``).

Limits: this module paints and samples pixels. It does not cut geometry, does
not weld topology and cannot tell a legitimate skin colour from a measured
one; the repair thresholds remain single-subject measurements and must be
passed explicitly by a caller that owns a different source atlas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

__all__ = [
    "AtlasLayout",
    "bridge_v_endpoints",
    "color_line_repair",
    "composite_atlas",
    "composite_atlas_layout",
    "linear_to_srgb",
    "neck_strip",
    "srgb_to_linear",
    "assert_zero_change_outside_mask",
]


# --------------------------------------------------------------------------------------------- colour maths
def srgb_to_linear(values: Any) -> np.ndarray:
    """Decode stored sRGB samples to linear light.

    ``values`` may be a float array in the encoded ``0..1`` range or an integer
    array in ``0..255``; integer inputs are scaled by 255 before decoding. The
    exact IEC 61966-2-1 transfer function is used so that encode(decode(byte))
    is byte-exact.
    """
    array = np.asarray(values)
    if np.issubdtype(array.dtype, np.integer):
        array = array.astype(np.float64) / 255.0
    else:
        array = array.astype(np.float64)
    decoded = np.where(array <= 0.04045, array / 12.92, ((array + 0.055) / 1.055) ** 2.4)
    return decoded.astype(np.float64)


def linear_to_srgb(values: Any) -> np.ndarray:
    """Encode linear-light samples as stored sRGB in the ``0..1`` range."""
    array = np.clip(np.asarray(values, dtype=np.float64), 0.0, 1.0)
    encoded = np.where(array <= 0.0031308, array * 12.92, 1.055 * np.power(np.maximum(array, 1e-12), 1.0 / 2.4) - 0.055)
    return encoded.astype(np.float64)


def _as_rgb01(value: Sequence[float]) -> np.ndarray:
    """Accept ``0..1`` floats or ``0..255`` integers and return floats in ``0..1``."""
    array = np.asarray(value, dtype=np.float64).reshape(-1)
    if array.size != 3:
        raise ValueError("expected three RGB components, got %d" % array.size)
    if np.any(array > 1.0):
        array = array / 255.0
    return np.clip(array, 0.0, 1.0)


# --------------------------------------------------------------------------------------------- atlas layout
@dataclass(frozen=True)
class AtlasLayout:
    """Normalised layout of one ``W x 9W/8`` head atlas.

    Rows are addressed from the bottom (V=0) like the case study's Blender
    pixel buffers. The dataclass is immutable; the remap methods are pure.
    """

    width: int
    body_height: int
    donor_tile: int
    strip_height: int
    height: int

    @property
    def body_rows(self) -> tuple[int, int]:
        return (0, self.body_height)

    @property
    def donor_rows(self) -> tuple[int, int]:
        return (self.body_height, self.body_height + self.donor_tile)

    @property
    def strip_rows(self) -> tuple[int, int]:
        return (self.body_height + self.donor_tile, self.height)

    @property
    def face_cols(self) -> tuple[int, int]:
        return (0, self.donor_tile)

    @property
    def neck_cols(self) -> tuple[int, int]:
        return (self.donor_tile, self.width)

    def body_uv(self, uv: Any) -> np.ndarray:
        """Map original body UV into the composite: ``(u, 4v/9)``."""
        points = np.asarray(uv, dtype=np.float64)
        return np.column_stack((points[..., 0], points[..., 1] * 4.0 / 9.0))

    def face_uv(self, uv: Any) -> np.ndarray:
        """Map donor face UV into the composite: ``(u/2, 4/9 + 4v/9)``."""
        points = np.asarray(uv, dtype=np.float64)
        return np.column_stack((points[..., 0] * 0.5, 4.0 / 9.0 + points[..., 1] * 4.0 / 9.0))

    def neck_uv(self, uv: Any) -> np.ndarray:
        """Map donor neck UV into the composite: ``(u/2 + 0.5, 4/9 + 4v/9)``."""
        points = np.asarray(uv, dtype=np.float64)
        return np.column_stack((points[..., 0] * 0.5 + 0.5, 4.0 / 9.0 + points[..., 1] * 4.0 / 9.0))


def composite_atlas_layout(W: int, body_shape: Sequence[int] | None = None) -> AtlasLayout:
    """Return the normalised composite layout for an atlas of width ``W``.

    ``W`` must be a positive multiple of eight so that the body tile is
    ``W x W/2``, the donor tiles are ``W/2`` square and the bridge strip is
    ``W/8`` rows tall (``native/transplant_head.py:447-472``).

    When ``body_shape`` is supplied it must be exactly ``(W/2, W)``; this is
    the phase-boundary check that keeps a mis-sized original atlas from being
    silently composited.
    """
    if not isinstance(W, (int, np.integer)):
        raise ValueError("atlas width must be an integer")
    width = int(W)
    if width <= 0:
        raise ValueError("atlas width must be positive, got %d" % width)
    if width % 8 != 0:
        raise ValueError("atlas width W must be divisible by 8, got %d" % width)
    body_height = width // 2
    donor_tile = width // 2
    strip_height = width // 8
    layout = AtlasLayout(
        width=width,
        body_height=body_height,
        donor_tile=donor_tile,
        strip_height=strip_height,
        height=body_height + donor_tile + strip_height,
    )
    if body_shape is not None:
        shape = tuple(int(v) for v in np.asarray(body_shape).reshape(-1)[:2])
        if shape != (body_height, width):
            raise ValueError(
                "original body atlas must be %r, got %r" % ((body_height, width), shape)
            )
    return layout


def _bilinear_2x_stored(values: np.ndarray) -> np.ndarray:
    """Texel-centre 2x upsample of stored (already encoded) samples.

    ``out[2i] = .75 * a[i] + .25 * a[i-1]`` and ``out[2i+1] = .75 * a[i] +
    .25 * a[i+1]``, edge clamped, applied separably. This is the case study's
    declared donor upsample (``native/build_halloween.py:1045-1080``); it is
    deliberately *not* a linear-light resample.
    """

    def axis(array: np.ndarray, ax: int) -> np.ndarray:
        count = array.shape[ax]
        previous_index = np.concatenate(([0], np.arange(0, count - 1)))
        next_index = np.concatenate((np.arange(1, count), [count - 1]))
        previous = np.take(array, previous_index, axis=ax)
        following = np.take(array, next_index, axis=ax)
        even = 0.75 * array + 0.25 * previous
        odd = 0.75 * array + 0.25 * following
        stacked = np.stack((even, odd), axis=ax + 1)
        shape = list(array.shape)
        shape[ax] = count * 2
        return stacked.reshape(shape)

    working = np.asarray(values, dtype=np.float64)
    return axis(axis(working, 0), 1)


def composite_atlas(
    body: Any,
    face: Any,
    neck: Any,
    *,
    layout: AtlasLayout | None = None,
) -> dict[str, Any]:
    """Composite original body, donor face and donor neck into one atlas.

    The original body pixels are copied byte-for-byte into the bottom band; the
    donor tiles are copied 1:1 or, when supplied at half the tile size,
    upsampled with the case study's declared texel-centre bilinear 2x rule. The
    bridge strip is left empty for :func:`neck_strip`.
    """
    body_array = np.asarray(body)
    if body_array.ndim != 3 or body_array.shape[2] not in (3, 4):
        raise ValueError("body atlas must be (H, W, 3) or (H, W, 4), got %r" % (body_array.shape,))
    if body_array.dtype != np.uint8:
        raise ValueError("original body atlas must be 8-bit")
    if body_array.shape[2] == 4 and np.any(body_array[..., 3] != 255):
        raise ValueError("original body atlas must be opaque")
    if layout is None:
        layout = composite_atlas_layout(body_array.shape[1], body_array.shape[:2])
    if tuple(body_array.shape[:2]) != (layout.body_height, layout.width):
        raise ValueError(
            "original body atlas must be %dx%d, got %dx%d"
            % (layout.body_height, layout.width, body_array.shape[0], body_array.shape[1])
        )

    channels = body_array.shape[2]
    atlas = np.zeros((layout.height, layout.width, channels), dtype=body_array.dtype)
    if channels == 4:
        atlas[..., 3] = 255
    atlas[layout.body_rows[0]:layout.body_rows[1]] = body_array

    tiles: dict[str, Any] = {}
    for name, donor, cols in (("face", face, layout.face_cols), ("neck", neck, layout.neck_cols)):
        donor_array = np.asarray(donor)
        if donor_array.ndim != 3 or donor_array.shape[2] not in (3, 4):
            raise ValueError("%s donor atlas must be (H, W, 3) or (H, W, 4)" % name)
        donor_rgb = donor_array[..., :3]
        if donor_rgb.shape[0] == donor_rgb.shape[1] == layout.donor_tile:
            fitted, how = donor_rgb, "copied 1:1"
        elif donor_rgb.shape[0] == donor_rgb.shape[1] == layout.donor_tile // 2:
            fitted, how = _bilinear_2x_stored(donor_rgb), "declared texel-centre bilinear 2x"
        else:
            raise ValueError(
                "%s donor atlas %r does not fit the %dpx donor tile" % (name, donor_rgb.shape, layout.donor_tile)
            )
        if np.issubdtype(atlas.dtype, np.integer):
            fitted = np.rint(fitted)
        atlas[layout.donor_rows[0]:layout.donor_rows[1], cols[0]:cols[1], :3] = fitted.astype(
            atlas.dtype, copy=False
        )
        tiles[name] = {
            "rows": list(layout.donor_rows),
            "cols": list(cols),
            "resample": how,
            "source_size": list(donor_rgb.shape[:2]),
        }

    return {
        "atlas": atlas,
        "layout": layout,
        "tiles": tiles,
        "strip_rows": list(layout.strip_rows),
    }


# --------------------------------------------------------------------------------------------- neck strip
def _ring_angle_samples(ring: Any, width: int) -> np.ndarray:
    """Sample a ring at the strip's column angles.

    Accepted ring descriptions:

    * ``{"rel": (n+1,), "uva": (n,2), "uvb": (n,2), "atlas": image}``
      interpolates owner UVs then samples the image with repeat-bilinear filtering;
    * ``{"rel": (n+1,), "edge_start": (n, 3), "edge_end": (n, 3)}`` -- the
      case study's owner-edge UV interpolation, with colours already sampled
      from the source atlas (``native/transplant_head.py:382-403``);
    * ``{"rel": (n+1,), "samples": (n+1, 3)}`` -- vertex colours at the ring
      angles;
    * an ``(n, 3)`` array -- colours sampled uniformly at the mid-angle of each
      of ``n`` equal sectors.

    Colours are returned in stored (encoded) sRGB in the ``0..1`` range.
    """
    columns = int(width)
    if columns <= 0:
        raise ValueError("strip width must be positive, got %d" % columns)
    angles = (np.arange(columns, dtype=np.float64) + 0.5) / columns * 2.0 * np.pi

    if isinstance(ring, Mapping):
        if all(k in ring for k in ("rel", "uva", "uvb", "atlas")):
            rel = np.asarray(ring["rel"], dtype=float)
            uva, uvb = np.asarray(ring["uva"], dtype=float), np.asarray(ring["uvb"], dtype=float)
            image = np.asarray(ring["atlas"])
            if (rel.ndim != 1 or rel.size < 2 or np.any(np.diff(rel) <= 0)
                    or rel[0] > 0 or rel[-1] < 2*np.pi
                    or uva.shape != (rel.size-1, 2) or uvb.shape != uva.shape
                    or image.ndim != 3 or image.shape[2] < 3 or min(image.shape[:2]) < 1):
                raise ValueError("invalid ring UVs, angles or atlas")
            index = np.clip(np.searchsorted(rel, angles, side="right")-1, 0, rel.size-2)
            f = ((angles-rel[index])/(rel[index+1]-rel[index]))[:, None]
            uv = uva[index]*(1-f)+uvb[index]*f
            h, w = image.shape[:2]
            x, y = uv[:, 0]*w-.5, uv[:, 1]*h-.5
            x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
            fx, fy = (x-x0)[:, None], (y-y0)[:, None]
            pixels = image[..., :3].astype(float)
            if np.issubdtype(image.dtype, np.integer):
                pixels /= 255
            def px(dx, dy):
                return pixels[(y0+dy)%h, (x0+dx)%w]
            return (px(0,0)*(1-fx)*(1-fy) + px(1,0)*fx*(1-fy)
                    + px(0,1)*(1-fx)*fy + px(1,1)*fx*fy)
        if "rel" in ring and ("edge_start" in ring or "edge_end" in ring):
            rel = np.asarray(ring["rel"], dtype=np.float64)
            start = np.asarray(ring["edge_start"], dtype=np.float64)
            end = np.asarray(ring.get("edge_end", ring["edge_start"]), dtype=np.float64)
            if rel.size < 2 or start.shape[0] != rel.size - 1 or end.shape[0] != rel.size - 1:
                raise ValueError("ring edge arrays must match len(rel)-1")
            index = np.clip(np.searchsorted(rel, angles, side="right") - 1, 0, rel.size - 2)
            fraction = (angles - rel[index]) / (rel[index + 1] - rel[index])
            return start[index] * (1.0 - fraction[:, None]) + end[index] * fraction[:, None]
        if "rel" in ring and "samples" in ring:
            rel = np.asarray(ring["rel"], dtype=np.float64)
            samples = np.asarray(ring["samples"], dtype=np.float64)
            if rel.size != samples.shape[0]:
                raise ValueError("ring samples must match len(rel)")
            index = np.clip(np.searchsorted(rel, angles, side="right") - 1, 0, rel.size - 2)
            fraction = (angles - rel[index]) / (rel[index + 1] - rel[index])
            return samples[index] * (1.0 - fraction[:, None]) + samples[index + 1] * fraction[:, None]
        raise ValueError("ring mapping must provide 'rel' plus 'edge_start'/'edge_end' or 'samples'")

    samples = np.asarray(ring)
    if samples.ndim != 2 or samples.shape[1] != 3:
        raise ValueError("ring array must be (n, 3), got %r" % (samples.shape,))
    if np.issubdtype(samples.dtype, np.integer):
        samples = samples.astype(np.float64) / 255.0
    else:
        samples = samples.astype(np.float64)
    count = samples.shape[0]
    if count < 2:
        raise ValueError("ring needs at least two samples")
    position = angles * count / (2.0 * np.pi) - 0.5
    base = np.floor(position)
    fraction = (position - base)[:, None]
    lower = base.astype(np.int64) % count
    upper = (base.astype(np.int64) + 1) % count
    return samples[lower] * (1.0 - fraction) + samples[upper] * fraction


def neck_strip(
    low_ring: Any,
    up_ring: Any,
    width: int,
    count: int,
    pad_scale: float = 1.0,
) -> np.ndarray:
    """Blend the two neck rings into the bridge strip.

    The blend happens in linear light. The parameter along the strip is
    ``t = clip((row + 0.5 - pad) / (count - 2 * pad), 0, 1)`` followed by
    ``t^2 * (3 - 2t)`` and the padding is resolution scaled:
    ``pad = 4 * width / 2048 * pad_scale`` (``native/transplant_head.py:475-488``).

    The result is encoded sRGB quantised to ``uint8``; the first and last
    rows are exactly the low and up ring colours.
    """
    columns = int(width)
    rows = int(count)
    if columns <= 0 or rows <= 0:
        raise ValueError("strip width and count must be positive")
    pad = 4.0 * columns / 2048.0 * float(pad_scale)
    if rows <= 2.0 * pad:
        raise ValueError("strip count %d is too small for padding %.3f" % (rows, pad))

    low = srgb_to_linear(_ring_angle_samples(low_ring, columns))
    up = srgb_to_linear(_ring_angle_samples(up_ring, columns))
    if low.shape != up.shape:
        raise ValueError("low and up rings must yield the same sample shape")

    t = np.clip((np.arange(rows, dtype=np.float64) + 0.5 - pad) / (rows - 2.0 * pad), 0.0, 1.0)
    t = t * t * (3.0 - 2.0 * t)
    blended = (1.0 - t)[:, None, None] * low[None, :, :] + t[:, None, None] * up[None, :, :]
    encoded = np.rint(np.clip(linear_to_srgb(blended), 0.0, 1.0) * 255.0).astype(np.uint8)
    return encoded


def bridge_v_endpoints(
    width: int,
    *,
    count: int | None = None,
    pad_scale: float = 1.0,
    layout: AtlasLayout | None = None,
) -> dict[str, Any]:
    """Return the bridge's normalised V endpoints for an atlas width.

    The endpoints include the resolution-scaled padding, so the returned
    ``v_bottom`` and ``v_top`` are identical at ``width=2048`` and
    ``width=4096`` (``native/transplant_head.py:482-488``).
    """
    if layout is None:
        layout = composite_atlas_layout(width)
    rows = int(count) if count is not None else layout.strip_height
    row0, row1 = layout.strip_rows
    if row0 + rows > layout.height:
        raise ValueError("strip of %d rows does not fit the atlas" % rows)
    pad = 4.0 * layout.width / 2048.0 * float(pad_scale)
    return {
        "rows": [row0, row0 + rows],
        "pad_px": pad,
        "v_bottom": (row0 + pad) / layout.height,
        "v_top": (row0 + rows - pad) / layout.height,
        "height": layout.height,
    }


# --------------------------------------------------------------------------------------------- colour-line repair


def assert_zero_change_outside_mask(
    before: Any,
    after: Any,
    mask: Any,
    *,
    label: str = "mask",
) -> None:
    """Raise when any pixel outside ``mask`` changed.

    The repair gate is only meaningful if it is bounded; this is the explicit
    check that the bounded claim is true for the arrays it was given.
    """
    before_array = np.asarray(before)
    after_array = np.asarray(after)
    if before_array.shape != after_array.shape:
        raise ValueError("before/after shapes differ: %r vs %r" % (before_array.shape, after_array.shape))
    mask_array = np.asarray(mask, dtype=bool)
    if mask_array.shape != before_array.shape[:2]:
        raise ValueError("mask shape %r does not match image %r" % (mask_array.shape, before_array.shape))
    changed = np.any(before_array != after_array, axis=-1)
    outside = changed & ~mask_array
    if np.any(outside):
        raise ValueError(
            "colour repair changed %d pixel(s) outside the %s" % (int(outside.sum()), label)
        )


def color_line_repair(
    img: Any,
    shadow_rgb: Sequence[float],
    skin_rgb: Sequence[float],
    box: Sequence[float],
    gate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Repair a painted shadow by projecting onto the shadow-to-skin colour line.

    ``img`` is an ``(H, W, 3)`` stored-sRGB image (``uint8`` or float in
    ``0..1``). ``shadow_rgb`` and ``skin_rgb`` are the measured colours at the
    two ends of the line; integers are interpreted as ``0..255`` levels.
    ``box`` is ``(u0, v0, u1, v1)`` in normalised, top-down image coordinates.

    The pixel weight is the case study's: projection amount along the colour
    line, a residual gate ``clip((r - residual) / fade, 0, 1)`` and a spatial
    feather inside the box (``native/nape_atlas.py:10-37``). The gate values
    are single-subject measurements and must be supplied through ``gate``.

    The returned image is a new array; the input is never modified. A pixel
    outside the box is never written, and the caller can independently verify
    that with :func:`assert_zero_change_outside_mask`.
    """
    source = np.asarray(img)
    if source.ndim != 3 or source.shape[2] != 3:
        raise ValueError("image must be (H, W, 3), got %r" % (source.shape,))
    integer = np.issubdtype(source.dtype, np.integer)
    work = source.astype(np.float64)
    if integer:
        work = work / 255.0

    shadow = _as_rgb01(shadow_rgb)
    skin = _as_rgb01(skin_rgb)
    delta = skin - shadow
    denominator = float(np.dot(delta, delta))
    if denominator <= 0.0:
        raise ValueError("shadow_rgb and skin_rgb must differ")

    bounds = [float(v) for v in np.asarray(box, dtype=np.float64).reshape(-1)]
    if len(bounds) != 4:
        raise ValueError("box must be (u0, v0, u1, v1)")
    u0, v0, u1, v1 = bounds
    if not (u0 < u1 and v0 < v1):
        raise ValueError("box must satisfy u0<u1 and v0<v1")

    if gate is None:
        raise ValueError("repair gate measurements are required")
    settings = dict(gate)
    if not {"residual", "residual_fade", "u_feather", "v_feather"} <= settings.keys():
        raise ValueError("repair gate is incomplete")
    if settings["residual_fade"] <= 0 or any(x <= 0 for x in (*settings["u_feather"], *settings["v_feather"])):
        raise ValueError("repair gate feather widths must be positive")

    height, width = source.shape[:2]
    u = (np.arange(width, dtype=np.float64) + 0.5) / width
    v = (np.arange(height, dtype=np.float64) + 0.5) / height

    amount = np.clip(np.sum((skin - work) * delta, axis=2) / denominator, 0.0, 1.0)
    residual = np.linalg.norm(work - (skin - amount[..., None] * delta), axis=2)
    match = np.clip((float(settings["residual"]) - residual) / float(settings["residual_fade"]), 0.0, 1.0)
    match = match * match * (3.0 - 2.0 * match)

    u_f0, u_f1 = (float(x) for x in settings["u_feather"])
    v_f0, v_f1 = (float(x) for x in settings["v_feather"])
    edge_u = np.minimum((u - u0) / u_f0, (u1 - u) / u_f1)
    edge_v = np.minimum((v - v0) / v_f0, (v1 - v) / v_f1)
    feather = np.clip(np.minimum(edge_v[:, None], edge_u[None, :]), 0.0, 1.0)
    feather = feather * feather * (3.0 - 2.0 * feather)
    weight = amount * match * feather

    repaired = np.clip(work + weight[..., None] * delta, 0.0, 1.0)
    allowed = (u[None, :] > u0) & (u[None, :] < u1) & (v[:, None] > v0) & (v[:, None] < v1)

    if integer:
        result = np.rint(repaired * 255.0).astype(np.uint8)
    else:
        result = repaired.astype(source.dtype)
    result[~allowed] = source[~allowed]

    assert_zero_change_outside_mask(source, result, allowed, label="repair box")
    changed = np.any(source != result, axis=2)
    return {
        "image": result,
        "changed_pixels": int(changed.sum()),
        "outside_changes": 0,
        "mask": allowed,
        "gate": {
            "residual": float(settings["residual"]),
            "residual_fade": float(settings["residual_fade"]),
            "u_feather": list(settings["u_feather"]),
            "v_feather": list(settings["v_feather"]),
        },
    }
