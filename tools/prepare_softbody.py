#!/usr/bin/env python3
"""Prepare an authored Blender character for the softbody-character route.

Run with a Python containing bpy, or `blender -b --factory-startup
--disable-autoexec --python-exit-code 2 --python tools/prepare_softbody.py -- ...`:

    prepare_softbody.py --source original.blend --config regions.json --out NEW_DIR

The config is the softbody sidecar v1 `meshes` array where every region names an
already-authored Blender vertex group (`vertexGroup`) instead of a glTF attribute,
and a mesh may name its hair mask group with `hairGroup`:

    {"version": 1, "meshes": [{"name": "Body", "hairGroup": "mask_hair",
      "regions": [{"id": "chest-left", "group": "chest",
                   "vertexGroup": "mask_chest_left", "bone": "Spine2"}]}]}

Nothing is guessed: regions, masks and bones come from the author. Masks are copied
to scalar POINT float attributes `_SOFT_<ID>` / `_HAIR`, the project is saved as a copy
into the new directory, exported with the stock Blender glTF exporter, and the *exported
file* is read back and checked before `softbody.json` and `preparation.json` are written:
per mask the accessor must be FLOAT SCALAR with one value per POSITION vertex, inside
[0, 1], not all zero, and made only of values present in the authored mask. That proves
count, range and value set, not per-vertex topology correspondence (the exporter splits and
reorders vertices). Skin presence/joints and shape-key count are checked the same way.
The source .blend is never modified.

This tool does not install software, does not touch Character Creator, and does not
generate a character; it only prepares one that already exists.
"""
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import struct
import sys
from array import array
from pathlib import Path

ROUTE = 'softbody-character'
SOFT_PREFIX = '_SOFT_'
HAIR_ATTRIBUTE = '_HAIR'
MAX_ATTRIBUTE_BYTES = 63  # Blender's name limit (MAX_NAME 64 including terminator)
SUPPORT_EPSILON = 1e-9
FLOAT_COMPONENT = 5126

CONFIG_KEYS = {'version', 'meshes'}
MESH_KEYS = {'name', 'hairGroup', 'hairAttribute', 'regions'}
REGION_KEYS = {'id', 'group', 'vertexGroup', 'bone', 'center', 'radius'}
HAIR_ATTRIBUTE_RE = re.compile(r'^_[A-Z][A-Z0-9_]*$')

UNVERIFIED = [
    'region placement and anatomy review (masks are the author\'s, never inferred)',
    'Three.js runtime behavior of the prepared asset',
    'rights and provenance of the source character',
    'likeness, material fidelity and clip preservation under pose stress',
]


# --------------------------------------------------------------------------- config

def _reject_constant(token):
    raise ValueError(f'Config contains the non-finite JSON constant {token}')


def parse_config(text):
    """json.loads that refuses NaN/Infinity literals."""
    return json.loads(text, parse_constant=_reject_constant)


def _finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be a non-empty string')
    return value


def _no_extra(obj, allowed, label):
    if not isinstance(obj, dict):
        raise ValueError(f'{label} must be a JSON object')
    extra = sorted(set(obj) - allowed)
    if extra:
        raise ValueError(f'{label} has unsupported keys: {", ".join(extra)}')


def sanitize_region_id(region_id):
    """Deterministic uppercase ASCII token used inside the derived attribute name."""
    token = re.sub(r'[^A-Za-z0-9]+', '_', _text(region_id, 'Region id')).strip('_').upper()
    if not token:
        raise ValueError(f'Region id {region_id!r} has no ASCII letters or digits to derive an attribute from')
    return token


def attribute_name(region_id):
    name = SOFT_PREFIX + sanitize_region_id(region_id)
    if len(name.encode('utf-8')) > MAX_ATTRIBUTE_BYTES:
        raise ValueError(f'Region id {region_id!r} derives attribute {name!r} longer than {MAX_ATTRIBUTE_BYTES} bytes')
    return name


