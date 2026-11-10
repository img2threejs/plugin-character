"""Pure head transplant geometry. Case: native/transplant_head.py:273-345,727-781.

Boundary welding is only for topology analysis; source geometry is never globally welded.
Bridge manifold counts assume each input ring edge belongs to one adjoining surface.
"""
import numpy as np
from collections import Counter


def fit_similarity(donor_height_z_max, scale, crown_z, y_translation):
    vals = np.array([donor_height_z_max, scale, crown_z, y_translation], float)
    if not np.isfinite(vals).all() or scale <= 0:
        raise ValueError('finite values and positive scale required')
    mat = np.eye(4)
    mat[:3, :3] *= scale
    mat[1, 3] = y_translation
    mat[2, 3] = crown_z - scale * donor_height_z_max
    return mat


def clip_polygon_plane(poly_attrs, z_cut, keep):
    """Clip corner attribute arrays, keyed by 'position'; keep is 'above' or 'below'."""
    if keep not in ('above', 'below') or not np.isfinite(z_cut):
        raise ValueError('invalid clipping plane or side')
    attrs = {k: np.asarray(v, dtype=float) for k, v in poly_attrs.items()}
    if 'position' not in attrs or attrs['position'].ndim != 2 or attrs['position'].shape[1] != 3:
        raise ValueError('position must be an Nx3 array')
    n = len(attrs['position'])
    if n < 3 or any(v.ndim < 1 or len(v) != n or not np.isfinite(v).all() for v in attrs.values()):
        raise ValueError('invalid polygon attributes')
    result = {k: [] for k in attrs}
    inside = lambda z: z >= z_cut if keep == 'above' else z <= z_cut
    def emit(a, b, t):
        for k, v in attrs.items():
            result[k].append(v[a] + t * (v[b] - v[a]))
    for b in range(n):
        a = (b - 1) % n
        za, zb = attrs['position'][[a, b], 2]
        ia, ib = inside(za), inside(zb)
        if ia != ib and za != z_cut and zb != z_cut:
            emit(a, b, (z_cut - za) / (zb - za))
        if ib:
            emit(b, b, 0)
    return {k: np.asarray(v, float).reshape((-1,) + attrs[k].shape[1:]) for k, v in result.items()}


def boundary_rings(polys, weld_eps):
    """Walk all boundary loops of polygon position arrays, welding only in this analysis."""
    if not np.isfinite(weld_eps) or weld_eps <= 0:
        raise ValueError('positive weld epsilon required')
    points, edges = [], Counter()
    for poly in polys:
        p = np.asarray(poly['position'] if isinstance(poly, dict) else poly, float)
        if p.ndim != 2 or p.shape[1] != 3 or len(p) < 3 or not np.isfinite(p).all():
            raise ValueError('invalid polygon')
        ids = []
        for point in p:
            matches = [i for i, q in enumerate(points) if np.linalg.norm(point - q) <= weld_eps]
            if len(matches) > 1:
                raise ValueError('ambiguous boundary weld')
            if matches:
                ids.append(matches[0])
            else:
                ids.append(len(points)); points.append(point.copy())
        for a, b in zip(ids, ids[1:] + ids[:1]):
            if a == b:
                raise ValueError('zero-length edge')
            edges[tuple(sorted((a, b)))] += 1
    if not edges or any(v > 2 for v in edges.values()):
        raise ValueError('empty or nonmanifold topology')
    adj = {}
    for (a, b), count in edges.items():
        if count == 1:
            adj.setdefault(a, []).append(b); adj.setdefault(b, []).append(a)
    if not adj or any(len(v) != 2 for v in adj.values()):
        raise ValueError('boundary is not closed')
    rings = []
    remaining = set(adj)
    while remaining:
        start = min(remaining); seq = [start]; prev = None; cur = start
        while True:
            nxt = min(v for v in adj[cur] if v != prev)
            if nxt == start:
                break
            if nxt not in remaining or nxt in seq:
                raise ValueError('ambiguous boundary')
            seq.append(nxt); prev, cur = cur, nxt
        if len(seq) < 3:
            raise ValueError('short boundary')
        remaining.difference_update(seq)
        rings.append(np.array([points[i] for i in seq]))
    return rings


