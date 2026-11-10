"""Connected hair-chain binding, separate from geodesic skinning.

Derived from native/donor_hair_rig.py:97-310; classification assumes the dominant
below-pin component is the rear curtain. Ambiguous disconnected geometry is rejected.
"""
import numpy as np


def smooth(x):
    x = np.clip(x, 0, 1)
    return x**3 * (10 - 15*x + 6*x*x)


def weld_seams(positions, eps=1e-6):
    p = np.asarray(positions, float)
    if p.ndim != 2 or p.shape[1] != 3 or not len(p) or not np.isfinite(p).all() or not np.isfinite(eps) or eps <= 0:
        raise ValueError('invalid positions or weld epsilon')
    _, first, inverse = np.unique(np.round(p/eps).astype(np.int64), axis=0, return_index=True, return_inverse=True)
    return p[first], inverse


def classify_front_locks(positions, edges, pin_z):
    p = np.asarray(positions, float); e = np.asarray(edges, int)
    if p.ndim != 2 or p.shape[1] != 3 or not np.isfinite(p).all() or not np.isfinite(pin_z) or e.ndim != 2 or e.shape[1] != 2 or np.any(e < 0) or np.any(e >= len(p)):
        raise ValueError('invalid hair geometry')
    below = p[:,2] < pin_z
    if not below.any() or below.all(): raise ValueError('hair must straddle pin')
    parent = np.arange(len(p))
    def root(i):
        while parent[i] != i:
            i = parent[i]
        return i
    for a,b in e:
        if below[a] and below[b]: parent[root(a)] = root(b)
    groups = {}
    for i in np.flatnonzero(below): groups.setdefault(root(i), []).append(i)
    comps = sorted(groups.values(), key=lambda c: (-len(c), c[0]))
    rear = comps[0]
    if len(rear)*2 < below.sum(): raise ValueError('no dominant rear component')
    split_y = p[rear,1].min(); sides = np.zeros(len(p), int)
    for comp in comps[1:]:
        c = p[comp].mean(axis=0)
        if c[1] >= split_y or abs(c[0]) < .01: raise ValueError('ambiguous front lock')
        sides[comp] = 1 if c[0] > 0 else -1
    return sides


def chain_layout(points, weights, pin_z, tip_z, bones, min_bone_length=.01):
    p = np.asarray(points, float); w = np.asarray(weights, float)
    if p.ndim != 2 or p.shape[1] != 3 or w.shape != (len(p),) or not np.isfinite(p).all() or not np.isfinite(w).all() or np.any(w < 0) or not np.isfinite([pin_z,tip_z,min_bone_length]).all() or not isinstance(bones, int) or bones < 1 or min_bone_length < .01 or pin_z-tip_z < bones*min_bone_length:
        raise ValueError('invalid or too short chain')
    step = (pin_z-tip_z)/bones; result = []
    for level in np.linspace(pin_z, tip_z, bones+1):
        half = max(step*.35, .004)
        for _ in range(8):
            selected = (np.abs(p[:,2]-level) <= half) & (p[:,2] <= pin_z)
            total = w[selected].sum()
            if total > 0: break
            half *= 2
        else: raise ValueError('no points near chain level')
        xy = (p[selected,:2]*w[selected,None]).sum(axis=0)/total
        result.append([*xy, level])
    result = np.asarray(result)
    if np.any(np.linalg.norm(np.diff(result, axis=0),axis=1) < min_bone_length-1e-12): raise ValueError('short bone')
    return result