def _validate_region(region, mesh_name, index):
    label = f'Mesh {mesh_name!r} region #{index}'
    if isinstance(region, dict) and 'attribute' in region:
        raise ValueError(f'{label} uses attribute; preparation configs use vertexGroup')
    _no_extra(region, REGION_KEYS, label)
    region_id = _text(region.get('id'), f'{label} id')
    label = f'Mesh {mesh_name!r} region {region_id!r}'
    normalized = {
        'id': region_id,
        'vertexGroup': _text(region.get('vertexGroup'), f'{label} vertexGroup'),
        'attribute': attribute_name(region_id),
        'group': None,
        'bone': None,
        'center': None,
        'radius': None,
    }
    for key in ('group', 'bone'):
        if key in region:
            normalized[key] = _text(region[key], f'{label} {key}')
    has_center, has_radius = 'center' in region, 'radius' in region
    if has_center != has_radius:
        raise ValueError(f'{label} must supply center and radius together or neither')
    if has_center:
        center = region['center']
        if not isinstance(center, list) or len(center) != 3 or not all(_finite_number(c) for c in center):
            raise ValueError(f'{label} center must be three finite numbers')
        radius = region['radius']
        if not _finite_number(radius) or radius <= 0:
            raise ValueError(f'{label} radius must be a finite number above zero')
        normalized['center'] = [float(c) for c in center]
        normalized['radius'] = float(radius)
    return normalized


def validate_config(config):
    """Return the normalized plan or raise ValueError; pure, needs no bpy."""
    _no_extra(config, CONFIG_KEYS, 'Config')
    version = config.get('version')
    if type(version) is not int or version != 1:
        raise ValueError('Config version must be 1')
    meshes = config.get('meshes')
    if not isinstance(meshes, list) or not meshes:
        raise ValueError('Config meshes must be a non-empty array')
    plan, seen_meshes = [], set()
    for mesh_index, mesh in enumerate(meshes):
        _no_extra(mesh, MESH_KEYS, f'Mesh #{mesh_index}')
        name = _text(mesh.get('name'), f'Mesh #{mesh_index} name')
        if name in seen_meshes:
            raise ValueError(f'Mesh name {name!r} is used twice; mesh names must be unique')
        seen_meshes.add(name)
        hair_group = _text(mesh['hairGroup'], f'Mesh {name!r} hairGroup') if 'hairGroup' in mesh else None
        hair_attribute = None
        if 'hairAttribute' in mesh:
            hair_attribute = _text(mesh['hairAttribute'], f'Mesh {name!r} hairAttribute')
            if not HAIR_ATTRIBUTE_RE.match(hair_attribute) or len(hair_attribute.encode()) > MAX_ATTRIBUTE_BYTES:
                raise ValueError(f'Mesh {name!r} hairAttribute must look like _HAIR (underscore + uppercase glTF name)')
        if hair_group is not None and hair_attribute is not None:
            raise ValueError(f'Mesh {name!r} sets both hairGroup and hairAttribute; choose one')
        regions = mesh.get('regions')
        if not isinstance(regions, list) or not regions:
            raise ValueError(f'Mesh {name!r} regions must be a non-empty array')
        normalized, ids, attributes, groups = [], {}, {}, {}
        for region_index, region in enumerate(regions):
            item = _validate_region(region, name, region_index)
            if item['id'] in ids:
                raise ValueError(f'Mesh {name!r} repeats region id {item["id"]!r}')
            if item['attribute'] in attributes:
                raise ValueError(
                    f'Mesh {name!r} regions {attributes[item["attribute"]]!r} and {item["id"]!r} '
                    f'both derive attribute {item["attribute"]}')
            if item['vertexGroup'] in groups:
                raise ValueError(
                    f'Mesh {name!r} regions {groups[item["vertexGroup"]]!r} and {item["id"]!r} '
                    f'read the same vertex group {item["vertexGroup"]!r}')
            ids[item['id']] = True
            attributes[item['attribute']] = item['id']
            groups[item['vertexGroup']] = item['id']
            normalized.append(item)
        if hair_group is not None and hair_group in groups:
            raise ValueError(f'Mesh {name!r} hairGroup {hair_group!r} is also the mask of region {groups[hair_group]!r}')
        hair_name = HAIR_ATTRIBUTE if hair_group is not None else hair_attribute
        if hair_name in attributes:
            raise ValueError(f'Mesh {name!r} hair attribute {hair_name} collides with region {attributes[hair_name]!r}')
        plan.append({'name': name, 'hairGroup': hair_group, 'hairAttribute': hair_attribute, 'regions': normalized})
    return {'version': 1, 'meshes': plan}


# ----------------------------------------------------------------------- mask helpers

def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def validate_mask_values(values, expected_count, label):
    """Every value finite and inside [0, 1], one per vertex."""
    if len(values) != expected_count:
        raise ValueError(f'{label} has {len(values)} values for {expected_count} vertices')
    for index, value in enumerate(values):
        if not math.isfinite(value):
            raise ValueError(f'{label} has a non-finite value at vertex {index}')
        if value < 0.0 or value > 1.0:
            raise ValueError(f'{label} has {value!r} at vertex {index}, outside [0, 1]')


