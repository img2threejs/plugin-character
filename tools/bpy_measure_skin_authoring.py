#!/usr/bin/env python3
"""Measure neutral painted atlas regions without modifying or saving the blend.

Reference targets are encoded-sRGB patch medians, not physical reflectance.
UV coordinates are rasterized at texel centres using skin_texture semantics.
"""
import argparse
import json
from pathlib import Path
import numpy as np
try:
    import bpy
except ImportError:
    bpy = None
try:
    from . import skin_authoring as sa, skin_texture
except ImportError:
    import skin_authoring as sa
    import skin_texture

# A neutral label is not proof that the selected triangles are neutral.
NEUTRAL = sa.NEUTRAL_REGIONS


def measure_arrays(rgb, masks, targets, *, uv_areas=None, world_areas=None, triangle_regions=None,
                   pairs=None, ownership=None, padding_radius=None, baseline=None, support=None):
    """Produce only independently measurable scalars; missing inputs stay absent.

    Deltas require all selected regions in the supplied reference, preventing a
    partial regional comparison from becoming a misleading global maximum.
    """
    a = sa._rgb(rgb); reports = sa.region_tone_report(a, masks)
    uniformity = sa.region_uniformity(a, masks)
    out = {'skin_region_uniformity_p99': max(r['rgb_distance'][-1] for r in uniformity.values())}
    if targets is not None and set(reports) <= set(targets):
        rgb_errors = []; l_errors = []
        for name, report in reports.items():
            target = targets[name]; ref = np.asarray(target['rgb'], float); lstar = float(target['lstar'])
            if ref.shape != (3,) or not np.isfinite(ref).all() or np.any((ref < 0) | (ref > 1)) or not np.isfinite(lstar) or not 0 <= lstar <= 100:
                raise ValueError('invalid reference target')
            rgb_errors.append(float(np.max(np.abs(np.asarray(report['rgb']) - ref))))
            l_errors.append(abs(report['lstar'] - lstar))
        out['skin_region_tone_max_delta_rgb'] = max(rgb_errors)
        out['skin_region_tone_max_delta_lstar'] = max(l_errors)
    if uv_areas is not None and world_areas is not None and triangle_regions is not None:
        ratio = sa.texel_density(uv_areas, world_areas, triangle_regions)['face_body_ratio']
        if ratio is not None: out['skin_face_body_density_ratio'] = ratio
    if pairs is not None:
        out['skin_mirror_tone_residual'] = sa.mirror_residual(a, pairs)
    if ownership is not None and padding_radius is not None:
        padding = sa.seam_padding_report(a, ownership, padding_radius)['min_px']
        if padding is not None: out['skin_seam_padding_min_px'] = padding
    if baseline is not None and support is not None:
        base = sa._rgb(baseline); mask = np.asarray(support, bool)
        if base.shape != a.shape or mask.shape != a.shape[:2]:
            raise ValueError('baseline or support shape mismatch')
        out['skin_changed_outside_support'] = int(np.count_nonzero(np.any(a != base, axis=2) & ~mask))
    return out, {'regions': reports, 'uniformity': uniformity}


def rasterized_masks(positions, triangles, uvs, shape, region_triangles):
    """Rasterize declared triangle indices; ambiguous shared UV texels are excluded."""
    t = np.asarray(triangles, int); uv = np.asarray(uvs, float)
    # Unique synthetic coordinates identify triangle membership without relying on
    # geometry centroids, which may coincide between disconnected objects.
    synthetic = np.repeat(np.arange(len(t), dtype=float), 3)
    points = np.column_stack((synthetic, np.zeros((len(synthetic), 2))))
    faces = np.arange(len(synthetic)).reshape(-1, 3)
    predicates = {name: (lambda p, indexes=set(indexes): int(p[0, 0]) in indexes) for name, indexes in region_triangles.items()}
    return skin_texture.rasterize_regions(points, faces, uv, shape, predicates, origin='bottom-up', overlap_policy='exclude')


def _image(image):
    if image is None or not image.size[0] or not image.size[1] or image.colorspace_settings.name != 'sRGB':
        raise ValueError('atlas must exist and be tagged sRGB')
    w, h = image.size; pixels = np.asarray(image.pixels[:], float).reshape(h, w, 4)[..., :3]
    # Blender image.pixels exposes the image buffer in its stored color space.
    return sa._rgb(pixels)


def samples_image(tree, image, seen=None):
    """True when a node tree, including nested groups, has an image-texture node on this image."""
    seen = set() if seen is None else seen
    if tree is None or tree.as_pointer() in seen: return False
    seen.add(tree.as_pointer())
    return any(node.type == 'TEX_IMAGE' and node.image == image or node.type == 'GROUP' and samples_image(node.node_tree, image, seen) for node in tree.nodes)


