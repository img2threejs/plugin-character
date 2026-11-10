#!/usr/bin/env python3
"""Measure authored skin/body structure without saving or modifying the input artifact.

Region vertex groups use ``region:<id>``. Mirror and repair inputs are explicit;
missing correspondence, unsupported image encodings and visual properties remain unmeasured.
"""
import argparse
import hashlib
import json
import math
import re
import statistics
from pathlib import Path

try:
    import bpy
except ImportError:
    bpy = None


def weight_stats(rows):
    """Measure normalization, four-influence and 1e-4 pruning rules; donor_hair_rig.py:132-183."""
    if not rows:
        raise ValueError('No vertices')
    weights = [list(row.values()) for row in rows]
    if any(not math.isfinite(w) or w < 0 for row in weights for w in row):
        raise ValueError('Invalid weight')
    return {'weight_sum_max_error': max(abs(sum(row) - 1) for row in weights),
            'weight_max_influences': max(sum(w > 0 for w in row) for row in weights),
            'weight_small_count': sum(0 < w < 1e-4 for row in weights for w in row)}


def mirror_difference(rows_a, rows_b, pairs, permutation):
    """Compare declared pairs through a bone mapping; case 681 foot pairs, limit 1e-4."""
    unmatched, differences, seen_a, seen_b = 0, [], set(), set()
    if not isinstance(permutation, dict) or len(set(permutation.values())) != len(permutation):
        raise ValueError('Bone permutation must be one-to-one')
    for pair in pairs:
        if not isinstance(pair, list) or len(pair) != 2 or any(not isinstance(i, int) or isinstance(i, bool) for i in pair):
            unmatched += 1
            continue
        a, b = pair
        if a < 0 or b < 0 or a >= len(rows_a) or b >= len(rows_b) or a in seen_a or b in seen_b:
            unmatched += 1
            continue
        seen_a.add(a); seen_b.add(b)
        left, right = rows_a[a], rows_b[b]
        if any(name not in permutation for name in left) or any(name not in permutation.values() for name in right):
            unmatched += 1
            continue
        differences.extend(abs(value - right.get(permutation[name], 0)) for name, value in left.items())
        differences.extend(abs(value - left.get(next(k for k, v in permutation.items() if v == name), 0)) for name, value in right.items())
    return {'mirror_max_difference': max(differences) if differences else None, 'mirror_unmatched_count': unmatched}


def group_bones(names, catalogue):
    """Count incomplete semantic groups; catalogue is the explicitly selected asset, not a universal rig."""
    if not catalogue.get('bone_groups'):
        raise ValueError('Selected asset has no semantic bone groups')
    present = set(names)
    return {g['id']: sorted(set(g['bones']) - present) for g in catalogue['bone_groups']}


def pixel_diff(a, b, mask=None):
    """Count unequal pixels and changes outside an explicit mask; nape case requires zero outside."""
    if len(a) != len(b) or not a or (mask is not None and len(mask) != len(a)):
        raise ValueError('Pixel or mask sizes differ or are empty')
    changed = [x != y for x, y in zip(a, b)]
    return {'changed_pixels': sum(changed), 'changed_outside_repair_mask': None if mask is None else sum(c and not m for c, m in zip(changed, mask))}


def load_mask(path, size):
    """Read a bottom-up mask with one boolean per pixel; empty selection is unusable."""
    data = json.loads(Path(path).read_text())
    pixels = data.get('pixels')
    if data.get('size') != size or not isinstance(pixels, list) or len(pixels) != size[0] * size[1] or any(type(v) is not bool for v in pixels):
        raise ValueError(f'{path}: expected matching size and one boolean per pixel')
    return pixels


def island_tone_deviation(pixels, island, reference):
    """Compare encoded-sRGB channel medians; case head-report.json:315-330, limit 0.08."""
    if len(pixels) != len(island) or len(pixels) != len(reference):
        raise ValueError('Mask and pixel sizes differ')
    channels = [[p[c] for p, selected in zip(pixels, mask) if selected]
                for mask in (island, reference) for c in range(3)]
    if any(not samples or any(not math.isfinite(x) or x < 0 or x > 1 for x in samples) for samples in channels):
        raise ValueError('Island and reference require nonempty finite encoded RGB samples in [0,1]')
    return max(abs(statistics.median(channels[c]) - statistics.median(channels[c + 3])) for c in range(3))


