import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
from tools.bpy_measure_skin_authoring import measure_arrays, rasterized_masks
try:
    import bpy
except ImportError:
    bpy = None

ROOT = Path(__file__).resolve().parents[1]


class ArrayTests(unittest.TestCase):
    def test_metrics_and_counterexamples(self):
        rgb = np.array([[[.2]*3,[.2]*3,[.8]*3,[.8]*3]])
        masks = {'face':np.array([[1,1,0,0]],bool), 'arm':np.array([[0,0,1,1]],bool)}
        targets = {'face':{'rgb':[.2]*3,'lstar':float(__import__('tools.skin_authoring',fromlist=['_lstar'])._lstar(np.array([.2]*3)))}, 'arm':{'rgb':[.7]*3,'lstar':50}}
        values, details = measure_arrays(rgb,masks,targets,uv_areas=[16,4],world_areas=[1,1],triangle_regions=['face','body'],pairs=[[[0,0],[0,2]]],baseline=np.zeros_like(rgb),support=np.array([[1,1,0,0]],bool))
        self.assertAlmostEqual(values['skin_region_tone_max_delta_rgb'], .1)
        self.assertGreater(values['skin_region_tone_max_delta_lstar'], 0)
        self.assertEqual(values['skin_region_uniformity_p99'], 0)
        self.assertEqual(values['skin_face_body_density_ratio'], 2)
        self.assertAlmostEqual(values['skin_mirror_tone_residual'], .6)
        self.assertEqual(values['skin_changed_outside_support'], 2)
        values, _ = measure_arrays(rgb,masks,{'face':targets['face']})
        self.assertNotIn('skin_region_tone_max_delta_rgb', values)
        self.assertNotIn('skin_changed_outside_support', values)
        self.assertEqual(details['regions']['face']['count'], 2)

    def test_raster_excludes_ambiguous_overlap(self):
        points = [[0,0,0],[1,0,0],[0,1,0]]
        masks, report = rasterized_masks(points, [[0,1,2],[0,1,2]], [[[0,0],[1,0],[0,1]]]*2, (8,8,3), {'face':[0], 'arm':[1]})
        self.assertFalse(masks['face'].any()); self.assertGreater(report['shared_texels'], 0)


@unittest.skipUnless(bpy is not None, 'requires bpy interpreter')
class RealBpy(unittest.TestCase):
    def test_blend_atlas_and_perturbed_tone(self):
        from tools.skin_authoring import _lstar
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp); bpy.ops.wm.read_factory_settings(use_empty=True)
            def textured(name, colour):
                """A UV triangle over the whole lower-left half, sampling its own image."""
                mesh = bpy.data.meshes.new(name); mesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)], [], [(0,1,2)]); mesh.update()
                obj = bpy.data.objects.new(name,mesh); bpy.context.collection.objects.link(obj)
                uv = mesh.uv_layers.new(name='UV')
                for i, xy in enumerate([(0,0),(1,0),(0,1)]): uv.data[i].uv = xy
                image = bpy.data.images.new(name+'Image', width=8, height=8, alpha=True)
                image.pixels[:] = colour * 64
                image.filepath_raw = str(work/(name+'.png')); image.file_format = 'PNG'; image.save(); image.pack(); image.use_fake_user = True
                material = bpy.data.materials.new(name+'Material'); material.use_nodes = True
                node = material.node_tree.nodes.new('ShaderNodeTexImage'); node.image = image
                mesh.materials.append(material)
                return obj, image, node
            obj, image, node = textured('Body', [.4,.4,.4,1]); image.name = 'Atlas'
            # Hair keeps its own image: its UVs cover the same square without sharing an atlas texel.
            _, hair_image, _ = textured('Hair', [.1,.1,.1,1])
            group = obj.vertex_groups.new(name='face'); group.add([0,1,2],1,'REPLACE')
            path = work/'fixture.blend'; bpy.ops.wm.save_as_mainfile(filepath=str(path))
            regions = work/'regions.json'; regions.write_text(json.dumps({'face':{'object':'Body','vertex_group':'face'}}))
            # Read back the actual stored pixel value, accounting for image serialization.
            actual = float(image.pixels[0]); targets = work/'targets.json'
            targets.write_text(json.dumps({'face':{'rgb':[actual]*3,'lstar':float(_lstar(np.array([actual]*3)))}}))
            out = work/'evidence.json'
            def measure(blend):
                cmd = [sys.executable,str(ROOT/'tools/bpy_measure_skin_authoring.py'),'--blend',str(blend),'--atlas','Atlas','--regions',str(regions),'--targets',str(targets),'--subject','fixture','--out',str(out)]
                return subprocess.run(cmd,capture_output=True,text=True)
            def run():
                proc = measure(path)
                self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
                return json.loads(out.read_text())['measurements']['skin_region_tone_max_delta_rgb']['value']
            self.assertLess(run(),.01)
            image.pixels[:] = [.7,.7,.7,1] * 64
            image.save()
            data = (work/'Body.png').read_bytes()
            image.pack(data=data, data_len=len(data))
            bpy.ops.wm.save_as_mainfile(filepath=str(path))
            self.assertGreater(run(),.1)
            # A body whose material samples another image does not occupy the atlas at all.
            node.image = hair_image
            unlinked = work/'unlinked.blend'; bpy.ops.wm.save_as_mainfile(filepath=str(unlinked))
            proc = measure(unlinked)
            self.assertEqual(proc.returncode,2,proc.stdout+proc.stderr)
            self.assertIn('no material sampling the atlas',proc.stderr)
