"""Softbody preparation must reject unauthored/ambiguous masks and only accept what the exported GLB proves."""
import copy
import hashlib
import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / 'tools' / 'prepare_softbody.py'
sys.path.insert(0, str(TOOL.parent))
import prepare_softbody as prep  # noqa: E402  (pure helpers must import without bpy)


def region(**overrides):
    base = {'id': 'chest-left', 'group': 'chest', 'vertexGroup': 'mask_chest_left', 'bone': 'Spine2'}
    base.update(overrides)
    return base


def config(*regions, **mesh):
    return {'version': 1, 'meshes': [{'name': 'Body', 'regions': list(regions) or [region()], **mesh}]}


class ConfigContract(unittest.TestCase):
    def test_valid_config_derives_attributes_and_keeps_authored_fields(self):
        plan = prep.validate_config(config(
            region(center=[0, 1.5, -2], radius=0.25),
            region(id='chest right', vertexGroup='mask_chest_right'),
            hairGroup='mask_hair'))
        mesh = plan['meshes'][0]
        self.assertEqual([r['attribute'] for r in mesh['regions']], ['_SOFT_CHEST_LEFT', '_SOFT_CHEST_RIGHT'])
        self.assertEqual(mesh['regions'][0]['center'], [0.0, 1.5, -2.0])
        self.assertEqual(mesh['regions'][0]['radius'], 0.25)
        self.assertEqual(mesh['hairGroup'], 'mask_hair')

    def assertRejected(self, document):
        with self.assertRaises(ValueError):
            prep.validate_config(document)

    def test_ids_that_sanitize_to_one_attribute_collide(self):
        self.assertRejected(config(region(id='chest-left'), region(id='chest_left', vertexGroup='other')))

    def test_duplicate_ids_meshes_and_shared_groups_are_rejected(self):
        self.assertRejected(config(region(), region(vertexGroup='other')))
        self.assertRejected(config(region(), region(id='b')))
        doubled = config()
        doubled['meshes'].append(copy.deepcopy(doubled['meshes'][0]))
        self.assertRejected(doubled)

    def test_hair_declarations_cannot_be_ambiguous(self):
        self.assertRejected(config(hairGroup='h', hairAttribute='_HAIR'))
        self.assertRejected(config(hairGroup='mask_chest_left'))
        self.assertRejected(config(hairAttribute='hair'))
        self.assertRejected(config(region(id='hair', vertexGroup='x'), hairAttribute='_SOFT_HAIR'))

    def test_unknown_keys_and_runtime_attribute_key_are_rejected(self):
        self.assertRejected(config(region(attribute='_SOFT_X')))
        self.assertRejected(config(region(vertex_group='typo')))
        bad = config()
        bad['extra'] = 1
        self.assertRejected(bad)
        self.assertRejected({'version': 2, 'meshes': config()['meshes']})
        self.assertRejected({'version': True, 'meshes': config()['meshes']})

    def test_ids_must_yield_a_bounded_attribute_name(self):
        self.assertRejected(config(region(id='---')))
        self.assertRejected(config(region(id='x' * 80)))
        self.assertRejected(config(region(id='')))
        self.assertRejected({'version': 1, 'meshes': [{'name': 'Body', 'regions': []}]})

    def test_explicit_geometry_must_be_complete_and_finite(self):
        self.assertRejected(config(region(center=[0, 0, 0])))
        self.assertRejected(config(region(radius=1.0)))
        self.assertRejected(config(region(center=[0, 0], radius=1)))
        self.assertRejected(config(region(center=[0, 0, 1e999], radius=1)))
        self.assertRejected(config(region(center=[0, 0, True], radius=1)))
        self.assertRejected(config(region(center=[0, 0, 0], radius=0)))
        self.assertRejected(config(region(center=[0, 0, 0], radius=-1)))
        with self.assertRaises(ValueError):
            prep.parse_config('{"version": 1, "meshes": [{"name": "B", "regions": '
                              '[{"id": "a", "vertexGroup": "g", "center": [NaN, 0, 0], "radius": 1}]}]}')


