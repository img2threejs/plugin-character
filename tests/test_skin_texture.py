import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np
from tools import skin_texture as s


class SkinTextureTests(unittest.TestCase):
    def test_rasterization_shared_degenerate_and_boundary(self):
        positions = np.array([[0,0,0], [1,0,0], [0,1,2], [0,0,3], [1,0,3], [0,1,3]])
        triangles = np.array([[0,1,2], [3,4,5], [0,1,2], [0,1,2]])
        uv = np.array([[[0,0],[1,0],[0,1]], [[0,0],[1,0],[0,1]],
                       [[0,0],[0,0],[0,0]], [[2,2],[3,2],[2,3]]], float)
        predicates = {'lower': lambda p: p[:,2].mean() < 1, 'upper': lambda p: p[:,2].mean() >= 1}
        masks, report = s.rasterize_regions(positions, triangles, uv, (8,8), predicates)
        self.assertGreater(report['shared_texels'], 0)
        self.assertEqual(report['degenerate_triangles'], 1)
        self.assertEqual(report['off_image_triangles'], 1)
        self.assertFalse(masks['lower'].any())
        self.assertIn('upper', report['empty'])
        with self.assertRaises(ValueError):
            s.rasterize_regions(positions, triangles, uv, (8,8), predicates, overlap_policy='error')
        one, _ = s.rasterize_regions(positions, triangles[:1], uv[:1], (8,8), {'lower': predicates['lower']})
        bottom, _ = s.rasterize_regions(positions, triangles[:1], uv[:1], (8,8), {'lower': predicates['lower']}, origin='bottom-up')
        np.testing.assert_array_equal(one['lower'], bottom['lower'][::-1])
        self.assertTrue(one['lower'].any())
        same, same_report = s.rasterize_regions(positions, triangles[:2], uv[:2], (8,8), {'all': lambda p: True})
        self.assertGreater(same_report['shared_texels'], 0)
        self.assertFalse(same['all'].any())

    def test_tone_spaces_and_empty(self):
        image = np.array([[[.1,.1,.1], [.5,.5,.5], [.9,.9,.9]]])
        mask = np.ones((1,3), bool)
        encoded = s.measure_tone(image, mask)['value'][0]
        linear = s.measure_tone(image, mask, statistic='mean', color_space='linear')['value'][0]
        self.assertNotAlmostEqual(encoded, linear)
        self.assertEqual(s.measure_tone(image, mask, luminance_gate=.3)['count'], 1)
        self.assertEqual(s.measure_tone(image, mask, color_space='linear', luminance_gate=.3)['count'], 2)
        with self.assertRaises(ValueError): s.measure_tone(image, ~mask)
        with self.assertRaises(ValueError): s.measure_tone(image, mask, luminance_gate=.01)
        bad = image.copy(); bad[0,0,0] = np.nan
        with self.assertRaises(ValueError): s.measure_tone(bad, mask)

    def test_fill_no_wrap_or_protected_leak(self):
        image = np.zeros((5,7,3), np.uint8); image[4,6] = [200,150,100]
        island = np.zeros((5,7), bool); island[2,0] = True
        sample = np.zeros_like(island); sample[4,6] = True
        protected = np.zeros_like(island); protected[:,2] = True
        result, receipt = s.fill_skin_island(image, island, sample, dilation=4, protected_mask=protected)
        self.assertTrue(receipt['support'][2,1])
        self.assertFalse(receipt['support'][2,6])
        self.assertFalse(receipt['support'][:,2:].any())
        np.testing.assert_array_equal(result[~receipt['support']], image[~receipt['support']])
        with self.assertRaises(ValueError): s.fill_skin_island(image, island, ~sample & False, dilation=1)
        with self.assertRaises(ValueError): s.fill_skin_island(image, island, sample, dilation=1, protected_mask=island)

    def test_shadow_support_and_dark_free(self):
        image = np.ones((21,21,3), float)*.95
        image[10,10] = [.3,.3,.3]; image[10,11] = [.6,.6,.6]
        neck = np.zeros((21,21), bool); neck[10,10] = True
        ref = np.zeros_like(neck); ref[0,0] = True
        params = {'dark_luminance': .5, 'dilation': 1, 'blur_iterations': 2, 'strength': .5, 'darkness_gate': [.4,.7]}
        result, receipt = s.lift_shadow(image, neck, ref, params)
        self.assertGreater(result[10,10,0], image[10,10,0])
        self.assertEqual(result[10,9,0], image[10,9,0])
        np.testing.assert_array_equal(result[~receipt['support']], image[~receipt['support']])
        with self.assertRaises(ValueError): s.lift_shadow(image, ref, ref, params)
        with self.assertRaises(ValueError): s.lift_shadow(image, neck, np.zeros_like(ref), params)
        with self.assertRaises(ValueError): s.lift_shadow(image, neck, ref, {})

    def test_root_original_selection_and_bounded_edges(self):
        original = np.ones((4,6,3), float)*.7
        original[1,0] = [.9,.4,.1]; original[1,5] = [.2,.2,.2]
        image = original.copy(); image[1,0] = [.05,.05,.05]
        nearby = np.ones((4,6), bool); nearby[1,0] = False
        recipe = {'boxes': [(0,0,6,4)], 'saturation_ranges': [(.4,.65)], 'nearby_mask': nearby}
        result, report = s.repair_root_paint(image, original, np.ones((4,6)), recipe, iterations=20)
        self.assertEqual(report['selected_pixels'], 1)
        self.assertGreater(result[1,0,0], image[1,0,0])
        np.testing.assert_array_equal(result[:,5], image[:,5])
        with self.assertRaises(ValueError): s.repair_root_paint(image, original, np.zeros((4,6)), recipe, iterations=20)

    def test_color_line_and_counterexample(self):
        image = np.tile(np.array([60,90,120], np.uint8), (16,16,1))
        gate = {'residual': .02, 'residual_fade': .01, 'u_feather': (.05,.05), 'v_feather': (.05,.05)}
        result = s.repair_color_line(image, [60,90,120], [90,120,150], (.25,.25,.75,.75), gate)
        self.assertGreater(result['changed_pixels'], 0)
        np.testing.assert_array_equal(result['image'][~result['mask']], image[~result['mask']])
        with self.assertRaises(ValueError): s.repair_color_line(image, [60,90,120], [60,90,120], (.25,.25,.75,.75), gate)

    def test_iris_counts_and_domain(self):
        image = np.array([[[.1,.7,.9], [1,1,1], [0,0,0], [.4,.1,.9]]])
        thresholds = {'saturation': .3, 'maximum': .1, 'blue_ratio': 1.2, 'green_ratio': 1.2}
        result, counts = s.recolor_iris(image, 30, thresholds=thresholds)
        self.assertEqual((counts['changed'], counts['protected']), (1,3))
        np.testing.assert_array_equal(result[0,1:], image[0,1:])
        _, covered = s.recolor_iris(image, 30, thresholds=thresholds, coverage=np.array([[False,True,True,True]]))
        self.assertEqual((covered['pigment'], covered['protected']), (0,3))
        with self.assertRaises(ValueError): s.recolor_iris(image, 61, thresholds=thresholds)

    def test_detail_highlights_and_boxes(self):
        image = np.array([[[1.,1.,1.], [.2,.1,.1], [.8,.7,.6], [.3,.2,.1]]])
        palette = {'background': [.7,.7,.7], 'iris_dark': [0,0,.2], 'iris_bright': [.2,.5,1], 'brow_dark': [.1,.1,.1], 'crease_multiply': .5,
                   'background_distance': .2, 'highlight_luminance': .9, 'highlight_saturation': .1, 'iris_curve': [.05,.6,1], 'brow_gain': [.1,.1,.1]}
        result, counts = s.recolor_details(image, {'iris': (0,0,2,1), 'brow': (2,0,3,1), 'crease': (3,0,4,1)}, {}, palette)
        self.assertEqual(counts['iris']['protected'], 1)
        self.assertEqual(counts['brow']['selected'], 0)
        np.testing.assert_array_equal(result[0,0], image[0,0])
        self.assertFalse(np.array_equal(result[0,3], image[0,3]))
        with self.assertRaises(ValueError): s.recolor_details(image, {'iris': (0,0,9,1)}, {}, palette)

    def test_composite_and_layout_counterexamples(self):
        body = np.arange(8*16*3, dtype=np.uint8).reshape(8,16,3)
        face = np.full((8,8,3), 25, np.uint8); neck = np.full((8,8,3), 200, np.uint8)
        low = np.zeros((16,3), np.uint8); high = np.full((16,3), 255, np.uint8)
        atlas, uv, report = s.build_composite(body, face, neck, (low, high))
        np.testing.assert_array_equal(atlas[:8], body)
        self.assertEqual(atlas.shape, (18,16,3))
        self.assertGreater(atlas[17,0,0], 128)
        _, uv2, _ = s.build_composite(np.zeros((16,32,3), np.uint8), np.zeros((16,16,3), np.uint8), np.zeros((16,16,3), np.uint8), (np.zeros((32,3), np.uint8), np.full((32,3),255,np.uint8)))
        np.testing.assert_allclose(uv['face']([[.4,.5]]), uv2['face']([[.4,.5]]))
        with self.assertRaises(ValueError): s.build_composite(body, face[:3], neck, (low, high))
        rgba = np.full((8,8,4), 255, np.uint8); rgba[0,0,3] = 0
        with self.assertRaises(ValueError): s.build_composite(body, rgba, neck, (low, high))

    @unittest.skipUnless(importlib.util.find_spec('PIL'), 'Pillow is required to write the PNG (the NumPy cores do not need it)')
    def test_save_and_stale_packed_bytes(self):
        image = np.zeros((2,3,3), np.uint8)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'atlas.png'
            receipt = s.save_pack_verify(image, path)
            self.assertTrue(receipt['pixel_equal'])
            self.assertIn(b'sRGB', path.read_bytes())
            with self.assertRaises(ValueError): s.save_pack_verify(image, path, packed_bytes=b'stale')
            with self.assertRaises(ValueError): s.save_pack_verify(np.zeros((2,3,4), np.uint8), path)

    def test_material_missing_maps_and_no_sss_claim(self):
        params = {'metallic': 0, 'roughness': .6, 'ior': 1.5, 'subsurface_weight': .1, 'subsurface_radius': (1,.5,.25), 'subsurface_scale': .01, 'detail_roughness': .4, 'base_color_map': True, 'normal_map': True, 'roughness_map': True}
        spec = s.skin_material_spec(params)
        export = {'metallic': 0, 'roughness': .6, 'base_color_map': True, 'base_color_space': 'sRGB'}
        report = s.validate_skin_material(spec, export)
        self.assertFalse(report['ok'])
        self.assertIn('missing normal_map', report['failures'])
        self.assertIn('missing roughness_map', report['failures'])
        self.assertEqual(report['native_scattering'], 'not exported')
        export.update(normal_map=True, roughness_map=True, normal_map_color_space='linear', roughness_map_color_space='linear')
        self.assertTrue(s.validate_skin_material(spec, export)['ok'])
        with self.assertRaises(ValueError): s.skin_material_spec({})

    def test_tone_report_counterexample(self):
        a = np.full((1,4,3), .5); a[0,0] = .7
        b = np.full_like(a, .6); mask = np.ones((1,4), bool)
        report = s.tone_match_report(a, b, {'leg': mask}, deviation_limit=.1)['leg']
        self.assertEqual(report['before_deviation_count'], 1)
        self.assertEqual(report['after_deviation_count'], 0)
        with self.assertRaises(ValueError): s.tone_match_report(a,b,{'leg': ~mask},deviation_limit=.1)


if __name__ == '__main__':
    unittest.main()
