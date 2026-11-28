#!/usr/bin/env python3
"""Measure declared rest geometry without saving the blend. See body-geometry-standards.md."""
import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

try:
    import bpy
except ImportError:
    bpy = None


def mirror_match(points, plane, tol, exclude=()):
    """Reflect about declared plane; report all eligible points, not only matches (R:13072-13081)."""
    p = np.asarray(points, dtype=float).reshape(-1, 3)
    normal = np.asarray(plane['normal'], dtype=float)
    length = np.linalg.norm(normal)
    if not length or tol <= 0 or not np.isfinite(p).all():
        raise ValueError('Invalid plane, tolerance or points')
    normal /= length
    origin = np.asarray(plane['point'], dtype=float)
    side = (p - origin) @ normal
    keep = np.ones(len(p), dtype=bool)
    keep[list(exclude)] = False
    indices = np.flatnonzero(keep & (np.abs(side) > 1e-12))
    if not len(indices):
        return None
    reflected = p[indices] - 2 * side[indices, None] * normal
    distances = np.full(len(indices), np.inf)
    # Bounded batches avoid a quadratic-size temporary for character meshes.
    for sign in (-1, 1):
        source = np.flatnonzero(side[indices] * sign > 0)
        target = p[keep & (side * sign < 0)]
        if not len(target):
            continue
        if bpy is not None:
            from mathutils.kdtree import KDTree
            tree = KDTree(len(target))
            for j, point in enumerate(target): tree.insert(point, j)
            tree.balance()
            for j in source: distances[j] = tree.find(reflected[j])[2]
        else:
            for j in source:
                distances[j] = np.sqrt(np.min(np.sum((target - reflected[j]) ** 2, axis=1)))
    matched = distances <= tol
    result = {'coverage': float(np.mean(matched))}
    if matched.any():
        result.update(p95=float(np.percentile(distances[matched], 95)), max=float(np.max(distances[matched])))
    return result


def edge_incidence(faces):
    """Count incident face occurrences per undirected edge; welded topology is caller supplied."""
    edges = defaultdict(int)
    for face in faces:
        for a, b in zip(face, face[1:] + face[:1]):
            if a != b: edges[tuple(sorted((int(a), int(b))))] += 1
    return dict(edges)


def _raster(triangles, size):
    """Pixel-centre triangle sampling, without wrapping; boundary-only contact is not overlap."""
    width, height = size
    if width <= 0 or height <= 0: raise ValueError('Invalid atlas size')
    masks = []
    for triangle in triangles:
        t = np.asarray(triangle, dtype=float) * [width, height]
        if not np.isfinite(t).all() or np.any(t < 0) or np.any(t > [width, height]):
            raise ValueError('UV outside declared atlas')
        x0, y0 = np.maximum(np.floor(t.min(axis=0)).astype(int), 0)
        x1, y1 = np.minimum(np.ceil(t.max(axis=0)).astype(int), [width, height])
        yy, xx = np.mgrid[y0:y1, x0:x1]
        points = np.stack((xx + .5, yy + .5), axis=-1)
        cross = lambda a, b: a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]
        e = [cross(t[(i+1)%3]-t[i], points-t[i]) for i in range(3)]
        inside = ((e[0] > 1e-9) & (e[1] > 1e-9) & (e[2] > 1e-9)) | ((e[0] < -1e-9) & (e[1] < -1e-9) & (e[2] < -1e-9))
        masks.append(set(zip(xx[inside].tolist(), yy[inside].tolist())))
    return masks


def uv_overlap_texels(triangles, islands, size, approved=()):
    """Count texels with unapproved triangle overlap; approval is an explicit island pair."""
    if len(triangles) != len(islands): raise ValueError('Triangle/island mismatch')
    allowed = {frozenset(pair) for pair in approved}
    owners, bad = defaultdict(list), set()
    for mask, island in zip(_raster(triangles, size), islands):
        for pixel in mask:
            if any(frozenset((other, island)) not in allowed for other in owners[pixel]): bad.add(pixel)
            owners[pixel].append(island)
    return len(bad)


