"""Pure catalogue validation and neutral skin-mask mathematics.

No asset data or Blender runtime is loaded by this module. Case-specific values
belong in the cited catalogue, not in computational defaults.
"""
import math
import re
from collections import Counter

import numpy as np


_UNITS = {'m', 'mm', 'px/m', 'px', 'count', 'ratio', 'degree', 'Hz', 'dimensionless'}
_REGIONS = {'abdomen', 'waist-left', 'waist-right', 'cheek-left', 'cheek-right',
            'hair', 'fabric', 'hem', 'hand-left', 'hand-right', 'face', 'neck',
            'head', 'torso'}


def _vector(value, name):
    result = np.asarray(value, dtype=float)
    if result.shape != (3,) or not np.isfinite(result).all():
        raise ValueError(f'{name} must be a finite 3-vector')
    return result


def ellipsoid_mask_weight(point, centre, radii, convert='blender-to-gltf', exclude=None):
    """Evaluate a compact quintic ellipsoid, optionally excluding converted points.

    A reference case uses neutral ellipsoids and Blender-to-glTF axes
    (centres and radii are case data, not defaults). The predicate
    receives the converted point; it is caller-supplied, not anatomical inference.
    """
    p = _vector(point, 'point')
    c = _vector(centre, 'centre')
    r = _vector(radii, 'radii')
    if np.any(r <= 0):
        raise ValueError('radii must be positive')
    if convert == 'blender-to-gltf':
        p = p[[0, 2, 1]] * [1, 1, -1]
    elif convert != 'none':
        raise ValueError('unknown coordinate conversion')
    if exclude is not None:
        if not callable(exclude):
            raise ValueError('exclude must be callable')
        if exclude(p):
            return 0.0
    q = float(np.sum(((p - c) / r) ** 2))
    u = max(0.0, 1.0 - q)
    return u ** 3 * (10 - 15 * u + 6 * u * u)


def normalize_masks(weights):
    """Normalize overlap by max(1, sum), leaving unused mass untouched.

    The case uses this rule for its authored masks (max(1, sum) overlap
    normalization); empty input is not a measurement.
    """
    values = np.asarray(weights, dtype=float)
    if values.ndim != 1 or not values.size or not np.isfinite(values).all() or np.any(values < 0):
        raise ValueError('weights must be a nonempty finite nonnegative vector')
    return values / max(1.0, float(values.sum()))


def mirrored_weight_symmetry(weights_a, weights_b, pairs, bone_permutation):
    """Compare named bone-weight rows through an explicit bilateral permutation.

    Rows are sequences of bone-to-weight mappings. Pairs are index pairs; None,
    duplicate indices, invalid indices and missing bone mappings are reported.
    No tolerance is imposed: the caller owns the acceptance threshold.
    """
    if not weights_a or not weights_b or not pairs or not bone_permutation:
        raise ValueError('nonempty rows, pairs and permutation required')
    for rows in (weights_a, weights_b):
        for row in rows:
            if not isinstance(row, dict) or not row:
                raise ValueError('each row must contain named weights')
            values = np.asarray(list(row.values()), dtype=float)
            if not np.isfinite(values).all() or np.any(values < 0) or not np.isclose(values.sum(), 1.0, atol=1e-6, rtol=0):
                raise ValueError('weight rows must be finite, nonnegative and normalized')
    counts_a = Counter(pair[0] for pair in pairs if len(pair) == 2 and pair[0] is not None)
    counts_b = Counter(pair[1] for pair in pairs if len(pair) == 2 and pair[1] is not None)
    target_counts = Counter(bone_permutation.values())
    unmatched, ambiguous, diffs = [], [], []
    for pair in pairs:
        if len(pair) != 2:
            unmatched.append(pair)
            continue
        a, b = pair
        if not isinstance(a, int) or not isinstance(b, int) or not (0 <= a < len(weights_a) and 0 <= b < len(weights_b)):
            unmatched.append(pair)
            continue
        if counts_a[a] > 1 or counts_b[b] > 1:
            ambiguous.append(pair)
            continue
        row_a, row_b = weights_a[a], weights_b[b]
        if any(name not in bone_permutation for name in row_a):
            unmatched.append(pair)
            continue
        targets = [bone_permutation[name] for name in row_a]
        if any(target_counts[name] != 1 for name in targets):
            ambiguous.append(pair)
            continue
        if set(targets) != set(row_b):
            unmatched.append(pair)
            continue
        diffs.append(max(abs(value - row_b[bone_permutation[name]]) for name, value in row_a.items()))
    used_a = {p[0] for p in pairs if len(p) == 2 and isinstance(p[0], int) and 0 <= p[0] < len(weights_a)}
    used_b = {p[1] for p in pairs if len(p) == 2 and isinstance(p[1], int) and 0 <= p[1] < len(weights_b)}
    unmatched.extend((i, None) for i in range(len(weights_a)) if i not in used_a)
    unmatched.extend((None, i) for i in range(len(weights_b)) if i not in used_b)
    return {'max_difference': max(diffs) if diffs else None, 'compared': len(diffs),
            'unmatched': unmatched, 'ambiguous': ambiguous,
            'measured': bool(diffs) and not unmatched and not ambiguous}


