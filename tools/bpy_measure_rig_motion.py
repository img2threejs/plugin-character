#!/usr/bin/env python3
"""Non-destructive, explicitly scoped rig and hair measurements; see rig-motion-standards.md."""
import argparse
import json
import math
from pathlib import Path

import numpy as np
try:
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
except ImportError:
    bpy = None


def strain(rest, posed, triangles):
    """Fixed triangle tangent strain; spike 17.11824 -> 1.009584, no universal limit."""
    rest, posed = np.asarray(rest, float), np.asarray(posed, float)
    stretch, area = [], []
    excluded = 0
    for ids in triangles:
        r, p = rest[ids], posed[ids]
        a, b = r[1]-r[0], r[2]-r[0]
        length = np.linalg.norm(a)
        cross = np.linalg.norm(np.cross(a, b))
        if length <= 1e-12 or cross <= 1e-12:
            excluded += 1
            continue
        basis = np.array([[length, np.dot(a, b)/length], [0, cross/length]])
        gradient = np.column_stack((p[1]-p[0], p[2]-p[0])) @ np.linalg.inv(basis)
        singular = np.linalg.svd(gradient, compute_uv=False)
        stretch.append(float(singular[0])); area.append(float(np.prod(singular)))
    if not stretch:
        return None
    return {'p99': float(np.percentile(stretch, 99)), 'max': max(stretch),
            'p01_area_ratio': float(np.percentile(area, 1)),
            'severe_area_count': sum(x < .25 for x in area),
            'severe_stretch_count': sum(x > 2 for x in stretch), 'degenerate_rest_count': excluded}


def weight_profile(coordinates, influences, transitions=(), direction=1):
    """Count monotonic reversals outside declared intervals; no subject-independent gradient limit."""
    x, w = np.asarray(coordinates, float), np.asarray(influences, float)
    if len(x) < 2 or len(x) != len(w) or not np.isfinite(x).all() or not np.isfinite(w).all():
        raise ValueError('Invalid weight strip')
    order = np.argsort(x, kind='stable'); x, w = x[order], w[order]
    dx = np.diff(x)
    if np.any(dx <= 0) or np.any((w < 0) | (w > 1)) or direction not in (-1, 1):
        raise ValueError('Strip coordinates must be unique and weights normalised')
    slopes = np.diff(w) / dx
    outside = [not any(lo <= (x[i]+x[i+1])/2 <= hi for lo, hi in transitions) for i in range(len(dx))]
    return {'rig_weight_reversal_count': int(sum(direction * s < -1e-12 and ok for s, ok in zip(slopes, outside))),
            'rig_weight_max_gradient': float(max(abs(slopes)))}


def antipodal_pairs(quaternions):
    """Count negative adjacent quaternion dots; 92 -> 0 sign repair preserves rotations."""
    q = np.asarray(quaternions, dtype=float)
    if q.ndim != 2 or q.shape[1] != 4 or len(q) < 2 or not np.isfinite(q).all():
        raise ValueError('At least two finite quaternion keys required')
    norm = np.linalg.norm(q, axis=1)
    if np.any(norm <= 1e-12):
        raise ValueError('Zero quaternion')
    q = q / norm[:, None]
    return int(np.sum(np.sum(q[:-1] * q[1:], axis=1) < 0))


