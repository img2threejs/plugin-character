import unittest
import numpy as np
from tools.head_transplant import fit_similarity, clip_polygon_plane, boundary_rings, bridge_rings, cheek_masks


class HeadTests(unittest.TestCase):
    def test_fit(self):
        m = fit_similarity(8, .2, 3, -.1)
        self.assertAlmostEqual((m @ [0,0,8,1])[2],3)
        self.assertAlmostEqual((m @ [0,0,8,1])[1],-.1)
        with self.assertRaises(ValueError): fit_similarity(1,0,1,0)

    def test_clip_interpolation(self):
        p = {'position': [[0,0,-1],[1,0,-1],[1,0,1],[0,0,1]], 'uv': [[0,0],[1,0],[1,1],[0,1]], 'weights': [[1,0],[1,0],[0,1],[0,1]], 'normal': [[0,0,1]]*4}
        out = clip_polygon_plane(p,0,'above')
        self.assertEqual(len(out['position']),4)
        cut = out['position'][:,2] == 0
        np.testing.assert_allclose(out['uv'][cut,1],.5)
        np.testing.assert_allclose(out['weights'][cut],[[.5,.5],[.5,.5]])
        self.assertEqual(len(clip_polygon_plane(p,2,'above')['position']),0)
        on_plane = {'position': [[0,0,0],[1,0,-1],[1,0,1]]}
        clipped = clip_polygon_plane(on_plane,0,'above')['position']
        self.assertEqual(len(clipped),3)
        self.assertEqual(len(np.unique(clipped,axis=0)),3)

    def test_rings_and_bridge(self):
        a = np.array([[1,0,0],[0,1,0],[-1,0,0],[0,-1,0]])
        rings = boundary_rings([a],1e-6)
        self.assertEqual(len(rings),1)
        v,t,r = bridge_rings(a,a+[0,0,1],.01)
        self.assertEqual((len(t),r['open_edges'],r['nonmanifold_edges']),(8,0,0))
        _,_,r = bridge_rings(a,(a+[.2,0,1])[:3],.01)
        self.assertTrue(r['count_mismatch']); self.assertGreater(r['centre_offset'],0)
        _,_,r = bridge_rings(a,a+[0,0,5e-7],.01)
        self.assertGreater(r['degenerate_edges'],0)
        self.assertGreater(r['nonmanifold_edges'],0)
        with self.assertRaises(ValueError): boundary_rings([],1e-6)

    def test_cheeks_and_counterexample(self):
        calibration = {'center_x_over_eye':1, 'center_z_offset_over_span':.5, 'radii_over_landmarks':[.5,.5,.5], 'medial_x_over_eye':.5, 'iris_clearance':.1}
        left = np.array([[.5 + .01*i, 0, .8] for i in range(8)])
        right = left.copy(); right[:,0] *= -1
        p = np.vstack([left,right])
        m = cheek_masks(.5,1,1,.4,p,np.ones(len(p),bool),calibration=calibration)
        self.assertEqual(np.count_nonzero(m['left']),8)
        with self.assertRaises(ValueError): cheek_masks(.5,1,1,.4,np.vstack([left[:7],right]),np.ones(15,bool),calibration=calibration)
        with self.assertRaises(ValueError): cheek_masks(.5,1,1,.4,p,calibration=calibration)
        with self.assertRaises(ValueError): cheek_masks(.5,1,1,.4,p,np.ones(len(p),bool),calibration={})