def mask_summary(values, label):
    """Summary of a validated mask; rejects masks with no influence at all."""
    nonzero = [v for v in values if v > 0.0]
    if not nonzero:
        raise ValueError(f'{label} has zero influence on every vertex; refusing an empty region')
    return {
        'vertices': len(values),
        'nonzero': len(nonzero),
        'min': min(values),
        'max': max(values),
        'distinct': frozenset(f32(v) for v in values),
    }


def public_summary(summary):
    return {key: value for key, value in summary.items() if key != 'distinct'}


def support_geometry(positions, mask, hair=None):
    """Weighted center and extent radius of the influenced, non-hair vertices.

    Mirrors the runtime rule (center = weighted mean, radius = support extent, must be
    nonzero) so a region the runtime cannot size is rejected here, not silently skipped.
    """
    members, total = [], 0.0
    sx = sy = sz = 0.0
    for index, weight in enumerate(mask):
        if weight <= 0.0 or (hair is not None and hair[index] > 0.0):
            continue
        x, y, z = positions[index]
        members.append(index)
        total += weight
        sx += weight * x
        sy += weight * y
        sz += weight * z
    if not members:
        raise ValueError('the mask has no influenced non-hair vertex to derive a center from')
    center = (sx / total, sy / total, sz / total)
    radius = max(math.dist(positions[i], center) for i in members)
    if not math.isfinite(radius) or radius <= SUPPORT_EPSILON:
        raise ValueError('the influenced non-hair vertices have zero extent')
    return center, radius, len(members)


# ------------------------------------------------------------------------- GLB reading

def digest(path):
    sha = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            sha.update(block)
    return sha.hexdigest()


def read_glb(path):
    """Return (json document, embedded BIN chunk bytes) of a GLB 2 file."""
    data = Path(path).read_bytes()
    if len(data) < 20:
        raise ValueError('GLB header is incomplete')
    magic, version, total = struct.unpack_from('<4sII', data, 0)
    if magic != b'glTF' or version != 2:
        raise ValueError('Not a GLB 2 file')
    if total != len(data):
        raise ValueError('GLB length does not match the file')
    offset, document, binary = 12, None, None
    while offset < total:
        if offset + 8 > total:
            raise ValueError('GLB chunk header is truncated')
        length, kind = struct.unpack_from('<II', data, offset)
        offset += 8
        if offset + length > total:
            raise ValueError('GLB chunk exceeds the file length')
        chunk = data[offset:offset + length]
        offset += length
        if kind == 0x4E4F534A and document is None:
            document = json.loads(chunk.decode('utf-8'))
        elif kind == 0x004E4942 and binary is None:
            binary = chunk
    if document is None:
        raise ValueError('GLB has no JSON chunk')
    return document, binary or b''


def glb_inventory(document):
    meshes = document.get('meshes', [])
    return {
        'nodes': len(document.get('nodes', [])),
        'meshes': len(meshes),
        'skins': len(document.get('skins', [])),
        'skinnedNodes': sum('skin' in node for node in document.get('nodes', [])),
        'morphTargets': sum(max((len(p.get('targets', [])) for p in m.get('primitives', [])), default=0)
                            for m in meshes),
        'animations': [a.get('name', str(i)) for i, a in enumerate(document.get('animations', []))],
        'materials': len(document.get('materials', [])),
        'images': len(document.get('images', [])),
    }


def _accessor(document, index, label):
    accessors = document.get('accessors', [])
    if type(index) is not int or not 0 <= index < len(accessors):
        raise ValueError(f'{label} references a missing accessor')
    return accessors[index]


def read_float_scalars(document, binary, index, label):
    """Decode an unnormalized FLOAT SCALAR accessor from the GLB-embedded buffer."""
    accessor = _accessor(document, index, label)
    if accessor.get('componentType') != FLOAT_COMPONENT or accessor.get('type') != 'SCALAR' \
            or accessor.get('normalized'):
        raise ValueError(f'{label} must be an unnormalized FLOAT SCALAR accessor, '
                         f'got componentType={accessor.get("componentType")} type={accessor.get("type")} '
                         f'normalized={bool(accessor.get("normalized"))}')
    if 'sparse' in accessor:
        raise ValueError(f'{label} uses sparse storage')
    count = accessor.get('count')
    if type(count) is not int or count <= 0:
        raise ValueError(f'{label} has no elements')
    view_index = accessor.get('bufferView')
    views = document.get('bufferViews', [])
    if type(view_index) is not int or not 0 <= view_index < len(views):
        raise ValueError(f'{label} has no bufferView')
    view = views[view_index]
    buffers = document.get('buffers', [])
    if view.get('buffer', 0) != 0 or not buffers or 'uri' in buffers[0]:
        raise ValueError(f'{label} is not stored in the GLB-embedded buffer')
    stride = view.get('byteStride') or 4
    view_start = view.get('byteOffset', 0)
    start = view_start + accessor.get('byteOffset', 0)
    end = start + (count - 1) * stride + 4
    if stride < 4 or end > view_start + view.get('byteLength', 0) or end > len(binary):
        raise ValueError(f'{label} reads outside its buffer view')
    if stride == 4:
        values = list(struct.unpack_from(f'<{count}f', binary, start))
    else:
        values = [struct.unpack_from('<f', binary, start + i * stride)[0] for i in range(count)]
    for position, value in enumerate(values):
        if not math.isfinite(value):
            raise ValueError(f'{label} has a non-finite value at element {position}')
    return values