def island_gutter(triangles, islands, size, approved=()):
    """Minimum Euclidean empty-texel gap between non-approved islands; absent pair is unmeasured."""
    allowed = {frozenset(pair) for pair in approved}
    groups = defaultdict(set)
    for mask, island in zip(_raster(triangles, size), islands): groups[island].update(mask)
    best = None
    names = list(groups)
    for i, a in enumerate(names):
        for b in names[i+1:]:
            if frozenset((a, b)) in allowed or not groups[a] or not groups[b]: continue
            if groups[a] & groups[b]: return 0.0
            aa, bb = np.asarray(list(groups[a])), np.asarray(list(groups[b]))
            if bpy is not None:
                from mathutils.kdtree import KDTree
                tree = KDTree(len(bb))
                for j, point in enumerate(bb): tree.insert((float(point[0]), float(point[1]), 0), j)
                tree.balance()
                for point in aa:
                    d = tree.find((float(point[0]), float(point[1]), 0))[2]
                    best = d if best is None else min(best, d)
            else:
                for point in aa:
                    d = float(np.sqrt(np.min(np.sum((bb-point)**2, axis=1))))
                    best = d if best is None else min(best, d)
    return None if best is None else max(0.0, best - 1.0)


def density(world_triangles, uv_triangles, size):
    """sqrt(total UV pixel area / world area), not a median (anatomy.py:1037-1068)."""
    w, u = np.asarray(world_triangles, dtype=float), np.asarray(uv_triangles, dtype=float)
    if not len(w) or w.shape != (len(u), 3, 3) or u.shape != (len(w), 3, 2): return None
    area = np.linalg.norm(np.cross(w[:, 1]-w[:, 0], w[:, 2]-w[:, 0]), axis=1).sum() / 2
    d = u[:, 1]-u[:, 0]; e = u[:, 2]-u[:, 0]
    uv = np.abs(d[:, 0]*e[:, 1]-d[:, 1]*e[:, 0]).sum() / 2
    if area <= 0 or not np.isfinite(area + uv): return None
    return float(math.sqrt(uv * size[0] * size[1] / area))


def landmark_ratios(points, reference, height, reference_height, pairs):
    """Maximum difference of explicitly named length/H ratios; any missing point is unmeasured."""
    if not pairs or height <= 0 or reference_height <= 0: return None
    values = []
    for a, b in pairs:
        if a not in points or b not in points or a not in reference or b not in reference: return None
        values.append(abs(np.linalg.norm(np.asarray(points[a])-points[b])/height - np.linalg.norm(np.asarray(reference[a])-reference[b])/reference_height))
    return float(max(values))


def _load(path):
    return json.loads(Path(path).read_text()) if path else {}


def _weld(points, faces, tolerance=1e-6):
    # Spatial hashing searches adjacent cells, so near-boundary coordinates weld correctly.
    buckets, mapping, unique = defaultdict(list), [], []
    for point in points:
        cell = tuple(np.floor(np.asarray(point) / tolerance).astype(int))
        found = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for idx in buckets.get((cell[0]+dx, cell[1]+dy, cell[2]+dz), ()):
                        if np.linalg.norm(unique[idx] - point) <= tolerance:
                            found = idx; break
                    if found is not None: break
                if found is not None: break
            if found is not None: break
        if found is None:
            found = len(unique); unique.append(np.asarray(point)); buckets[cell].append(found)
        mapping.append(found)
    return unique, [[mapping[i] for i in face] for face in faces], mapping


def _points(objects, declarations):
    result = {}
    for name, spec in declarations.items():
        obj = objects.get(spec.get('object', ''))
        if obj is None: continue
        if obj.type == 'MESH' and spec.get('group') in obj.vertex_groups:
            group = obj.vertex_groups[spec['group']]
            vertices = [obj.matrix_world @ v.co for v in obj.data.vertices if any(g.group == group.index and g.weight > 0 for g in v.groups)]
            if vertices: result[name] = np.mean(np.asarray(vertices), axis=0)
        elif obj.type == 'ARMATURE' and spec.get('bone') in obj.data.bones:
            result[name] = np.asarray(obj.matrix_world @ obj.data.bones[spec['bone']].head_local)
    return result


