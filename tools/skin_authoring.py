"""Reference-relative painted base tone, not reflectance, pores or de-lighting.

Images are encoded sRGB arrays. Masks and pixel coordinates are top-down unless
explicitly supplied otherwise. No spatial adjacency is inferred from UV proximity.
"""
import numpy as np



NEUTRAL_REGIONS = frozenset({'face', 'cheek-left', 'cheek-right', 'neck', 'arm',
    'arm-left', 'arm-right', 'hand', 'hand-left', 'hand-right', 'leg',
    'leg-left', 'leg-right', 'foot', 'foot-left', 'foot-right', 'abdomen',
    'waist-left', 'waist-right'})


def _neutral(names):
    if not names or set(names) - NEUTRAL_REGIONS:
        raise ValueError('only explicitly named neutral semantic regions are allowed')


def _rgb(rgb):
    a = np.asarray(rgb)
    if a.ndim != 3 or a.shape[2] != 3 or not a.size:
        raise ValueError('expected nonempty H x W x 3 RGB')
    if a.dtype == np.uint8:
        return a.astype(float) / 255
    a = np.asarray(a, float)
    if not np.isfinite(a).all() or np.any((a < 0) | (a > 1)):
        raise ValueError('RGB must be finite encoded sRGB in [0,1]')
    return a


def _lstar(rgb):
    linear = np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
    y = linear @ np.array([.2126, .7152, .0722])
    delta = 6 / 29
    return 116 * np.where(y > delta ** 3, np.cbrt(y), y / (3 * delta ** 2) + 4 / 29) - 16


def _masks(masks, shape):
    _neutral(masks)
    result = {name: np.asarray(mask, bool) for name, mask in masks.items()}
    if not result or any(m.shape != shape or not m.any() for m in result.values()):
        raise ValueError('each region requires a nonempty matching mask')
    return result


def region_tone_report(rgb, masks):
    """Median per-channel encoded RGB and median per-pixel L*, not L* of median RGB."""
    a = _rgb(rgb)
    return {name: {'rgb': np.median(a[m], axis=0).tolist(),
                   'lstar': float(np.median(_lstar(a[m]))), 'count': int(m.sum())}
            for name, m in _masks(masks, a.shape[:2]).items()}


def region_tone_targets(reference_patches, *, color_space='encoded-srgb', statistic='median', min_pixels):
    """Sample valid unclipped reference patches; clipping is not recoverable lighting.

    Case: reference job (not bundled). Any
    channel at either encoded endpoint is considered clipped; no universal
    exposure or lighting correction is inferred.
    """
    if color_space != 'encoded-srgb' or statistic != 'median' or not isinstance(min_pixels, int) or min_pixels < 1 or not reference_patches:
        raise ValueError('expected encoded-srgb median and positive min_pixels')
    _neutral(reference_patches)
    result = {}
    for name, patch in reference_patches.items():
        a = np.asarray(patch)
        if a.ndim == 2 and a.shape[-1] == 3:
            a = a.reshape(1, -1, 3)
        a = _rgb(a)
        if a.shape[0] * a.shape[1] < min_pixels or np.any((a <= 0) | (a >= 1)):
            raise ValueError(f'{name}: insufficient or clipped reference pixels')
        result[name] = region_tone_report(a, {name: np.ones(a.shape[:2], bool)})[name]
    return result


def region_uniformity(rgb, masks, quantiles=(.5, .9, .99)):
    """Report distance quantiles and L* range; the reference sets the limit."""
    a = _rgb(rgb); q = np.asarray(quantiles, float)
    if q.ndim != 1 or not len(q) or not np.isfinite(q).all() or np.any((q < 0) | (q > 1)):
        raise ValueError('invalid quantiles')
    out = {}
    for name, m in _masks(masks, a.shape[:2]).items():
        pixels = a[m]; l = _lstar(pixels)
        out[name] = {'quantiles': q.tolist(), 'rgb_distance': np.quantile(np.linalg.norm(pixels - np.median(pixels, axis=0), axis=1), q).tolist(),
                     'lstar_spread': float(l.max() - l.min()), 'count': len(pixels)}
    return out


