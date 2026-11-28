import json
import inspect
import re
import tempfile
import unittest
from pathlib import Path

import numpy as np
from tools import bpy_measure_geometry as geo
from tools import gate_skin_body

try:
    import bpy
except ImportError:
    bpy = None

ROOT = Path(__file__).resolve().parents[1]
FRAGMENT = ROOT / 'reference/skin-body-standards.s9-geometry.json'


class Helpers(unittest.TestCase):
    def test_mirror_coverage_counterexample(self):
        points = [[-1,0,0], [1,0,0], [-2,0,0], [-3,0,0]]
        r = geo.mirror_match(points, {'point':[0,0,0], 'normal':[1,0,0]}, .01)
        self.assertEqual(r['coverage'], .5)
        self.assertEqual(r['p95'], 0)
        self.assertEqual(geo.mirror_match(points, {'point':[0,0,0], 'normal':[1,0,0]}, .01, [2,3])['coverage'], 1)

    def test_nonmanifold_counterexample(self):
        edges = geo.edge_incidence([[0,1,2], [1,0,3], [0,1,4]])
        self.assertEqual(edges[(0,1)], 3)

    def test_uv_overlap_and_gutter_counterexamples(self):
        a = [[.05,.05],[.45,.05],[.05,.45]]
        b = [[.55,.55],[.95,.55],[.95,.95]]
        self.assertGreater(geo.uv_overlap_texels([a,a], ['a','b'], (40,40)), 0)
        self.assertEqual(geo.uv_overlap_texels([a,a], ['a','b'], (40,40), [['a','b']]), 0)
        self.assertEqual(geo.island_gutter([a,a], ['a','b'], (40,40)), 0)
        self.assertGreater(geo.island_gutter([a,b], ['a','b'], (40,40)), 0)

    def test_density_counterexample(self):
        w = [[[0,0,0],[1,0,0],[0,1,0]]]
        u = [[[0,0],[1,0],[0,1]]]
        self.assertEqual(geo.density(w, u, (16,16)), 16)
        self.assertIsNone(geo.density([[[0,0,0]]*3], u, (16,16)))

    def test_missing_landmark_counterexample(self):
        points = {'a':[0,0,0], 'b':[0,0,1]}
        self.assertIsNone(geo.landmark_ratios(points, {'a':[0,0,0]}, 1, 1, [['a','b']]))
        self.assertEqual(geo.landmark_ratios(points, points, 1, 1, [['a','b']]), 0)

    def test_fragment_metrics_are_emittable(self):
        stages = gate_skin_body.load_standards([FRAGMENT])
        self.assertEqual(stages[0]['id'], 'S9')
        checks = stages[0]['checks']
        source = inspect.getsource(geo.measure)
        literals = set(re.findall(r"'(geo_[a-z0-9_]+)'", source))
        emitted = {name for name in literals if not name.endswith('_')}
        self.assertIn('geo_mirror_', literals)
        self.assertIn('geo_uv_density_', literals)
        self.assertIn('geo_vertices_', literals)
        self.assertIn('geo_triangles_', literals)
        emitted.update({'geo_mirror_p95_over_h','geo_mirror_max_over_h',
                        'geo_uv_density_face_px_per_m','geo_uv_density_body_px_per_m',
                        'geo_triangles_body','geo_vertices_body'})
        self.assertFalse({c['metric'] for c in checks} - emitted)
        self.assertTrue(all(c.get('severity') == 'advisory' for c in checks if c['tag'] == 'single-subject'))


@unittest.skipUnless(bpy is not None, 'requires bpy interpreter')
class RealBpy(unittest.TestCase):
    def test_fixture_and_counterexamples(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            bpy.ops.wm.read_factory_settings(use_empty=True)
            mesh = bpy.data.meshes.new('Body')
            mesh.from_pydata([(-1,0,0),(1,0,0),(0,1,0),(0,0,2)], [], [(0,2,3),(2,1,3),(1,0,3),(0,1,2)])
            mesh.update()
            obj = bpy.data.objects.new('Body', mesh); bpy.context.collection.objects.link(obj)
            uv = mesh.uv_layers.new(name='UV')
            for poly in mesh.polygons:
                x = (poly.index % 2)*.5; y = (poly.index // 2)*.5
                for n, loop in enumerate(poly.loop_indices): uv.data[loop].uv = [(x+.03,y+.03),(x+.47,y+.03),(x+.03,y+.47)][n]
            blend = path/'fixture.blend'; bpy.ops.wm.save_as_mainfile(filepath=str(blend))
            mirror = path/'mirror.json'; mirror.write_text(json.dumps({'plane':{'point':[0,0,0],'normal':[1,0,0]},'tolerance_m':.1}))
            regions = path/'regions.json'; regions.write_text(json.dumps({'objects':['Body']}))
            landmarks = path/'landmarks.json'
            landmarks.write_text(json.dumps({'points':{'missing':{'object':'Body','group':'missing'},'other':{'object':'Body','group':'also_missing'}}, 'pairs':[['missing','other']]}))
            missing = geo.measure(blend, reference=blend, landmarks=landmarks, regions=regions)['measurements']
            self.assertNotIn('geo_landmark_ratio_max_delta', missing)
            evidence = geo.measure(blend, regions=regions, mirror=mirror, atlas_size=(32,32))
            values = evidence['measurements']
            self.assertEqual(values['geo_nonmanifold_edges_global']['value'], 0)
            self.assertEqual(values['geo_mirror_coverage']['value'], 1)
            self.assertEqual(values['geo_uv_unapproved_overlap_texels']['value'], 0)
            check = next(c for c in gate_skin_body.load_standards([FRAGMENT])[0]['checks'] if c['id'] == 'geometry-nonmanifold')
            self.assertEqual(gate_skin_body.judge(check, evidence, [])['verdict'], 'pass')
            obj = bpy.data.objects['Body']; obj.data.vertices[1].co.x = 1.5
            bpy.ops.wm.save_as_mainfile(filepath=str(blend))
            changed = geo.measure(blend, regions=regions, mirror=mirror, atlas_size=(32,32))['measurements']
            self.assertLess(changed['geo_mirror_coverage']['value'], 1)
            obj = bpy.data.objects['Body']; mesh = obj.data
            vertices = [tuple(v.co) for v in mesh.vertices]
            faces = [tuple(p.vertices) for p in mesh.polygons] + [(0,2,3)]
            mesh.clear_geometry(); mesh.from_pydata(vertices, [], faces); mesh.update()
            uv = mesh.uv_layers.active or mesh.uv_layers.new(name='UV')
            for poly in mesh.polygons:
                for n, loop in enumerate(poly.loop_indices): uv.data[loop].uv = [(0.05,0.05),(.45,.05),(.05,.45)][n]
            bpy.ops.wm.save_as_mainfile(filepath=str(blend))
            changed_evidence = geo.measure(blend, regions=regions, mirror=mirror, atlas_size=(32,32))
            changed = changed_evidence['measurements']
            self.assertGreater(changed['geo_nonmanifold_edges_global']['value'], 0)
            self.assertGreater(changed['geo_uv_unapproved_overlap_texels']['value'], 0)
            self.assertEqual(gate_skin_body.judge(check, changed_evidence, [])['verdict'], 'fail')


if __name__ == '__main__': unittest.main()
