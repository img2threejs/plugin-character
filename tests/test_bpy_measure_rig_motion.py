import json
import math
import unittest
from pathlib import Path
import numpy as np
from tools.bpy_measure_rig_motion import (strain, weight_profile, antipodal_pairs,
    quaternion_error, section_center, hair_clearance, mesh_data, bpy)
from tools.gate_skin_body import judge

ROOT = Path(__file__).resolve().parents[1]

class Helpers(unittest.TestCase):
    def test_strain_counterexample(self):
        rest = np.array([[0.,0,0],[1,0,0],[0,1,0]])
        triangles = [[0,1,2]]
        self.assertAlmostEqual(strain(rest, rest, triangles)['p99'], 1)
        bad = rest.copy(); bad[1] *= 3
        self.assertGreater(strain(rest, bad, triangles)['p99'], 2)
        self.assertIsNone(strain(rest, rest, [[0,0,1]]))

    def test_displaced_pivot_fails_baseline(self):
        rest = np.array([[0.,0,0],[1,0,0],[0,0,1],[1,0,1]])
        tris = [[0,1,3],[0,3,2]]
        rotation = np.array([[1,0,0],[0,0,-1],[0,1,0]])
        def posed(pivot):
            out = rest.copy()
            out[2:] = (rest[2:]-pivot) @ rotation.T + pivot
            return out
        good = strain(rest, posed(np.array([0,0,1])), tris)['p99']
        bad = strain(rest, posed(np.array([0,0,3])), tris)['p99']
        check = {'id':'strain', 'stage':'S10', 'metric':'rig_strain_p99__leg__bend', 'unit':'ratio', 'comparator':'no-worse-than-baseline'}
        def evaluate(value):
            evidence = {'declared':{'baselines':{check['metric']:{'value':good,'source':'fixture'}}},
                        'measurements':{check['metric']:{'value':value,'unit':'ratio','source':'fixture','method':'fixed triangles'}}}
            return judge(check,evidence,[])['verdict']
        self.assertEqual(evaluate(good),'pass')
        self.assertEqual(evaluate(bad),'fail')

    def test_weight_counterexample(self):
        self.assertEqual(weight_profile([0,1,2], [0,.8,.4])['rig_weight_reversal_count'],1)
        self.assertEqual(weight_profile([0,1,2], [0,.8,.4], [(1,2)])['rig_weight_reversal_count'],0)

    def test_quaternion_counterexample(self):
        q = [[1,0,0,0],[-1,0,0,0]]
        self.assertEqual(antipodal_pairs(q), 1)
        self.assertEqual(antipodal_pairs([q[0], [-x for x in q[1]]]), 0)
        self.assertEqual(quaternion_error(*q), 0)

    def test_open_section_is_unmeasured(self):
        self.assertIsNone(section_center([[0,0,-1],[1,0,1],[0,1,1]], [[0,1,2]], [0,0,0], [0,0,1]))

    def test_fragments(self):
        for name in ('rig','hair'):
            path = ROOT / ('reference/skin-body-standards.s10-rig.json' if name == 'rig' else 'reference/skin-body-standards.s11-hair.json')
            data = json.loads(path.read_text()); self.assertEqual(data['schema'], 'skin-body-standards/1')
            self.assertTrue(data['stages'][0]['checks'])

@unittest.skipUnless(bpy is not None, 'requires bpy interpreter')
class RealBpy(unittest.TestCase):
    def test_armature_strain_and_quaternions(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        mesh = bpy.data.meshes.new('mesh'); mesh.from_pydata([(0,0,0),(1,0,0),(0,0,1),(1,0,1)], [], [(0,1,3),(0,3,2)]); mesh.update()
        obj = bpy.data.objects.new('body',mesh); bpy.context.collection.objects.link(obj)
        arm = bpy.data.armatures.new('arm'); rig = bpy.data.objects.new('rig',arm); bpy.context.collection.objects.link(rig)
        bpy.context.view_layer.objects.active = rig; rig.select_set(True); bpy.ops.object.mode_set(mode='EDIT')
        root = arm.edit_bones.new('root'); root.head=(0,0,0); root.tail=(0,0,1)
        child = arm.edit_bones.new('child'); child.head=(0,0,1); child.tail=(0,0,2); child.parent=root
        bpy.ops.object.mode_set(mode='OBJECT')
        group = obj.vertex_groups.new(name='child'); group.add([2,3],1,'REPLACE')
        group = obj.vertex_groups.new(name='root'); group.add([0,1],1,'REPLACE')
        mod = obj.modifiers.new('armature','ARMATURE'); mod.object=rig
        deps = bpy.context.evaluated_depsgraph_get(); rig.data.pose_position='REST'; bpy.context.view_layer.update()
        rest, tris = mesh_data(obj,deps)
        rig.data.pose_position='POSE'; rig.pose.bones['child'].rotation_mode='QUATERNION'; rig.pose.bones['child'].rotation_quaternion=(math.cos(.5),math.sin(.5),0,0); bpy.context.view_layer.update()
        good = strain(rest,mesh_data(obj,deps)[0],tris)['p99']
        bpy.context.view_layer.objects.active = rig; bpy.ops.object.mode_set(mode='EDIT'); arm.edit_bones['child'].head=(0,0,3); arm.edit_bones['child'].tail=(0,0,4); bpy.ops.object.mode_set(mode='OBJECT'); bpy.context.view_layer.update()
        bad = strain(rest,mesh_data(obj,deps)[0],tris)['p99']
        self.assertGreater(bad,good)
        self.assertEqual(antipodal_pairs([[1,0,0,0],[-1,0,0,0]]),1)
        self.assertEqual(quaternion_error([1,0,0,0],[-1,0,0,0]),0)

    def test_hair_inside_and_open_body(self):
        vertices = [[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]]
        tris = [[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]]
        self.assertEqual(hair_clearance(vertices,tris,[[0,0,0],[2,0,0]])['hair_penetrating_vertices'],1)
        self.assertIsNone(hair_clearance(vertices,tris[:-1],[[0,0,0]]))

if __name__ == '__main__': unittest.main()