class MaskHelpers(unittest.TestCase):
    def test_masks_must_be_finite_and_inside_unit_range(self):
        for bad in (math.nan, math.inf, -math.inf, -0.001, 1.001):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                prep.validate_mask_values([0.0, bad, 1.0], 3, 'mask')
        with self.assertRaises(ValueError):
            prep.validate_mask_values([0.0, 1.0], 3, 'mask')
        prep.validate_mask_values([0.0, 0.5, 1.0], 3, 'mask')

    def test_empty_mask_is_not_a_region(self):
        with self.assertRaises(ValueError):
            prep.mask_summary([0.0, 0.0, 0.0], 'mask')
        summary = prep.mask_summary([0.0, 0.5, 1.0], 'mask')
        self.assertEqual((summary['nonzero'], summary['min'], summary['max']), (2, 0.0, 1.0))

    def test_support_is_weighted_mean_without_hair(self):
        positions = [(0, 0, 0), (2, 0, 0), (10, 0, 0), (5, 5, 5)]
        center, radius, members = prep.support_geometry(positions, [1.0, 3.0, 1.0, 0.0], hair=[0, 0, 1.0, 0])
        self.assertEqual(members, 2)
        self.assertAlmostEqual(center[0], 1.5)
        self.assertAlmostEqual(radius, 1.5)

    def test_hair_only_or_degenerate_support_cannot_be_sized(self):
        with self.assertRaises(ValueError):
            prep.support_geometry([(0, 0, 0), (1, 0, 0)], [1.0, 1.0], hair=[0.2, 1.0])
        with self.assertRaises(ValueError):
            prep.support_geometry([(1, 1, 1), (1, 1, 1)], [1.0, 1.0])


def pad(blob):
    return blob + b'\0' * (-len(blob) % 4)


class GlbBuilder:
    """Smallest glTF writer able to express a skinned mesh with custom scalar attributes."""

    def __init__(self):
        self.binary = b''
        self.views, self.accessors = [], []

    def add(self, blob, component, kind, count, normalized=False, stride=None, extra=None):
        offset = len(self.binary)
        self.binary += pad(blob)
        view = {'buffer': 0, 'byteOffset': offset, 'byteLength': len(blob)}
        if stride:
            view['byteStride'] = stride
        self.views.append(view)
        accessor = {'bufferView': len(self.views) - 1, 'componentType': component, 'type': kind, 'count': count}
        if normalized:
            accessor['normalized'] = True
        accessor.update(extra or {})
        self.accessors.append(accessor)
        return len(self.accessors) - 1

    def scalars(self, values, **kwargs):
        return self.add(struct.pack(f'<{len(values)}f', *values), 5126, 'SCALAR', len(values), **kwargs)

    def build(self, attributes, count, skinned=True, node_names=('Body', 'Root', 'Spine2'), primitives=1,
              mesh_name='BodyMesh'):
        positions = self.add(struct.pack(f'<{count * 3}f', *([0.0] * count * 3)), 5126, 'VEC3', count)
        primitive = {'attributes': {'POSITION': positions, **attributes}}
        if skinned:
            primitive['attributes']['JOINTS_0'] = self.add(bytes(count * 4), 5121, 'VEC4', count)
            primitive['attributes']['WEIGHTS_0'] = self.add(
                struct.pack(f'<{count * 4}f', *([1.0, 0.0, 0.0, 0.0] * count)), 5126, 'VEC4', count)
        nodes = [{'name': name} for name in node_names]
        nodes[0]['mesh'] = 0
        document = {'asset': {'version': '2.0'}, 'nodes': nodes,
                    'meshes': [{'name': mesh_name, 'primitives': [copy.deepcopy(primitive) for _ in range(primitives)]}],
                    'accessors': self.accessors, 'bufferViews': self.views,
                    'buffers': [{'byteLength': len(self.binary)}]}
        if skinned:
            nodes[0]['skin'] = 0
            document['skins'] = [{'joints': [1, 2]}]
        return document, self.binary


def summary_of(values):
    return prep.mask_summary(values, 'authored')


