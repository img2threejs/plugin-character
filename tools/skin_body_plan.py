#!/usr/bin/env python3
"""Create a deterministic agent plan from explicit source rights and standards.

The plan is a work contract, not an authoring, measurement or rights-verification tool.
Case-specific thresholds come only from the supplied standards; they are not defaults.
"""
import argparse
import json
import os
import re
import shlex
import sys
from pathlib import Path

STAGES = ('S1', 'S2', 'S9', 'S2B', 'S3', 'S4', 'S10', 'S5', 'S6', 'S7', 'S11', 'S8')
DEPENDENCIES = {
    'S1': [], 'S2': ['S1'], 'S9': ['S1'], 'S2B': ['S2', 'S9'],
    'S3': ['S2B'], 'S4': ['S3'], 'S10': ['S4'], 'S5': ['S4', 'S9', 'S10'],
    'S6': ['S5'], 'S7': ['S6'], 'S11': ['S10'], 'S8': ['S6', 'S7', 'S11'],
}
REFERENCE_STAGES = frozenset(('S2B', 'S5', 'S9', 'S10', 'S11'))
STAGE_INPUTS = {
    'S2B': ('skinRegionsFile', 'skinTargetsFile', 'skinOptionsFile'),
    'S9': ('referenceBlend', 'landmarksFile', 'geometryRegionsFile', 'geometryMirrorFile',
           'geometryBudgetFile', 'atlasSize', 'joinBoundary'),
    'S10': ('armatureName', 'bodyObject', 'posesFile', 'chainsFile', 'jointSectionsFile',
            'faceGroup', 'restReferenceFile'),
    'S5': ('armatureName', 'bodyObject', 'posesFile', 'chainsFile', 'jointSectionsFile',
           'faceGroup', 'restReferenceFile'),
    'S11': ('armatureName', 'bodyObject', 'posesFile', 'chainsFile', 'jointSectionsFile',
            'faceGroup', 'restReferenceFile', 'hairObject'),
}
NEUTRAL_REGIONS = frozenset({'abdomen', 'waist-left', 'waist-right', 'cheek-left',
                             'cheek-right', 'face', 'hair'})


def default_bpy_python():
    """The documented local layout: $IMG2_HOME (default ~/.img2)/runtime/character-bpy/bin/python."""
    home = os.environ.get('IMG2_HOME') or str(Path.home() / '.img2')
    return str(Path(home) / 'runtime' / 'character-bpy' / 'bin' / 'python')


FORBIDDEN = [
    'Never overwrite pinned source files or modify their hashes.',
    'Never re-freeze geometry to pass a regression or change standards to pass.',
    'Never recolour globally to hide a geometry defect.',
    'Never create chest, hip or buttock regions.',
    'No neural mesh generation without explicit user opt-in.',
    'Never claim a check that was not run.',
    'Never write concurrently to the master blend; the integration owner alone writes it.',
]
DESCRIPTIONS = {
    'S1': ('source-rights', 'Admit rights-cleared body, head and atlas, verifying source hashes.'),
    'S2': ('skin-author', 'Author bounded skin texture and preserve protected source pixels.'),
    'S9': ('geometry-author', 'Author geometry, topology and UV against declared references.'),
    'S2B': ('skin-author', 'Author neutral painted skin from declared target references.'),
    'S3': ('integration-owner', 'Fit and join head and neck, preserving donor and join correspondence.'),
    'S4': ('rig-author', 'Author skeleton and inventory body parts and hair.'),
    'S10': ('rig-author', 'Author and measure rig, poses and motion against declared baselines.'),
    'S5': ('weights-author', 'Transfer and repair skin weights and measure mirrored pairs.'),
    'S6': ('integration-owner', 'Author only the declared neutral region masks.'),
    'S7': ('integration-owner', 'Wire skin material and document native versus exported properties.'),
    'S11': ('hair-author', 'Author hair fit and motion against subject-specific baselines.'),
    'S8': ('integration-owner', 'Export from a working copy and inspect actual export parity.'),
}


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be a non-empty string')
    return value