def hair_weights(positions, inverse, lock_side, centres, chain_heights, face_heights, halfwidth_z, halfwidth, pin_z, blend):
    """Build dense rows and names. heights are descending bone centres per band/side."""
    p = np.asarray(positions, float); inverse = np.asarray(inverse, int); sides = np.asarray(lock_side, int)
    centres = np.asarray(centres, float); hz = np.asarray(halfwidth_z, float); hw = np.asarray(halfwidth, float)
    if p.ndim != 2 or p.shape[1] != 3 or not len(p) or not np.isfinite(p).all() or inverse.ndim != 1 or not len(inverse) or np.any(inverse < 0) or np.any(inverse >= len(p)) or sides.shape != (len(p),) or not np.isin(sides, [-1,0,1]).all() or len(centres) < 2 or not np.isfinite(centres).all() or np.any(np.diff(centres) >= 0) or hz.ndim != 1 or len(hz) < 2 or hw.shape != hz.shape or not np.isfinite(hz).all() or not np.isfinite(hw).all() or np.any(np.diff(hz) <= 0) or np.any(hw <= 0) or not np.isfinite([pin_z,blend]).all() or blend <= 0:
        raise ValueError('invalid binding inputs')
    if len(chain_heights) != len(centres) or set(face_heights) != {-1,1}: raise ValueError('missing chain heights')
    heights = [np.asarray(x, float) for x in chain_heights] + [np.asarray(face_heights[s],float) for s in (-1,1)]
    if any(h.ndim != 1 or not len(h) or not np.isfinite(h).all() or np.any(np.diff(h) >= 0) for h in heights): raise ValueError('invalid bone heights')
    names = ['Head']; indices = []
    for i,h in enumerate(heights):
        indices.append(list(range(len(names),len(names)+len(h))))
        names.extend(f'chain_{i}_{k}' for k in range(len(h)))
    rows = np.zeros((len(p),len(names)))
    for v,(x,_,z) in enumerate(p):
        head = 1-float(smooth((pin_z-z)/blend)); rows[v,0] = head
        if head == 1: continue
        if sides[v]: sources = [(len(centres)+(0 if sides[v] == -1 else 1),1.)]
        else:
            s = x/np.interp(z,hz,hw)
            b = int(np.clip(np.searchsorted(-centres,-s)-1,0,len(centres)-2))
            t = float(smooth((centres[b]-s)/(centres[b]-centres[b+1])))
            sources = [(b,1-t),(b+1,t)]
        for band,lat in sources:
            h = heights[band]; k = int(np.clip(np.searchsorted(-h,-z)-1,0,max(0,len(h)-2)))
            if len(h) == 1: rows[v,indices[band][0]] += (1-head)*lat
            else:
                t = float(smooth((h[k]-z)/(h[k]-h[k+1])))
                rows[v,indices[band][k]] += (1-head)*lat*(1-t)
                rows[v,indices[band][k+1]] += (1-head)*lat*t
        rows[v,rows[v] < 1e-4] = 0
        if np.count_nonzero(rows[v]) > 4: raise ValueError('more than four influences; adjust chain heights')
        total = rows[v].sum()
        if total <= 0: raise ValueError('empty binding')
        rows[v] /= total
    return names, rows[inverse]


def validate_binding(positions, weights, pin_z, head_index=0, eps=1e-6):
    p = np.asarray(positions, float); w = np.asarray(weights, float)
    if p.ndim != 2 or p.shape[1] != 3 or not len(p) or w.ndim != 2 or len(w) != len(p) or not w.shape[1] or not 0 <= head_index < w.shape[1] or not np.isfinite(w).all() or np.any(w < 0) or not np.isfinite(pin_z): raise ValueError('invalid or unmeasured binding')
    if np.any((w > 0).sum(axis=1) > 4): raise ValueError('more than four influences')
    if not np.allclose(w.sum(axis=1),1,rtol=0,atol=1e-6): raise ValueError('unnormalised weights')
    _, inv = weld_seams(p,eps)
    for group in range(inv.max()+1):
        rows = w[inv == group]
        if not np.allclose(rows,rows[0],rtol=0,atol=1e-6): raise ValueError('seam unequal weights')
    roots = p[:,2] >= pin_z
    if not roots.any(): raise ValueError('unmeasured roots')
    if not np.allclose(w[roots,head_index],1,rtol=0,atol=1e-6): raise ValueError('unpinned roots')
    return {'vertices': len(p), 'roots': int(roots.sum()), 'max_influences': int((w > 0).sum(axis=1).max())}