def author_region_base(shape, region_masks, targets, *, feather_px, ownership):
    """Paint owned regions; only explicitly 3D-adjacent transition masks may blend.

    ``shape`` is an existing RGB image or (H,W,3) for a zero-initialized image.
    Ownership contains integer ``islands`` (zero means unowned) and optional
    ``transitions``: {regions:[a,b], islands:[id,...], mask, adjacent_3d:true}.
    Feathering uses bounded four-neighbour distances within that mask; no UV
    adjacency is assumed. The receipt compares actual pixels outside support.
    """
    if isinstance(shape, tuple):
        source = np.zeros(shape, float)
    else:
        source = np.asarray(shape).copy()
    a = _rgb(source); masks = _masks(region_masks, a.shape[:2])
    islands = np.asarray(ownership['islands'])
    if islands.shape != a.shape[:2] or not np.issubdtype(islands.dtype, np.integer) or not isinstance(feather_px, int) or feather_px < 0:
        raise ValueError('invalid island ownership or feather radius')
    stack = np.stack(list(masks.values()))
    if np.any(stack.sum(axis=0) > 1) or np.any(stack.any(axis=0) & (islands <= 0)):
        raise ValueError('overlapping or unowned region masks')
    work = a.copy(); support = stack.any(axis=0)
    tones = {}
    for name, mask in masks.items():
        tone = np.asarray(targets[name]['rgb'], float)
        if tone.shape != (3,) or not np.isfinite(tone).all() or np.any((tone < 0) | (tone > 1)):
            raise ValueError('invalid target tone')
        tones[name] = tone; work[mask] = tone
    for band in ownership.get('transitions', []):
        names = band['regions']; ids = band['islands']; mask = np.asarray(band['mask'], bool)
        if len(names) != 2 or names[0] == names[1] or any(n not in masks for n in names) or band.get('adjacent_3d') is not True or not ids or mask.shape != islands.shape or np.any(mask & ~np.isin(islands, ids)) or np.any(mask & ~support):
            raise ValueError('invalid declared adjacent transition')
        if np.any(mask & ~(masks[names[0]] | masks[names[1]])):
            raise ValueError('transition intersects another region')
        if feather_px:
            # Distances propagate only within the declared transition.
            distances = []
            for n in names:
                reached = masks[n] & mask; dist = np.full(mask.shape, feather_px + 1, float); dist[reached] = 0
                for step in range(1, feather_px + 1):
                    expanded = _expand(reached) & mask
                    dist[expanded & ~reached] = step; reached = expanded
                distances.append(dist)
            da, db = distances
            blend = mask & (da <= feather_px) & (db <= feather_px) & ((da + db) > 0)
            t = np.clip(.5 + (da[blend] - db[blend]) / (2 * feather_px), 0, 1)
            work[blend] = (1-t[:, None])*tones[names[0]] + t[:, None]*tones[names[1]]
    result = source.copy()
    result[support] = np.rint(work[support] * 255).astype(np.uint8) if source.dtype == np.uint8 else work[support]
    changed = np.any(result != source, axis=2)
    return result, {'region_pixel_counts': {n: int(m.sum()) for n, m in masks.items()},
                    'support': support, 'changed_outside_declared_support': int(np.count_nonzero(changed & ~support))}


def _expand(mask):
    out = mask.copy(); out[1:] |= mask[:-1]; out[:-1] |= mask[1:]; out[:, 1:] |= mask[:, :-1]; out[:, :-1] |= mask[:, 1:]
    return out


def mirror_residual(rgb, pairs):
    """Maximum encoded channel error over explicit pixel pairs; no symmetry inferred."""
    a = _rgb(rgb); pairs = list(pairs)
    if not pairs:
        raise ValueError('mirror pairs required')
    vals = []
    for p, q in pairs:
        if len(p) != 2 or len(q) != 2 or any(not isinstance(v, (int, np.integer)) for v in (*p, *q)) or any(v < 0 for v in (*p, *q)) or p[0] >= a.shape[0] or q[0] >= a.shape[0] or p[1] >= a.shape[1] or q[1] >= a.shape[1]:
            raise ValueError('invalid mirror pixel coordinate')
        vals.append(float(np.max(np.abs(a[tuple(p)] - a[tuple(q)]))))
    return max(vals)