def height_fraction(value, height):
    """Divide compatible lengths by positive height for scale-independent ratios.

    Callers supply the length, height and units; the ratio is meaningful only
    for matching units and frame.
    """
    value, height = float(value), float(height)
    if not math.isfinite(value) or not math.isfinite(height) or height <= 0:
        raise ValueError('value and positive height must be finite')
    return value / height


def validate_catalogue(doc):
    """Validate catalogue structure, not the truth of measurements or permissions."""
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    def ids(items, label):
        require(isinstance(items, list) and bool(items), f'{label} must be nonempty')
        names = [item.get('id') for item in items]
        require(all(isinstance(x, str) and x for x in names), f'{label} needs IDs')
        require(len(names) == len(set(names)), f'duplicate {label} id')
        return set(names)

    def finite(value):
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            return math.isfinite(value)
        return isinstance(value, list) and bool(value) and all(finite(v) for v in value)

    def measurement(item):
        require(isinstance(item, dict) and finite(item.get('value')), 'measurement must be finite and nonempty')
        require(item.get('unit') in _UNITS, 'invalid measurement unit')
        require(item.get('tag') in {'single-subject', 'behaviour'}, 'invalid evidence tag')
        require(isinstance(item.get('source'), str) and re.search(r':\d+', item['source']), 'evidence needs file:line citation')
        for key in ('frame', 'method', 'evidenceClass', 'limitations'):
            require(isinstance(item.get(key), str) and bool(item[key]), f'measurement needs {key}')

    require(isinstance(doc, dict) and doc.get('schema') == 'body-parts/1', 'invalid schema')
    ids(doc.get('characters'), 'character')
    for character in doc['characters']:
        assets = character.get('assets')
        ids(assets, 'asset')
        stages = [asset.get('stage') for asset in assets]
        require(all(isinstance(s, str) and s for s in stages) and len(stages) == len(set(stages)), 'conflicting asset stages')
        for asset in assets:
            require(asset.get('coordinate_basis') and asset.get('rights'), 'asset basis and rights required')
            bone_ids = ids(asset.get('bones'), 'bone')
            mesh_ids = ids(asset.get('meshes'), 'mesh')
            bone_map = {bone['id']: bone for bone in asset['bones']}
            for bone in asset['bones']:
                require(bone.get('side') in {'left', 'right', 'centre', 'unknown'}, 'invalid bone side')
                parent = bone.get('parent')
                require(parent is None or parent in bone_ids, 'dangling bone parent')
                mirror = bone.get('mirror')
                require(mirror is None or mirror in bone_ids, 'dangling bone mirror')
                if mirror is not None:
                    require(bone_map[mirror].get('mirror') == bone['id'], 'nonreciprocal bone mirror')
            part_ids = ids(asset.get('parts'), 'part')
            for part in asset['parts']:
                region = part['id']
                require(region in _REGIONS or re.fullmatch(r'(arm|leg|foot)-[a-z0-9-]+', region), 'forbidden region id')
                require(part.get('side') in {'left', 'right', 'centre', 'unknown'}, 'invalid part side')
                require(part.get('status') in {'present', 'absent', 'unknown'}, 'invalid part status')
                require(all(x in bone_ids for x in part.get('bones', [])), 'dangling part bone')
                require(all(x in mesh_ids for x in part.get('meshes', [])), 'dangling part mesh')
                require(all(x in part_ids for x in part.get('children', [])), 'dangling part child')
            for key in ('bone_groups', 'measurements', 'masks', 'profiles', 'textures'):
                if asset.get(key):
                    ids(asset[key], key)
            for group in asset.get('bone_groups', []):
                require(group.get('bones') and all(x in bone_ids for x in group['bones']), 'dangling group bone')
            for item in asset.get('measurements', []):
                measurement(item)
            for mask in asset.get('masks', []):
                require(mask.get('id') in part_ids, 'dangling mask region')
                require(mask.get('bone') in bone_ids, 'dangling mask bone')
                measurement(mask.get('centre'))
                measurement(mask.get('radii'))
                require(len(mask['centre']['value']) == 3 and len(mask['radii']['value']) == 3 and all(x > 0 for x in mask['radii']['value']), 'invalid mask radii or centre')
            for profile in asset.get('profiles', []):
                require(profile.get('id') in {'abdomen', 'waist', 'cheek'}, 'invalid profile id')
                fields = profile.get('fields', {})
                require(set(fields) == {'frequency', 'dampingRatio', 'cap', 'compression', 'pressDepth'}, 'profile fields incomplete')
                for key, field in fields.items():
                    require(isinstance(field, dict) and field.get('status') in {'present', 'absent'}, 'invalid profile status')
                    if field['status'] == 'absent':
                        require(key == 'pressDepth' and set(field) == {'status'}, 'absent profile field must not have a value or measurement')
                    else:
                        measurement(field.get('measurement'))
                        require('value' not in field, 'profile value must be inside measurement')
                if profile['id'] == 'waist':
                    require(fields['pressDepth']['status'] == 'absent', 'waist pressDepth is absent, not zero')
    return True