def three_node_name(name):
    """Name three.js GLTFLoader gives a node (PropertyBinding.sanitizeNodeName)."""
    return re.sub(r'[\[\].:/]', '', re.sub(r'\s', '_', name))


def _runtime_name_holders(document, runtime):
    holders = [n for n in document.get('nodes', []) if n.get('name') and three_node_name(n['name']) == runtime]
    meshes = document.get('meshes', [])
    for node in document.get('nodes', []):
        mesh = meshes[node['mesh']] if type(node.get('mesh')) is int and node['mesh'] < len(meshes) else None
        if mesh and len(mesh.get('primitives', [])) > 1 and three_node_name(mesh.get('name', '')) == runtime:
            holders.append(mesh)
    return holders


def resolve_runtime_node(document, exported_name, label):
    """Find the one GLB node for a Blender object and the name three.js will expose."""
    nodes = document.get('nodes', [])
    matches = [i for i, node in enumerate(nodes) if node.get('name') == exported_name]
    if len(matches) != 1:
        raise ValueError(f'{label}: expected exactly one GLB node named {exported_name!r}, found {len(matches)}; '
                         'was the object exported?')
    runtime = three_node_name(exported_name)
    if not runtime:
        raise ValueError(f'{label}: name {exported_name!r} is empty after three.js sanitizing')
    if len(_runtime_name_holders(document, runtime)) != 1:
        raise ValueError(f'{label}: three.js would load another object as {runtime!r} too, so the sidecar '
                         'name would not resolve uniquely; rename the colliding Blender objects')
    node = nodes[matches[0]]
    meshes = document.get('meshes', [])
    if type(node.get('mesh')) is not int or node['mesh'] >= len(meshes):
        raise ValueError(f'{label}: GLB node {exported_name!r} carries no mesh')
    primitives = meshes[node['mesh']].get('primitives', [])
    if len(primitives) != 1:
        raise ValueError(f'{label}: exports {len(primitives)} primitives (material slots in use); GLTFLoader '
                         'splits those into separate meshes so one sidecar mesh name cannot address them. '
                         'Use one material slot per configured mesh')
    return matches[0], runtime


def _resolve_joint(document, bone, skin_joints, label):
    nodes = document.get('nodes', [])
    candidates = [i for i, node in enumerate(nodes) if node.get('name') == bone]
    if skin_joints is not None:
        candidates = [i for i in candidates if i in skin_joints]
    if len(candidates) != 1:
        where = 'in the exported skin joints' if skin_joints is not None else 'in the exported GLB'
        raise ValueError(f'{label}: bone {bone!r} was not found exactly once {where}')
    runtime = three_node_name(bone)
    if not runtime or len(_runtime_name_holders(document, runtime)) != 1:
        raise ValueError(f'{label}: bone {bone!r} would not resolve uniquely as {runtime!r} after three.js loading')
    return runtime


def check_exported_mask(values, summary, vertex_count, label):
    """Exported mask checks: one value per POSITION vertex, inside [0, 1], not all zero, and
    every value taken from the authored mask. Does not prove per-vertex correspondence."""
    if len(values) != vertex_count:
        raise ValueError(f'{label} has {len(values)} values for {vertex_count} POSITION vertices')
    low, high, nonzero = math.inf, -math.inf, 0
    for value in values:
        if value < 0.0 or value > 1.0:
            raise ValueError(f'{label} exported {value!r}, outside [0, 1]')
        low, high = min(low, value), max(high, value)
        nonzero += value > 0.0
    if nonzero == 0:
        raise ValueError(f'{label} exported as all zero; the authored influence was lost')
    strays = [v for v in set(values) if v not in summary['distinct']]
    if strays:
        raise ValueError(f'{label} exported value {strays[0]!r} that is not in the authored mask')
    return {'vertices': vertex_count, 'nonzero': nonzero, 'min': low, 'max': high}


