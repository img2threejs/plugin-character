#!/usr/bin/env python3
"""Judge independently measured skin/body evidence; missing or unusable evidence never passes."""
import argparse
import json
import math
import re
import sys
from pathlib import Path

DEFAULT_STANDARDS = Path(__file__).resolve().parent.parent / 'reference' / 'skin-body-standards.json'
NEUTRAL_REGIONS = frozenset(('abdomen', 'waist-left', 'waist-right', 'cheek-left', 'cheek-right', 'face', 'hair'))


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def usable(value):
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return finite(value)
    if isinstance(value, str):
        return bool(value.strip()) and value not in ('unmeasured', 'unmeasured-by-export')
    if isinstance(value, list):
        return bool(value) and all(usable(x) for x in value)
    if isinstance(value, dict):
        return bool(value) and all(usable(x) for x in value.values())
    return False


def judge(check, evidence, allowlist):
    """Judge a single receipt; see standards for the cited case and numeric limit."""
    metric = check['metric']
    result = {'id': check['id'], 'name': metric, 'stage': check['stage'], 'severity': check.get('severity', 'required'), 'verdict': 'unmeasured', 'summary': ''}
    if check.get('when'):
        declaration = evidence.get('declared', {}).get(check['when'])
        if declaration is False:
            result.update(verdict='pass', summary='Not applicable: explicitly declared absent')
            return result
        if declaration is not True:
            result['summary'] = 'Applicability not declared'
            return result
    item = evidence.get('measurements', {}).get(metric)
    if not isinstance(item, dict) or not isinstance(item.get('method'), str) or not item['method'].strip() or not isinstance(item.get('source'), str) or not item['source'].strip():
        result['summary'] = 'Missing measurement, method, or source'
        return result
    value = item.get('value')
    if item.get('unit') != check['unit']:
        result['summary'] = 'Missing or mismatched unit'
        return result
    if metric == 'mask_region_ids':
        if not isinstance(value, list) or not value or any(not isinstance(x, str) or not x for x in value):
            result['summary'] = 'Missing or invalid region IDs'
            return result
        bad = sorted(set(value) - NEUTRAL_REGIONS)
        result.update(verdict='fail' if bad else 'pass', summary=('Forbidden region IDs: ' + ', '.join(bad)) if bad else 'Only neutral region IDs')
        return result
    if metric == 'source_hash':
        if not isinstance(value, dict) or not value:
            result['summary'] = 'Expected named source hash records'
            return result
        for name, record in value.items():
            if (not isinstance(name, str) or not name.strip() or not isinstance(record, dict)
                    or not isinstance(record.get('path'), str) or not record['path'].strip()
                    or not isinstance(record.get('actual'), str) or not re.fullmatch(r'[0-9a-f]{64}', record['actual'])
                    or not isinstance(record.get('expected'), str) or not re.fullmatch(r'[0-9a-f]{64}', record['expected'])
                    or type(record.get('matches')) is not bool
                    or record['matches'] != (record['actual'] == record['expected'])):
                result['summary'] = 'Invalid source hash record'
                return result
        result.update(verdict='pass', summary=f'{len(value)} named source hashes recorded')
        return result
    if not usable(value):
        result['summary'] = 'Missing, non-finite, or unusable value'
        return result
    if metric == 'mirror_mapping':
        if not isinstance(value, dict) or not isinstance(value.get('pairs'), list) or not value['pairs'] or not isinstance(value.get('permutation'), dict) or not value['permutation']:
            result['summary'] = 'Explicit nonempty vertex pairs and bone permutation required'
            return result
        if any(not isinstance(pair, list) or len(pair) != 2 or any(type(index) is not int or index < 0 for index in pair) for pair in value['pairs']):
            result['summary'] = 'Invalid vertex pair mapping'
            return result
        if any(not isinstance(k, str) or not k or not isinstance(v, str) or not v for k, v in value['permutation'].items()) or len(set(value['permutation'].values())) != len(value['permutation']):
            result['summary'] = 'Invalid bone permutation'
            return result
    comparator, threshold = check['comparator'], check.get('threshold')
    direction = check.get('direction')
    if direction not in (None, 'lower-is-better', 'higher-is-better'):
        result['summary'] = 'Invalid comparison direction'
        return result
    if comparator in ('reference-within', 'no-worse-than-baseline'):
        declarations = evidence.get('declared', {}).get(
            'references' if comparator == 'reference-within' else 'baselines', {})
        declaration = declarations.get(metric) if isinstance(declarations, dict) else None
        if not isinstance(declaration, dict) or not finite(declaration.get('value')):
            result['summary'] = 'no declared reference' if comparator == 'reference-within' else 'no declared baseline'
            return result
        reference = declaration['value']
        if comparator == 'reference-within':
            tolerance = declaration.get('tolerance')
            if not finite(tolerance) or tolerance <= 0:
                result['summary'] = 'no declared reference'
                return result
            used = {'value': reference, 'tolerance': tolerance}
        else:
            factor, epsilon = declaration.get('factor', 1), declaration.get('epsilon', 0)
            if (not finite(factor) or factor <= 0 or not finite(epsilon)
                    or reference < 0 and 'epsilon' not in declaration):
                result['summary'] = 'no declared baseline'
                return result
            used = {'value': reference, 'factor': factor, 'epsilon': epsilon}
        if isinstance(declaration.get('source'), str):
            used['source'] = declaration['source']
        result['used'] = used
        if not finite(value):
            result['summary'] = 'Expected a finite number'
            return result
        if comparator == 'reference-within':
            if direction == 'lower-is-better':
                ok = value <= reference + tolerance
            elif direction == 'higher-is-better':
                ok = value >= reference - tolerance
            else:
                ok = abs(value - reference) <= tolerance
        elif direction == 'higher-is-better':
            ok = value >= (reference / factor if reference >= 0 else reference) - epsilon
        else:
            ok = value <= (reference * factor if reference >= 0 else reference) + epsilon
        result.update(verdict='pass' if ok else 'fail', summary=f'{value!r} {comparator} {used!r}')
        return result
    if comparator in ('declared-min', 'declared-max'):
        limits = evidence.get('declared', {}).get('limits', {})
        declaration = limits.get(metric) if isinstance(limits, dict) else None
        if not isinstance(declaration, dict) or not finite(declaration.get('value')):
            result['summary'] = 'no declared limit'
            return result
        used = {'value': declaration['value']}
        if isinstance(declaration.get('source'), str):
            used['source'] = declaration['source']
        result['used'] = used
        if not finite(value):
            result['summary'] = 'Expected a finite number'
            return result
        ok = value >= used['value'] if comparator == 'declared-min' else value <= used['value']
        result.update(verdict='pass' if ok else 'fail', summary=f'{value!r} {comparator} {used!r}')
        return result
    if comparator == 'exists':
        expected_number = check['unit'] in ('bones', 'edges', 'triangles', 'scalar')
        if expected_number and (not finite(value) or value < 0):
            result['summary'] = 'Expected a nonnegative finite number'
            return result
        ok = True
    elif comparator in ('<=', '>=', 'between') or isinstance(threshold, (int, float)) and not isinstance(threshold, bool):
        if not finite(value):
            result['summary'] = 'Expected a finite number'
            return result
        if metric != 'mask_min' and value < 0:
            result['summary'] = 'Negative count or error is unusable'
            return result
        if comparator == '<=': ok = value <= threshold
        elif comparator == '>=': ok = value >= threshold
        elif comparator == 'between': ok = threshold[0] <= value <= threshold[1]
        else: ok = value == threshold
    elif comparator == '==':
        if not isinstance(value, type(threshold)):
            result['summary'] = 'Wrong value type'
            return result
        ok = value == threshold
    else:
        result['summary'] = 'Unsupported comparator'
        return result
    result.update(verdict='pass' if ok else 'fail', summary=f'{value!r} {comparator} {threshold!r}')
    return result