class ExportedMaskContract(unittest.TestCase):
    authored = [0.0, 0.25, 1.0, 0.5]

    def fixture(self, exported=None, **kwargs):
        builder = GlbBuilder()
        attributes = {'_SOFT_CHEST_LEFT': builder.scalars(exported if exported is not None else self.authored)}
        return builder.build(attributes, 4, **kwargs)

    def check(self, document, binary, skin=True, bones=('Spine2',)):
        return prep.check_mesh_export(document, binary, 'Body', {'_SOFT_CHEST_LEFT': summary_of(self.authored)},
                                      skin, bones)

    def test_matching_export_reports_what_was_read(self):
        observed = self.check(*self.fixture())
        self.assertEqual(observed['runtimeName'], 'Body')
        self.assertEqual(observed['vertexCount'], 4)
        self.assertEqual(observed['masks']['_SOFT_CHEST_LEFT'], {'vertices': 4, 'nonzero': 3, 'min': 0.0, 'max': 1.0})
        self.assertEqual(observed['skin']['joints'], 2)
        self.assertEqual(observed['skin']['bones'], {'Spine2': 'Spine2'})

    def test_written_glb_roundtrips_through_the_reader(self):
        document, binary = self.fixture()
        encoded = pad(json.dumps(document).encode()).replace(b'\0', b' ')
        body = struct.pack('<II', len(encoded), 0x4E4F534A) + encoded + struct.pack('<II', len(binary), 0x004E4942) + binary
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'a.glb'
            path.write_bytes(struct.pack('<4sII', b'glTF', 2, 12 + len(body)) + body)
            read, blob = prep.read_glb(path)
            self.assertEqual(blob, binary)
            self.assertEqual(prep.glb_inventory(read)['skinnedNodes'], 1)
            path.write_bytes(path.read_bytes()[:-3])
            with self.assertRaises(ValueError):
                prep.read_glb(path)

    def test_count_must_equal_position_count(self):
        document, binary = self.fixture(exported=[0.0, 0.25, 1.0])
        with self.assertRaises(ValueError):
            self.check(document, binary)

    def test_range_zero_and_foreign_values_are_rejected(self):
        for exported in ([0.0, 0.25, 1.5, 0.5], [0.0, 0.0, 0.0, 0.0], [0.0, 0.25, 1.0, 0.75],
                         [0.0, 0.25, 255 / 256, 0.5]):
            with self.subTest(exported=exported):
                document, binary = self.fixture(exported=exported)
                with self.assertRaises(ValueError):
                    self.check(document, binary)

    def test_missing_attribute_and_wrong_encoding_are_rejected(self):
        document, binary = self.fixture()
        document['meshes'][0]['primitives'][0]['attributes']['_soft_chest_left'] = \
            document['meshes'][0]['primitives'][0]['attributes'].pop('_SOFT_CHEST_LEFT')
        with self.assertRaises(ValueError):
            self.check(document, binary)
        builder = GlbBuilder()
        attributes = {'_SOFT_CHEST_LEFT': builder.add(bytes(8), 5123, 'SCALAR', 4, normalized=True)}
        with self.assertRaises(ValueError):
            self.check(*builder.build(attributes, 4))
        builder = GlbBuilder()
        attributes = {'_SOFT_CHEST_LEFT': builder.add(struct.pack('<4f', *self.authored), 5126, 'VEC2', 2)}
        with self.assertRaises(ValueError):
            self.check(*builder.build(attributes, 4))

    def test_non_finite_exported_value_is_rejected(self):
        document, binary = self.fixture(exported=[0.0, math.nan, 1.0, 0.5])
        with self.assertRaises(ValueError):
            self.check(document, binary)

    def test_strided_accessors_are_decoded(self):
        builder = GlbBuilder()
        interleaved = b''.join(struct.pack('<ff', value, 9.0) for value in self.authored)
        attributes = {'_SOFT_CHEST_LEFT': builder.add(interleaved, 5126, 'SCALAR', 4, stride=8)}
        self.assertEqual(self.check(*builder.build(attributes, 4))['masks']['_SOFT_CHEST_LEFT']['nonzero'], 3)

    def test_rigged_source_requires_skin_joints_and_bones(self):
        document, binary = self.fixture(skinned=False)
        with self.assertRaises(ValueError):
            self.check(document, binary)
        document, binary = self.fixture()
        del document['meshes'][0]['primitives'][0]['attributes']['WEIGHTS_0']
        with self.assertRaises(ValueError):
            self.check(document, binary)
        document, binary = self.fixture()
        with self.assertRaises(ValueError):
            self.check(document, binary, bones=('Chest',))
        document, binary = self.fixture()
        document['skins'][0]['joints'] = [1]  # Spine2 exists as a node but is not a skin joint
        with self.assertRaises(ValueError):
            self.check(document, binary)

    def test_unskinned_source_needs_no_skin(self):
        observed = self.check(*self.fixture(skinned=False), skin=False, bones=())
        self.assertFalse(observed['skin']['skinned'])

    def test_runtime_names_must_resolve_uniquely(self):
        document, binary = self.fixture(node_names=('Body', 'Body', 'Spine2'))
        with self.assertRaises(ValueError):
            self.check(document, binary)
        document, binary = self.fixture(node_names=('Body', 'Root', 'Bo.dy'))
        with self.assertRaises(ValueError):
            self.check(document, binary)
        document, binary = self.fixture(primitives=2)
        with self.assertRaises(ValueError):
            self.check(document, binary)

    def test_names_the_loader_rewrites_are_reported_as_loaded(self):
        self.assertEqual(prep.three_node_name('Body.001 mesh'), 'Body001_mesh')
        document, binary = self.fixture(node_names=('Body', 'Root', 'Spine.2'))
        observed = prep.check_mesh_export(document, binary, 'Body', {'_SOFT_CHEST_LEFT': summary_of(self.authored)},
                                          True, ('Spine.2',))
        self.assertEqual(observed['skin']['bones'], {'Spine.2': 'Spine2'})

    def test_sidecar_is_the_v1_runtime_contract(self):
        sidecar = prep.build_sidecar([{
            'runtimeName': 'Body', 'hairAttribute': '_HAIR',
            'regions': [{'id': 'a', 'group': 'g', 'attribute': '_SOFT_A', 'bone': 'Spine2',
                         'center': [1, 2, 3], 'radius': 0.5},
                        {'id': 'b', 'group': None, 'attribute': '_SOFT_B', 'bone': None,
                         'center': None, 'radius': None}]}])
        self.assertEqual(sidecar, {'version': 1, 'meshes': [{
            'name': 'Body', 'hairAttribute': '_HAIR', 'regions': [
                {'id': 'a', 'group': 'g', 'attribute': '_SOFT_A', 'bone': 'Spine2', 'center': [1, 2, 3], 'radius': 0.5},
                {'id': 'b', 'attribute': '_SOFT_B'}]}]})