def validate_input(plan):
    """Require explicit source hashes/rights and neutral masks; do not certify rights."""
    if not isinstance(plan, dict) or plan.get('schema') != 'skin-body-plan-input/1':
        raise ValueError('character plan schema must be skin-body-plan-input/1')
    for key in ('subjectId', 'blendPath', 'catalogueCharacterId', 'mirrorPairsFile',
                'repairMaskFile', 'outputDir'):
        text(plan.get(key), key)
    sources = plan.get('sources')
    if not isinstance(sources, dict) or not sources:
        raise ValueError('sources must contain body, head and atlas')
    for required in ('body', 'head', 'atlas'):
        if required not in sources:
            raise ValueError(f'sources.{required} is required')
    for name, source in sources.items():
        if not isinstance(source, dict):
            raise ValueError(f'sources.{name} must be an object')
        text(source.get('path'), f'sources.{name}.path')
        text(source.get('rights'), f'sources.{name}.rights')
        digest = source.get('sha256')
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', digest):
            raise ValueError(f'sources.{name}.sha256 must be 64 hexadecimal digits')
    atlases = plan.get('atlasNames')
    if not isinstance(atlases, list) or not atlases:
        raise ValueError('atlasNames must be a non-empty list')
    for atlas in atlases:
        text(atlas, 'atlasNames entry')
    regions = plan.get('regions')
    if not isinstance(regions, list) or not regions:
        raise ValueError('regions must be a non-empty list of neutral region ids')
    for region in regions:
        if not isinstance(region, str) or region not in NEUTRAL_REGIONS:
            raise ValueError(f'forbidden region id: {region!r}')
    return plan


def validate_standards(doc):
    """Require the versioned check fields; thresholds remain standards-owned data."""
    if not isinstance(doc, dict) or doc.get('schema') != 'skin-body-standards/1':
        raise ValueError('standards schema must be skin-body-standards/1')
    checks = doc.get('checks')
    if checks is None:
        groups = doc.get('stages')
        if not isinstance(groups, list) or not groups:
            raise ValueError('standards stages must be a non-empty list')
        checks = []
        for group in groups:
            if not isinstance(group, dict) or group.get('id') not in STAGES or not isinstance(group.get('checks'), list):
                raise ValueError('invalid standards stage group')
            for check in group['checks']:
                if not isinstance(check, dict) or check.get('stage') != group['id']:
                    raise ValueError('standards check stage disagrees with its group')
                checks.append(check)
    if not isinstance(checks, list) or not checks:
        raise ValueError('standards checks must be a non-empty list')
    seen = set()
    for check in checks:
        if not isinstance(check, dict):
            raise ValueError('standards check must be an object')
        for key in ('id', 'stage', 'metric', 'comparator', 'unit', 'tag'):
            text(check.get(key), f'standards check {key}')
        if 'case' not in check:
            raise ValueError('standards check missing case')
        if check['comparator'] in ('==', '<=', '>=', 'between') and 'threshold' not in check:
            raise ValueError('standards check missing threshold')
        if check.get('severity', 'required') not in ('required', 'advisory'):
            raise ValueError(f'invalid severity for {check["id"]}')
        if check['id'] in seen:
            raise ValueError(f'duplicate standards check id: {check["id"]}')
        seen.add(check['id'])
        if check['stage'] not in STAGES:
            raise ValueError(f'unknown standards stage: {check["stage"]}')
    return checks


def load_standards(path):
    """Merge base and sorted sibling fragments, rejecting duplicate check identities."""
    path = Path(path)
    paths = [path, *sorted(path.parent.glob('skin-body-standards.s*.json'))]
    paths = list(dict.fromkeys(paths))
    checks = []
    for item in paths:
        document = json.loads(item.read_text(encoding='utf-8'))
        checks.extend(validate_standards(document))
    merged = {'schema': 'skin-body-standards/1', 'checks': checks}
    validate_standards(merged)
    return merged, [str(item) for item in paths]


