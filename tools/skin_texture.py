"""Array-based painted skin atlas operations; inputs are not measured reflectance.

Images are caller-supplied top-down stored-sRGB RGB arrays, either uint8 or
floating point in [0, 1]. No historical subject palette is supplied.
"""
import hashlib
from pathlib import Path

import numpy as np

try:  # imported as tools.skin_texture (the tests) ...
    from . import atlas_surface
except ImportError:  # ... or with tools/ on sys.path (the plugin's other tools and CLI use)
    import atlas_surface


def _image(rgb):
    a = np.asarray(rgb)
    if a.ndim != 3 or a.shape[2] != 3 or not a.size:
        raise ValueError('expected a nonempty H x W x 3 image')
    if a.dtype == np.uint8:
        return a, a.astype(float) / 255
    if not np.issubdtype(a.dtype, np.floating) or not np.isfinite(a).all() or np.any((a < 0) | (a > 1)):
        raise ValueError('expected finite uint8 or floating sRGB in [0, 1]')
    return a, a.astype(float)


def _mask(mask, shape):
    a = np.asarray(mask, dtype=bool)
    if a.shape != shape:
        raise ValueError('mask shape mismatch')
    return a


def _output(source, work, selected):
    result = source.copy()
    values = np.clip(work[selected], 0, 1)
    result[selected] = np.rint(values * 255).astype(np.uint8) if source.dtype == np.uint8 else values
    return result


def _luminance(a):
    return a @ np.array([.2126, .7152, .0722])


def _saturation(a):
    high = a.max(axis=-1)
    return (high - a.min(axis=-1)) / np.maximum(high, 1e-8)


def _smooth(a, lo, hi):
    if not np.isfinite([lo, hi]).all() or hi <= lo:
        raise ValueError('smoothstep limits must increase')
    t = np.clip((a - lo) / (hi - lo), 0, 1)
    return t * t * (3 - 2 * t)


def _dilate(mask, iterations, blocked=None):
    if not isinstance(iterations, int) or iterations < 0:
        raise ValueError('dilation must be a nonnegative integer')
    out = mask.copy()
    blocked = np.zeros_like(out) if blocked is None else blocked
    for _ in range(iterations):
        n = out.copy()
        n[1:] |= out[:-1]; n[:-1] |= out[1:]
        n[:, 1:] |= out[:, :-1]; n[:, :-1] |= out[:, 1:]
        out = n & ~blocked
    return out


def _neighbours(field):
    # Edge replication is bounded: unlike roll, opposite edges are never neighbours.
    p = np.pad(field, ((1, 1), (1, 1)) + ((0, 0),) * (field.ndim - 2), mode='edge')
    return p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:]