def enforce_mirror_consistency(rgb, pairs, *, tolerance):
    """Copy first to second for explicit disjoint pairs; report before/after residual."""
    if not np.isfinite(tolerance) or tolerance < 0:
        raise ValueError('invalid tolerance')
    pairs = list(pairs); before = mirror_residual(rgb, pairs); result = np.asarray(rgb).copy()
    indices = [tuple(p) for pair in pairs for p in pair]
    if len(set(indices)) != len(indices):
        raise ValueError('mirror pairs must be disjoint')
    for p, q in pairs: result[tuple(q)] = result[tuple(p)]
    after = mirror_residual(result, pairs)
    return result, {'before': before, 'residual': after, 'within_tolerance': after <= tolerance}


def pad_islands(rgb, ownership, radius_px):
    """Bounded nearest-owner four-neighbour dilation; ties and -1 barriers stay untouched."""
    _rgb(rgb); owner = np.asarray(ownership)
    if owner.shape != np.asarray(rgb).shape[:2] or not np.issubdtype(owner.dtype, np.integer) or np.any(owner < -1) or not isinstance(radius_px, int) or radius_px < 0:
        raise ValueError('invalid ownership or radius')
    result = np.asarray(rgb).copy(); labels = owner.copy(); dist = np.full(owner.shape, -1, int); dist[owner > 0] = 0
    for step in range(1, radius_px + 1):
        candidates = []
        for dy, dx in ((1,0), (-1,0), (0,1), (0,-1)):
            lab = np.zeros_like(labels); col = np.zeros_like(result)
            ys = slice(max(0,dy), min(owner.shape[0],owner.shape[0]+dy)); xs = slice(max(0,dx), min(owner.shape[1],owner.shape[1]+dx))
            srcy = slice(max(0,-dy), min(owner.shape[0],owner.shape[0]-dy)); srcx = slice(max(0,-dx), min(owner.shape[1],owner.shape[1]-dx))
            lab[ys,xs] = np.where(dist[srcy,srcx] == step-1, labels[srcy,srcx], 0); col[ys,xs] = result[srcy,srcx]
            candidates.append((lab,col))
        labs = np.stack([x[0] for x in candidates]); maximum = labs.max(axis=0)
        minimum = np.where(labs > 0, labs, np.iinfo(np.int64).max).min(axis=0)
        fill = (owner == 0) & (dist < 0) & (maximum > 0) & (maximum == minimum)
        labels[fill] = maximum[fill]; dist[fill] = step
        for lab, col in candidates:
            take = fill & (lab == maximum); result[take] = col[take]; fill[take] = False
    return result, {'ownership': labels, 'distance': dist}


def seam_padding_report(rgb, ownership, radius_px):
    """Measure complete identical-color nearest-owner layers up to a declared radius.

    Ties and protected pixels are excluded; this does not simulate filtering or
    establish 3D seam color continuity. Unreachable layers are unmeasured.
    """
    a = np.asarray(rgb); expected, info = pad_islands(a, ownership, radius_px)
    owner = np.asarray(ownership); dist = info['distance']; minimum = 0; measured = False
    for step in range(1, radius_px + 1):
        ring = (owner == 0) & (dist == step)
        if not ring.any(): break
        measured = True
        if np.any(a[ring] != expected[ring]): break
        minimum = step
    return {'min_px': minimum if measured else None, 'tested_radius_px': radius_px}


def texel_density(uv_tri_area_px, world_tri_area_m, region_of_tri):
    """Area-weighted px/m, anatomy.py:1037-1059; duplicate UVs count per triangle."""
    uv = np.asarray(uv_tri_area_px, float); world = np.asarray(world_tri_area_m, float); regions = np.asarray(region_of_tri)
    if uv.ndim != 1 or world.shape != uv.shape or regions.shape != uv.shape or not len(uv) or not np.isfinite(uv).all() or not np.isfinite(world).all() or np.any(uv < 0) or np.any(world <= 0):
        raise ValueError('invalid triangle areas or regions')
    densities = {str(r): float(np.sqrt(uv[regions == r].sum() / world[regions == r].sum())) for r in np.unique(regions)}
    ratio = densities['face'] / densities['body'] if densities.get('body', 0) > 0 and 'face' in densities else None
    return {'regions': densities, 'face_body_ratio': ratio}