def source_hashes(specs):
    """Compare explicitly pinned source SHA-256 values; an altered source must fail S1."""
    result = {}
    for spec in specs:
        name, sep, rest = spec.partition('=')
        path, colon, expected = rest.rpartition(':')
        if not sep or not colon or not name.strip() or not path or not re.fullmatch(r'[0-9a-fA-F]{64}', expected) or name in result:
            raise ValueError('Each --source must be unique NAME=PATH:SHA256')
        digest = hashlib.sha256()
        with open(path, 'rb') as source:
            for block in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(block)
        actual = digest.hexdigest()
        result[name] = {'path': str(Path(path).resolve()), 'actual': actual, 'expected': expected.lower(), 'matches': actual == expected.lower()}
    return result


def select_asset(catalogue, ident):
    matches = [a for character in catalogue['characters'] for a in character['assets'] if a['id'] == ident]
    if len(matches) != 1:
        raise ValueError('Character must identify exactly one catalogue asset ID')
    return matches[0]


def snapshot(path, atlas):
    """Read an isolated file into memory; do not save it or execute embedded scripts."""
    if path.suffix.lower() == '.blend':
        bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=False, use_scripts=False)
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(path))
    bones = sorted({b.name for o in bpy.data.objects if o.type == 'ARMATURE' for b in o.data.bones})
    bone_parents = {b.name: b.parent.name if b.parent else None for o in bpy.data.objects if o.type == 'ARMATURE' for b in o.data.bones}
    meshes = {}
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        bone_set = set(bones)
        names = {g.index: g.name for g in obj.vertex_groups}
        weights, masks = [], []
        for vertex in obj.data.vertices:
            weights.append({names[g.group]: float(g.weight) for g in vertex.groups if names.get(g.group) in bone_set and g.weight > 0})
            masks.append({names[g.group][7:]: float(g.weight) for g in vertex.groups if names.get(g.group, '').startswith('region:')})
        uv = obj.data.uv_layers.active
        faces = [tuple(p.vertices) for p in obj.data.polygons]
        meshes[obj.name] = {'positions': [tuple(obj.matrix_world @ v.co) for v in obj.data.vertices], 'weights': weights, 'masks': masks,
                            'region_ids': [g.name[7:] for g in obj.vertex_groups if g.name.startswith('region:')],
                            'uv': [tuple(l.uv) for l in uv.data] if uv else None, 'faces': faces,
                            'edges': [tuple(e.vertices) for e in obj.data.edges],
                            'boundary': [v.index for v in obj.data.vertices if any(names.get(g.group) == 'join-boundary' and g.weight > 0 for g in v.groups)],
                            'face_reference': [v.index for v in obj.data.vertices if any(names.get(g.group) == 'face-reference' and g.weight > 0 for g in v.groups)]}
    image = bpy.data.images.get(atlas) if atlas else None
    img = None
    if image and image.size[0] and image.size[1]:
        raw = bytes(image.packed_file.data) if image.packed_file else (Path(bpy.path.abspath(image.filepath)).read_bytes() if image.filepath and Path(bpy.path.abspath(image.filepath)).is_file() else b'')
        depth = raw[24] if len(raw) > 24 and raw[:8] == b'\x89PNG\r\n\x1a\n' else None
        pixels = list(image.pixels[:])
        img = {'size': list(image.size), 'depth': depth, 'space': image.colorspace_settings.name,
               'pixels': [tuple(pixels[i:i+4]) for i in range(0, len(pixels), 4)]}
    materials = []
    for material in bpy.data.materials:
        if material.use_nodes:
            for node in material.node_tree.nodes:
                if node.type == 'BSDF_PRINCIPLED':
                    socket = node.inputs['Base Color']
                    links = list(socket.links)
                    source = links[0].from_node.image if len(links) == 1 and links[0].from_node.type == 'TEX_IMAGE' else None
                    materials.append((source.name if source else None, source.colorspace_settings.name if source else None,
                                      float(node.inputs['Roughness'].default_value), float(node.inputs['Metallic'].default_value)))
    return {'bones': bones, 'bone_parents': bone_parents, 'meshes': meshes, 'image': img, 'materials': materials}