def rasterize_regions(positions, triangles, loop_uv, image_shape, predicates, origin='top-down', overlap_policy='exclude'):
    """Rasterize centroid-classified triangles at texel centres, excluding shared UVs by default.

    [behaviour] build_head.py:339-355 used a .02 barycentric tolerance; this
    conservative raster can mark adjacent boundaries ambiguous. Predicates take
    a triangle's (3,3) positions; crossings are not geometrically clipped.
    UVs are Blender bottom-up; output origin explicitly selects row ordering.
    """
    p = np.asarray(positions, float); t = np.asarray(triangles); uv = np.asarray(loop_uv, float)
    if p.ndim != 2 or p.shape[1] != 3 or not len(p) or not np.isfinite(p).all():
        raise ValueError('invalid positions')
    if t.ndim != 2 or t.shape[1] != 3 or not np.issubdtype(t.dtype, np.integer) or not len(t) or np.any(t < 0) or np.any(t >= len(p)):
        raise ValueError('invalid triangles')
    if uv.shape != (len(t), 3, 2) or not np.isfinite(uv).all():
        raise ValueError('loop_uv must be (triangles, 3, 2)')
    if len(image_shape) < 2 or any(not isinstance(x, (int, np.integer)) or x <= 0 for x in image_shape[:2]):
        raise ValueError('invalid image shape')
    if origin not in ('top-down', 'bottom-up') or overlap_policy not in ('exclude', 'report', 'error') or not predicates:
        raise ValueError('invalid origin, overlap policy or predicates')
    h, w = image_shape[:2]
    names = list(predicates)
    masks = {name: np.zeros((h, w), bool) for name in names}
    owners = np.zeros((h, w), np.uint64)
    seen = np.zeros((h, w), bool)
    multiple = np.zeros((h, w), bool)
    if len(names) > 62:
        raise ValueError('at most 62 regions supported')
    triangle_counts = dict.fromkeys(names, 0); degenerate = off_image = 0
    for verts, coords in zip(t, uv):
        flags = [bool(predicates[name](p[verts])) for name in names]
        for name, active in zip(names, flags):
            triangle_counts[name] += int(active)
        bits = sum(1 << i for i, active in enumerate(flags) if active) or (1 << len(names))
        xy = coords * [w, h]
        xy[:, 1] = h - xy[:, 1]
        a, b, c = xy
        d = (b[0]-a[0]) * (c[1]-a[1]) - (b[1]-a[1]) * (c[0]-a[0])
        if abs(d) < 1e-9:
            degenerate += 1; continue
        lo = np.maximum(np.floor(xy.min(axis=0) - 1).astype(int), 0)
        hi = np.minimum(np.ceil(xy.max(axis=0) + 1).astype(int), [w-1, h-1])
        if np.any(hi < lo):
            off_image += 1; continue
        y, x = np.mgrid[lo[1]:hi[1]+1, lo[0]:hi[0]+1]; x = x + .5; y = y + .5
        u = ((x-a[0])*(c-a)[1] - (y-a[1])*(c-a)[0]) / d
        v = ((b-a)[0]*(y-a[1]) - (b-a)[1]*(x-a[0])) / d
        inside = (u >= -.02) & (v >= -.02) & (u+v <= 1.02)
        sl = np.s_[lo[1]:hi[1]+1, lo[0]:hi[0]+1]
        multiple[sl] |= seen[sl] & inside
        seen[sl] |= inside
        owners[sl][inside] |= np.uint64(bits)
        for name, active in zip(names, flags):
            if active:
                masks[name][sl] |= inside
    shared = multiple | ((owners & (owners - np.uint64(1))) != 0)
    if overlap_policy == 'error' and shared.any():
        raise ValueError('shared or ambiguous UV texels')
    raw_counts = {name: int(mask.sum()) for name, mask in masks.items()}
    if overlap_policy == 'exclude':
        masks = {name: mask & ~shared for name, mask in masks.items()}
    if origin == 'bottom-up':
        masks = {name: mask[::-1].copy() for name, mask in masks.items()}
        shared = shared[::-1].copy()
    return masks, {'triangle_counts': triangle_counts, 'raw_texels': raw_counts,
                   'texels': {name: int(m.sum()) for name, m in masks.items()},
                   'empty': [name for name, m in masks.items() if not m.any()],
                   'shared_texels': int(shared.sum()), 'shared_mask': shared,
                   'degenerate_triangles': degenerate, 'off_image_triangles': off_image}


def measure_tone(rgb, mask, statistic='median', color_space='encoded-srgb', luminance_gate=None):
    """Measure selected channel statistics; encoded gate and linear gate are distinct.

    The caller chooses the luminance gate in the named colour space.
    Neither statistic estimates unpainted reflectance.
    """
    _, a = _image(rgb); selected = _mask(mask, a.shape[:2]).copy()
    if statistic not in ('median', 'mean') or color_space not in ('encoded-srgb', 'linear'):
        raise ValueError('invalid statistic or color space')
    data = a if color_space == 'encoded-srgb' else atlas_surface.srgb_to_linear(a)
    if luminance_gate is not None:
        if not np.isfinite(luminance_gate):
            raise ValueError('invalid luminance gate')
        selected &= _luminance(data) < luminance_gate
    values = data[selected]
    if not len(values) or not np.isfinite(values).all():
        raise ValueError('empty or nonfinite tone samples')
    value = np.median(values, axis=0) if statistic == 'median' else np.mean(values, axis=0)
    return {'count': len(values), 'value': value.tolist(), 'diagnostics': {'statistic': statistic,
            'color_space': color_space, 'luminance_gate': luminance_gate,
            'minimum': values.min(axis=0).tolist(), 'maximum': values.max(axis=0).tolist()}}


