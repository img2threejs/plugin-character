import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STANDARDS = json.loads((ROOT / 'reference/skin-body-standards.json').read_text())
GATE = ROOT / 'tools/gate_skin_body.py'


def passing_evidence():
    measurements = {}
    declared = {'hair_declared': True, 'limits': {}, 'references': {}}
    for stage in STANDARDS['stages']:
        for check in stage['checks']:
            threshold = check['threshold']
            if check['metric'] == 'mask_region_ids': value = ['abdomen']
            elif check['metric'] == 'source_hash': value = {'source': {'path': 'fixture', 'actual': 'a' * 64, 'expected': 'a' * 64, 'matches': True}}
            elif check['metric'] == 'mirror_mapping': value = {'pairs': [[0, 1]], 'permutation': {'L': 'R'}}
            elif check['comparator'] == 'exists': value = 1 if check['unit'] in ('bones', 'edges', 'triangles', 'scalar') else 'observed'
            elif check['comparator'] == 'declared-max':
                value = 0
                declared['limits'][check['metric']] = {'value': 0.05, 'source': 'fixture project limit'}
            elif check['comparator'] == 'reference-within':
                value = 24
                declared['references'][check['metric']] = {'value': 24, 'tolerance': .5, 'source': 'fixture declared hair rig'}
            else: value = threshold
            measurements[check['metric']] = {'value': value, 'unit': check['unit'], 'method': 'fixture', 'source': 'fixture'}
    return {'schema': 'skin-body-evidence/1', 'subject': 'fixture', 'declared': declared, 'measurements': measurements}