def check_skin(document, node_index, primitive, vertex_count, expect_skin, bones, label):
    node = document['nodes'][node_index]
    info = {'skinned': 'skin' in node, 'joints': 0, 'bones': {}}
    skin_joints = None
    if expect_skin:
        skins = document.get('skins', [])
        if type(node.get('skin')) is not int or node['skin'] >= len(skins):
            raise ValueError(f'{label} is skinned in Blender but exported without a skin')
        joints = skins[node['skin']].get('joints') or []
        if not joints:
            raise ValueError(f'{label} exported a skin without joints')
        attributes = primitive.get('attributes', {})
        for key in ('JOINTS_0', 'WEIGHTS_0'):
            if key not in attributes:
                raise ValueError(f'{label} exported a skin but no {key} attribute')
            if _accessor(document, attributes[key], f'{label} {key}').get('count') != vertex_count:
                raise ValueError(f'{label} {key} count differs from POSITION')
        info['joints'] = len(joints)
        skin_joints = set(joints)
    for bone in bones:
        info['bones'][bone] = _resolve_joint(document, bone, skin_joints, label)
    return info


def check_mesh_export(document, binary, object_name, expected_masks, expect_skin, bones, label=None):
    """Validate one configured mesh in the exported GLB; return what was observed."""
    label = label or f'Mesh {object_name!r}'
    node_index, runtime = resolve_runtime_node(document, object_name, label)
    node = document['nodes'][node_index]
    primitive = document['meshes'][node['mesh']]['primitives'][0]
    attributes = primitive.get('attributes', {})
    if 'POSITION' not in attributes:
        raise ValueError(f'{label} exported without POSITION')
    vertex_count = _accessor(document, attributes['POSITION'], f'{label} POSITION').get('count')
    masks = {}
    for name, summary in expected_masks.items():
        if name not in attributes:
            hint = [key for key in attributes if key.upper() == name.upper()]
            raise ValueError(f'{label}: exported primitive has no {name} attribute' +
                             (f' (found {hint[0]!r})' if hint else ''))
        values = read_float_scalars(document, binary, attributes[name], f'{label} {name}')
        masks[name] = check_exported_mask(values, summary, vertex_count, f'{label} {name}')
    skin = check_skin(document, node_index, primitive, vertex_count, expect_skin, bones, label)
    return {'runtimeName': runtime, 'vertexCount': vertex_count, 'masks': masks, 'skin': skin,
            'morphTargets': len(primitive.get('targets', []))}


def build_sidecar(meshes):
    """Runtime softbody.json v1 from prepared meshes (runtime names already resolved)."""
    out = []
    for mesh in meshes:
        item = {'name': mesh['runtimeName']}
        if mesh.get('hairAttribute'):
            item['hairAttribute'] = mesh['hairAttribute']
        item['regions'] = []
        for region in mesh['regions']:
            entry = {'id': region['id']}
            if region.get('group'):
                entry['group'] = region['group']
            entry['attribute'] = region['attribute']
            if region.get('bone'):
                entry['bone'] = region['bone']
            if region.get('center') is not None:
                entry['center'] = list(region['center'])
                entry['radius'] = region['radius']
            item['regions'].append(entry)
        out.append(item)
    return {'version': 1, 'meshes': out}


# ------------------------------------------------------------------------ bpy (lazy)

def _read_point_floats(attribute, count):
    values = array('f', bytes(4 * count))
    attribute.data.foreach_get('value', values)
    return values


def _existing_attribute_clash(data, wanted, label):
    upper = {name.upper(): name for name in wanted}
    for attribute in data.attributes:
        if attribute.name.upper() in upper:
            raise ValueError(f'{label} already has attribute {attribute.name!r}; refusing to overwrite '
                             f'geometry data or collide with {upper[attribute.name.upper()]}')


def _rig(obj):
    armatures = {m.object for m in obj.modifiers if m.type == 'ARMATURE' and m.object is not None}
    if len(armatures) > 1:
        raise ValueError(f'Mesh {obj.name!r} has several armature modifiers; one rig per mesh is supported')
    if armatures:
        return next(iter(armatures)), True
    if obj.parent is not None and obj.parent.type == 'ARMATURE':
        return obj.parent, False
    return None, False