def fill_skin_island(rgb, island_mask, sample_mask, dilation, protected_mask=None):
    """Fill a selected island with encoded-channel median and explicit padding.

    Supply all other islands as protected; absent protection cannot establish ownership.
    """
    source, work = _image(rgb); shape = work.shape[:2]
    island = _mask(island_mask, shape); sample = _mask(sample_mask, shape)
    protected = np.zeros(shape, bool) if protected_mask is None else _mask(protected_mask, shape)
    if not island.any() or np.any(island & protected):
        raise ValueError('empty island or protected overlap')
    tone = measure_tone(source, sample)['value']
    support = _dilate(island, dilation, protected)
    painted = work.copy(); painted[support] = tone
    return _output(source, painted, support), {'island_pixels': int(island.sum()), 'filled_pixels': int(support.sum()), 'sample_pixels': int(sample.sum()), 'fill_srgb': tone, 'support': support}


def lift_shadow(rgb, neck_mask, reference_mask, params):
    """Lift selected paint with caller-selected gates, padding, blur and strength."""
    required = ('dark_luminance', 'dilation', 'blur_iterations', 'strength', 'darkness_gate')
    if not isinstance(params, dict) or any(k not in params for k in required):
        raise ValueError('complete explicit shadow parameters required')
    source, a = _image(rgb); shape = a.shape[:2]
    neck = _mask(neck_mask, shape); ref = _mask(reference_mask, shape)
    dark = measure_tone(source, neck, luminance_gate=params['dark_luminance'])
    target = measure_tone(source, ref)
    gain = np.asarray(target['value']) / np.maximum(dark['value'], .001)
    feather = _dilate(neck, params['dilation']).astype(float)
    for _ in range(params['blur_iterations']):
        feather = (feather + _neighbours(feather)) / 5
    strength = params['strength']
    if not np.isfinite(strength) or not 0 <= strength <= 1:
        raise ValueError('invalid strength')
    lo, hi = params['darkness_gate']
    weight = feather * (1 - _smooth(_luminance(a), lo, hi)) * strength
    support = weight > 0
    result = _output(source, a * (1 + weight[..., None] * (gain - 1)), support)
    return result, {'gain': gain.tolist(), 'dark_count': dark['count'], 'reference_count': target['count'], 'support': support, 'changed_pixels': int(np.any(result != source, axis=2).sum())}


