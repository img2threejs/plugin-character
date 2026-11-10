"""CC5 route must not accept a static, textureless or facially damaged export."""
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from cc5_headshot import check_export, glb_inventory


class CharacterExportIntegrity(unittest.TestCase):
    def test_static_mesh_is_not_a_rigged_character(self):
        after = {'meshes': 1, 'skins': 0, 'skinnedNodes': 0, 'morphTargets': 52, 'images': 3}
        with self.assertRaisesRegex(ValueError, 'skinned character'):
            check_export({'morphTargets': 52}, after)

    def test_unused_skin_does_not_prove_binding(self):
        after = {'meshes': 1, 'skins': 1, 'skinnedNodes': 0, 'morphTargets': 52, 'images': 3}
        with self.assertRaisesRegex(ValueError, 'skinned character'):
            check_export({'morphTargets': 52}, after)

    def test_missing_face_targets_blocks_export(self):
        after = {'meshes': 2, 'skins': 1, 'skinnedNodes': 2, 'morphTargets': 51, 'images': 3}
        with self.assertRaisesRegex(ValueError, 'facial morph'):
            check_export({'morphTargets': 52}, after)

    def test_textureless_export_is_not_appearance_ready(self):
        after = {'meshes': 2, 'skins': 1, 'skinnedNodes': 2, 'morphTargets': 52, 'images': 0}
        with self.assertRaisesRegex(ValueError, 'appearance textures'):
            check_export({'morphTargets': 52}, after)

    def test_primitives_do_not_duplicate_the_mesh_morph_inventory(self):
        document = {'meshes': [{'primitives': [{'targets': [{}, {}]}, {'targets': [{}, {}]}]}],
                    'nodes': [{'mesh': 0, 'skin': 0}], 'skins': [{'joints': [1]}]}
        encoded = json.dumps(document).encode()
        encoded += b' ' * (-len(encoded) % 4)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'inventory.glb'
            path.write_bytes(struct.pack('<4sIIII', b'glTF', 2, 20 + len(encoded),
                                         len(encoded), 0x4E4F534A) + encoded)
            inventory = glb_inventory(path)
            self.assertEqual(inventory['morphTargets'], 2)
            self.assertEqual(inventory['skinnedNodes'], 1)

    def test_truncated_glb_cannot_be_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'broken.glb'
            path.write_bytes(struct.pack('<4sIIII', b'glTF', 2, 1000, 980, 0x4E4F534A) + b'{}')
            with self.assertRaisesRegex(ValueError, 'length'):
                glb_inventory(path)


@unittest.skipUnless(os.environ.get('IMG2_CC5_PYTHON') and os.environ.get('IMG2_CC5_ADDON'),
                     'Set IMG2_CC5_PYTHON and IMG2_CC5_ADDON for the real bpy runtime regression')
class CharacterRuntimeRejection(unittest.TestCase):
    def test_non_cc_source_is_rejected_without_crash_or_artifact(self):
        python = os.environ['IMG2_CC5_PYTHON']
        addon = os.environ['IMG2_CC5_ADDON']
        tool = Path(__file__).resolve().parents[1] / 'tools' / 'cc5_headshot.py'
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'not-a-cc-character.blend'
            out = Path(tmp) / 'output'
            created = subprocess.run(
                [python, '-c', f'import bpy; bpy.ops.wm.save_as_mainfile(filepath={str(source)!r})'],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
            original = hashlib.sha256(source.read_bytes()).hexdigest()
            result = subprocess.run(
                [python, str(tool), '--addon', addon, '--source', str(source), '--out', str(out)],
                capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            report = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertEqual(report['status'], 'blocked')
            self.assertIn('exactly one imported Auto Setup character', report['reason'])
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), original)
            self.assertFalse(out.exists(), 'Rejected input must not produce a fake character')


if __name__ == '__main__':
    unittest.main()
