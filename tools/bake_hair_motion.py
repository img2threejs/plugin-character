"""Fixed-root spring hair motion with explicit caller parameters.

Targets are already carried to world space by the caller. No collision solver or
Blender keyframe writer is provided; callers must check clearance independently.
"""
import math
import numpy as np


def simulate_chain(targets, dt, hz_start, hz_end, zeta, substeps):
    """Integrate world-space targets (frames, joints, 3), projecting rest lengths."""
    t = np.asarray(targets, float)
    if t.ndim != 3 or t.shape[2] != 3 or t.shape[0] < 1 or t.shape[1] < 2 or not np.isfinite(t).all() or not np.isfinite([dt,hz_start,hz_end,zeta]).all() or dt <= 0 or min(hz_start,hz_end) <= 0 or zeta < 0 or not isinstance(substeps, int) or substeps < 1:
        raise ValueError('invalid spring parameters or targets')
    lengths = np.linalg.norm(np.diff(t[0], axis=0), axis=1)
    if np.any(lengths <= 1e-12): raise ValueError('zero-length segment')
    omega = 2*np.pi*np.linspace(hz_start,hz_end,len(lengths)); h = dt/substeps
    if max(omega)*h > .2 + 1e-15: raise ValueError('omega*h exceeds 0.2')
    p = t[0].copy(); vel = np.zeros_like(p)
    if len(t) > 1: vel[1:] = (t[1,1:]-t[0,1:])/dt
    out = [p.copy()]
    for frame in range(1,len(t)):
        for s in range(1,substeps+1):
            target = t[frame-1] + (t[frame]-t[frame-1])*(s/substeps)
            old = p.copy(); p[0] = target[0]
            vel[1:] += ((target[1:]-p[1:])*omega[:,None]**2 - vel[1:]*(2*zeta*omega[:,None]))*h
            p[1:] += vel[1:]*h
            for k,length in enumerate(lengths,1):
                d = p[k]-p[k-1]; norm = np.linalg.norm(d)
                if norm < 1e-12:
                    d = target[k]-target[k-1]; norm = np.linalg.norm(d)
                    if norm < 1e-12: raise ValueError('degenerate target segment')
                p[k] = p[k-1] + d*(length/norm)
                vel[k] = (p[k]-old[k])/h
            vel[0] = 0
        out.append(p.copy())
    return np.asarray(out)


def shape_quaternion(q, amplitude, cap):
    """Quaternion is [w,x,y,z], cap in radians."""
    q = np.asarray(q,float)
    if q.shape != (4,) or not np.isfinite(q).all() or not np.isfinite([amplitude,cap]).all() or amplitude < 0 or cap < 0 or np.linalg.norm(q) < 1e-12: raise ValueError('invalid quaternion or shaping parameters')
    q = q/np.linalg.norm(q)
    if q[0] < 0: q = -q
    axis_length = np.linalg.norm(q[1:]); angle = 2*math.atan2(axis_length,q[0])
    shaped = cap*math.tanh(amplitude*angle/cap) if cap else 0
    if angle < 1e-6 or shaped < 1e-6: return np.array([1.,0.,0.,0.])
    return np.r_[math.cos(shaped/2), q[1:]/axis_length*math.sin(shaped/2)]


def assert_non_hair_channels_unchanged(before, after, hair_channels):
    """Compare all explicitly named non-hair channels including their existence."""
    if before is None or after is None or hair_channels is None: raise ValueError('channel evidence required')
    hair = set(hair_channels)
    a = {k:v for k,v in before.items() if k not in hair}
    b = {k:v for k,v in after.items() if k not in hair}
    if set(a) != set(b) or any(not np.array_equal(np.asarray(a[k]),np.asarray(b[k])) for k in a):
        raise ValueError('non-hair channels changed')
    return True