def repair_root_paint(rgb, original_rgb, spatial_mask, recipe, *, iterations):
    """Repair explicitly eligible warm paint using bounded harmonic fill.

    Recipe requires boxes, saturation_ranges and an explicit nearby_mask.
    Iteration count is caller-selected; array edges never wrap.
    """
    source, a = _image(rgb); _, original = _image(original_rgb)
    if original.shape != a.shape:
        raise ValueError('original image shape mismatch')
    spatial = np.asarray(spatial_mask, float)
    if spatial.shape != a.shape[:2] or not np.isfinite(spatial).all() or np.any((spatial < 0) | (spatial > 1)):
        raise ValueError('invalid spatial mask')
    if not isinstance(iterations, int) or iterations < 1:
        raise ValueError('iterations must be positive')
    boxes, ranges = recipe['boxes'], recipe['saturation_ranges']
    if not boxes or len(boxes) != len(ranges):
        raise ValueError('paint boxes and saturation ranges required')
    weight = np.zeros(a.shape[:2], float)
    for box, limits in zip(boxes, ranges):
        x0, y0, x1, y1 = box
        if not (0 <= x0 < x1 <= a.shape[1] and 0 <= y0 < y1 <= a.shape[0]):
            raise ValueError('invalid box')
        reg = original[y0:y1, x0:x1]
        orange = (reg[..., 0] > reg[..., 1]) & (reg[..., 1] > reg[..., 2])
        weight[y0:y1, x0:x1] = np.maximum(weight[y0:y1, x0:x1], orange * _smooth(_saturation(reg), *limits))
    weight *= spatial
    active = weight > 0
    nearby = _mask(recipe['nearby_mask'], a.shape[:2]) & ~active
    if not active.any() or not nearby.any():
        raise ValueError('empty root selection or local skin samples')
    clean = np.median(a[nearby], axis=0)
    fill = a.copy(); fill[active] = clean
    for _ in range(iterations):
        average = _neighbours(fill) / 4
        fill[active] = average[active]
    result = _output(source, a * (1-weight[..., None]) + fill * weight[..., None], active)
    return result, {'selected_pixels': int(active.sum()), 'changed_pixels': int(np.any(result != source, axis=2).sum()), 'local_median': clean.tolist(), 'support': active, 'boundary': 'bounded'}


def repair_color_line(rgb, shadow_rgb, skin_rgb, box, gate):
    """Delegate caller-calibrated bounded colour-line repair.

    Chromaticity alone cannot prove the source pigment is a shadow.
    """
    return atlas_surface.color_line_repair(rgb, shadow_rgb, skin_rgb, box, gate)


def recolor_details(rgb, boxes, predicates, palette):
    """Recolour selected iris, brow and crease boxes while protecting highlights.

    Selection gates and pigment curves are explicitly supplied in the palette.
    Box-based selection cannot prove anatomical ownership.
    """
    source, a = _image(rgb); result = a.copy(); counts = {}
    background = np.asarray(palette['background'], float)
    required = ('background_distance', 'highlight_luminance', 'highlight_saturation', 'iris_curve', 'brow_gain')
    if any(k not in palette for k in required):
        raise ValueError('complete explicit detail selection and pigment curves required')
    curve = np.asarray(palette['iris_curve'], float)
    brow_gain = np.asarray(palette['brow_gain'], float)
    if curve.shape != (3,) or brow_gain.shape != (3,) or not np.isfinite(curve).all() or not np.isfinite(brow_gain).all() or curve[1] <= 0 or curve[2] <= 0:
        raise ValueError('invalid detail pigment curve')
    if background.shape != (3,) or not np.isfinite(background).all():
        raise ValueError('invalid background')
    for name, box in boxes.items():
        if name not in ('iris', 'brow', 'crease'):
            raise ValueError('unknown detail')
        x0, y0, x1, y1 = box
        if not (0 <= x0 < x1 <= a.shape[1] and 0 <= y0 < y1 <= a.shape[0]):
            raise ValueError('invalid box')
        sl = np.s_[y0:y1, x0:x1]; reg = a[sl]; lum = _luminance(reg)
        eligible = np.linalg.norm(reg-background, axis=2) > palette['background_distance']
        if name in predicates:
            eligible &= _mask(predicates[name], a.shape[:2])[sl]
        highlights = (lum > palette['highlight_luminance']) & (_saturation(reg) < palette['highlight_saturation'])
        selected = eligible & ~highlights
        if name == 'iris':
            t = np.clip((lum-curve[0])/curve[1], 0, 1)**curve[2]
            dark = np.asarray(palette['iris_dark']); bright = np.asarray(palette['iris_bright'])
            paint = dark + (bright-dark)*t[..., None]
        elif name == 'brow':
            paint = np.asarray(palette['brow_dark']) + lum[..., None] * brow_gain
        else:
            paint = reg * palette['crease_multiply']
        result[sl][selected] = paint[selected]
        counts[name] = {'selected': int(selected.sum()), 'protected': int((eligible & highlights).sum())}
    changed = np.any(result != a, axis=2)
    return _output(source, result, changed), counts


