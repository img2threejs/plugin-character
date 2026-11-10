import unittest
import numpy as np
from tools import atlas_surface as a


class AtlasTests(unittest.TestCase):
    def test_layout_and_original_pixels(self):
        body = np.arange(8 * 16 * 3, dtype=np.uint8).reshape(8, 16, 3)
        donor = np.full((8, 8, 3), 42, np.uint8)
        result = a.composite_atlas(body, donor, donor)
        np.testing.assert_array_equal(result['atlas'][:8], body)
        layout = result['layout']
        np.testing.assert_allclose(layout.body_uv([[1, 1]]), [[1, 4/9]])
        np.testing.assert_allclose(layout.face_uv([[1, 1]]), [[.5, 8/9]])
        np.testing.assert_allclose(layout.neck_uv([[0, 0]]), [[.5, 4/9]])
        with self.assertRaises(ValueError): a.composite_atlas_layout(15)
        with self.assertRaises(ValueError): a.composite_atlas_layout(16, (7, 16))

    def test_bridge_endpoints_and_strip(self):
        x = a.bridge_v_endpoints(2048)
        y = a.bridge_v_endpoints(4096)
        self.assertEqual((x['v_bottom'], x['v_top']), (y['v_bottom'], y['v_top']))
        low = np.tile([12, 24, 36], (2048, 1)).astype(np.uint8)
        up = np.tile([128, 180, 220], (2048, 1)).astype(np.uint8)
        strip = a.neck_strip(low, up, 2048, 256, 1)
        np.testing.assert_array_equal(strip[0], low)
        np.testing.assert_array_equal(strip[-1], up)
        np.testing.assert_array_equal(np.rint(a.linear_to_srgb(a.srgb_to_linear(low))*255).astype(np.uint8), low)

    def test_uv_ring_sampling(self):
        image = np.array([[[0, 0, 0], [200, 100, 40]]], dtype=np.uint8)
        ring = {'rel': [0, 2*np.pi], 'uva': [[.75, .5]], 'uvb': [[.75, .5]], 'atlas': image}
        strip = a.neck_strip(ring, ring, 2048, 16)
        np.testing.assert_array_equal(strip[0, 0], [200, 100, 40])

    def test_repair_and_counterexample(self):
        original = np.tile(np.array([60, 90, 120], np.uint8), (16, 16, 1))
        gate = {'residual': .02, 'residual_fade': .01, 'u_feather': (.05,.05), 'v_feather': (.05,.05)}
        result = a.color_line_repair(original, [60,90,120], [90,120,150], (.25,.25,.75,.75), gate)
        self.assertGreater(result['changed_pixels'], 0)
        np.testing.assert_array_equal(result['image'][~result['mask']], original[~result['mask']])
        bad = result['image'].copy(); bad[0, 0, 0] += 1
        with self.assertRaises(ValueError): a.assert_zero_change_outside_mask(original, bad, result['mask'])
        with self.assertRaises(ValueError): a.color_line_repair(original, [60,90,120], [90,120,150], (.25,.25,.75,.75))


if __name__ == '__main__': unittest.main()