class CliWithoutBpy(unittest.TestCase):
    def test_bad_config_is_blocked_before_any_runtime_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'a.blend'
            source.write_bytes(b'not really blender')
            cfg = Path(tmp) / 'regions.json'
            cfg.write_text(json.dumps(config(region(), region(id='chest_left', vertexGroup='x'))))
            out = Path(tmp) / 'out'
            result = subprocess.run([sys.executable, str(TOOL), '--source', str(source), '--config', str(cfg),
                                     '--out', str(out)], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            report = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertEqual(report['status'], 'blocked')
            self.assertTrue(report['reason'])
            self.assertFalse(out.exists())


FIXTURE = r'''
import json, sys
import bpy  # bpy must initialize before bmesh can import
import bmesh

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
mesh = bpy.data.meshes.new('BodyMesh')
bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=1.0)
bm.to_mesh(mesh)
bm.free()
body = bpy.data.objects.new('Body', mesh)
scene.collection.objects.link(body)

rig_data = bpy.data.armatures.new('RigData')
rig = bpy.data.objects.new('Rig', rig_data)
scene.collection.objects.link(rig)
bpy.context.view_layer.update()
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode='EDIT')
root = rig_data.edit_bones.new('Root')
root.head, root.tail = (0, 0, -1), (0, 0, 0)
spine = rig_data.edit_bones.new('Spine2')
spine.head, spine.tail = (0, 0, 0), (0, 0, 1)
spine.parent = root
bpy.ops.object.mode_set(mode='OBJECT')

body.parent = rig
modifier = body.modifiers.new('Armature', 'ARMATURE')
modifier.object = rig

names = ('Root', 'Spine2', 'mask_chest_left', 'mask_chest_right', 'mask_hair', 'mask_empty', 'mask_zero')
groups = {name: body.vertex_groups.new(name=name) for name in names}
for vertex in mesh.vertices:
    x, y, z = vertex.co
    lift = min(1.0, max(0.0, (z + 1.0) / 2.0))
    groups['Root'].add([vertex.index], 1.0 - lift, 'REPLACE')
    groups['Spine2'].add([vertex.index], lift, 'REPLACE')
    if -0.2 < z < 0.4 and x > 0.2:
        groups['mask_chest_left'].add([vertex.index], 0.25 + 0.75 * min(1.0, (x - 0.2) / 0.6), 'REPLACE')
    if -0.2 < z < 0.4 and x < -0.2:
        groups['mask_chest_right'].add([vertex.index], 0.25 + 0.75 * min(1.0, (-x - 0.2) / 0.6), 'REPLACE')
    if z > 0.75:
        groups['mask_hair'].add([vertex.index], 1.0, 'REPLACE')
    elif z > 0.5:
        groups['mask_hair'].add([vertex.index], 0.5, 'REPLACE')
groups['mask_zero'].add([0], 0.0, 'REPLACE')

body.shape_key_add(name='Basis', from_mix=False)
puff = body.shape_key_add(name='Puff', from_mix=False)
for index in range(8):
    co = puff.data[index].co.copy()
    co.z += 0.1
    puff.data[index].co = co

keep = mesh.attributes.new('_KEEP', 'FLOAT', 'POINT')
keep.data.foreach_set('value', [0.5] * len(mesh.vertices))

rig.animation_data_create()
pose_bone = rig.pose.bones['Spine2']
pose_bone.rotation_mode = 'XYZ'
for frame, angle in ((1, 0.0), (12, 0.4)):
    pose_bone.rotation_euler = (angle, 0.0, 0.0)
    pose_bone.keyframe_insert('rotation_euler', frame=frame)


def stats(name):
    index = body.vertex_groups[name].index
    weights = [e.weight for v in mesh.vertices for e in v.groups if e.group == index]
    return {'members': len(weights), 'nonzero': sum(w > 0 for w in weights), 'max': max(weights, default=0.0)}


report = {'vertices': len(mesh.vertices), 'groups': {name: stats(name) for name in names}}
bpy.ops.wm.save_as_mainfile(filepath=sys.argv[1])
print(json.dumps(report))
'''


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@unittest.skipUnless(os.environ.get('IMG2_CC5_PYTHON'),
                     'Set IMG2_CC5_PYTHON to a Python containing bpy for the real preparation regression')
class RealBpyPreparation(unittest.TestCase):
    """Diagnostic skinned sphere with authored vertex groups: proves the pipeline, not a human."""

    @classmethod
    def setUpClass(cls):
        cls.python = os.environ['IMG2_CC5_PYTHON']
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        script = cls.root / 'fixture.py'
        script.write_text(FIXTURE)
        cls.source = cls.root / 'diagnostic.blend'
        created = subprocess.run([cls.python, str(script), str(cls.source)], capture_output=True, text=True,
                                 timeout=120)
        assert created.returncode == 0, created.stdout + created.stderr
        cls.authored = json.loads(created.stdout.strip().splitlines()[-1])
        cls.runs = 0

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_tool(self, document, out=None):
        type(self).runs += 1
        out = out or self.root / f'out{self.runs}'
        cfg = self.root / f'regions{self.runs}.json'
        cfg.write_text(json.dumps(document))
        before = sha256(self.source)
        result = subprocess.run([self.python, str(TOOL), '--source', str(self.source), '--config', str(cfg),
                                 '--out', str(out)], capture_output=True, text=True, timeout=240)
        self.assertEqual(sha256(self.source), before, 'The original authoring project must never change')
        return result, json.loads(result.stdout.strip().splitlines()[-1]), out

    def assertBlocked(self, document):
        result, report, out = self.run_tool(document)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(report['status'], 'blocked')
        self.assertTrue(report['reason'])
        self.assertFalse(out.exists(), 'A rejected input must leave no half-prepared character')

    def full_config(self, **mesh):
        return {'version': 1, 'meshes': [{'name': 'Body', 'regions': [
            region(),
            region(id='chest-right', vertexGroup='mask_chest_right')], **mesh}]}

    def test_prepared_glb_carries_authored_masks_skin_morphs_and_animation(self):
        result, report, out = self.run_tool(self.full_config(hairGroup='mask_hair'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(report['status'], 'prepared-unreviewed')
        self.assertEqual(sorted(p.name for p in out.iterdir()),
                         ['character.blend', 'character.glb', 'preparation.json', 'softbody.json'])
        self.assertEqual(report, json.loads((out / 'preparation.json').read_text()))
        self.assertEqual(report['sourceSha256'], sha256(self.source))
        for key, name in (('glbSha256', 'character.glb'), ('blendSha256', 'character.blend'),
                          ('sidecarSha256', 'softbody.json')):
            self.assertEqual(report[key], sha256(out / name))

        self.assertEqual(json.loads((out / 'softbody.json').read_text()), {'version': 1, 'meshes': [{
            'name': 'Body', 'hairAttribute': '_HAIR', 'regions': [
                {'id': 'chest-left', 'group': 'chest', 'attribute': '_SOFT_CHEST_LEFT', 'bone': 'Spine2'},
                {'id': 'chest-right', 'group': 'chest', 'attribute': '_SOFT_CHEST_RIGHT', 'bone': 'Spine2'}]}]})

        document, binary = prep.read_glb(out / 'character.glb')
        node = next(n for n in document['nodes'] if n.get('name') == 'Body')
        primitive = document['meshes'][node['mesh']]['primitives'][0]
        attributes = primitive['attributes']
        count = document['accessors'][attributes['POSITION']]['count']
        self.assertGreaterEqual(count, self.authored['vertices'])
        for name, group in (('_SOFT_CHEST_LEFT', 'mask_chest_left'), ('_SOFT_CHEST_RIGHT', 'mask_chest_right'),
                            ('_HAIR', 'mask_hair')):
            accessor = document['accessors'][attributes[name]]
            self.assertEqual((accessor['type'], accessor['componentType'], accessor['count']), ('SCALAR', 5126, count))
            values = prep.read_float_scalars(document, binary, attributes[name], name)
            self.assertTrue(all(0.0 <= v <= 1.0 for v in values), name)
            self.assertAlmostEqual(max(values), self.authored['groups'][group]['max'], places=6)
        left = prep.read_float_scalars(document, binary, attributes['_SOFT_CHEST_LEFT'], 'left')
        right = prep.read_float_scalars(document, binary, attributes['_SOFT_CHEST_RIGHT'], 'right')
        self.assertFalse(any(a > 0 and b > 0 for a, b in zip(left, right)), 'disjoint authored regions stay disjoint')
        keep = prep.read_float_scalars(document, binary, attributes['_KEEP'], 'keep')
        self.assertEqual(set(keep), {0.5}, 'Unrelated attributes survive untouched')

        self.assertIn('skin', node)
        joints = [document['nodes'][i]['name'] for i in document['skins'][node['skin']]['joints']]
        self.assertTrue({'Root', 'Spine2'} <= set(joints))
        for key in ('JOINTS_0', 'WEIGHTS_0'):
            self.assertEqual(document['accessors'][attributes[key]]['count'], count)
        self.assertEqual(len(primitive['targets']), 1)
        self.assertGreaterEqual(len(document['animations']), 1)
        mesh = report['meshes'][0]
        self.assertEqual((mesh['blenderName'], mesh['runtimeName'], mesh['armature']), ('Body', 'Body', 'Rig'))
        self.assertEqual(mesh['glbVertices'], count)

    def test_existing_hair_attribute_and_explicit_geometry_are_carried_through(self):
        document = self.full_config(hairAttribute='_KEEP')
        result, report, out = self.run_tool(document)
        self.assertEqual(result.returncode, 2, 'every region is hair-only under an all-vertex hair mask')
        self.assertEqual(report['status'], 'blocked')
        self.assertFalse(out.exists())
        for item in document['meshes'][0]['regions']:
            item.update(center=[0.5, 0.0, 0.1], radius=0.4)
        result, report, out = self.run_tool(document)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        sidecar = json.loads((out / 'softbody.json').read_text())
        self.assertEqual(sidecar['meshes'][0]['hairAttribute'], '_KEEP')
        for item in sidecar['meshes'][0]['regions']:
            self.assertEqual((item['center'], item['radius']), ([0.5, 0.0, 0.1], 0.4))

    def test_existing_output_is_refused_untouched(self):
        out = self.root / 'occupied'
        out.mkdir()
        (out / 'keep.txt').write_text('mine')
        result, report, _ = self.run_tool(self.full_config(), out=out)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(report['status'], 'blocked')
        self.assertEqual([p.name for p in out.iterdir()], ['keep.txt'])
        self.assertEqual((out / 'keep.txt').read_text(), 'mine')

    def test_missing_empty_and_zero_weight_groups_are_rejected(self):
        for group in ('does_not_exist', 'mask_empty', 'mask_zero'):
            with self.subTest(group=group):
                self.assertBlocked(config(region(vertexGroup=group)))
        self.assertBlocked(config(region(), hairGroup='mask_empty'))

    def test_bone_and_mesh_must_exist_in_the_project(self):
        self.assertBlocked(config(region(bone='NoSuchBone')))
        self.assertBlocked({'version': 1, 'meshes': [{'name': 'Rig', 'regions': [region()]}]})
        self.assertBlocked({'version': 1, 'meshes': [{'name': 'Ghost', 'regions': [region()]}]})


if __name__ == '__main__':
    unittest.main()