def bridge_rings(lower, upper, angle_merge):
    """Return (vertices, triangle indices, report); input rings must be star-shaped about their own centres.

    angle_merge is the angular mismatch tolerance in radians; offset and mismatch are reported,
    not silently treated as a geometric fit. Boundary edges include the adjoining surface incidence.
    """
    if not np.isfinite(angle_merge) or angle_merge < 0:
        raise ValueError('invalid angular tolerance')
    rings, angles, centres = [], [], []
    for raw in (lower, upper):
        p = np.asarray(raw, float)
        if p.ndim != 2 or p.shape[1] != 3 or len(p) < 3 or not np.isfinite(p).all():
            raise ValueError('invalid ring')
        c = p[:, :2].mean(axis=0); centres.append(c)
        a = np.mod(np.arctan2(p[:, 1] - c[1], p[:, 0] - c[0]), 2*np.pi)
        area = np.sum(p[:, 0]*np.roll(p[:, 1], -1)-p[:, 1]*np.roll(p[:, 0], -1))
        if abs(area) < 1e-15 or np.any(np.linalg.norm(p[:, :2]-c, axis=1) < 1e-12):
            raise ValueError('degenerate ring')
        if area < 0: p, a = p[::-1], a[::-1]
        start = int(np.argmin(a)); p = np.roll(p, -start, axis=0); a = np.roll(a, -start)
        if np.any(np.diff(a) <= 1e-12):
            raise ValueError('ring must be angularly ordered and star-shaped')
        rings.append(p); angles.append(a)
    n, m = map(len, rings); vertices = np.vstack(rings)
    # Start both rings at their first angle; merge absolute next angles.
    la = np.r_[angles[0], angles[0][0]+2*np.pi]
    ua = np.r_[angles[1], angles[1][0]+2*np.pi]
    i = j = 0; tris = []
    while i < n or j < m:
        if i == n or (j < m and ua[j+1] < la[i+1]):
            tris.append((i % n, n+(j+1)%m, n+j%m)); j += 1
        else:
            tris.append((i%n, (i+1)%n, n+j%m)); i += 1
    # Position-weld for the report only. Do not alter the returned mesh.
    representatives, classes = [], []
    for point in vertices:
        match = next((i for i, q in enumerate(representatives)
                      if np.linalg.norm(point - q) <= 1e-6), None)
        if match is None:
            match = len(representatives)
            representatives.append(point)
        classes.append(match)
    counts = Counter()
    degenerate = 0
    for tri in tris:
        for a, b in zip(tri, tri[1:]+tri[:1]):
            a, b = classes[a], classes[b]
            if a == b:
                degenerate += 1
            else:
                counts[tuple(sorted((a, b)))] += 1
    for offset, count in ((0,n),(n,m)):
        for k in range(count):
            a, b = classes[offset+k], classes[offset+(k+1)%count]
            if a == b:
                degenerate += 1
            else:
                counts[tuple(sorted((a, b)))] += 1
    mismatch = max(max(min(abs(np.angle(np.exp(1j*(a-b)))) for b in angles[1]) for a in angles[0]),
                   max(min(abs(np.angle(np.exp(1j*(b-a)))) for a in angles[0]) for b in angles[1]))
    report = {'open_edges': sum(v == 1 for v in counts.values()), 'nonmanifold_edges': sum(v > 2 for v in counts.values()),
              'edge_count': len(counts), 'triangle_count': len(tris), 'weld_epsilon': 1e-6, 'degenerate_edges': degenerate,
              'count_mismatch': n != m, 'angular_mismatch': float(mismatch),
              'angle_mismatch': bool(mismatch > angle_merge), 'centre_offset': float(np.linalg.norm(centres[0]-centres[1]))}
    return vertices, np.asarray(tris, dtype=int), report


def cheek_masks(eye_x, eye_z, iris_min_z, span, verts, skin_vertices=None):
    """Bilateral cheek masks; verts are Nx3, skin_vertices is a required eligibility mask."""
    p = np.asarray(verts, float)
    if p.ndim != 2 or p.shape[1] != 3 or not np.isfinite(p).all() or not np.isfinite([eye_x, eye_z, iris_min_z, span]).all() or eye_x <= 0 or span <= 0:
        raise ValueError('invalid cheek landmarks or vertices')
    if skin_vertices is None:
        raise ValueError('skin eligibility is required')
    skin = np.asarray(skin_vertices, bool)
    if skin.shape != (len(p),): raise ValueError('invalid skin eligibility')
    cx, cz = 1.30*eye_x, eye_z-.55*span
    r = np.array([.55*eye_x, .70*eye_x, .22*span])
    window = skin & (np.abs(np.abs(p[:,0])-cx) < .5*r[0]) & (np.abs(p[:,2]-cz) < .5*r[2])
    if window.sum() < 3: raise ValueError('insufficient cheek landmark vertices')
    cy = np.median(p[window,1]); result = {}
    for name, sign in (('left', 1), ('right', -1)):
        u = np.maximum(0, 1-np.sum(((p-[sign*cx, cy, cz])/r)**2, axis=1))
        w = u**3*(10-15*u+6*u*u)
        w[(np.abs(p[:,0]) < .68*eye_x) | (p[:,2] > iris_min_z-.009) | ~skin | (np.sign(p[:,0]) != sign)] = 0
        if np.count_nonzero(w > 1e-9) < 8: raise ValueError(f'{name} cheek has fewer than eight active vertices')
        result[name] = w
    return result
