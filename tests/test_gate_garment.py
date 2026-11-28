"""Functional gate contracts. Fixtures are independently authored truth tables, not receipts.

Trusted flags in these test inputs exercise gate decisions; they do not claim real
browser events occurred. Real acceptance still requires freshly recorded evidence.
"""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / 'tests/fixtures/garment-gate'
GATE = ROOT / 'tools/gate_garment.py'


def load(name):
    return json.loads((FIX / ('synthetic-' + name + '.json')).read_text())


class GateContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_gate(self, desktop=None, other=None, release=None, parameters=True, extra=()):
        documents = [load('desktop') if desktop is None else desktop,
                     load('other') if other is None else other,
                     load('release') if release is None else release]
        args = [sys.executable, str(GATE), '--json']
        for i, doc in enumerate(documents):
            path = self.root / f'{i}.json'
            path.write_text(json.dumps(doc))
            args += ['--matrix', str(path)]
        if parameters:
            args += ['--parameters', str(FIX / 'synthetic-calibration.json')]
        result = subprocess.run(args + list(extra), capture_output=True, text=True, timeout=10)
        env = json.loads(result.stdout)
        return result.returncode, env, {c['id']: c for c in env['evidence'].get('checks', [])}

    def test_complete_contract_passes_every_rule(self):
        code, env, checks = self.run_gate()
        self.assertEqual((code, env['status']), (0, 'pass'))
        self.assertEqual({k: v['verdict'] for k, v in checks.items()}, {f'G{i}': 'pass' for i in range(1, 6)})

    def test_skin_in_front_and_deepest_threshold_fail_even_if_other_fields_clean(self):
        for patch in ({'inside': 1}, {'deepestMm': 0.31}):
            doc = load('desktop'); doc['cases'][0].update(patch)
            code, _, checks = self.run_gate(desktop=doc)
            self.assertEqual((code, checks['G1']['verdict']), (1, 'fail'))

    def test_negative_phase_cannot_hide_behind_clean_headline(self):
        doc = load('other'); doc['touch'][0]['phases']['rebound']['insideSkin'] = 1
        self.assertEqual(self.run_gate(other=doc)[2]['G1']['verdict'], 'fail')

    def test_missing_depth_and_pull_are_unmeasured(self):
        doc = load('desktop')
        for row in doc['cases']:
            del row['inside']; del row['deepestMm']; del row['pullMm']
        _, _, checks = self.run_gate(desktop=doc)
        self.assertEqual(checks['G1']['verdict'], 'unmeasured')
        self.assertEqual(checks['G4']['verdict'], 'unmeasured')

    def test_every_mouse_angle_side_and_outfit_is_required(self):
        for predicate in (lambda r: r['kind']=='ribbon' and r['side']==1 and r['angleDeg']==135,
                          lambda r: r['kind']=='cup' and r['side']==-1,
                          lambda r: r['outfit']=='gold'):
            doc = load('desktop'); doc['cases'] = [r for r in doc['cases'] if not predicate(r)]
            self.assertEqual(self.run_gate(desktop=doc)[2]['G2']['verdict'], 'fail')

    def test_untrusted_events_cannot_establish_coverage(self):
        doc = load('desktop')
        for r in doc['cases']: r['trusted'] = False
        self.assertEqual(self.run_gate(desktop=doc)[2]['G2']['verdict'], 'fail')

    def test_touch_tissue_and_combo_coverage_remain_required(self):
        for section in ('touch', 'tissue', 'combos'):
            doc = load('other'); doc[section] = []
            self.assertEqual(self.run_gate(other=doc)[2]['G2']['verdict'], 'fail')
        doc = load('other'); doc['combos'] = doc['combos'][:9]
        self.assertEqual(self.run_gate(other=doc)[2]['G2']['verdict'], 'fail')

    def test_gentle_pulls_and_stricter_relative_fraction_fail(self):
        doc = load('desktop')
        for row in doc['cases']: row['pullMm'] = 1
        self.assertEqual(self.run_gate(desktop=doc)[2]['G4']['verdict'], 'fail')
        self.assertEqual(self.run_gate(extra=['--min-pull-fraction', '0.9'])[2]['G4']['verdict'], 'fail')

    def test_no_selected_real_calibration_is_unmeasured_not_demo_fallback(self):
        self.assertEqual(self.run_gate(parameters=False)[2]['G4']['verdict'], 'unmeasured')
        path = self.root / 'empty.json'; path.write_text('{}')
        self.assertEqual(self.run_gate(parameters=False, extra=['--parameters', str(path)])[2]['G4']['verdict'], 'unmeasured')
        self.assertEqual(self.run_gate(parameters=False, extra=['--ribbon-limit-mm','60','--cup-limit-mm','40'])[2]['G4']['verdict'], 'pass')
        self.assertEqual(self.run_gate(parameters=False, extra=['--parameters',str(self.root/'absent')])[0], 2)

    def test_absolute_pull_overrides_are_explicit(self):
        self.assertEqual(self.run_gate(parameters=False, extra=['--min-ribbon-pull-mm','48','--min-cup-pull-mm','32'])[2]['G4']['verdict'], 'pass')
        self.assertEqual(self.run_gate(parameters=False, extra=['--min-ribbon-pull-mm','49','--min-cup-pull-mm','33'])[2]['G4']['verdict'], 'fail')

    def test_missing_or_insufficient_phase_counts_never_pass_silently(self):
        doc = load('desktop')
        for row in doc['cases']: del row['phases']
        self.assertEqual(self.run_gate(desktop=doc)[2]['G3']['verdict'], 'unmeasured')
        self.assertEqual(self.run_gate(desktop=doc, extra=['--sampling-declared','synthetic contract schedule'])[2]['G3']['verdict'], 'pass')
        doc['cases'][0]['samples'] = 5
        self.assertEqual(self.run_gate(desktop=doc, extra=['--sampling-declared','synthetic contract schedule'])[2]['G3']['verdict'], 'fail')
        doc = load('desktop'); doc['cases'][0]['phases']['hold']['n'] = 1
        self.assertEqual(self.run_gate(desktop=doc)[2]['G3']['verdict'], 'fail')

    def test_release_is_exact_and_no_capture_may_survive(self):
        for after in ({'renderMismatch':0.001,'stillGrabbed':False}, {'renderMismatch':0,'stillGrabbed':True}):
            doc=load('release');doc['matrix']['contract'][0]['afterRelease']=after
            self.assertEqual(self.run_gate(release=doc)[2]['G5']['verdict'],'fail')
        self.assertEqual(self.run_gate(release={'matrix':{}})[2]['G5']['verdict'],'unmeasured')
        doc=load('release');del doc['matrix']['contract'][0]['afterRelease']['stillGrabbed']
        self.assertEqual(self.run_gate(release=doc)[2]['G5']['verdict'],'unmeasured')

    def test_empty_or_unusable_inputs_are_not_passes(self):
        code, _, checks=self.run_gate(desktop={'cases':[]},other={'touch':[],'tissue':[],'combos':[]},release={'matrix':{}})
        self.assertEqual(code,1);self.assertTrue(all(c['verdict']!='pass' for c in checks.values()))
        self.assertEqual(set(checks),{f'G{i}' for i in range(1,6)})
        self.assertEqual(checks['G5']['verdict'],'unmeasured')
        self.assertEqual(self.run_gate(desktop={'unrecognized':True})[0],2)
        for malformed in ({'matrix':[]},{'matrix':{'release':None}},{'cases':None},{'cases':[],'touch':{}}):
            self.assertEqual(self.run_gate(desktop=malformed)[0],2)
        result=subprocess.run([sys.executable,str(GATE)],capture_output=True,timeout=10)
        self.assertEqual(result.returncode,2)


if __name__ == '__main__':
    unittest.main()