def measure(blend, reference=None, landmarks=None, regions=None, mirror=None, join_boundary=(), atlas_size=None, budget=None):
    """Read rest meshes in world coordinates; explicit declarations bound each measurement."""
    if bpy is None: raise RuntimeError('Requires bpy')
    bpy.ops.wm.open_mainfile(filepath=str(Path(blend).resolve()), load_ui=False, use_scripts=False)
    objects = bpy.data.objects
    cfg, reg, mir, budgets = _load(landmarks), _load(regions), _load(mirror), _load(budget)
    names = reg.get('objects', [o.name for o in objects if o.type == 'MESH'])
    meshes = [objects[n] for n in names if n in objects and objects[n].type == 'MESH']
    if len(meshes) != len(names):
        raise ValueError('A declared mesh is missing')
    measurements = {}
    source = str(Path(blend).resolve())
    def put(name, value, unit, method):
        if value is not None and np.isfinite(value): measurements[name] = {'value': float(value) if isinstance(value, (float, np.floating)) else int(value), 'unit': unit, 'method': method, 'source': source}
    pts, faces, join_vertices, tri_world, tri_uv, island_ids, triangle_regions = [], [], set(), [], [], [], []
    uv_by_vertex, found_joins = [], set()
    all_uv = True
    mesh_edges, part_counts = [], defaultdict(lambda: [0, 0])
    # Islands are connected through shared mesh edges with matching loop UVs.
    for obj in meshes:
        mesh = obj.data; mesh.calc_loop_triangles()
        offset = len(pts); coords = [np.asarray(obj.matrix_world @ v.co) for v in mesh.vertices]; pts.extend(coords)
        faces.extend([[offset+i for i in poly.vertices] for poly in mesh.polygons])
        mesh_edges.extend((offset+e.vertices[0], offset+e.vertices[1]) for e in mesh.edges)
        for group_name in join_boundary:
            group = obj.vertex_groups.get(group_name)
            if group:
                found_joins.add(group_name)
                join_vertices.update(offset+v.index for v in mesh.vertices if any(g.group == group.index and g.weight > 0 for g in v.groups))
        uv = mesh.uv_layers.active
        if not uv: all_uv = False
        vertex_uv = [set() for _ in mesh.vertices]
        if uv:
            for loop in mesh.loops: vertex_uv[loop.vertex_index].add(tuple(uv.data[loop.index].uv))
        uv_by_vertex.extend(vertex_uv)
        if uv and atlas_size:
            parent = list(range(len(mesh.polygons))); edge_owner = {}
            def root(n):
                while parent[n] != n: n = parent[n]
                return n
            for poly in mesh.polygons:
                loops = list(poly.loop_indices)
                for l, nxt in zip(loops, loops[1:]+loops[:1]):
                    va, vb = mesh.loops[l].vertex_index, mesh.loops[nxt].vertex_index
                    key = tuple(sorted((va, vb)))
                    uva, uvb = tuple(uv.data[l].uv), tuple(uv.data[nxt].uv)
                    signature = (uva, uvb) if va < vb else (uvb, uva)
                    if key in edge_owner and edge_owner[key][1] == signature:
                        parent[root(poly.index)] = root(edge_owner[key][0])
                    else: edge_owner[key] = (poly.index, signature)
            for tri in mesh.loop_triangles:
                tri_world.append([coords[i] for i in tri.vertices]); tri_uv.append([tuple(uv.data[i].uv) for i in tri.loops]); island_ids.append(f'{obj.name}:{root(tri.polygon_index)}')
                triangle_regions.append((obj.name, tri.polygon_index))
        if obj.name in budgets.get('parts', {}):
            part = budgets['parts'][obj.name]
            part_counts[part][0] += len(mesh.vertices)
            part_counts[part][1] += len(mesh.loop_triangles)
    for part, (vertices, triangles) in part_counts.items():
        put('geo_vertices_'+part, vertices, 'vertices', 'native mesh vertex count')
        put('geo_triangles_'+part, triangles, 'triangles', 'rest mesh loop triangles')
    if pts:
        points = np.asarray(pts); height = float(np.ptp(points[:, 2])); put('geo_height_m', height, 'm', 'world Z bounds of declared objects')
        unique, welded, mapping = _weld(points, faces)
        edges = edge_incidence(welded)
        for a, b in mesh_edges:
            a, b = mapping[a], mapping[b]
            if a != b: edges.setdefault(tuple(sorted((a, b))), 0)
        if faces:
            put('geo_boundary_edges_global', sum(v == 1 for v in edges.values()), 'edges', 'world-position weld 1e-6 m, face incidence')
            put('geo_nonmanifold_edges_global', sum(v == 0 or v > 2 for v in edges.values()), 'edges', 'world-position weld 1e-6 m, face incidence')
        if join_boundary and join_vertices and found_joins == set(join_boundary):
            selected = {mapping[i] for i in join_vertices}
            join_edges = [v for (a,b), v in edges.items() if a in selected and b in selected]
            if join_edges:
                put('geo_boundary_edges_at_join', sum(v == 1 for v in join_edges), 'edges', 'declared group endpoints after weld')
                put('geo_nonmanifold_edges_at_join', sum(v == 0 or v > 2 for v in join_edges), 'edges', 'declared group endpoints after weld')
        zero = 0
        for obj in meshes:
            obj.data.calc_loop_triangles()
            for tri in obj.data.loop_triangles:
                base = sum(len(o.data.vertices) for o in meshes[:meshes.index(obj)])
                p = [unique[mapping[base+i]] for i in tri.vertices]
                zero += np.linalg.norm(np.cross(p[1]-p[0], p[2]-p[0])) <= 1e-15
        if faces: put('geo_zero_area_triangles', zero, 'triangles', 'world triangle cross product after weld')
        if mir and height > 0 and (not mir.get('exclude_group') or any(o.vertex_groups.get(mir['exclude_group']) for o in meshes)):
            excluded = set()
            start = 0
            for obj in meshes:
                group = obj.vertex_groups.get(mir.get('exclude_group', ''))
                if group: excluded.update(start+v.index for v in obj.data.vertices if any(g.group == group.index and g.weight > 0 for g in v.groups))
                start += len(obj.data.vertices)
            match = mirror_match(points, mir['plane'], mir['tolerance_m'], excluded)
            if match:
                put('geo_mirror_coverage', match['coverage'], 'ratio', 'opposite-side nearest reflected vertex, declared exclusion and tolerance')
                for key in ('p95','max'):
                    if key in match: put('geo_mirror_'+key+'_over_h', match[key]/height, 'ratio', 'matched reflected distance / height; coverage reported separately')
                if all_uv:
                    normal = np.asarray(mir['plane']['normal'], dtype=float)
                    normal /= np.linalg.norm(normal)
                    side = (points - np.asarray(mir['plane']['point'])) @ normal
                    positive = [i for i in range(len(points)) if side[i] > 1e-12 and i not in excluded]
                    negative = [i for i in range(len(points)) if side[i] < -1e-12 and i not in excluded]
                    if positive and negative:
                        from mathutils.kdtree import KDTree
                        tree = KDTree(len(negative))
                        for i in negative: tree.insert(points[i], i)
                        tree.balance()
                        shared, count = 0, 0
                        for i in positive:
                            _, j, distance = tree.find(points[i]-2*side[i]*normal)
                            if distance <= mir['tolerance_m'] and uv_by_vertex[i] and uv_by_vertex[j]:
                                count += 1
                                shared += bool(uv_by_vertex[i] & uv_by_vertex[j])
                        if count: put('geo_uv_shared_mirror_pair_ratio', shared/count, 'ratio', 'nearest matched positive-side vertex with any identical UV loop')
        landmarks_current = _points(objects, cfg.get('points', {}))
        if height > 0:
            for metric, pair, inverse in (('geo_heads_tall', cfg.get('head_pair'), True), ('geo_shoulder_over_h', cfg.get('shoulder_pair'), False)):
                if pair and len(pair) == 2 and all(name in landmarks_current for name in pair):
                    length = np.linalg.norm(landmarks_current[pair[0]] - landmarks_current[pair[1]])
                    if length > 0: put(metric, height/length if inverse else length/height, 'ratio', 'declared landmark distance and world Z height')
        pose = cfg.get('pose')
        if pose and pose.get('shoulder') in landmarks_current and pose.get('wrist') in landmarks_current:
            v = landmarks_current[pose['wrist']] - landmarks_current[pose['shoulder']]
            if np.linalg.norm(v): put('geo_pose_arm_angle_deg', math.degrees(math.acos(np.clip(abs(v[2])/np.linalg.norm(v), 0, 1))), 'degrees', 'shoulder to wrist versus vertical')
        if reference and cfg and height > 0:
            bpy.ops.wm.open_mainfile(filepath=str(Path(reference).resolve()), load_ui=False, use_scripts=False)
            ref_objects = bpy.data.objects
            ref_meshes = [ref_objects[n] for n in names if n in ref_objects and ref_objects[n].type == 'MESH']
            ref_pts = [np.asarray(o.matrix_world @ v.co) for o in ref_meshes for v in o.data.vertices]
            if ref_pts and len(ref_meshes) == len(names):
                ref_height = float(np.ptp(np.asarray(ref_pts)[:, 2]))
                put('geo_landmark_ratio_max_delta', landmark_ratios(landmarks_current, _points(ref_objects, cfg.get('points', {})), height, ref_height, cfg.get('pairs', [])), 'ratio', 'max absolute declared landmark length/H difference against '+str(Path(reference).resolve()))
    if tri_uv and atlas_size and all_uv:
        approved = reg.get('approved_island_pairs', [])
        # A triangle with no sample makes overlap/gutter coverage incomplete.
        if all(_raster(tri_uv, atlas_size)):
            put('geo_uv_unapproved_overlap_texels', uv_overlap_texels(tri_uv, island_ids, atlas_size, approved), 'texels', 'pixel-centre triangle raster; approved island pairs excluded')
            put('geo_uv_min_gutter_px', island_gutter(tri_uv, island_ids, atlas_size, approved), 'pixels', 'minimum pixel-centre inter-island distance minus one')
        values = {}
        for name, selection in reg.get('regions', {}).items():
            requested = {(obj, polygon) for obj, polygons in selection.items() for polygon in polygons}
            available = set(triangle_regions)
            indexes = [i for i, identity in enumerate(triangle_regions) if identity in requested]
            if requested and requested <= available and indexes:
                values[name] = density([tri_world[i] for i in indexes], [tri_uv[i] for i in indexes], atlas_size)
                put('geo_uv_density_'+name+'_px_per_m', values[name], 'px/m', 'sqrt(sum UV pixel area / sum world area)')
        if values.get('face') is not None and values.get('body'):
            put('geo_face_body_density_ratio', values['face']/values['body'], 'ratio', 'area-weighted face density / body density')
    declared = {}
    for data in (cfg, reg, mir, budgets):
        for key in ('references', 'baselines', 'limits'):
            declared.setdefault(key, {}).update(data.get(key, {}))
    return {'schema':'skin-body-evidence/1', 'declared':declared, 'measurements':measurements}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('blend', 'reference', 'landmarks', 'regions', 'mirror', 'budget', 'atlas-size', 'out'): parser.add_argument('--'+name, required=name in ('blend','out'))
    parser.add_argument('--join-boundary', action='append', default=[])
    args = parser.parse_args(argv)
    size = tuple(map(int, args.atlas_size.lower().split('x'))) if args.atlas_size else None
    if size and (len(size) != 2 or min(size) <= 0): parser.error('atlas size must be WxH with positive dimensions')
    try:
        result = measure(args.blend, args.reference, args.landmarks, args.regions, args.mirror, args.join_boundary, size, args.budget)
        Path(args.out).write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    except (OSError, ValueError, KeyError, IndexError, TypeError, RuntimeError) as exc:
        parser.exit(2, f'measurement error: {exc}\n')
    return 0


if __name__ == '__main__': raise SystemExit(main())
