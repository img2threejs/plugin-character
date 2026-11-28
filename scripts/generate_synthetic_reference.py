#!/usr/bin/env python3
"""Regenerate independent contract fixtures, primitive catalogue and integrity manifest.

Repository maintenance only; not a caller-workspace runtime command.
Run extract_garment_parameters.mjs first. Gate fixtures are deliberately constructed
truth-table inputs, NOT browser/native measurements or evidence of trusted events.
No third-party asset, previous receipt or native transform is read.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def save(path, value):
    (ROOT / path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def main():
    parameters = json.loads((ROOT / 'reference/garment-parameters.json').read_text())
    config = parameters['synthetic']
    calibration = config['garment']
    note = 'Constructed synthetic gate contract input, not observed events, browser measurements or native acceptance.'
    limits = {'ribbon': calibration['strap']['maxPull'] * 1000,
              'cup': calibration['panel']['maxPull'] * 1000}
    phases = {'hold': {'n': 3}, 'rebound': {'n': 5}, 'settled': {'n': 1}}
    clean = {'inside': 0, 'deepestMm': 0, 'samples': 9, 'phases': phases}
    cases = [dict(clean, outfit=outfit, kind=kind, side=side, angleDeg=angle,
                  input='mouse', trusted=True, pullMm=limit * 0.8)
             for outfit in calibration['outfits'] for kind, limit in limits.items()
             for side in (1, -1) for angle in range(0, 360, 45)]
    touch = [dict(clean, outfit=outfit, kind=kind, side=side, angleDeg=angle,
                  input='touch', trusted=True, pullMm=limit * 0.8)
             for outfit in calibration['outfits'] for kind, limit in limits.items()
             for side, angle in ((1, 0), (-1, 90), (1, 180), (-1, 270))]
    tissue = [dict(clean, kind='cup', side=side, mode=mode, input='mouse', trusted=True)
              for side in (1, -1) for mode in ('grab', 'squeeze')]
    combos = [dict(clean, id=f'contract-combo-{i}', pulls=[{'kind': 'strap', 'side': 1}, {'kind': 'panel', 'side': -1}],
                   pullMmAtHold={'strap': {'1': limits['ribbon'] * 0.8}, 'panel': {'-1': limits['cup'] * 0.8}})
              for i in range(10)]
    save('tests/fixtures/garment-gate/synthetic-desktop.json', {'scope': note, 'cases': cases})
    save('tests/fixtures/garment-gate/synthetic-other.json', {'scope': note, 'touch': touch, 'tissue': tissue, 'combos': combos})
    save('tests/fixtures/garment-gate/synthetic-release.json', {'scope': note, 'matrix': {'contract': [
        {'id': f'contract-release-{outfit}-{kind}-{side}', 'kind':kind, 'side':side, 'outfit':outfit,
         'afterRelease': {'renderMismatch': 0, 'stillGrabbed': False}}
        for outfit in calibration['outfits'] for kind in ('ribbon','cup') for side in (1,-1)]}})
    save('tests/fixtures/garment-gate/synthetic-calibration.json', {'scope': note, 'calibration': calibration})
    catalogue = {'schema': 'body-parts/1', 'scope': 'Independent board/cloth primitive inventory. Anatomical parts and real-input measurements are unknown.',
                 'characters': [{'id': 'synthetic-board', 'assets': [{
                     'id': 'synthetic-board-rig', 'stage': 'procedural-board',
                     'coordinate_basis': 'metres, Y up, support normal +Z, Cartesian board (not anatomy)',
                     'rights': 'Project-authored procedural geometry; no third-party asset inputs. Not a rights grant for caller data or history.',
                     'source_identity': 'runtime/garment-character/synthetic-scene.mjs',
                     'bones': [{'id': 'BoardAnchor', 'side': 'centre', 'parent': None, 'mirror': None}],
                     'meshes': [{'id': calibration['bodyMesh']}, {'id': calibration['garmentMesh']}],
                     'parts': [{'id': 'fabric', 'side': 'centre', 'status': 'present', 'bones': ['BoardAnchor'], 'meshes': [calibration['garmentMesh']]},
                               *[{'id': part, 'side': 'centre', 'status': 'unknown', 'bones': [], 'meshes': []} for part in ('head', 'hair', 'torso', 'abdomen')]],
                     'bone_groups': [{'id': 'board-anchor', 'bones': ['BoardAnchor']}],
                     'measurements': [{'id': 'bone-count', 'value': 1, 'unit': 'count', 'frame': 'procedural rig',
                                       'method': 'one Bone constructed by createSyntheticScene', 'evidenceClass': 'authored',
                                       'source': 'runtime/garment-character/synthetic-scene.mjs:29',
                                       'limitations': 'primitive only; no anatomical measurements', 'tag': 'behaviour'}],
                     'profiles': [], 'masks': [], 'textures': []}]}]}
    save('reference/body-parts.json', catalogue)
    files = []
    for directory, kind in (('runtime/garment-character', 'runtime'), ('tests/garment-character', 'test')):
        for path in sorted((ROOT / directory).iterdir()):
            if not path.is_file() or path.name == 'manifest.json' or path.name.startswith('.'):
                continue
            data = path.read_bytes()
            files.append({'path': str(path.relative_to(ROOT)), 'kind': kind,
                          'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)})
    save('runtime/garment-character/manifest.json', {
        'schema': 1, 'route': 'garment-character', 'buildStamp': 'synthetic-1',
        'hashCheck': 'sha256 and bytes of the file at path, relative to plugin root; enforced by test_garment_character_manifest.py.',
        'runtimeLicense': 'Project code Apache-2.0; Three.js 0.186.1 MIT. No third-party assets bundled.',
        'files': files})


if __name__ == '__main__':
    main()