def create_plan(standards, character, stages=None, standards_path='reference/skin-body-standards.json',
                bpy_python=None):
    """Build a topological work plan; omitted dependencies remain external prerequisites.

    `bpy_python` is the interpreter containing bpy that runs the author and measure commands;
    it defaults to `default_bpy_python()`.
    """
    validate_input(character)
    checks = validate_standards(standards)
    selected = list(STAGES) if stages is None else list(stages)
    if not selected or any(stage not in STAGES for stage in selected):
        raise ValueError('unknown or empty stage selection')
    if len(set(selected)) != len(selected):
        raise ValueError('duplicate stage selection')
    if any(stage in REFERENCE_STAGES for stage in selected):
        text(character.get('declaredReferenceFile'), 'declaredReferenceFile')
    for stage in selected:
        for key in STAGE_INPUTS.get(stage, ()):
            text(character.get(key), f'{stage} {key}')
    paths = [standards_path] if isinstance(standards_path, str) else standards_path
    gate_standards = ' '.join('--standards ' + shlex.quote(p) for p in paths)
    out = Path(character['outputDir'])
    quote = shlex.quote
    interpreter = quote(text(bpy_python, 'bpy_python') if bpy_python is not None else default_bpy_python())
    tasks = []
    for stage in STAGES:
        if stage not in selected:
            continue
        relevant = [dict(check) for check in checks
                    if check['stage'] == stage or stage == 'S5' and check['stage'] == 'S10']
        if not any(check['stage'] == stage for check in relevant):
            raise ValueError(f'no standards checks for {stage}')
        role, description = DESCRIPTIONS[stage]
        script = str(out / f'{stage.lower()}_author.py')
        artifact = str(out / ('character.glb' if stage == 'S8' else f'{stage.lower()}_artifact.blend'))
        raw = str(out / f'{stage.lower()}_raw_evidence.json')
        evidence = str(out / f'{stage.lower()}_evidence.json')
        verdict = str(out / f'{stage.lower()}_verdict.json')
        dependencies = DEPENDENCIES[stage].copy()
        upstream = {dep: str(out / f'{dep.lower()}_artifact.blend') for dep in dependencies}
        inputs = {'sources': character['sources'], 'blendPath': character['blendPath'],
                  'atlasNames': character['atlasNames'], 'catalogueCharacterId': character['catalogueCharacterId'],
                  'mirrorPairsFile': character['mirrorPairsFile'], 'repairMaskFile': character['repairMaskFile'],
                  'regions': character['regions'], 'standardsFiles': paths, 'upstreamArtifacts': upstream,
                  'upstreamHashes': 'Require accepted SHA-256 for each prerequisite before execution.'}
        if stage in REFERENCE_STAGES:
            inputs['declaredReferenceFile'] = character['declaredReferenceFile']
        inputs.update({key: character[key] for key in STAGE_INPUTS.get(stage, ())})
        author = f'{interpreter} {quote(script)}'
        q = lambda key: quote(character[key])
        if stage == 'S9':
            measure = (f'{interpreter} tools/bpy_measure_geometry.py --blend {quote(artifact)} '
                       f'--reference {q("referenceBlend")} --landmarks {q("landmarksFile")} '
                       f'--regions {q("geometryRegionsFile")} --mirror {q("geometryMirrorFile")} '
                       f'--budget {q("geometryBudgetFile")} --atlas-size {q("atlasSize")} '
                       f'--join-boundary {q("joinBoundary")} --out {quote(raw)}')
        elif stage == 'S2B':
            measure = (f'{interpreter} tools/bpy_measure_skin_authoring.py --blend {quote(artifact)} '
                       f'--atlas {quote(character["atlasNames"][0])} --regions {q("skinRegionsFile")} '
                       f'--targets {q("skinTargetsFile")} --options {q("skinOptionsFile")} '
                       f'--baseline-blend {quote(upstream["S2"])} --subject {q("subjectId")} --out {quote(raw)}')
        elif stage in ('S10', 'S11'):
            measure = (f'{interpreter} tools/bpy_measure_rig_motion.py --blend {quote(artifact)} '
                       f'--armature {q("armatureName")} --body {q("bodyObject")} --poses {q("posesFile")} '
                       f'--chains {q("chainsFile")} --joint-sections {q("jointSectionsFile")} '
                       f'--face-ids {q("faceGroup")} --rest-reference {q("restReferenceFile")} '
                       + (f'--hair {q("hairObject")} ' if stage == 'S11' else '') + f'--out {quote(raw)}')
        else:
            baseline_stage = {'S2': 'S1', 'S3': 'S2B', 'S4': 'S3', 'S5': 'S4',
                              'S6': 'S5', 'S7': 'S6', 'S8': 'S7'}.get(stage)
            baseline = f'--baseline-blend {quote(upstream[baseline_stage])} ' if baseline_stage else ''
            sources = ' '.join('--source ' + quote(f'{name}={source["path"]}:{source["sha256"]}')
                               for name, source in character['sources'].items())
            measure = (f'{interpreter} tools/bpy_measure_skin_body.py '
                       f'--{"glb" if stage == "S8" else "blend"} {quote(artifact)} '
                       + baseline + f'--catalogue reference/body-parts.json --character {q("catalogueCharacterId")} '
                       + f'--atlas {quote(character["atlasNames"][0])} {sources} '
                       + (f'--mirror-pairs {q("mirrorPairsFile")} ' if stage == 'S5' else '')
                       + (f'--repair-mask {q("repairMaskFile")} ' if stage == 'S2' else '')
                       + f'--out {quote(evidence)}')
        commands = [author, measure]
        # Measurers return distinct declarations; merge reviewed per-metric values without
        # modifying measurements. Geometry/rig tools do not supply a subject field.
        merge = ("import json,sys; from pathlib import Path; "
                 "e=json.loads(Path(sys.argv[1]).read_text()); "
                 "d=json.loads(Path(sys.argv[2]).read_text())['declared']; "
                 "e['subject']=sys.argv[3]; "
                 "e.setdefault('declared',{}).update({k:{**e.get('declared',{}).get(k,{}),**d[k]} "
                 "for k in ('references','baselines','limits') if k in d}); "
                 "Path(sys.argv[4]).write_text(json.dumps(e,indent=2,allow_nan=False)+'\\n')")
        if stage in REFERENCE_STAGES and stage != 'S5':
            commands.append(f'python3 -c {quote(merge)} {quote(raw)} {q("declaredReferenceFile")} '
                            f'{q("subjectId")} {quote(evidence)}')
        commands.append(f'python3 tools/gate_skin_body.py {gate_standards} '
                        f'--evidence {quote(evidence)} --stage {stage} --json > {quote(verdict)}')
        extra_outputs = []
        if stage == 'S5':
            strain_raw = str(out / 's5_strain_raw_evidence.json')
            strain_evidence = str(out / 's5_strain_evidence.json')
            strain_verdict = str(out / 's5_strain_verdict.json')
            commands.append(f'{interpreter} tools/bpy_measure_rig_motion.py --blend {quote(artifact)} '
                            f'--armature {q("armatureName")} --body {q("bodyObject")} --poses {q("posesFile")} '
                            f'--chains {q("chainsFile")} --joint-sections {q("jointSectionsFile")} '
                            f'--face-ids {q("faceGroup")} --rest-reference {q("restReferenceFile")} '
                            f'--out {quote(strain_raw)}')
            commands.append(f'python3 -c {quote(merge)} {quote(strain_raw)} {q("declaredReferenceFile")} '
                            f'{q("subjectId")} {quote(strain_evidence)}')
            commands.append(f'python3 tools/gate_skin_body.py {gate_standards} --evidence {quote(strain_evidence)} '
                            f'--stage S10 --json > {quote(strain_verdict)}')
            extra_outputs = [strain_evidence, strain_verdict]
        owned = [script, artifact] + ([character['blendPath']] if role == 'integration-owner' else [])
        task = {'stage': stage, 'role': role, 'ownedFiles': owned, 'inputs': inputs,
                'outputs': [artifact, evidence, verdict] + extra_outputs, 'standards': relevant,
                'runCommands': commands, 'forbidden': FORBIDDEN.copy(), 'dependsOn': dependencies}
        task['brief'] = (f'{stage} / {role}: {description}\n'
                         f'Ownership: {json.dumps(owned, sort_keys=True)}\n'
                         f'Inputs (including source hashes and rights): {json.dumps(inputs, sort_keys=True)}\n'
                         f'Outputs: {json.dumps(task["outputs"])}\n'
                         f'Dependencies (must already be accepted): {json.dumps(dependencies)}\n'
                         f'Standards: {json.dumps(relevant, sort_keys=True)}\n'
                         f'Run in order:\n' + '\n'.join(commands) + '\n'
                         f'Forbidden: {json.dumps(FORBIDDEN)}\n'
                         'Declare target references, baselines and limits before authoring. '
                         'Write the job-specific script; report artifact hashes, measured evidence and open checks. '
                         'The independent verifier runs measurement and gate after writers finish.')
        tasks.append(task)
    return {'schema': 'skin-body-agent-plan/1', 'subjectId': character['subjectId'], 'tasks': tasks}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--standards', default='reference/skin-body-standards.json')
    parser.add_argument('--character-plan', required=True)
    parser.add_argument('--stages', help='comma-separated stage IDs')
    parser.add_argument('--bpy-python', help='Python containing bpy for the author and measure commands '
                        '(default: $IMG2_HOME/runtime/character-bpy/bin/python, IMG2_HOME defaulting to ~/.img2)')
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    try:
        standards, paths = load_standards(args.standards)
        character = json.loads(Path(args.character_plan).read_text(encoding='utf-8'))
        stages = args.stages.split(',') if args.stages is not None else None
        result = create_plan(standards, character, stages, paths, args.bpy_python)
        Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    except (OSError, ValueError, TypeError) as error:
        print(f'skin_body_plan: {error}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