def recolor_iris(rgb, hue_deg, *, thresholds, coverage=None):
    """Map cyan pigment to a hue in [0,60], preserving every other texel.

    Caller thresholds and UV coverage determine pigment eligibility.
    Counts over a whole map differ from UV coverage counts.
    """
    source, a = _image(rgb)
    if not np.isfinite(hue_deg) or not 0 <= hue_deg <= 60:
        raise ValueError('hue must be in [0, 60]')
    sat, minimum, blue_ratio, green_ratio = (thresholds[k] for k in ('saturation', 'maximum', 'blue_ratio', 'green_ratio'))
    if not np.isfinite([sat, minimum, blue_ratio, green_ratio]).all():
        raise ValueError('invalid thresholds')
    domain = np.ones(a.shape[:2], bool) if coverage is None else _mask(coverage, a.shape[:2])
    high = a.max(axis=2); low = a.min(axis=2)
    pigment = domain & (_saturation(a) > sat) & (high > minimum) & (a[..., 2] > blue_ratio*a[..., 0]) & (a[..., 1] > green_ratio*a[..., 0])
    mapped = np.stack((high, low+(high-low)*hue_deg/60, low), axis=2)
    result = _output(source, mapped, pigment)
    return result, {'pigment': int(pigment.sum()), 'changed': int(np.any(result != source, axis=2).sum()), 'protected': int((domain & ~pigment).sum()), 'domain': 'full-map' if coverage is None else 'uv-covered', 'padding': 0}


def build_composite(body, face, neck, ring_uvs, layout=None):
    """Build bottom-up composite and linear-light bridge using atlas_surface.

    The fixed W x 9W/8 layout is an algorithmic format. ring_uvs is a pair
    of sampled rings or owner-UV dictionaries. Geometry alignment is separate.
    """
    for donor in (face, neck):
        arr = np.asarray(donor)
        if arr.dtype != np.uint8 or (arr.ndim == 3 and arr.shape[2] == 4 and np.any(arr[..., 3] != 255)):
            raise ValueError('donor must be opaque uint8')
    composite = atlas_surface.composite_atlas(body, face, neck, layout=layout)
    layout = composite['layout']; atlas = composite['atlas']
    if len(ring_uvs) != 2:
        raise ValueError('two bridge rings required')
    start, end = layout.strip_rows
    atlas[start:end, :, :3] = atlas_surface.neck_strip(ring_uvs[0], ring_uvs[1], layout.width, end-start)
    return atlas, {'body': layout.body_uv, 'face': layout.face_uv, 'neck': layout.neck_uv}, {'layout': layout, 'tiles': composite['tiles'], 'strip_rows': composite['strip_rows']}


def save_pack_verify(image, path, *, packed_bytes=None):
    """Write and reload an opaque PNG, comparing exact saved and packed bytes.

    Explicit packed bytes avoid retaining stale pixels. No Blender state is altered.
    """
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo
    import io
    source = np.asarray(image)
    if source.dtype != np.uint8 or source.ndim != 3 or source.shape[2] not in (3, 4) or not source.size or (source.shape[2] == 4 and np.any(source[..., 3] != 255)):
        raise ValueError('opaque uint8 RGB or RGBA required')
    path = Path(path)
    info = PngInfo()
    info.add(b'sRGB', b'\x00')
    Image.fromarray(source, 'RGB' if source.shape[2] == 3 else 'RGBA').save(path, format='PNG', pnginfo=info)
    saved = path.read_bytes()
    packed = saved if packed_bytes is None else bytes(packed_bytes)
    if packed != saved:
        raise ValueError('packed image bytes are stale or differ from saved PNG')
    with Image.open(io.BytesIO(packed)) as decoded:
        pixels = np.asarray(decoded)
    if not np.array_equal(pixels, source):
        raise ValueError('reloaded image pixels differ')
    return {'path': str(path), 'sha256': hashlib.sha256(saved).hexdigest(), 'bytes': len(saved), 'packed_bytes': packed, 'pixel_equal': True}