def measure(args):
    """Produce only observations justified by this input; absent comparison inputs remain unmeasured."""
    if bpy is None:
        raise RuntimeError('bpy is required: run with the Blender Python interpreter')
    source = Path(args.blend or args.glb).resolve()
    catalogue = json.loads(Path(args.catalogue).read_text())
    asset = select_asset(catalogue, args.character)
    baseline_path = args.baseline_blend or args.baseline_glb
    baseline = snapshot(Path(baseline_path).resolve(), args.atlas) if baseline_path else None
    resolution_path = args.resolution_baseline_blend or args.resolution_baseline_glb
    resolution_baseline = snapshot(Path(resolution_path).resolve(), args.atlas) if resolution_path else None
    current = snapshot(source, args.atlas)
    evidence = {'schema': 'skin-body-evidence/1', 'subject': args.character, 'declared': {'hair_declared': False} if args.hair_absent else {}, 'measurements': {}}
    measurements = evidence['measurements']
    def emit(metric, value, unit, method):
        if value is not None:
            measurements[metric] = {'value': value, 'unit': unit, 'method': method, 'source': str(source)}
    if args.source:
        sources = source_hashes(args.source)
        emit('source_hash', sources, 'sha256', 'SHA-256 of each explicitly pinned source file')
        emit('original_changed_bytes', sum(not record['matches'] for record in sources.values()), 'sources', 'count of source files whose SHA-256 differs from pinned digest')
    if args.glb:
        emit('export_maps_and_sss', 'unmeasured-by-export', 'observation', 'Browser shading and map availability not established by Blender import')
    groups = group_bones(current['bones'], asset)
    emit('missing_bone_groups', sum(bool(missing) for missing in groups.values()), 'groups', 'catalogue bone group membership: ' + json.dumps(groups, sort_keys=True))
    emit('bone_count', len(current['bones']), 'bones', 'unique armature bone names')
    if args.hair_prefix:
        evidence['declared']['hair_declared'] = True
        emit('hair_chain_bones', sum(name.startswith(args.hair_prefix) for name in current['bones']), 'bones', 'bone name prefix ' + args.hair_prefix)
        parents = {name: parent for name, parent in current['bone_parents'].items() if name.startswith(args.hair_prefix)}
        children = {name: [] for name in parents}
        for name, parent in parents.items():
            if parent in children:
                children[parent].append(name)
        roots = [name for name, parent in parents.items() if parent not in parents]
        lengths = []
        for root in roots:
            node, count = root, 0
            while node is not None:
                count += 1
                if len(children[node]) > 1:
                    count = 0
                    break
                node = children[node][0] if children[node] else None
            lengths.append(count)
        if lengths:
            emit('hair_chain_lengths', sorted(lengths), 'bones-per-chain', 'parent links among prefix-selected hair bones')
    meshes = current['meshes']
    if meshes:
        rows = [row for mesh in meshes.values() for row in mesh['weights']]
        for metric, value in weight_stats(rows).items():
            emit(metric, value, {'weight_sum_max_error':'weight', 'weight_max_influences':'bones', 'weight_small_count':'weights'}[metric], 'vertex groups matching armature bone names')
        regions = [region for mesh in meshes.values() for region in mesh['region_ids']]
        mask_rows = [row for mesh in meshes.values() for row in mesh['masks']]
        if regions:
            values = [v for row in mask_rows for v in row.values()] or [0.0]
            emit('mask_region_ids', sorted(set(regions)), 'regions', 'region: prefixed vertex groups')
            emit('mask_min', min(values), 'weight', 'region group membership')
            emit('mask_max', max(values), 'weight', 'region group membership')
            emit('mask_max_sum', max(sum(row.values()) for row in mask_rows), 'weight', 'sum region groups per vertex')
        for mesh in meshes.values():
            boundary = set(mesh['boundary'])
            if not boundary:
                continue
            edges = [edge for edge in mesh['edges'] if set(edge) <= boundary]
            if not edges:
                continue
            incidence = [sum(set(edge) <= set(face) for face in mesh['faces']) for edge in edges]
            emit('join_edge_count', len(edges), 'edges', 'edges with both vertices in join-boundary')
            emit('join_open_edges', sum(n == 1 for n in incidence), 'edges', 'polygon incidence of join edges')
            emit('join_nonmanifold_edges', sum(n != 2 and n != 1 for n in incidence), 'edges', 'polygon incidence of join edges')
            emit('join_triangle_count', sum(max(0, len(face)-2) for face in mesh['faces'] if set(face) <= boundary), 'triangles', 'triangulated faces within join-boundary')
            break
    image = current['image']
    if image:
        width, height = image['size']
        emit('nonopaque_pixels', sum(p[3] < 1 for p in image['pixels']), 'pixels', 'Blender decoded RGBA alpha')
        emit('image_bit_depth', image['depth'], 'bits', 'PNG IHDR sample bit depth')
        emit('atlas_color_space', image['space'], 'color-space', 'image colour-space setting')
        if args.composite_atlas:
            emit('atlas_layout_error', abs(height * 8 - width * 9) / 8, 'pixels', 'absolute height difference from 9W/8; integral height implies width divisible by eight at zero')
        if args.island_mask and args.reference_mask and image['space'] == 'sRGB':
            island = load_mask(args.island_mask, image['size'])
            reference = load_mask(args.reference_mask, image['size'])
            emit('island_tone_deviation', island_tone_deviation(image['pixels'], island, reference), 'encoded-rgb', 'maximum channel median difference of selected encoded-sRGB pixels')
    # Hair, eyes and clothing bring their own materials: with an atlas named, the skin material is
    # the one whose base colour is that image.
    skin = [m for m in current['materials'] if m[0] == args.atlas] if args.atlas else current['materials']
    if len(skin) == 1:
        _, space, rough, metal = skin[0]
        emit('material_base_color_space', space, 'color-space', 'direct base colour image connection')
        emit('material_roughness', rough, 'scalar', 'Principled input default')
        emit('material_metallic', metal, 'scalar', 'Principled input default')
    if args.mirror_pairs:
        config = json.loads(Path(args.mirror_pairs).read_text())
        a, b = meshes[config['object_a']], meshes[config['object_b']]
        result = mirror_difference(a['weights'], b['weights'], config['pairs'], config['permutation'])
        emit('mirror_max_difference', result['mirror_max_difference'], 'weight', 'explicit vertex pairs and bone permutation')
        emit('mirror_unmatched_count', result['mirror_unmatched_count'], 'pairs', 'invalid, repeated, or unmapped pairs')
        emit('mirror_mapping', config, 'mapping', 'declared vertex pairs and bone permutation')
    if baseline:
        base_img = baseline['image']
        if image and base_img and image['size'] == base_img['size']:
            mask = None
            if args.repair_mask:
                mask = load_mask(args.repair_mask, image['size'])
            if args.protected_mask:
                protected = load_mask(args.protected_mask, image['size'])
                if not any(protected):
                    raise ValueError('Protected mask must select at least one pixel')
                changed = sum(a != b and selected for a, b, selected in zip(image['pixels'], base_img['pixels'], protected))
                emit('original_body_changed_pixels', changed, 'pixels', 'exact decoded RGBA comparison inside declared protected mask vs baseline')
            diff = pixel_diff(image['pixels'], base_img['pixels'], mask)
            emit('changed_outside_repair_mask', diff['changed_outside_repair_mask'], 'pixels', 'decoded RGBA vs baseline outside declared mask')
            if args.glb and args.baseline_blend or args.blend and args.baseline_glb:
                emit('export_changed_pixels', diff['changed_pixels'], 'pixels', 'decoded RGBA native versus GLB')
        if set(meshes) == set(baseline['meshes']) and meshes:
            uv_errors, position_errors, weight_errors, face_errors = [], [], [], []
            compatible = True
            for name, mesh in meshes.items():
                other = baseline['meshes'][name]
                if len(mesh['positions']) != len(other['positions']) or mesh['faces'] != other['faces'] or mesh['uv'] is None or other['uv'] is None or len(mesh['uv']) != len(other['uv']):
                    compatible = False
                    break
                uv_errors.extend(abs(x-y) for a, b in zip(mesh['uv'], other['uv']) for x, y in zip(a, b))
                position_errors.extend(math.dist(a, b) for a, b in zip(mesh['positions'], other['positions']))
                face_errors.extend(math.dist(mesh['positions'][i], other['positions'][i]) for i in mesh['face_reference'])
                for a, b in zip(mesh['weights'], other['weights']):
                    weight_errors.extend(abs(a.get(k, 0)-b.get(k, 0)) for k in set(a) | set(b))
            if compatible and uv_errors:
                emit('uv_max_error', max(uv_errors), 'uv', 'matching object, polygon and loop indices vs baseline')
                if image and base_img and image['size'] != base_img['size']:
                    emit('normalized_uv_max_error', max(uv_errors), 'uv', 'matching UV loops at distinct atlas dimensions')
                if face_errors:
                    emit('face_max_position_error', max(face_errors), 'm', 'world positions of face-reference vertices at matching indices')
                if args.glb and args.baseline_blend or args.blend and args.baseline_glb:
                    emit('export_uv_error', max(uv_errors), 'uv', 'matching object, polygon and loop indices vs native')
                    emit('export_position_error', max(position_errors), 'm', 'world positions at matching vertex indices')
                    if weight_errors:
                        emit('export_weight_error', max(weight_errors), 'weight', 'named bone weights at matching vertex indices')
    if resolution_baseline and image and resolution_baseline['image'] and image['size'] != resolution_baseline['image']['size']:
        comparison = resolution_baseline['meshes']
        if meshes and set(meshes) == set(comparison):
            errors = []
            for name, mesh in meshes.items():
                other = comparison[name]
                if mesh['faces'] != other['faces'] or mesh['uv'] is None or other['uv'] is None or len(mesh['uv']) != len(other['uv']):
                    errors = []
                    break
                errors.extend(abs(x - y) for a, b in zip(mesh['uv'], other['uv']) for x, y in zip(a, b))
            if errors:
                emit('normalized_uv_max_error', max(errors), 'uv', 'matching loops against distinct-resolution baseline ' + str(resolution_path))
    return evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--blend'); source.add_argument('--glb')
    baseline = parser.add_mutually_exclusive_group()
    baseline.add_argument('--baseline-blend'); baseline.add_argument('--baseline-glb')
    resolution = parser.add_mutually_exclusive_group()
    resolution.add_argument('--resolution-baseline-blend'); resolution.add_argument('--resolution-baseline-glb')
    parser.add_argument('--catalogue', default=str(Path(__file__).resolve().parent.parent / 'reference' / 'body-parts.json'))
    parser.add_argument('--character', required=True, help='catalogue asset ID')
    parser.add_argument('--atlas'); parser.add_argument('--mirror-pairs'); parser.add_argument('--repair-mask')
    parser.add_argument('--source', action='append', default=[], metavar='NAME=PATH:SHA256')
    parser.add_argument('--protected-mask'); parser.add_argument('--island-mask'); parser.add_argument('--reference-mask')
    parser.add_argument('--composite-atlas', action='store_true')
    hair = parser.add_mutually_exclusive_group()
    hair.add_argument('--hair-prefix'); hair.add_argument('--hair-absent', action='store_true')
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    try:
        Path(args.out).write_text(json.dumps(measure(args), indent=2, allow_nan=False) + '\n')
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        parser.exit(2, f'measurement error: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
