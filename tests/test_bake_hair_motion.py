import unittest
import numpy as np
from tools.bake_hair_motion import simulate_chain, shape_quaternion, assert_non_hair_channels_unchanged


class BakeTests(unittest.TestCase):
    def test_spring_constraints(self):
        rest = np.array([[0,0,0],[0,0,-1],[0,0,-2]],float)
        targets = np.stack([rest,rest+[.2,0,0],rest+[.4,0,0]])
        out = simulate_chain(targets,.1,2,1,.5,8)
        np.testing.assert_allclose(out[:,0],targets[:,0])
        np.testing.assert_allclose(np.linalg.norm(np.diff(out,axis=1),axis=2),1,atol=1e-6)
        with self.assertRaises(ValueError): simulate_chain(targets,.1,2,1,.5,1)

    def test_quaternion_cap(self):
        q = shape_quaternion([np.cos(.5),0,0,np.sin(.5)],.5,.1)
        angle = 2*np.arccos(q[0])
        self.assertLess(angle,.1)
        np.testing.assert_array_equal(shape_quaternion([1,1e-8,0,0],1,.1),[1,0,0,0])

    def test_channels(self):
        a = {'head':[1,2], 'hair':[1]}; b = {'head':[1,2], 'hair':[2]}
        self.assertTrue(assert_non_hair_channels_unchanged(a,b,{'hair'}))
        with self.assertRaises(ValueError): assert_non_hair_channels_unchanged(a,{'head':[2,2]}, {'hair'})
        with self.assertRaises(ValueError): assert_non_hair_channels_unchanged(None,b,{'hair'})
