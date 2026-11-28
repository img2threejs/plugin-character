import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.bpy_measure_skin_body import weight_stats, mirror_difference, group_bones, pixel_diff, source_hashes, island_tone_deviation
try:
    import bpy
except ImportError:
    bpy = None

ROOT = Path(__file__).resolve().parents[1]
MEASURER = ROOT / 'tools/bpy_measure_skin_body.py'
GATE = ROOT / 'tools/gate_skin_body.py'


class Helpers(unittest.TestCase):
    def test_weight_counterexamples(self):
        stats = weight_stats([{'a': .5, 'b': .5}, {'a': .2, 'b': .2, 'c': .2, 'd': .2, 'e': .19999, 'f': .00001}])
        self.assertEqual(stats['weight_max_influences'], 6)
        self.assertEqual(stats['weight_small_count'], 1)
        self.assertGreater(weight_stats([{'a': .8}])['weight_sum_max_error'], .0001)

    def test_mirror_counterexamples(self):
        result = mirror_difference([{'L': 1}], [{'R': .8}], [[0, 0], [1, 0]], {'L': 'R'})
        self.assertAlmostEqual(result['mirror_max_difference'], .2)
        self.assertEqual(result['mirror_unmatched_count'], 1)

    def test_catalogue_counterexample(self):
        self.assertEqual(group_bones(['a'], {'bone_groups': [{'id': 'limbs', 'bones': ['a', 'b']}]}), {'limbs': ['b']})

    def test_pixel_counterexample(self):
        self.assertEqual(pixel_diff([(0,), (1,)], [(0,), (2,)], [True, False])['changed_outside_repair_mask'], 1)
        with self.assertRaises(ValueError): pixel_diff([(0,)], [], None)

    def test_source_and_tone_counterexamples(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'source'
            path.write_bytes(b'original')
            digest = hashlib.sha256(b'original').hexdigest()
            self.assertTrue(source_hashes([f'source={path}:{digest}'])['source']['matches'])
            path.write_bytes(b'changed')
            self.assertFalse(source_hashes([f'source={path}:{digest}'])['source']['matches'])
            with self.assertRaises(ValueError): source_hashes([f'source={path}:bad'])
        pixels = [(0.2, 0.3, 0.4, 1), (0.8, 0.3, 0.4, 1)]
        self.assertAlmostEqual(island_tone_deviation(pixels, [True, False], [False, True]), 0.6)
        with self.assertRaises(ValueError): island_tone_deviation(pixels, [False, False], [True, False])


@unittest.skipUnless(bpy is not None, 'requires bpy interpreter')
class RealBpy(unittest.TestCase):
    def test_real_measurement_and_counterexamples(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            catalogue = work / 'catalogue.json'
            catalogue.write_text(json.dumps({'characters': [{'assets': [{'id': 'fixture', 'bone_groups': [{'id': 'central', 'bones': ['Root']}, {'id': 'paired', 'bones': ['Left', 'Right']}]}]}]}))
            bpy.ops.wm.read_factory_settings(use_empty=True)
            mesh = bpy.data.meshes.new('Body')
            mesh.from_pydata([(0,0,0), (1,0,0), (0,1,0), (1,1,0)], [], [(0,1,3), (0,3,2)])
            mesh.update()
            obj = bpy.data.objects.new('Body', mesh); bpy.context.collection.objects.link(obj)
            uv = mesh.uv_layers.new(name='UV')
            for loop in uv.data: loop.uv = (.25, .25)
            for name in ('Left', 'Right'):
                group = obj.vertex_groups.new(name=name); group.add([0,1,2,3], .5, 'REPLACE')
            region = obj.vertex_groups.new(name='region:abdomen')
            region.add([0, 1, 2, 3], .25, 'REPLACE')
            arm = bpy.data.armatures.new('Rig'); rig = bpy.data.objects.new('Rig', arm); bpy.context.collection.objects.link(rig)
            bpy.context.view_layer.objects.active = rig; rig.select_set(True)
            bpy.ops.object.mode_set(mode='EDIT')
            for name in ('Root', 'Left', 'Right'):
                bone = arm.edit_bones.new(name); bone.head = (0,0,0); bone.tail = (0,0,1)
            bpy.ops.object.mode_set(mode='OBJECT')
            image = bpy.data.images.new('Atlas', width=8, height=9, alpha=True)
            image.pixels[:] = [0.5, 0.4, 0.3, 1.0] * 72
            image.filepath_raw = str(work / 'atlas.png'); image.file_format = 'PNG'; image.save()
            image.source = 'FILE'; image.reload(); image.pack(); image.use_fake_user = True
            material = bpy.data.materials.new('Skin'); material.use_nodes = True
            texture = material.node_tree.nodes.new('ShaderNodeTexImage'); texture.image = image
            principled = next(node for node in material.node_tree.nodes if node.type == 'BSDF_PRINCIPLED')
            material.node_tree.links.new(texture.outputs['Color'], principled.inputs['Base Color'])
            mesh.materials.append(material)
            hair_material = bpy.data.materials.new('Hair'); hair_material.use_nodes = True
            mesh.materials.append(hair_material)
            original = work / 'original.blend'; bpy.ops.wm.save_as_mainfile(filepath=str(original))
            image.scale(16, 18)
            image.filepath_raw = str(work / 'resolution.png'); image.save()
            data = (work / 'resolution.png').read_bytes(); image.pack(data=data, data_len=len(data))
            resolution = work / 'resolution.blend'; bpy.ops.wm.save_as_mainfile(filepath=str(resolution))
            bpy.ops.wm.open_mainfile(filepath=str(original), load_ui=False, use_scripts=False)
            obj = bpy.data.objects['Body']; uv = obj.data.uv_layers.active; image = bpy.data.images['Atlas']
            pairs = work / 'pairs.json'
            pairs.write_text(json.dumps({'object_a':'Body', 'object_b':'Body', 'pairs':[[0,1],[2,3]], 'permutation':{'Left':'Right','Right':'Left'}}))
            def make_mask(name, indexes):
                path = work / (name + '.json')
                path.write_text(json.dumps({'size': [8, 9], 'pixels': [i in indexes for i in range(72)]}))
                return path
            repair = make_mask('repair', set())
            protected = make_mask('protected', {0})
            island = make_mask('island', set(range(1, 11)))
            reference = make_mask('reference', set(range(20, 30)))
            source = work / 'source.bin'; source.write_bytes(b'original')
            expected = hashlib.sha256(b'original').hexdigest()
            def run(path, stages):
                evidence = work / 'evidence.json'
                cmd = [sys.executable, str(MEASURER), '--blend', str(path), '--character', 'fixture', '--catalogue', str(catalogue), '--atlas', 'Atlas', '--mirror-pairs', str(pairs), '--hair-absent', '--out', str(evidence),
                       '--source', f'body={source}:{expected}', '--baseline-blend', str(original),
                       '--resolution-baseline-blend', str(resolution), '--repair-mask', str(repair),
                       '--protected-mask', str(protected), '--island-mask', str(island),
                       '--reference-mask', str(reference), '--composite-atlas']
                measured = subprocess.run(cmd, capture_output=True, text=True)
                self.assertEqual(measured.returncode, 0, measured.stdout + measured.stderr)
                document = json.loads(evidence.read_text())
                document.setdefault('declared', {}).setdefault('limits', {})['island_tone_deviation'] = {'value': .1, 'source': 'independently authored test project limit'}
                evidence.write_text(json.dumps(document))
                command = [sys.executable, str(GATE), '--evidence', str(evidence), '--json']
                for stage in stages: command += ['--stage', stage]
                verdict = subprocess.run(command, capture_output=True, text=True)
                return verdict.returncode, json.loads(verdict.stdout)
            def failed(verdict):
                return {c['id'] for c in verdict['evidence']['checks'] if c['verdict'] == 'fail'}
            code, verdict = run(original, ['S1', 'S2', 'S4', 'S5', 'S6'])
            self.assertEqual(code, 0, verdict)
            code, verdict = run(original, ['S7'])
            self.assertEqual(code, 2)
            self.assertEqual({c['id'] for c in verdict['evidence']['checks'] if c['verdict'] == 'unmeasured'}, {'export-maps'})
            source.write_bytes(b'changed')
            code, verdict = run(original, ['S1'])
            self.assertEqual(code, 1); self.assertIn('original-unchanged', failed(verdict))
            source.write_bytes(b'original')
            pixels = list(image.pixels[:]); pixels[0] = .9
            image.pixels[:] = pixels; image.update()
            image.filepath_raw = str(work / 'protected.png'); image.save()
            data = (work / 'protected.png').read_bytes(); image.pack(data=data, data_len=len(data))
            edited = work / 'protected.blend'; bpy.ops.wm.save_as_mainfile(filepath=str(edited))
            code, verdict = run(edited, ['S2'])
            self.assertEqual(code, 1); self.assertIn('body-pixels', failed(verdict))
            bpy.ops.wm.open_mainfile(filepath=str(original), load_ui=False, use_scripts=False)
            image = bpy.data.images['Atlas']; obj = bpy.data.objects['Body']; uv = obj.data.uv_layers.active
            pixels = list(image.pixels[:])
            for index in range(1, 11): pixels[index * 4] = .9
            image.pixels[:] = pixels; image.update()
            image.filepath_raw = str(work / 'tone.png'); image.save()
            data = (work / 'tone.png').read_bytes(); image.pack(data=data, data_len=len(data))
            uv.data[0].uv.x = .5; obj.vertex_groups['Left'].add([0], .8, 'REPLACE')
            edited = work / 'tone.blend'; bpy.ops.wm.save_as_mainfile(filepath=str(edited))
            code, verdict = run(edited, ['S2'])
            self.assertEqual(code, 1)
            self.assertTrue({'island-tone', 'uv-error', 'repair-boundary'} <= failed(verdict), failed(verdict))
            code, verdict = run(edited, ['S5'])
            self.assertEqual(code, 1); self.assertIn('weight-sum', failed(verdict))


if __name__ == '__main__': unittest.main()
