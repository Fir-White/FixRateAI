"""Regrade archived material-selection runs without changing the historical artifacts."""
import argparse
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys


def grade_material_selection(original_grade, case, accepted, answer, workflow, calls, *, changes=False,
                             proposals=False, inferred=True, errors=()):
    """Bind the chosen candidate to its own evidence, independently of tie order."""
    revised = deepcopy(case)
    revised['oracle']['ids'] = ['unverified-materials-selection']
    ranked = next((proof['result']['groups'] for proof in (workflow or {}).get('evidence', [])
                   if proof.get('output_type') == 'aggregate' and proof.get('retained')), [])
    if len(ranked) == 1:
        selected = ranked[0]['id']
        receipt = next((call['result'] for call in calls if call['tool'] == 'task_acceptance_evidence'
                        and call['status'] == 'completed' and call['arguments'].get('path', {}).get('task_id') == selected
                        and call['result'].get('task_id') == selected), {})
        expected = accepted.get(selected)
        if expected and receipt.get('execution_id') == expected['execution_id']:
            observed = set(receipt.get('missing_materials') or []) | set(receipt.get('acceptance_blocks') or [])
            required = set(expected['blockers'])
            if observed and required <= observed and all(item in answer for item in (required or observed)):
                revised['oracle']['ids'] = [selected]
                if expected['execution_id'] is None:
                    revised['oracle'].pop('report', None)
                else:
                    revised['oracle']['report'] = expected['execution_id']
    return original_grade(revised, answer, workflow, calls, changes, proposals, inferred, errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('historical', type=Path)
    parser.add_argument('oracle', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.historical.resolve()):
        parser.error('Output must remain outside the historical experiment')
    contract = json.loads(args.oracle.read_text(encoding='utf-8'))
    sys.path.insert(0, str(args.historical.resolve()))
    original_grade = importlib.import_module('grading').grade
    report = []
    for path in sorted((args.historical / 'traces').glob('*.json')):
        trace = json.loads(path.read_text(encoding='utf-8'))
        case = trace.get('study_case', {})
        if case.get('id') not in contract['cases']:
            continue
        turn = trace['turns'][-1]
        before = trace['grading']
        after = grade_material_selection(original_grade, case, contract['cases'][case['id']],
            turn['answer'], turn.get('workflow'), trace['tool_calls'], changes=trace.get('domain_changes'),
            proposals=trace.get('proposals'), inferred=trace['model_verified'],
            errors=[error for error in before.get('errors', []) if error == 'PROVIDER_ERROR'])
        report.append(dict(cell=trace['cell'], historical=before, revised=after))
    args.output.write_text(json.dumps(dict(version=contract['version'], results=report), ensure_ascii=False, indent=2) + '\n',
                           encoding='utf-8')


if __name__ == '__main__':
    main()
