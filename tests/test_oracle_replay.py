"""Complete canonical report oracle for an independently authored skinned primitive.

The full report is compared, not a selected subset of measurements. Only the
machine-specific input path is excluded. No external showcase path or historical
subject report is shipped. Explicit caller GLB/report pairs remain supported.
"""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / 'tests/fixtures/oracle-synthetic'
VOLATILE_KEYS = ('path',)


def canonical(payload):
    return json.dumps({k:v for k,v in payload.items() if k not in VOLATILE_KEYS},sort_keys=True,separators=(',',':')).encode()


def digest(payload):
    return hashlib.sha256(canonical(payload)).hexdigest()


class SyntheticOracle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frozen=json.loads((FIX/'glb-rig.json').read_text())
        with tempfile.TemporaryDirectory(prefix='synthetic-oracle-replay-') as workspace:
            result=subprocess.run([sys.executable,str(ROOT/'tools/rig_glb_reference.py'),str(FIX/'synthetic-rig.glb'),'--workspace',workspace],capture_output=True,text=True,timeout=20)
        if result.returncode:
            raise AssertionError(result.stdout+result.stderr)
        cls.replayed=json.loads(result.stdout)

    def test_complete_report_is_byte_identical_in_canonical_form(self):
        self.assertEqual(canonical(self.replayed),canonical(self.frozen))
        version=json.loads((ROOT/'plugin.json').read_text())['version']
        self.assertEqual(self.replayed['provenance'],{'provider':'character','version':version})

    def test_fixture_is_substantive_and_skin_order_is_not_node_or_traversal_order(self):
        self.assertTrue(self.frozen['ok'])
        self.assertEqual(self.frozen['nodeCount'],8)
        self.assertEqual(self.frozen['skinCount'],1)
        self.assertEqual(self.frozen['clipCount'],3)
        self.assertEqual([j['nodeIndex'] for j in self.replayed['joints']],[5,2,6,1,4,3])
        self.assertEqual(self.replayed['joints'][0]['nodeName'],'JointE')
        self.assertEqual(self.replayed['inverseBindMatrices'][0][13],-2)
        self.assertEqual(len(self.replayed['clips']),3)
        self.assertTrue(all(clip['channelCount']>0 for clip in self.replayed['clips']))

    def test_geometry_really_has_joint_attributes_weights_and_animation_paths(self):
        data=(FIX/'synthetic-rig.glb').read_bytes();size=struct.unpack_from('<I',data,12)[0]
        doc=json.loads(data[20:20+size])
        attrs=doc['meshes'][0]['primitives'][0]['attributes']
        self.assertTrue({'POSITION','NORMAL','JOINTS_0','WEIGHTS_0'}<=set(attrs))
        self.assertEqual(doc['accessors'][attrs['WEIGHTS_0']]['count'],9)
        self.assertEqual({c['target']['path'] for a in doc['animations'] for c in a['channels']},{'translation','rotation','scale'})

    def test_hash_manifest_pins_both_input_and_complete_report(self):
        manifest=json.loads((FIX/'manifest.json').read_text())
        self.assertEqual({e['path'] for e in manifest['files']},{'synthetic-rig.glb','glb-rig.json'})
        for entry in manifest['files']:
            data=(FIX/entry['path']).read_bytes()
            self.assertEqual(len(data),entry['bytes'])
            self.assertEqual(hashlib.sha256(data).hexdigest(),entry['sha256'])

    def test_negative_controls_cover_skin_animation_rig_and_envelope_changes(self):
        for mutate in (lambda d:d['joints'].reverse(),
                       lambda d:d['inverseBindMatrices'][0].__setitem__(13,-3),
                       lambda d:d['clips'].pop(),
                       lambda d:d.__setitem__('nodeCount',9),
                       lambda d:d['provenance'].__setitem__('version','wrong'),
                       lambda d:d.__setitem__('unexpected',True)):
            changed=copy.deepcopy(self.frozen);mutate(changed)
            self.assertNotEqual(canonical(changed),canonical(self.frozen))
        formatted=json.loads(json.dumps(self.frozen,indent=7))
        self.assertEqual(digest(formatted),digest(self.frozen))
        changed={**self.frozen,'path':'another machine'}
        self.assertEqual(canonical(changed),canonical(self.frozen))
        self.assertEqual(VOLATILE_KEYS,('path',))
        self.assertIn('path',self.replayed)

    def test_explicit_caller_pair_requires_both_files(self):
        asset=os.environ.get('IMG2_ORACLE_GLB');report=os.environ.get('IMG2_ORACLE_REPORT')
        if not asset and not report:
            return
        self.assertTrue(asset and report,'Supply both IMG2_ORACLE_GLB and IMG2_ORACLE_REPORT; no synthetic fallback')
        with tempfile.TemporaryDirectory(prefix='caller-oracle-replay-') as workspace:
            result=subprocess.run([sys.executable,str(ROOT/'tools/rig_glb_reference.py'),asset,'--workspace',workspace],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(canonical(json.loads(result.stdout)),canonical(json.loads(Path(report).read_text())))


if __name__=='__main__':
    unittest.main()