def pack_blender_image(image, saved_bytes):
    """Pack verified saved bytes into a Blender image.

    [behaviour] Explicit bytes avoid stale packing; caller owns node association
    and must verify the resulting exported asset independently.
    """
    try:
        import bpy  # noqa: F401
    except ImportError as exc:
        raise RuntimeError('Blender bpy is required for packing') from exc
    image.pack(data=bytes(saved_bytes), data_len=len(saved_bytes))


def skin_material_spec(params):
    """Return an explicit native material specification, not invented texture maps.

    Parameters must be supplied; native scattering is not browser scattering.
    """
    required = ('metallic', 'roughness', 'ior', 'subsurface_weight', 'subsurface_radius', 'subsurface_scale', 'detail_roughness', 'base_color_map', 'normal_map', 'roughness_map')
    if any(k not in params for k in required):
        raise ValueError('complete material parameters required')
    spec = {k: params[k] for k in required}
    scalar = [spec[k] for k in ('metallic', 'roughness', 'ior', 'subsurface_weight', 'subsurface_scale', 'detail_roughness')]
    radius = np.asarray(spec['subsurface_radius'], float)
    if not np.isfinite(scalar).all() or radius.shape != (3,) or not np.isfinite(radius).all() or np.any(radius < 0) or not 0 <= spec['metallic'] <= 1 or not 0 <= spec['roughness'] <= 1 or not 0 <= spec['detail_roughness'] <= 1 or not 0 <= spec['subsurface_weight'] <= 1 or spec['ior'] <= 0 or spec['subsurface_scale'] < 0:
        raise ValueError('invalid material values')
    spec['subsurface_radius'] = radius.tolist()
    spec['micro_detail'] = 'unmeasured'
    spec['base_color_space'] = 'sRGB'
    return spec


def validate_skin_material(spec, exported):
    """Compare actual exported maps/scalars, reporting native SSS separately."""
    failures = []
    for key in ('base_color_map', 'normal_map', 'roughness_map'):
        if spec.get(key) and not exported.get(key):
            failures.append('missing ' + key)
    for key in ('metallic', 'roughness'):
        if key not in exported or not np.isclose(exported[key], spec[key]):
            failures.append('missing or mismatched ' + key)
    if spec.get('base_color_map') and exported.get('base_color_space') != 'sRGB':
        failures.append('base color must be sRGB')
    for key in ('normal_map', 'roughness_map'):
        if spec.get(key) and exported.get(key + '_color_space') != 'linear':
            failures.append(key + ' must be linear')
    return {'ok': not failures, 'failures': failures, 'native_scattering': 'not exported', 'micro_detail': 'unmeasured'}


def tone_match_report(before, after, masks, *, deviation_limit):
    """Report encoded medians and deviations above the caller's explicit limit."""
    if not np.isfinite(deviation_limit) or deviation_limit < 0:
        raise ValueError('finite nonnegative deviation_limit required')
    _, a = _image(before); _, b = _image(after)
    if a.shape != b.shape or not masks:
        raise ValueError('matching images and masks required')
    report = {}
    for name, raw in masks.items():
        mask = _mask(raw, a.shape[:2])
        if not mask.any():
            raise ValueError('empty island: ' + name)
        x, y = a[mask], b[mask]; xmed = np.median(x, axis=0); ymed = np.median(y, axis=0)
        report[name] = {'count': len(x), 'before_median': xmed.tolist(), 'after_median': ymed.tolist(), 'before_deviation_count': int((np.linalg.norm(x-xmed, axis=1) > deviation_limit).sum()), 'after_deviation_count': int((np.linalg.norm(y-ymed, axis=1) > deviation_limit).sum())}
    return report