def _group_masks(obj, wanted):
    """{group name: array('f')} read from vertex weights; absent membership is 0."""
    data = obj.data
    index_to_name = {}
    for name in wanted:
        group = obj.vertex_groups.get(name)
        if group is None:
            raise ValueError(f'Mesh {obj.name!r} has no vertex group {name!r}; author it in Blender first')
        index_to_name[group.index] = name
    masks = {name: array('f', bytes(4 * len(data.vertices))) for name in wanted}
    for vertex in data.vertices:
        for element in vertex.groups:
            name = index_to_name.get(element.group)
            if name is not None:
                masks[name][vertex.index] = element.weight
    return masks


def _animated(objects):
    for obj in objects:
        owners = [obj]
        shape_keys = getattr(obj.data, 'shape_keys', None)
        if shape_keys is not None:
            owners.append(shape_keys)
        for owner in owners:
            animation = owner.animation_data
            if animation and (animation.action or len(animation.nla_tracks)):
                return True
    return False


def gather_authoring(bpy, plan):
    """Validate everything the Blender project must satisfy; mutates nothing."""
    prepared = []
    for mesh in plan['meshes']:
        obj = bpy.data.objects.get(mesh['name'])
        if obj is None or obj.type != 'MESH':
            raise ValueError(f'Config mesh {mesh["name"]!r} is not a Mesh object in the source project')
        label = f'Mesh {obj.name!r}'
        data = obj.data
        if data.library or obj.library or obj.override_library:
            raise ValueError(f'{label} is linked from a library; make it local before preparing')
        if data.users > 1:
            raise ValueError(f'{label} shares mesh data with another object; attributes would leak, make it single-user')
        count = len(data.vertices)
        if count == 0:
            raise ValueError(f'{label} has no vertices')
        positions = [tuple(v.co) for v in data.vertices]
        hair_group = mesh['hairGroup']
        wanted = [r['vertexGroup'] for r in mesh['regions']] + ([hair_group] if hair_group else [])
        masks = _group_masks(obj, wanted)

        hair = None
        if hair_group:
            _existing_attribute_clash(data, [HAIR_ATTRIBUTE], label)
            values = masks[hair_group]
            validate_mask_values(values, count, f'{label} hair group {hair_group!r}')
            hair = {'attribute': HAIR_ATTRIBUTE, 'values': values, 'create': True,
                    'summary': mask_summary(values, f'{label} hair group {hair_group!r}')}
        else:
            name = mesh['hairAttribute'] or HAIR_ATTRIBUTE
            present = [a for a in data.attributes if a.name.upper() == name.upper()]
            if mesh['hairAttribute'] and not present:
                raise ValueError(f'{label} has no existing hair attribute {name!r}')
            if present:
                attribute = present[0]
                if attribute.name != name or attribute.domain != 'POINT' or attribute.data_type != 'FLOAT':
                    raise ValueError(f'{label} attribute {attribute.name!r} must be a POINT FLOAT attribute '
                                     f'named exactly {name!r} to serve as the hair mask')
                values = _read_point_floats(attribute, count)
                validate_mask_values(values, count, f'{label} existing hair attribute {name!r}')
                hair = {'attribute': name, 'values': values, 'create': False,
                        'summary': mask_summary(values, f'{label} existing hair attribute {name!r}')}

        derived = [r['attribute'] for r in mesh['regions']]
        _existing_attribute_clash(data, derived, label)
        armature, expect_skin = _rig(obj)
        regions, sums = [], array('f', bytes(4 * count))
        for region in mesh['regions']:
            rlabel = f'{label} region {region["id"]!r} (group {region["vertexGroup"]!r})'
            values = masks[region['vertexGroup']]
            validate_mask_values(values, count, rlabel)
            summary = mask_summary(values, rlabel)
            for i, value in enumerate(values):
                sums[i] += value
            if region['bone'] is not None and (armature is None or armature.data.bones.get(region['bone']) is None):
                raise ValueError(f'{rlabel} names bone {region["bone"]!r}, which is not in the mesh\'s armature'
                                 + (f' {armature.name!r}' if armature else ' (the mesh has no armature)'))
            support = None
            center, radius = region['center'], region['radius']
            if center is None:
                try:
                    c, r, members = support_geometry(positions, values, hair['values'] if hair else None)
                except ValueError as error:
                    raise ValueError(f'{rlabel}: {error}; supply explicit center and radius for hair-only or '
                                     'degenerate regions (no anatomy is guessed)') from None
                support = {'vertices': members, 'radiusBlenderUnits': r}
            regions.append({**region, 'values': values, 'summary': summary, 'support': support})
        shape_keys = list(data.shape_keys.key_blocks) if data.shape_keys else []
        # Same rule as the glTF exporter (skip_sk): basis, muted and self-relative keys are not exported.
        expected_morphs = sum(1 for key in shape_keys[1:] if not key.mute and key.relative_key != key)
        prepared.append({
            'plan': mesh, 'object': obj.name, 'vertices': count, 'regions': regions, 'hair': hair,
            'armature': armature.name if armature else None, 'expectSkin': expect_skin,
            'bones': sorted({r['bone'] for r in mesh['regions'] if r['bone']}),
            'expectedMorphs': expected_morphs, 'maxSummedInfluence': max(sums),
            'rigObjects': [obj] + ([armature] if armature else []),
        })
    return prepared