def judge_expanded(check, evidence, allowlist):
    """Judge the union of matching measured and declared metric names."""
    pattern = check['metric']
    if '*' not in pattern:
        return judge(check, evidence, allowlist)
    expression = re.compile('^' + re.escape(pattern).replace(r'\*', '.*') + '$')
    measurements = evidence['measurements']
    names = set(measurements)
    declared = evidence.get('declared', {})
    for key in ('baselines', 'references', 'limits'):
        records = declared.get(key)
        if isinstance(records, dict):
            names.update(records)
    names = sorted(name for name in names if isinstance(name, str) and expression.fullmatch(name))
    details = []
    for name in names:
        item = judge({**check, 'metric': name}, evidence, allowlist)
        if name not in measurements:
            item.update(verdict='unmeasured', summary='declared but not measured')
        details.append(item)
    if not details:
        return {'id': check['id'], 'name': pattern, 'stage': check['stage'],
                'severity': check.get('severity', 'required'), 'verdict': 'unmeasured',
                'summary': 'No matching measurements', 'detail': []}
    verdict = ('fail' if any(item['verdict'] == 'fail' for item in details) else
               'unmeasured' if any(item['verdict'] == 'unmeasured' for item in details) else 'pass')
    problems = [f"{item['name']}: {item['verdict']} ({item['summary']})"
                for item in details if item['verdict'] != 'pass']
    return {'id': check['id'], 'name': pattern, 'stage': check['stage'],
            'severity': check.get('severity', 'required'), 'verdict': verdict,
            'summary': '; '.join(problems) if problems else f'{len(details)} matching measurements pass',
            'detail': details}