def quaternion_error(a, b):
    """Sign-invariant angular difference; rebase case 0.596454 vs 2.27e-7 rad."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    if not np.isfinite(a).all() or not np.isfinite(b).all() or np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
        raise ValueError('Invalid quaternion')
    dot = abs(np.dot(a / np.linalg.norm(a), b / np.linalg.norm(b)))
    return 2 * math.acos(min(1., float(dot)))


def mirror_error(pairs, normal, offset=0):
    """Maximum paired rest endpoint reflection error, divided by H by caller."""
    n = np.asarray(normal, float); n /= np.linalg.norm(n)
    return max(float(np.linalg.norm((np.asarray(a) - 2*(np.dot(a, n)-offset)*n) - b)) for a, b in pairs)


def section_center(vertices, triangles, point, axis):
    """Closed, unbranched triangle-plane contour only; ambiguous/open sections are unmeasured."""
    vertices = np.asarray(vertices, float); point = np.asarray(point, float); axis = np.asarray(axis, float)
    axis /= np.linalg.norm(axis)
    segments = []
    for ids in triangles:
        p = vertices[ids]; d = (p-point) @ axis
        if np.any(np.abs(d) < 1e-10):
            return None
        hits = []
        for i, j in ((0, 1), (1, 2), (2, 0)):
            if d[i]*d[j] < 0:
                hits.append(p[i] + (p[j]-p[i]) * d[i]/(d[i]-d[j]))
        if len(hits) == 2: segments.append(hits)
    if len(segments) < 3: return None
    nodes = {}; edges = []
    for a, b in segments:
        ka, kb = tuple(np.round(a, 8)), tuple(np.round(b, 8))
        nodes.setdefault(ka, []).append(kb); nodes.setdefault(kb, []).append(ka); edges.append((ka, kb))
    if any(len(v) != 2 for v in nodes.values()): return None
    seen = set(); stack = [next(iter(nodes))]
    while stack:
        node = stack.pop()
        if node not in seen:
            seen.add(node); stack.extend(nodes[node])
    if len(seen) != len(nodes): return None
    # Length-weighted contour centroid, not a guessed anatomical interior.
    lengths = [np.linalg.norm(a-b) for a, b in segments]
    return sum((a+b)*.5*l for (a,b), l in zip(segments, lengths)) / sum(lengths)


def hair_clearance(vertices, triangles, points):
    """Closed oriented manifold required for signed proximity; open mesh remains indeterminate."""
    if bpy is None: raise RuntimeError('bpy required')
    counts = {}
    for tri in triangles:
        for a, b in zip(tri, np.roll(tri, -1)):
            key = tuple(sorted((int(a), int(b))))
            counts.setdefault(key, []).append((int(a), int(b)))
    if not counts or any(len(v) != 2 or v[0] != v[1][::-1] for v in counts.values()): return None
    tree = BVHTree.FromPolygons([Vector(v) for v in vertices], [list(map(int, t)) for t in triangles], all_triangles=True)
    distances, signed_distances, inside = [], [], 0
    for point in points:
        p = Vector(point); nearest = tree.find_nearest(p)
        if nearest[0] is None: return None
        distances.append(nearest[3])
        votes = []
        for direction in ((1,.173,.071), (.091,1,.137), (.113,.071,1)):
            direction = Vector(direction).normalized(); origin = p.copy(); intersections = 0
            for _ in range(len(triangles)+1):
                hit, _, _, distance = tree.ray_cast(origin, direction)
                if hit is None: break
                intersections += 1; origin = hit + direction * 1e-7
            votes.append(intersections % 2)
        if len(set(votes)) != 1: return None
        inside += votes[0]
        signed_distances.append(-nearest[3] if votes[0] else nearest[3])
    if not distances: return None
    return {'hair_penetrating_vertices': inside, 'hair_min_clearance': min(signed_distances),
            'hair_under_1mm_count': sum(d < .001 for d in distances)}


def mesh_data(obj, depsgraph=None, polygons=False):
    """Return world coordinates and loop triangles without modifying the original mesh.

    Loop triangles are a geometry-dependent tessellation: Blender splits a quad along its other
    diagonal once a pose makes it concave. A pose comparison therefore keeps the rest triangles
    and asks for `polygons` (the polygon vertex lists, appended to the result) to prove that
    the posed mesh still has the rest topology.
    """
    evaluated = obj.evaluated_get(depsgraph) if depsgraph else obj
    mesh = evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        vertices = np.array([tuple(evaluated.matrix_world @ v.co) for v in mesh.vertices])
        triangles = np.array([tuple(t.vertices) for t in mesh.loop_triangles], dtype=int)
        if polygons:
            return vertices, triangles, [tuple(p.vertices) for p in mesh.polygons]
        return vertices, triangles
    finally:
        evaluated.to_mesh_clear()


def load(path):
    return json.loads(Path(path).read_text()) if path else {}

def measure(args):
    if bpy is None: raise RuntimeError('bpy required')
    bpy.ops.wm.open_mainfile(filepath=str(Path(args.blend).resolve()), load_ui=False, use_scripts=False)
    rig, body = bpy.data.objects[args.armature], bpy.data.objects[args.body]
    rig.data.pose_position = 'REST'; bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get(); rest, triangles, topology = mesh_data(body, deps, polygons=True)
    height = float(np.ptp(rest[:, 2]))
    if height <= 0: raise ValueError('Body height must be positive')
    result = {'schema':'skin-body-evidence/1', 'subject':body.name, 'stage_scope':['S10','S11'], 'declared':{}, 'measurements':{}, 'details':{}}
    def emit(key, value, unit, method):
        result['measurements'][key] = {'value':value, 'unit':unit, 'source':str(Path(args.blend).resolve()), 'method':method}
    chains = load(args.chains)
    if chains.get('mirror_pairs'):
        pairs = []
        for a,b in chains['mirror_pairs']:
            ba, bb = rig.data.bones[a], rig.data.bones[b]
            pairs.extend([(np.array(rig.matrix_world @ ba.head_local), np.array(rig.matrix_world @ bb.head_local)), (np.array(rig.matrix_world @ ba.tail_local), np.array(rig.matrix_world @ bb.tail_local))])
        plane = chains['mirror_plane']
        emit('rig_rest_mirror_error_over_h', mirror_error(pairs, plane['normal'], plane.get('offset',0))/height, 'H', 'Declared rest bone endpoint reflection')
    sections = load(args.joint_sections).get('sections', [])
    if sections:
        offsets = []
        for s in sections:
            bone = rig.data.bones[s['bone']]; head = np.array(rig.matrix_world @ bone.head_local)
            axis = np.asarray(s['axis'],float); axis /= np.linalg.norm(axis)
            lo, hi = s['interval']; position = float(np.dot(head, axis))
            if not lo <= position <= hi: offsets = []; break
            center = section_center(rest, triangles, axis * position, axis)
            if center is None: offsets = []; break
            offsets.append(float(np.linalg.norm(head-center)/height))
        if offsets: emit('rig_joint_section_offset_over_h', max(offsets), 'H', 'Closed contour section at declared bone head')
    strips = chains.get('strips', [])
    if strips:
        profiles = []
        for strip in strips:
            axis = np.asarray(strip['axis'],float); axis /= np.linalg.norm(axis)
            group = body.vertex_groups[strip['influence']]; groups = [body.vertex_groups[n].index for n in strip['chain']]
            coords, weights = [], []
            for i in strip['vertices']:
                row = {g.group:g.weight for g in body.data.vertices[i].groups}
                mass = sum(row.get(g,0) for g in groups)
                if mass <= 0: raise ValueError('Unweighted chain strip')
                coords.append(float(np.dot(rest[i],axis))); weights.append(row.get(group.index,0)/mass)
            profiles.append(weight_profile(coords,weights,strip.get('transitions',[]),strip.get('direction',1)))
        emit('rig_weight_reversal_count',sum(p['rig_weight_reversal_count'] for p in profiles),'reversals','Declared chain strips')
        emit('rig_weight_max_gradient',max(p['rig_weight_max_gradient'] for p in profiles),'1/m','Declared chain strips')
    pose_spec = load(args.poses); poses = pose_spec.get('poses', [])
    rig.data.pose_position = 'POSE'; bpy.context.view_layer.update()
    samples = []; region_specs = pose_spec.get('regions', {'all': list(range(len(triangles)))})
    face_group = body.vertex_groups.get(args.face_ids) if args.face_ids else None
    face_ids = [v.index for v in body.data.vertices if face_group and any(g.group == face_group.index and g.weight > 0 for g in v.groups)]
    root_ids = pose_spec.get('hair_roots', {}).get('vertices', [])
    head_name = pose_spec.get('head_bone')
    if (face_ids or root_ids) and not head_name: raise ValueError('head_bone required for face or hair roots')
    head_rest = (rig.matrix_world @ rig.data.bones[head_name].matrix_local).copy() if head_name else None
    rig.data.pose_position = 'REST'; bpy.context.view_layer.update()
    hair_rest = mesh_data(bpy.data.objects[args.hair], deps)[0] if root_ids else None
    rig.data.pose_position = 'POSE'; bpy.context.view_layer.update()
    face_errors, root_errors, hair_samples = [], [], []
    for pose in poses:
        for bone in rig.pose.bones:
            bone.rotation_mode = 'QUATERNION'; bone.rotation_quaternion = (1,0,0,0)
        if pose.get('action'):
            rig.animation_data_create(); rig.animation_data.action = bpy.data.actions[pose['action']]
            frames = pose.get('frames', [])
        else:
            if rig.animation_data: rig.animation_data.action = None
            frames = [None]
        for frame in frames:
            if frame is not None: bpy.context.scene.frame_set(int(frame), subframe=frame-int(frame))
            for name, q in pose.get('bones',{}).items(): rig.pose.bones[name].rotation_quaternion = q
            bpy.context.view_layer.update()
            coords, _, posed_topology = mesh_data(body, deps, polygons=True)
            if len(coords) != len(rest) or posed_topology != topology: raise ValueError('Evaluated topology changed')
            if args.hair:
                hp, _ = mesh_data(bpy.data.objects[args.hair], deps)
                hair_samples.append(hair_clearance(coords, triangles, hp))
            if head_name:
                delta = (rig.matrix_world @ rig.pose.bones[head_name].matrix) @ head_rest.inverted()
                face_errors.extend(float(np.linalg.norm(coords[i] - np.array(delta @ Vector(rest[i]))))/height for i in face_ids)
                if root_ids:
                    hp, _ = mesh_data(bpy.data.objects[args.hair], deps)
                    root_errors.extend(float(np.linalg.norm(hp[i] - np.array(delta @ Vector(hair_rest[i]))))/height for i in root_ids)
            for region, ids in region_specs.items():
                stats = strain(rest, coords, triangles[np.asarray(ids, dtype=int)])
                if stats: samples.append({'region':region, 'pose':pose['name'], 'frame':frame, **stats})
    if samples:
        result['details']['strain_samples'] = samples
        for sample in samples:
            suffix = sample['region'] + '__' + sample['pose'] + ('__' + str(sample['frame']) if sample['frame'] is not None else '')
            for key, field, unit in [('rig_strain_p99','p99','ratio'),('rig_strain_p01_area_ratio','p01_area_ratio','ratio'),('rig_strain_severe_area_count','severe_area_count','triangles'),('rig_strain_severe_stretch_count','severe_stretch_count','triangles')]:
                emit(key+'__'+suffix, sample[field], unit, 'Fixed rest triangles in declared region and pose')
    if face_errors: emit('rig_face_rigid_max_over_h',max(face_errors),'H','Declared face vertices against head rigid transform')
    if root_errors: emit('hair_root_pin_drift_over_h',max(root_errors),'H','Declared root vertices against head rigid transform')
    actions = {pose['action'] for pose in poses if pose.get('action')}
    pair_count = 0; tracks = 0; incomplete_tracks = False
    for action_name in actions:
        action = bpy.data.actions[action_name]
        groups = {}
        for curve in action.fcurves:
            if curve.data_path.endswith('.rotation_quaternion') and 0 <= curve.array_index < 4:
                groups.setdefault(curve.data_path, {})[curve.array_index] = curve
        for curves in groups.values():
            if len(curves) != 4:
                incomplete_tracks = True; continue
            times = [tuple(float(k.co.x) for k in curves[i].keyframe_points) for i in range(4)]
            if len(times[0]) < 2 or any(t != times[0] for t in times[1:]):
                incomplete_tracks = True; continue
            if any(k.interpolation != 'LINEAR' for curve in curves.values() for k in curve.keyframe_points):
                incomplete_tracks = True; continue
            quats = [[curves[i].keyframe_points[j].co.y for i in range(4)] for j in range(len(times[0]))]
            pair_count += antipodal_pairs(quats); tracks += 1
    if tracks and not incomplete_tracks: emit('rig_quat_antipodal_pairs',pair_count,'pairs','Aligned LINEAR quaternion fcurve keys')
    rest_reference = load(args.rest_reference)
    if rest_reference.get('samples'):
        differences = [quaternion_error(s['before_world_delta'], s['after_world_delta']) for s in rest_reference['samples']]
        emit('rig_rebase_world_delta_error_deg',math.degrees(max(differences)),'deg','Declared before/after world skinning delta quaternions')
    loops = pose_spec.get('loops', [])
    if loops:
        angle_errors, root_errors_loop = [], []
        for loop in loops:
            rig.animation_data_create(); rig.animation_data.action = bpy.data.actions[loop['action']]
            endpoints = []
            for frame in (loop['start'],loop['end']):
                bpy.context.scene.frame_set(int(frame), subframe=frame-int(frame)); bpy.context.view_layer.update()
                endpoints.append({name:(rig.matrix_world @ rig.pose.bones[name].matrix).copy() for name in loop['bones']})
            for name in loop['bones']:
                angle_errors.append(math.degrees(quaternion_error(endpoints[0][name].to_quaternion(), endpoints[1][name].to_quaternion())))
            root = loop['root']; displacement = Vector(loop.get('displacement', [0,0,0]))
            root_errors_loop.append((endpoints[1][root].translation - endpoints[0][root].translation - displacement).length / height)
        emit('rig_loop_pose_error_deg',max(angle_errors),'deg','Declared endpoint bone orientations')
        emit('rig_loop_root_error_over_h',max(root_errors_loop),'H','Declared endpoint root displacement removed')
    if args.hair:
        rig.data.pose_position = 'REST'; bpy.context.view_layer.update()
        hp, _ = mesh_data(bpy.data.objects[args.hair], deps)
        hair_samples.insert(0, hair_clearance(rest, triangles, hp))
        if hair_samples and all(sample is not None for sample in hair_samples):
            emit('hair_penetrating_vertices',max(sample['hair_penetrating_vertices'] for sample in hair_samples),'vertices','Watertight body three-ray parity over rest and pose sweep')
            emit('hair_min_clearance_over_h',min(sample['hair_min_clearance'] for sample in hair_samples)/height,'H','Nearest body surface over rest and poses')
            emit('hair_under_1mm_count',max(sample['hair_under_1mm_count'] for sample in hair_samples),'vertices','Nearest body surface over rest and poses; scene units assumed metres')
        mask = pose_spec.get('scalp_paint_mask')
        if mask:
            hv, ht = mesh_data(bpy.data.objects[args.hair], deps)
            tree = BVHTree.FromPolygons([Vector(v) for v in hv], [list(map(int, t)) for t in ht], all_triangles=True)
            exposed = 0
            for texel in mask['texels']:
                direction = Vector(texel['direction'])
                if direction.length == 0 or texel['max_distance'] <= 0: raise ValueError('Invalid scalp ray')
                hit = tree.ray_cast(Vector(texel['origin']), direction.normalized(), texel['max_distance'])
                exposed += hit[0] is None
            if mask['texels']:
                emit('hair_exposed_scalp_texels',exposed,'texels','Declared scalp mask texel rays against rest hair')
                result['declared']['scalp_mask_supplied'] = True
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('blend','armature','body','out'): parser.add_argument('--'+arg, required=True)
    for arg in ('joint-sections','poses','chains','face-ids','hair','rest-reference'): parser.add_argument('--'+arg)
    args = parser.parse_args(argv)
    try:
        result = measure(args)
        Path(args.out).write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    except (OSError, ValueError, KeyError, IndexError, TypeError, RuntimeError) as exc:
        parser.exit(2, f'measurement error: {exc}\n')
    return 0


if __name__ == '__main__': raise SystemExit(main())
