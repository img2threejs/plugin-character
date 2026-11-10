import unittest
import numpy as np
from tools import skin_authoring as sa


class SkinAuthoring(unittest.TestCase):
    def test_pixel_lstar_is_not_rgb_mean_lstar(self):
        patch = np.array([[[.1,.1,.1],[.2,.2,.2],[.9,.9,.9]]])
        target = sa.region_tone_targets({'face':patch}, min_pixels=3)['face']
        self.assertNotAlmostEqual(target['lstar'], float(sa._lstar(patch.mean(axis=(0,1)))))

    def test_patch_rejections(self):
        for patch in (np.empty((0,3)), np.ones((2,3)), np.zeros((2,3)), np.full((1,3), .5)):
            with self.assertRaises(ValueError): sa.region_tone_targets({'face':patch}, min_pixels=2)
        with self.assertRaises(ValueError): sa.region_tone_targets({'chest':np.full((2,3), .5)}, min_pixels=2)

    def test_feather_ownership_and_unrelated_island(self):
        image = np.full((2,6,3), .1); a = np.zeros((2,6), bool); b = a.copy(); c = a.copy()
        a[:,0:2] = True; b[:,2:4] = True; c[:,5] = True
        owner = np.array([[1,1,1,1,0,2]]*2); band = a | b
        targets = {'face':{'rgb':[.2]*3}, 'neck':{'rgb':[.8]*3}, 'arm':{'rgb':[.4]*3}}
        result, receipt = sa.author_region_base(image, {'face':a,'neck':b,'arm':c}, targets, feather_px=2, ownership={'islands':owner, 'transitions':[{'regions':['face','neck'], 'islands':[1], 'mask':band, 'adjacent_3d':True}]})
        self.assertEqual(receipt['changed_outside_declared_support'], 0)
        np.testing.assert_allclose(result[:,4], .1); np.testing.assert_allclose(result[:,5], .4)
        self.assertGreater(result[0,1,0], .2); self.assertLess(result[0,2,0], .8)
        with self.assertRaises(ValueError): sa.author_region_base(image, {'face':a,'neck':b,'arm':c}, targets, feather_px=2, ownership={'islands':owner, 'transitions':[{'regions':['face','neck'], 'islands':[1], 'mask':c, 'adjacent_3d':True}]})

    def test_mirror_counterexample(self):
        rgb = np.array([[[.2]*3,[.8]*3]])
        pairs = [((0,0),(0,1))]
        self.assertAlmostEqual(sa.mirror_residual(rgb,pairs), .6)
        corrected, report = sa.enforce_mirror_consistency(rgb,pairs,tolerance=.01)
        self.assertEqual(report['residual'], 0); self.assertAlmostEqual(corrected[0,1,0], .2)
        with self.assertRaises(ValueError): sa.enforce_mirror_consistency(rgb,pairs*2,tolerance=.01)

    def test_padding_bounded_and_no_crossing(self):
        rgb = np.zeros((1,7,3)); rgb[0,0] = .2; rgb[0,6] = .8
        owner = np.array([[1,0,0,0,0,0,2]])
        result, info = sa.pad_islands(rgb,owner,3)
        self.assertEqual(info['ownership'][0,3], 0)
        self.assertAlmostEqual(result[0,1,0], .2); self.assertAlmostEqual(result[0,5,0], .8)
        self.assertEqual(sa.pad_islands(rgb,np.array([[1,-1,0,0,0,0,0]]),1)[0][0,6,0], .8)
        self.assertEqual(sa.seam_padding_report(result,owner,3)['min_px'], 2)
        broken = result.copy(); broken[0,1] = .6
        self.assertEqual(sa.seam_padding_report(broken,owner,3)['min_px'], 0)

    def test_density_weighted_ratio_and_invalid(self):
        d = sa.texel_density([16,9,4],[1,1,1],['face','face','body'])
        self.assertAlmostEqual(d['face_body_ratio'], np.sqrt(12.5)/2)
        with self.assertRaises(ValueError): sa.texel_density([1],[0],['face'])

    def test_uniformity_detects_outlier(self):
        rgb = np.array([[[.2]*3,[.2]*3,[.8]*3]])
        r = sa.region_uniformity(rgb, {'face':np.ones((1,3),bool)})['face']
        self.assertGreater(r['rgb_distance'][-1], .9); self.assertGreater(r['lstar_spread'], 0)
