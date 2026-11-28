import copy
import json
from pathlib import Path
import unittest

import numpy as np

from tools import body_parts as b


class MaskTests(unittest.TestCase):
    def test_ellipsoid_points(self):
        args = ([0, 0, 0], [1, 1, 1])
        self.assertEqual(b.ellipsoid_mask_weight([0, 0, 0], *args, convert='none'), 1)
        self.assertAlmostEqual(b.ellipsoid_mask_weight([0.5, 0, 0], *args, convert='none'), 0.896484375)
        self.assertEqual(b.ellipsoid_mask_weight([1, 0, 0], *args, convert='none'), 0)
        self.assertEqual(b.ellipsoid_mask_weight([2, 0, 0], *args, convert='none'), 0)

    def test_conversion_and_exclusion(self):
        self.assertEqual(b.ellipsoid_mask_weight([1, -3, 2], [1, 2, 3], [1, 1, 1]), 1)
        self.assertEqual(b.ellipsoid_mask_weight([1, -3, 2], [1, 2, 3], [1, 1, 1], convert='none'), 0)
        self.assertEqual(b.ellipsoid_mask_weight([1, -3, 2], [1, 2, 3], [1, 1, 1], exclude=lambda p: p[2] > 2), 0)

    def test_invalid_geometry_counterexamples(self):
        for radii in ([0, 1, 1], [-1, 1, 1], [float('nan'), 1, 1]):
            with self.subTest(radii=radii), self.assertRaises(ValueError):
                b.ellipsoid_mask_weight([0, 0, 0], [0, 0, 0], radii)
        with self.assertRaises(ValueError):
            b.ellipsoid_mask_weight([float('inf'), 0, 0], [0, 0, 0], [1, 1, 1])
        with self.assertRaises(ValueError):
            b.ellipsoid_mask_weight([0, 0, 0], [0, 0, 0], [1, 1, 1], convert='unknown')

    def test_normalize_and_counterexamples(self):
        np.testing.assert_allclose(b.normalize_masks([0.8, 0.8]), [0.5, 0.5])
        np.testing.assert_allclose(b.normalize_masks([0.1, 0.2]), [0.1, 0.2])
        for values in ([], [1, -1], [float('nan')]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                b.normalize_masks(values)


class SymmetryTests(unittest.TestCase):
    def test_permutation_and_divergence(self):
        a = [{'L': 0.8, 'C': 0.2}]
        mapping = {'L': 'R', 'C': 'C'}
        result = b.mirrored_weight_symmetry(a, [{'R': 0.8, 'C': 0.2}], [(0, 0)], mapping)
        self.assertTrue(result['measured'])
        self.assertEqual(result['max_difference'], 0)
        result = b.mirrored_weight_symmetry(a, [{'R': 0.2, 'C': 0.8}], [(0, 0)], mapping)
        self.assertAlmostEqual(result['max_difference'], 0.6)
        swapped = b.mirrored_weight_symmetry(a, [{'R': 0.8, 'C': 0.2}], [(0, 0)], {'L': 'C', 'C': 'R'})
        self.assertAlmostEqual(swapped['max_difference'], 0.6)

    def test_unmatched_ambiguous_and_invalid(self):
        rows = [{'L': 1}, {'L': 1}]
        result = b.mirrored_weight_symmetry(rows, [{'R': 1}], [(0, 0)], {'L': 'R'})
        self.assertIn((1, None), result['unmatched'])
        self.assertFalse(result['measured'])
        result = b.mirrored_weight_symmetry([{'L': 1}], [{'R': 1}], [(0, 0)], {'other': 'R'})
        self.assertEqual(result['unmatched'], [(0, 0)])
        self.assertIsNone(result['max_difference'])
        result = b.mirrored_weight_symmetry(rows, [{'R': 1}], [(0, 0), (1, 0)], {'L': 'R'})
        self.assertEqual(len(result['ambiguous']), 2)
        with self.assertRaises(ValueError):
            b.mirrored_weight_symmetry([{'L': 0.2}], [{'R': 1}], [(0, 0)], {'L': 'R'})
        with self.assertRaises(ValueError):
            b.mirrored_weight_symmetry([], [{'R': 1}], [], {'L': 'R'})


class HeightTests(unittest.TestCase):
    def test_scale_and_bad_height(self):
        self.assertEqual(b.height_fraction(0.5, 2), b.height_fraction(5, 20))
        for height in (0, -1, float('inf'), float('nan')):
            with self.subTest(height=height), self.assertRaises(ValueError):
                b.height_fraction(1, height)
        with self.assertRaises(ValueError):
            b.height_fraction(float('nan'), 1)


class CatalogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / 'reference/body-parts.json'
        cls.doc = json.loads(path.read_text())

    def asset(self, doc):
        return doc['characters'][0]['assets'][0]

    def test_shipped_catalogue(self):
        self.assertTrue(b.validate_catalogue(self.doc))

    def test_duplicate_and_dangling_counterexamples(self):
        doc = copy.deepcopy(self.doc)
        self.asset(doc)['parts'].append(copy.deepcopy(self.asset(doc)['parts'][0]))
        with self.assertRaises(ValueError): b.validate_catalogue(doc)
        for field in ('bones', 'meshes'):
            doc = copy.deepcopy(self.doc)
            self.asset(doc)['parts'][0][field].append('missing')
            with self.subTest(field=field), self.assertRaises(ValueError): b.validate_catalogue(doc)

    def test_invalid_metadata_counterexamples(self):
        for kind in ('side', 'unit', 'tag', 'citation', 'stage', 'region'):
            doc = copy.deepcopy(self.doc)
            asset = self.asset(doc)
            if kind == 'side': asset['parts'][0]['side'] = 'up'
            elif kind == 'unit': asset['measurements'][0]['unit'] = 'lightyear'
            elif kind == 'tag': asset['measurements'][0]['tag'] = 'verified'
            elif kind == 'citation': asset['measurements'][0]['source'] = 'unknown'
            elif kind == 'stage': doc['characters'][0]['assets'].append(copy.deepcopy(asset))
            else: asset['parts'][0]['id'] = 'chest-left'
            with self.subTest(kind=kind), self.assertRaises(ValueError): b.validate_catalogue(doc)

    def test_mask_and_absent_profile_counterexamples(self):
        # A caller-owned mask is independent of the default primitive catalogue.
        def meas(value):
            return {'value': value, 'unit': 'm', 'frame': 'glTF XYZ', 'method': 'synthetic', 'evidenceClass': 'authored',
                    'source': 'synthetic-fixture:1', 'limitations': 'test fixture', 'tag': 'behaviour'}
        doc = copy.deepcopy(self.doc)
        self.asset(doc)['masks'] = [{'id': 'abdomen', 'bone': 'BoardAnchor', 'centre': meas([0, 1, 0]), 'radii': meas([0.1, 0.1, 0.1])}]
        self.assertTrue(b.validate_catalogue(doc))
        self.asset(doc)['masks'][0]['radii']['value'][0] = 0
        with self.assertRaises(ValueError): b.validate_catalogue(doc)
        doc = copy.deepcopy(self.doc)
        fields = {name: {'status': 'present', 'measurement': meas(1)} for name in ('frequency','dampingRatio','cap','compression')}
        fields['pressDepth'] = {'status': 'absent'}
        self.asset(doc)['profiles'] = [{'id': 'waist', 'fields': fields}]
        self.assertTrue(b.validate_catalogue(doc))
        fields['pressDepth']['value'] = 0
        with self.assertRaises(ValueError): b.validate_catalogue(doc)
        fields['pressDepth'] = {'status': 'present', 'measurement': meas(0)}
        with self.assertRaises(ValueError): b.validate_catalogue(doc)


if __name__ == '__main__':
    unittest.main()
