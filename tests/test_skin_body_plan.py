"""Deterministic plan and fail-closed input counter-examples, no bpy required."""
import copy
import json
import os
import shlex
import subprocess
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import skin_body_plan as planner

ROOT = Path(__file__).resolve().parent.parent


def standards():
    return {'schema': 'skin-body-standards/1', 'checks': [
        {'id': f'check-{stage}', 'stage': stage, 'metric': f'metric-{stage}',
         'comparator': '<=', 'threshold': i / 10, 'unit': 'ratio',
         'tag': 'behaviour', 'case': 'synthetic'}
        for i, stage in enumerate(planner.STAGES, 1)]}


def character():
    return json.loads((ROOT / 'examples/skin-body/plan.example.json').read_text())


class PlanTests(unittest.TestCase):
    def test_missing_rights_is_refused(self):
        plan = character()
        plan['sources']['head']['rights'] = '  '
        with self.assertRaisesRegex(ValueError, 'sources.head.rights'):
            planner.create_plan(standards(), plan)

    def test_selected_catalogue_is_forwarded_to_every_skin_body_measurement(self):
        plan = character()
        plan['catalogueFile'] = '/caller data/selected-catalogue.json'
        tasks = planner.create_plan(standards(), plan)['tasks']
        for task in tasks:
            self.assertEqual(task['inputs']['catalogueFile'], plan['catalogueFile'])
            for command in task['runCommands']:
                args = shlex.split(command)
                if 'tools/bpy_measure_skin_body.py' in args:
                    self.assertEqual(args[args.index('--catalogue')+1], plan['catalogueFile'])
        del plan['catalogueFile']
        with self.assertRaisesRegex(ValueError, 'catalogueFile'):
            planner.create_plan(standards(), plan)

    def test_forbidden_region_is_refused(self):
        plan = character()
        plan['regions'].append('chest-left')
        with self.assertRaisesRegex(ValueError, 'forbidden region id'):
            planner.create_plan(standards(), plan)

    def test_missing_sha_is_refused(self):
        plan = character()
        del plan['sources']['atlas']['sha256']
        with self.assertRaisesRegex(ValueError, 'sources.atlas.sha256'):
            planner.create_plan(standards(), plan)

    def test_unknown_stage_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'unknown or empty stage'):
            planner.create_plan(standards(), character(), ['S12'])

    def test_order_dependencies_and_checks(self):
        tasks = planner.create_plan(standards(), character())['tasks']
        self.assertEqual([t['stage'] for t in tasks], list(planner.STAGES))
        for index, task in enumerate(tasks):
            self.assertEqual(task['dependsOn'], planner.DEPENDENCIES[task['stage']])
            for dependency in task['dependsOn']:
                self.assertLess(planner.STAGES.index(dependency), index)
            self.assertTrue(task['standards'])
            self.assertTrue(all(check['id'] for check in task['standards']))

    def test_filter_retains_external_dependency(self):
        tasks = planner.create_plan(standards(), character(), ['S5'])['tasks']
        self.assertEqual([t['stage'] for t in tasks], ['S5'])
        self.assertEqual(tasks[0]['dependsOn'], ['S4', 'S9', 'S10'])

    def test_s2b_keeps_geometry_dependency_when_filtered(self):
        tasks = planner.create_plan(standards(), character(), ['S2B'])['tasks']
        self.assertEqual(tasks[0]['dependsOn'], ['S2', 'S9'])

    def test_missing_reference_file_is_refused_for_reference_stage(self):
        plan = character()
        del plan['declaredReferenceFile']
        with self.assertRaisesRegex(ValueError, 'declaredReferenceFile'):
            planner.create_plan(standards(), plan, ['S2B'])

    def test_extended_measurement_commands(self):
        tasks = {t['stage']: t for t in planner.create_plan(standards(), character())['tasks']}
        self.assertIn('bpy_measure_skin_authoring.py', tasks['S2B']['runCommands'][1])
        self.assertIn('bpy_measure_geometry.py', tasks['S9']['runCommands'][1])
        self.assertIn('bpy_measure_rig_motion.py', tasks['S10']['runCommands'][1])
        self.assertTrue(any('bpy_measure_rig_motion.py' in c for c in tasks['S5']['runCommands']))
        self.assertIn('S10', tasks['S5']['runCommands'][-1])

    def test_bpy_interpreter_follows_the_caller_not_the_authoring_machine(self):
        """Every bpy command runs the interpreter the caller named, else the one under IMG2_HOME."""
        def interpreters(plan):
            return {shlex.split(c)[0] for t in plan['tasks'] for c in t['runCommands'] if not c.startswith('python3 ')}
        named = '/opt/blender 4.5/bin/python'
        self.assertEqual(interpreters(planner.create_plan(standards(), character(), bpy_python=named)), {named})
        with tempfile.TemporaryDirectory() as home:
            with mock.patch.dict(os.environ, {'IMG2_HOME': home}):
                self.assertEqual(interpreters(planner.create_plan(standards(), character())),
                                 {str(Path(home) / 'runtime/character-bpy/bin/python')})
            (Path(home) / 'standards.json').write_text(json.dumps(standards()))
            code = planner.main(['--standards', str(Path(home) / 'standards.json'), '--character-plan',
                                 str(ROOT / 'examples/skin-body/plan.example.json'), '--bpy-python', named,
                                 '--out', str(Path(home) / 'out.json')])
            self.assertEqual(code, 0)
            self.assertEqual(interpreters(json.loads((Path(home) / 'out.json').read_text())), {named})
        with self.assertRaisesRegex(ValueError, 'bpy_python'):
            planner.create_plan(standards(), character(), bpy_python=' ')

    def test_brief_has_every_threshold(self):
        for task in planner.create_plan(standards(), character())['tasks']:
            for check in task['standards']:
                self.assertIn(json.dumps(check['threshold']), task['brief'])
                self.assertIn(check['id'], task['brief'])

    def test_deterministic_json_and_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'standards.json').write_text(json.dumps(standards()))
            (path / 'input.json').write_text(json.dumps(character()))
            argv = [sys.executable, str(ROOT / 'tools/skin_body_plan.py'),
                    '--standards', str(path / 'standards.json'), '--character-plan',
                    str(path / 'input.json'), '--out', str(path / 'out.json')]
            first = subprocess.run(argv, capture_output=True, text=True, check=True)
            data = (path / 'out.json').read_bytes()
            second = subprocess.run(argv, capture_output=True, text=True, check=True)
            self.assertEqual(data, (path / 'out.json').read_bytes())
            self.assertEqual(first.stdout, second.stdout)
            self.assertEqual(json.loads(data)['schema'], 'skin-body-agent-plan/1')

    def test_missing_stage_standards_fails_closed(self):
        document = copy.deepcopy(standards())
        document['checks'] = [c for c in document['checks'] if c['stage'] != 'S5']
        with self.assertRaisesRegex(ValueError, 'no standards checks for S5'):
            planner.create_plan(document, character(), ['S5'])

    def test_bad_standards_schema_and_duplicate_id(self):
        document = standards()
        document['schema'] = 'bad'
        with self.assertRaisesRegex(ValueError, 'standards schema'):
            planner.create_plan(document, character())
        document = standards()
        document['checks'][1]['id'] = document['checks'][0]['id']
        with self.assertRaisesRegex(ValueError, 'duplicate standards'):
            planner.create_plan(document, character())

    def test_nested_standards_preserve_conditional_rules(self):
        checks = standards()['checks']
        checks[planner.STAGES.index('S4')]['when'] = 'hair_declared'
        nested = {'schema': 'skin-body-standards/1', 'stages': [
            {'id': stage, 'checks': [c for c in checks if c['stage'] == stage]}
            for stage in planner.STAGES]}
        task = planner.create_plan(nested, character(), ['S4'])['tasks'][0]
        self.assertEqual(task['standards'][0]['when'], 'hair_declared')
        nested['stages'][planner.STAGES.index('S4')]['checks'][0]['stage'] = 'S5'
        with self.assertRaisesRegex(ValueError, 'disagrees'):
            planner.create_plan(nested, character())

    def test_fragment_merge_preserves_reference_rules_and_rejects_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / 'base.json'
            base.write_text(json.dumps(standards()))
            fragment = Path(directory) / 'skin-body-standards.s10-extra.json'
            check = {'id': 'extra', 'stage': 'S10', 'metric': 'rig__*',
                     'comparator': 'no-worse-than-baseline', 'direction': 'higher-is-better',
                     'unit': 'ratio', 'tag': 'behaviour', 'case': 'fixture',
                     'severity': 'advisory'}
            fragment.write_text(json.dumps({'schema': 'skin-body-standards/1',
                                            'stages': [{'id': 'S10', 'checks': [check]}]}))
            merged, paths = planner.load_standards(base)
            self.assertEqual(paths, [str(base), str(fragment)])
            task = planner.create_plan(merged, character(), ['S10'], paths)['tasks'][0]
            self.assertIn(check, task['standards'])
            self.assertTrue(all('--standards' in task['runCommands'][-1] for _ in [0]))
            check['id'] = 'check-S10'
            fragment.write_text(json.dumps({'schema': 'skin-body-standards/1',
                                            'stages': [{'id': 'S10', 'checks': [check]}]}))
            with self.assertRaisesRegex(ValueError, 'duplicate standards'):
                planner.load_standards(base)

    def test_reference_merge_command_preserves_measurements(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            plan = character()
            plan['outputDir'] = directory
            plan['declaredReferenceFile'] = str(path / 'declared.json')
            (path / 'declared.json').write_text(json.dumps({'declared': {
                'references': {'metric': {'value': 0, 'tolerance': 1, 'source': 'fixture'}},
                'limits': {'other': {'value': 2, 'source': 'fixture'}}}}))
            raw = {'schema': 'skin-body-evidence/1', 'declared': {'other': True},
                   'measurements': {'metric': {'value': 0.5, 'unit': 'ratio',
                                                'method': 'fixture', 'source': 'fixture'}}}
            (path / 's9_raw_evidence.json').write_text(json.dumps(raw))
            task = planner.create_plan(standards(), plan, ['S9'])['tasks'][0]
            subprocess.run(task['runCommands'][2], shell=True, check=True)
            result = json.loads((path / 's9_evidence.json').read_text())
            self.assertEqual(result['measurements'], raw['measurements'])
            self.assertEqual(result['declared']['other'], True)
            self.assertEqual(result['declared']['limits']['other']['value'], 2)
            self.assertEqual(result['subject'], plan['subjectId'])


@unittest.skipUnless(importlib.util.find_spec('bpy'), 'optional bpy interpreter unavailable')
class RealBpySmoke(unittest.TestCase):
    def test_plan_under_real_bpy(self):
        import bpy
        self.assertTrue(bpy.app.version_string)
        self.assertEqual(len(planner.create_plan(standards(), character())['tasks']), len(planner.STAGES))


if __name__ == '__main__':
    unittest.main()