def external_paths(bpy):
    """Resolved on-disk paths of unpacked textures and libraries; missing ones reject."""
    found, missing = {}, []
    for kind, items in (('image', [i for i in bpy.data.images if i.source == 'FILE' and not i.packed_file]),
                        ('library', list(bpy.data.libraries))):
        for item in items:
            if not item.filepath or getattr(item, 'library', None):
                continue
            path = Path(bpy.path.abspath(item.filepath))
            if path.is_file():
                found[(kind, item.name)] = os.path.realpath(path)
            else:
                missing.append(f'{kind} {item.name}')
    if missing:
        raise ValueError('Unresolvable source files: ' + ', '.join(sorted(missing)))
    return found


def _gltf_properties(bpy):
    for attempt in (0, 1):
        try:
            return {p.identifier for p in bpy.ops.export_scene.gltf.get_rna_type().properties}
        except (AttributeError, KeyError, RuntimeError):
            if attempt:
                raise ValueError('This bpy runtime has no glTF exporter') from None
            import addon_utils
            addon_utils.enable('io_scene_gltf2', default_set=False, persistent=False)


def export_glb(bpy, path):
    properties = _gltf_properties(bpy)
    required = ('export_attributes', 'export_apply', 'export_skins', 'export_morph', 'export_animations')
    normal_maps = any(material.use_nodes and any(node.type == 'NORMAL_MAP' for node in material.node_tree.nodes)
                      for material in bpy.data.materials if material.users)
    if normal_maps:
        required += ('export_tangents',)
    missing = [name for name in required if name not in properties]
    if missing:
        raise ValueError('This Blender glTF exporter lacks options needed to preserve custom attributes, skins, '
                         'morphs, animations and normal-map tangents: ' + ', '.join(missing))
    settings = {'export_format': 'GLB', 'export_attributes': True, 'export_apply': False, 'export_skins': True,
                'export_morph': True, 'export_animations': True, 'use_selection': False,
                'check_existing': False}
    if normal_maps:
        settings['export_tangents'] = True
    result = bpy.ops.export_scene.gltf(filepath=str(path), **{k: v for k, v in settings.items() if k in properties})
    if 'FINISHED' not in result or not Path(path).is_file():
        raise ValueError('The glTF exporter returned without producing a GLB')


def _write_mask(data, name, values):
    attribute = data.attributes.new(name=name, type='FLOAT', domain='POINT')
    attribute.data.foreach_set('value', values)
    if _read_point_floats(attribute, len(values)) != values:
        raise ValueError(f'Attribute {name!r} did not read back identically after writing')


def _save(bpy, path):
    if 'FINISHED' not in bpy.ops.wm.save_as_mainfile(filepath=str(path), check_existing=False,
                                                     relative_remap=True):
        raise ValueError('Blender did not save the working project')