def snapshot(blend, atlas, mapping):
    """Load without scripts; classify explicit groups, slots or loop-triangle indices."""
    if bpy is None: raise RuntimeError('bpy interpreter required')
    bpy.ops.wm.open_mainfile(filepath=str(Path(blend).resolve()), load_ui=False, use_scripts=False)
    datablock = bpy.data.images.get(atlas)
    image = _image(datablock); positions = []; triangles = []; uvs = []; uv_areas = []; areas = []; region_triangles = {n: [] for n in mapping}
    if not mapping or set(mapping) - NEUTRAL: raise ValueError('only named neutral semantic regions are allowed')
    for obj in bpy.data.objects:
        if obj.type != 'MESH' or not obj.data.uv_layers.active: continue
        # Only a triangle whose material samples the atlas occupies its texels. Hair, eyes or
        # clothing with their own images cover the same UV square without sharing one texel.
        on_atlas = [bool(slot.material and samples_image(slot.material.node_tree, datablock)) for slot in obj.material_slots]
        if not any(on_atlas):
            if any(selector.get('object') == obj.name for selector in mapping.values()):
                raise ValueError(f'selected object {obj.name!r} has no material sampling the atlas')
            continue
        mesh = obj.data; mesh.calc_loop_triangles(); uv = mesh.uv_layers.active.data
        for tri in mesh.loop_triangles:
            if tri.material_index >= len(on_atlas) or not on_atlas[tri.material_index]: continue
            chosen = []
            for name, selector in mapping.items():
                if selector.get('object') != obj.name: continue
                keys = set(selector) - {'object'}
                if keys == {'vertex_group'}:
                    group = obj.vertex_groups.get(selector['vertex_group'])
                    if group is None: raise ValueError('unknown vertex group')
                    hit = all(any(g.group == group.index and g.weight > 0 for g in mesh.vertices[v].groups) for v in tri.vertices)
                elif keys == {'material_slot'}:
                    hit = tri.material_index == selector['material_slot']
                elif keys == {'uv_island_triangles'}:
                    hit = tri.index in selector['uv_island_triangles']
                else: raise ValueError('selector must specify exactly one supported selector')
                if hit: chosen.append(name)
            if len(chosen) > 1: raise ValueError('triangle has multiple semantic regions')
            # Unselected triangles on the atlas must also be rasterized to exclude overlap.
            index = len(triangles); coords = np.array([tuple(uv[l].uv) for l in tri.loops]); xyz = np.array([tuple(obj.matrix_world @ mesh.vertices[v].co) for v in tri.vertices])
            positions.extend(xyz.tolist()); triangles.append([index*3, index*3+1, index*3+2]); uvs.append(coords.tolist())
            uv_areas.append(float(abs(np.cross(coords[1]-coords[0], coords[2]-coords[0])) * .5 * image.shape[0] * image.shape[1]))
            areas.append(float(np.linalg.norm(np.cross(xyz[1]-xyz[0], xyz[2]-xyz[0])) * .5))
            if chosen: region_triangles[chosen[0]].append(index)
    if not triangles: raise ValueError('no UV triangle samples the atlas')
    masks, raster = rasterized_masks(positions, triangles, uvs, image.shape, region_triangles)
    if raster['empty']: raise ValueError('empty or ambiguous selected region: ' + ', '.join(raster['empty']))
    selected = [(i, 'face' if name == 'face' or name.startswith('cheek-') else 'body') for name, indices in region_triangles.items() for i in indices]
    density_args = {}
    if selected and all(areas[i] > 0 for i, _ in selected):
        density_args = {'uv_areas': [uv_areas[i] for i, _ in selected], 'world_areas': [areas[i] for i, _ in selected], 'triangle_regions': [name for _, name in selected]}
    return image, masks, density_args, {'raster': {k: v for k, v in raster.items() if k != 'shared_mask'}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blend', required=True); parser.add_argument('--atlas', required=True); parser.add_argument('--regions', required=True)
    parser.add_argument('--targets'); parser.add_argument('--options', help='JSON pairs, ownership, padding_radius, support and declared')
    parser.add_argument('--baseline-blend'); parser.add_argument('--subject', required=True); parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    try:
        mapping = json.loads(Path(args.regions).read_text()); opts = json.loads(Path(args.options).read_text()) if args.options else {}
        targets = json.loads(Path(args.targets).read_text()) if args.targets else None
        baseline = None
        if args.baseline_blend:
            baseline, _, _, _ = snapshot(args.baseline_blend, args.atlas, mapping)
        image, masks, density, details = snapshot(args.blend, args.atlas, mapping)
        values, info = measure_arrays(image, masks, targets, **density, pairs=opts.get('pairs'), ownership=opts.get('ownership'), padding_radius=opts.get('padding_radius'), baseline=baseline, support=opts.get('support'))
        units = {'skin_region_tone_max_delta_rgb':'encoded-rgb', 'skin_region_tone_max_delta_lstar':'L*', 'skin_region_uniformity_p99':'encoded-rgb', 'skin_face_body_density_ratio':'ratio', 'skin_mirror_tone_residual':'encoded-rgb', 'skin_seam_padding_min_px':'pixels', 'skin_changed_outside_support':'pixels'}
        evidence = {'schema':'skin-body-evidence/1', 'subject':args.subject, 'declared':opts.get('declared', {}), 'measurements':{k:{'value':v,'unit':units[k], 'method':'explicit neutral selection; see details', 'source':str(Path(args.blend).resolve())} for k,v in values.items()}, 'details':{**details, **info}}
        Path(args.out).write_text(json.dumps(evidence, indent=2, allow_nan=False) + '\n')
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        parser.exit(2, f'measurement error: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