def load_standards(paths):
    """Merge stages in file order and reject ambiguous check identities."""
    stages, by_id, check_ids = [], {}, set()
    for path in paths:
        standards = json.loads(path.read_text())
        if standards.get('schema') != 'skin-body-standards/1':
            raise ValueError(f'Unrecognised standards schema: {path}')
        for stage in standards['stages']:
            stage_id = stage['id']
            if stage_id not in by_id:
                by_id[stage_id] = {'id': stage_id, 'checks': []}
                stages.append(by_id[stage_id])
            for check in stage['checks']:
                if check['id'] in check_ids:
                    raise ValueError(f"Duplicate check id: {check['id']}")
                check_ids.add(check['id'])
                if check.get('severity', 'required') not in ('required', 'advisory'):
                    raise ValueError(f"Invalid severity for check {check['id']}")
                by_id[stage_id]['checks'].append(check)
    return stages


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--standards', action='append', metavar='FILE', help='Standards file; repeat to merge files')
    parser.add_argument('--standards-dir', default=str(DEFAULT_STANDARDS.parent), metavar='DIR',
                        help='Directory for default standards and sorted stage fragments')
    parser.add_argument('--evidence', required=True)
    parser.add_argument('--stage', action='append')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    checks, reasons = [], []
    standards_dir = Path(args.standards_dir)
    paths = ([Path(path) for path in args.standards] if args.standards else
             [standards_dir / DEFAULT_STANDARDS.name, *sorted(standards_dir.glob('skin-body-standards.s*.json'))])
    try:
        stages = load_standards(paths)
        evidence = json.loads(Path(args.evidence).read_text())
        if evidence.get('schema') != 'skin-body-evidence/1':
            raise ValueError('Unrecognised evidence schema')
        if not isinstance(evidence.get('subject'), str) or not evidence['subject'].strip() or not isinstance(evidence.get('measurements'), dict) or not isinstance(evidence.get('declared', {}), dict):
            raise ValueError('Invalid subject, measurements, or declarations')
        known = {stage['id'] for stage in stages}
        selected = set(args.stage or known)
        if not selected or not selected <= known:
            raise ValueError('Unknown or empty stage selection')
        scope = evidence.get('stage_scope')
        if scope is not None and (not isinstance(scope, list) or not selected <= set(scope)):
            raise ValueError('Requested stages exceed evidence scope')
        checks = [judge_expanded(c, evidence, NEUTRAL_REGIONS) for stage in stages if stage['id'] in selected for c in stage['checks']]
        if not checks:
            raise ValueError('No checks selected')
        for check in checks:
            if check['severity'] == 'advisory' and check['verdict'] == 'fail':
                check['verdict'] = 'warn'
        required = [c for c in checks if c['severity'] == 'required']
        status = 'fail' if any(c['verdict'] == 'fail' for c in required) else 'unmeasured' if any(c['verdict'] == 'unmeasured' for c in required) else 'pass'
        reasons = [f"{c['id']}: {c['summary']}" for c in checks if c['verdict'] != 'pass']
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        status, reasons = 'unmeasured', [str(exc)]
    envelope = {'kind': 'img2.gate-verdict', 'version': 1, 'gate': 'skin-body', 'plugin': 'character', 'status': status, 'reasons': reasons, 'evidence': {'files': [args.evidence, *map(str, paths)], 'checks': checks, 'ok': status == 'pass'}}
    if args.json:
        print(json.dumps(envelope, allow_nan=False))
    else:
        for check in checks:
            print(f"{check['id']} {check['verdict']}: {check['summary']}")
        print('skin-body gate:', status, '; '.join(reasons))
    return {'pass': 0, 'fail': 1, 'unmeasured': 2}[status]


if __name__ == '__main__':
    sys.exit(main())