def _build(bpy, source, source_hash, plan, prepared, paths, out):
    master, glb = out / 'character.blend', out / 'character.glb'
    # Blender would leave character.blend1 beside the second save; this is a process-local preference.
    bpy.context.preferences.filepaths.save_version = 0
    _save(bpy, master)  # from here on only the copy is ever written
    if external_paths(bpy) != paths:
        raise ValueError('Saving the working copy severed a texture or library path; refusing to continue')
    for item in prepared:
        data = bpy.data.objects[item['object']].data
        for region in item['regions']:
            _write_mask(data, region['attribute'], region['values'])
        if item['hair'] and item['hair']['create']:
            _write_mask(data, item['hair']['attribute'], item['hair']['values'])
    _save(bpy, master)
    export_glb(bpy, glb)

    document, binary = read_glb(glb)
    animated = _animated([o for item in prepared for o in item['rigObjects']])
    meshes = []
    for item in prepared:
        label = f'Mesh {item["object"]!r}'
        expected = {r['attribute']: r['summary'] for r in item['regions']}
        if item['hair']:
            expected[item['hair']['attribute']] = item['hair']['summary']
        observed = check_mesh_export(document, binary, item['object'], expected, item['expectSkin'], item['bones'])
        if observed['morphTargets'] < item['expectedMorphs']:
            raise ValueError(f'{label} exported {observed["morphTargets"]} morph targets, '
                             f'expected {item["expectedMorphs"]} from its shape keys')
        meshes.append((item, observed))
    inventory = glb_inventory(document)
    if animated and not inventory['animations']:
        raise ValueError('The source rig is animated but the exported GLB has no animations')

    sidecar = build_sidecar([{
        'runtimeName': observed['runtimeName'],
        'hairAttribute': item['hair']['attribute'] if item['hair'] else None,
        'regions': [{**r, 'bone': observed['skin']['bones'].get(r['bone']) if r['bone'] else None}
                    for r in item['regions']],
    } for item, observed in meshes])
    sidecar_path = out / 'softbody.json'
    sidecar_path.write_text(json.dumps(sidecar, indent=2) + '\n')

    if digest(source) != source_hash:
        raise ValueError('Incoming source changed during preparation; do not accept this run')
    receipt = {
        'route': ROUTE, 'status': 'prepared-unreviewed',
        'source': str(source), 'sourceSha256': source_hash, 'sourceUnchanged': True,
        'configSha256': hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'blender': bpy.app.version_string,
        'blend': master.name, 'blendSha256': digest(master),
        'glb': glb.name, 'glbSha256': digest(glb),
        'sidecar': sidecar_path.name, 'sidecarSha256': digest(sidecar_path),
        'meshes': [{
            'blenderName': item['object'], 'runtimeName': observed['runtimeName'],
            'sourceVertices': item['vertices'], 'glbVertices': observed['vertexCount'],
            'armature': item['armature'], 'skinned': observed['skin']['skinned'],
            'joints': observed['skin']['joints'], 'morphTargets': observed['morphTargets'],
            'maxSummedInfluence': item['maxSummedInfluence'],
            'hair': ({'attribute': item['hair']['attribute'], 'authoredFromGroup': item['hair']['create'],
                      'source': public_summary(item['hair']['summary']),
                      'glb': observed['masks'][item['hair']['attribute']]} if item['hair'] else None),
            'regions': [{
                'id': r['id'], 'vertexGroup': r['vertexGroup'], 'attribute': r['attribute'],
                'bone': r['bone'], 'runtimeBone': observed['skin']['bones'].get(r['bone']) if r['bone'] else None,
                'explicitSupport': r['center'] is not None, 'support': r['support'],
                'source': public_summary(r['summary']), 'glb': observed['masks'][r['attribute']],
            } for r in item['regions']],
        } for item, observed in meshes],
        'glbInventory': inventory,
        'maskValidation': 'per mask: POSITION-count FLOAT SCALAR, within [0, 1], not all zero, values drawn from '
                          'the authored mask; per-vertex correspondence is not verified',
        'unverified': UNVERIFIED,
    }
    (out / 'preparation.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def prepare(bpy, source, config, out):
    """Prepare `source` into the new directory `out`; returns the preparation receipt."""
    plan = validate_config(config)
    source = Path(os.path.abspath(source))
    out = Path(os.path.abspath(out))
    if source.suffix.lower() != '.blend' or not source.is_file():
        raise ValueError('--source must be a saved .blend authoring project')
    if os.path.lexists(out):
        raise ValueError('--out must be a new directory; refusing to touch an existing path')
    resolved_out = out.resolve()
    if resolved_out == source.parent.resolve() or resolved_out in source.resolve().parents:
        raise ValueError('--out must be a new directory outside the source project')
    source_hash = digest(source)
    if 'FINISHED' not in bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False, use_scripts=False):
        raise ValueError('Blender could not open the source project')
    prepared = gather_authoring(bpy, plan)
    paths = external_paths(bpy)
    out.mkdir(parents=True, exist_ok=False)
    try:
        return _build(bpy, source, source_hash, plan, prepared, paths, out)
    except BaseException:
        shutil.rmtree(out, ignore_errors=True)  # we created it a moment ago; leave no half-prepared character
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    if argv is None:
        argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    args = parser.parse_args(argv)
    try:
        config = parse_config(args.config.read_text())
        validate_config(config)  # reject bad configs before bpy is even needed
        try:
            import bpy
        except ImportError:
            raise ValueError('bpy is required: run with a Python containing bpy or inside `blender -b`') from None
        print(json.dumps(prepare(bpy, args.source, config, args.out)))
        return 0
    except (ImportError, OSError, RuntimeError, ValueError, KeyError, struct.error) as error:
        print(json.dumps({'route': ROUTE, 'status': 'blocked', 'reason': str(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