class GateTests(unittest.TestCase):
    def run_gate(self, evidence, stages=None, options=None):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'evidence.json'
            path.write_text(json.dumps(evidence))
            command = [sys.executable, str(GATE), '--evidence', str(path), '--json']
            command += options if options is not None else ['--standards', str(ROOT / 'reference/skin-body-standards.json')]
            for stage in stages or []: command += ['--stage', stage]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            return result.returncode, json.loads(result.stdout)

    def test_all_pass_and_stage_filter(self):
        code, verdict = self.run_gate(passing_evidence())
        self.assertEqual((code, verdict['status']), (0, 'pass'))
        self.assertEqual(verdict['kind'], 'img2.gate-verdict')
        self.assertEqual(self.run_gate(passing_evidence(), ['S2'])[0], 0)

    def test_counterexamples_every_stage(self):
        cases = [('original_changed_bytes', 1), ('original_body_changed_pixels', 1), ('nonopaque_pixels', 1),
                 ('image_bit_depth', 16), ('atlas_color_space', 'Linear'), ('atlas_layout_error', 1),
                 ('changed_outside_repair_mask', 1), ('island_tone_deviation', .2), ('uv_max_error', .01),
                 ('normalized_uv_max_error', .01), ('join_open_edges', 1), ('join_nonmanifold_edges', 1),
                 ('face_max_position_error', .01), ('missing_bone_groups', 1), ('hair_chain_bones', 23),
                 ('weight_sum_max_error', .1), ('weight_max_influences', 5), ('weight_small_count', 1),
                 ('mirror_max_difference', .1), ('mirror_unmatched_count', 1),
                 ('mask_region_ids', ['chest-left']), ('mask_min', -.1), ('mask_max', 1.1),
                 ('mask_max_sum', 1.1), ('material_base_color_space', 'Linear'),
                 ('export_position_error', .1), ('export_uv_error', .1), ('export_weight_error', .1),
                 ('export_changed_pixels', 1)]
        for metric, value in cases:
            with self.subTest(metric=metric):
                evidence = passing_evidence()
                evidence['measurements'][metric]['value'] = value
                code, verdict = self.run_gate(evidence)
                self.assertEqual(code, 1)
                self.assertTrue(any(c['name'] == metric and c['verdict'] == 'fail' for c in verdict['evidence']['checks']))
                if metric == 'mask_region_ids': self.assertIn('chest-left', str(verdict))

    def test_missing_nan_wrong_type_and_unit_unmeasured(self):
        for mode in ('missing', 'nan', 'wrong-type', 'unit'):
            evidence = passing_evidence()
            item = evidence['measurements']['weight_sum_max_error']
            if mode == 'missing': del evidence['measurements']['weight_sum_max_error']
            elif mode == 'nan': item['value'] = float('nan')
            elif mode == 'wrong-type': item['value'] = True
            else: item['unit'] = 'm'
            with self.subTest(mode=mode): self.assertEqual(self.run_gate(evidence)[0], 2)

    def test_every_missing_receipt_is_unmeasured(self):
        for stage in STANDARDS['stages']:
            for check in stage['checks']:
                with self.subTest(metric=check['metric']):
                    evidence = passing_evidence()
                    del evidence['measurements'][check['metric']]
                    code, verdict = self.run_gate(evidence, [stage['id']])
                    # An advisory check that is unmeasured is still reported, but never makes the gate exit 2.
                    self.assertEqual(code, 0 if check.get('severity') == 'advisory' else 2)
                    self.assertTrue(any(c['id'] == check['id'] and c['verdict'] == 'unmeasured' for c in verdict['evidence']['checks']))


    def test_single_subject_limits_must_be_declared(self):
        # Painted-tone and export tolerances require the caller's declaration.
        for metric in ('island_tone_deviation', 'export_uv_error'):
            with self.subTest(metric=metric):
                evidence = passing_evidence()
                del evidence['declared']['limits'][metric]
                code, verdict = self.run_gate(evidence)
                self.assertEqual(code, 2)
                self.assertTrue(any(c['name'] == metric and c['verdict'] == 'unmeasured' for c in verdict['evidence']['checks']))

    def test_unmeasured_export_never_passes(self):
        evidence = passing_evidence()
        evidence['measurements']['export_maps_and_sss']['value'] = 'unmeasured-by-export'
        self.assertEqual(self.run_gate(evidence, ['S7'])[0], 2)

    def test_reference_relative_comparators(self):
        """Exercise boundaries, missing declarations, and unusable tolerances."""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'standards.json'
            check = {'id': 'relative', 'stage': 'S1', 'metric': 'metric',
                     'unit': 'scalar', 'comparator': 'reference-within'}
            path.write_text(json.dumps({'schema': 'skin-body-standards/1',
                                        'stages': [{'id': 'S1', 'checks': [check]}]}))
            evidence = {'schema': 'skin-body-evidence/1', 'subject': 'fixture',
                        'declared': {'references': {'metric': {'value': 10, 'tolerance': 2, 'source': 'reference'}}},
                        'measurements': {'metric': {'value': 12, 'unit': 'scalar', 'method': 'fixture', 'source': 'fixture'}}}
            options = ['--standards', str(path)]
            code, verdict = self.run_gate(evidence, options=options)
            self.assertEqual((code, verdict['evidence']['checks'][0]['verdict']), (0, 'pass'))
            self.assertEqual(verdict['evidence']['checks'][0]['used']['value'], 10)
            evidence['measurements']['metric']['value'] = 12.001
            self.assertEqual(self.run_gate(evidence, options=options)[0], 1)
            for tolerance in (0, -1, float('nan'), float('inf'), None):
                with self.subTest(tolerance=tolerance):
                    evidence['declared']['references']['metric']['tolerance'] = tolerance
                    code, verdict = self.run_gate(evidence, options=options)
                    self.assertEqual(code, 2)
                    self.assertIn('no declared reference', verdict['reasons'][0])
            del evidence['declared']['references']['metric']['tolerance']
            self.assertEqual(self.run_gate(evidence, options=options)[0], 2)
            evidence['declared']['references'] = {}
            self.assertEqual(self.run_gate(evidence, options=options)[0], 2)

            check['comparator'] = 'no-worse-than-baseline'
            path.write_text(json.dumps({'schema': 'skin-body-standards/1',
                                        'stages': [{'id': 'S1', 'checks': [check]}]}))
            evidence['declared']['baselines'] = {'metric': {'value': 10, 'factor': 1.2, 'epsilon': 1, 'source': 'baseline'}}
            evidence['measurements']['metric']['value'] = 13
            code, verdict = self.run_gate(evidence, options=options)
            self.assertEqual(code, 0)
            self.assertEqual(verdict['evidence']['checks'][0]['used']['factor'], 1.2)
            evidence['measurements']['metric']['value'] = 13.01
            self.assertEqual(self.run_gate(evidence, options=options)[0], 1)
            evidence['declared']['baselines']['metric'] = {'value': 10, 'source': 'baseline'}
            evidence['measurements']['metric']['value'] = 10
            code, verdict = self.run_gate(evidence, options=options)
            self.assertEqual(code, 0)
            self.assertEqual(verdict['evidence']['checks'][0]['used']['epsilon'], 0)
            evidence['measurements']['metric']['value'] = 10.01
            self.assertEqual(self.run_gate(evidence, options=options)[0], 1)
            evidence['declared']['baselines'] = {}
            self.assertEqual(self.run_gate(evidence, options=options)[0], 2)

    def test_comparison_directions_and_signed_baselines(self):
        """Directional thresholds and negative baselines must not reverse quality."""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'standards.json'
            check = {'id': 'direction', 'stage': 'S1', 'metric': 'metric', 'unit': 'scalar',
                     'comparator': 'reference-within'}
            standards = {'schema': 'skin-body-standards/1', 'stages': [{'id': 'S1', 'checks': [check]}]}
            evidence = {'schema': 'skin-body-evidence/1', 'subject': 'fixture',
                        'declared': {'references': {'metric': {'value': 10, 'tolerance': 2}}},
                        'measurements': {'metric': {'value': 7, 'unit': 'scalar', 'method': 'fixture', 'source': 'fixture'}}}
            options = ['--standards', str(path)]
            def run(value, direction=None):
                evidence['measurements']['metric']['value'] = value
                if direction is None:
                    check.pop('direction', None)
                else:
                    check['direction'] = direction
                path.write_text(json.dumps(standards))
                return self.run_gate(evidence, options=options)[0]
            self.assertEqual(run(7), 1)
            self.assertEqual(run(7, 'lower-is-better'), 0)
            self.assertEqual(run(12.01, 'lower-is-better'), 1)
            self.assertEqual(run(13, 'higher-is-better'), 0)
            self.assertEqual(run(7.99, 'higher-is-better'), 1)
            check['comparator'] = 'no-worse-than-baseline'
            evidence['declared']['baselines'] = {'metric': {'value': 10, 'factor': 2, 'epsilon': 1}}
            self.assertEqual(run(4, 'higher-is-better'), 0)
            self.assertEqual(run(3.99, 'higher-is-better'), 1)
            self.assertEqual(run(21, 'lower-is-better'), 0)
            self.assertEqual(run(21.01, 'lower-is-better'), 1)
            evidence['declared']['baselines']['metric'] = {'value': -10, 'factor': 2, 'epsilon': 1}
            self.assertEqual(run(-9, 'lower-is-better'), 0)
            self.assertEqual(run(-8.99, 'lower-is-better'), 1)
            self.assertEqual(run(-11, 'higher-is-better'), 0)
            self.assertEqual(run(-11.01, 'higher-is-better'), 1)
            del evidence['declared']['baselines']['metric']['epsilon']
            self.assertEqual(run(-10, 'lower-is-better'), 2)

    def test_wildcard_metrics(self):
        """A single regional regression or missing baseline cannot hide among passes."""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'standards.json'
            check = {'id': 'regions', 'stage': 'S1', 'metric': 'rig_strain_p99__*',
                     'unit': 'scalar', 'comparator': 'no-worse-than-baseline'}
            path.write_text(json.dumps({'schema': 'skin-body-standards/1',
                                        'stages': [{'id': 'S1', 'checks': [check]}]}))
            names = [f'rig_strain_p99__region{i}' for i in range(5)]
            evidence = {'schema': 'skin-body-evidence/1', 'subject': 'fixture',
                        'declared': {'baselines': {name: {'value': 1} for name in names}},
                        'measurements': {name: {'value': 1, 'unit': 'scalar', 'method': 'fixture', 'source': 'fixture'}
                                         for name in names}}
            options = ['--standards', str(path)]
            code, verdict = self.run_gate(evidence, options=options)
            self.assertEqual(code, 0)
            self.assertEqual(len(verdict['evidence']['checks'][0]['detail']), 5)
            evidence['measurements'][names[3]]['value'] = 1.01
            code, verdict = self.run_gate(evidence, options=options)
            self.assertEqual(code, 1)
            self.assertIn(names[3], verdict['reasons'][0])
            evidence['measurements'][names[3]]['value'] = 1
            del evidence['declared']['baselines'][names[2]]
            code, verdict = self.run_gate(evidence, options=options)
            self.assertEqual(code, 2)
            self.assertIn(names[2], verdict['reasons'][0])
            evidence['declared']['baselines'][names[2]] = {'value': 1}
            del evidence['measurements'][names[4]]
            code, verdict = self.run_gate(evidence, options=options)
            self.assertEqual(code, 2)
            self.assertIn(names[4], verdict['reasons'][0])
            self.assertIn('declared but not measured', verdict['reasons'][0])
            self.assertEqual(len(verdict['evidence']['checks'][0]['detail']), 5)
            for section in ('references', 'limits'):
                with self.subTest(section=section):
                    evidence['declared'][section] = {'rig_strain_p99__extra': {'value': 1}}
                    code, verdict = self.run_gate(evidence, options=options)
                    self.assertEqual(code, 2)
                    self.assertIn('rig_strain_p99__extra: unmeasured (declared but not measured)', verdict['reasons'][0])
                    del evidence['declared'][section]
            evidence['measurements'] = {}
            evidence['declared']['baselines'] = {}
            code, verdict = self.run_gate(evidence, options=options)
            self.assertEqual(code, 2)
            self.assertEqual(verdict['evidence']['checks'][0]['detail'], [])

    def test_declared_limits(self):
        """Both limit directions reject their counter-example and missing limits."""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'standards.json'
            check = {'id': 'limit', 'stage': 'S1', 'metric': 'metric', 'unit': 'scalar'}
            standards = {'schema': 'skin-body-standards/1', 'stages': [{'id': 'S1', 'checks': [check]}]}
            evidence = {'schema': 'skin-body-evidence/1', 'subject': 'fixture',
                        'declared': {'limits': {'metric': {'value': 10, 'source': 'project'}}},
                        'measurements': {'metric': {'value': 10, 'unit': 'scalar', 'method': 'fixture', 'source': 'fixture'}}}
            options = ['--standards', str(path)]
            for comparator, outside in [('declared-min', 9.99), ('declared-max', 10.01)]:
                with self.subTest(comparator=comparator):
                    check['comparator'] = comparator
                    path.write_text(json.dumps(standards))
                    evidence['declared']['limits']['metric'] = {'value': 10, 'source': 'project'}
                    evidence['measurements']['metric']['value'] = 10
                    code, verdict = self.run_gate(evidence, options=options)
                    self.assertEqual((code, verdict['evidence']['checks'][0]['verdict']), (0, 'pass'))
                    self.assertEqual(verdict['evidence']['checks'][0]['used'], {'value': 10, 'source': 'project'})
                    evidence['measurements']['metric']['value'] = outside
                    self.assertEqual(self.run_gate(evidence, options=options)[0], 1)
                    for limit in (None, float('nan'), float('inf')):
                        if limit is None:
                            del evidence['declared']['limits']['metric']
                        else:
                            evidence['declared']['limits']['metric'] = {'value': limit}
                        code, verdict = self.run_gate(evidence, options=options)
                        self.assertEqual(code, 2)
                        self.assertIn('no declared limit', verdict['reasons'][0])

    def test_advisory_and_required_checks(self):
        """Advisory problems remain visible without changing the required status."""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'standards.json'
            check = {'id': 'sanity', 'stage': 'S1', 'metric': 'metric', 'unit': 'scalar',
                     'comparator': 'between', 'threshold': [1, 2], 'severity': 'advisory'}
            standards = {'schema': 'skin-body-standards/1', 'stages': [{'id': 'S1', 'checks': [check]}]}
            evidence = {'schema': 'skin-body-evidence/1', 'subject': 'fixture', 'declared': {},
                        'measurements': {'metric': {'value': 3, 'unit': 'scalar', 'method': 'fixture', 'source': 'fixture'}}}
            path.write_text(json.dumps(standards))
            options = ['--standards', str(path)]
            code, verdict = self.run_gate(evidence, options=options)
            self.assertEqual((code, verdict['status'], verdict['evidence']['checks'][0]['verdict']), (0, 'pass', 'warn'))
            self.assertEqual(verdict['evidence']['checks'][0]['severity'], 'advisory')
            self.assertTrue(verdict['reasons'])
            evidence['measurements'] = {}
            code, verdict = self.run_gate(evidence, options=options)
            self.assertEqual((code, verdict['evidence']['checks'][0]['verdict']), (0, 'unmeasured'))
            self.assertTrue(verdict['reasons'])
            del check['severity']
            path.write_text(json.dumps(standards))
            evidence['measurements']['metric'] = {'value': 3, 'unit': 'scalar', 'method': 'fixture', 'source': 'fixture'}
            self.assertEqual(self.run_gate(evidence, options=options)[0], 1)

    def test_standards_merge_and_default_discovery(self):
        """Same-stage fragments merge; duplicate IDs are input errors."""
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            base = directory / 'skin-body-standards.json'
            fragment = directory / 'skin-body-standards.s2.json'
            check = {'id': 'first', 'stage': 'S1', 'metric': 'one', 'unit': 'scalar', 'comparator': '==', 'threshold': 1}
            other = {'id': 'second', 'stage': 'S1', 'metric': 'two', 'unit': 'scalar', 'comparator': '==', 'threshold': 2}
            def save(path, checks):
                path.write_text(json.dumps({'schema': 'skin-body-standards/1', 'stages': [{'id': 'S1', 'checks': checks}]}))
            save(base, [check])
            save(fragment, [other])
            evidence = {'schema': 'skin-body-evidence/1', 'subject': 'fixture', 'declared': {},
                        'measurements': {name: {'value': value, 'unit': 'scalar', 'method': 'fixture', 'source': 'fixture'}
                                         for name, value in [('one', 1), ('two', 2)]}}
            for options in (['--standards', str(base), '--standards', str(fragment)],
                            ['--standards-dir', str(directory)]):
                code, verdict = self.run_gate(evidence, ['S1'], options)
                self.assertEqual(code, 0)
                self.assertEqual([c['id'] for c in verdict['evidence']['checks']], ['first', 'second'])
                self.assertEqual(verdict['evidence']['files'][1:], [str(base), str(fragment)])
            other['id'] = 'first'
            save(fragment, [other])
            code, verdict = self.run_gate(evidence, options=['--standards', str(base), '--standards', str(fragment)])
            self.assertEqual(code, 2)
            self.assertIn('Duplicate check id', verdict['reasons'][0])


if __name__ == '__main__': unittest.main()
