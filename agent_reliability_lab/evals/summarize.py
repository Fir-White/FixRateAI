"""Aggregate completed or partial independent runs without regrading answers."""
import argparse
from collections import Counter
import json
from math import ceil
from pathlib import Path


def percentile(values, fraction):
    return sorted(values)[ceil(fraction * len(values)) - 1] if values else None


def summary(root, planned=None):
    paths = sorted((root / 'run' / 'agent-audit' / 'independent-v3').glob('*.json'))
    cases = [json.loads(path.read_text(encoding='utf-8')) for path in paths]
    protocol_dir = root / 'run' / 'agent-audit' / 'transcripts'
    protocols = [json.loads(path.read_text(encoding='utf-8')) for path in sorted(protocol_dir.glob('*.json'))]
    protocol_turns = [turn for record in protocols for turn in record['turns']]
    turns = [turn for case in cases for turn in case['turns']]
    durations = [turn['seconds'] for turn in turns]
    measured_llm = [turn for turn in turns if 'llm_calls' in turn['metrics']]
    inference_events = [event for turn in turns for event in turn.get('graph_events', [])
                        if event['event'] == 'inference']
    inference_attempts = [event for turn in turns for event in turn.get('graph_events', [])
                          if event['event'] == 'inference_start']
    successful = sum(case['passed'] for case in cases)
    source = root / 'provenance.json'
    run = root / 'summary.json'
    return dict(
        run=str(root), planned=planned, cases_recorded=len(cases), passed=successful,
        failed=len(cases)-successful, pass_rate=successful/len(cases) if cases else None,
        cases_by_role={role: dict(cases=sum(case['role'] == role for case in cases),
                                  passed=sum(case['role'] == role and case['passed'] for case in cases))
                       for role in sorted({case['role'] for case in cases})},
        cases_by_suite={suite: dict(cases=sum(case['suite'] == suite for case in cases),
                                    passed=sum(case['suite'] == suite and case['passed'] for case in cases))
                        for suite in sorted({case['suite'] for case in cases})},
        changed_domain_tables=dict(Counter(table for case in cases for table in case['changed_tables'])),
        turns=len(turns), turns_with_llm_metrics=len(measured_llm),
        turns_with_llm=sum(turn['metrics']['llm_calls'] > 0 for turn in measured_llm),
        totals={key: sum(turn['metrics'].get(key, 0) for turn in turns)
                for key in ('llm_calls', 'llm_requests', 'tool_calls', 'prompt_tokens', 'completion_tokens')},
        traced_inference=dict(started=len(inference_attempts), finished=len(inference_events),
                              completed=sum(item['status'] == 'completed' for item in inference_events),
                              prompt_tokens=sum(int(item['prompt_tokens']) for item in inference_events
                                                if item['prompt_tokens'] != 'None'),
                              completion_tokens=sum(int(item['completion_tokens']) for item in inference_events
                                                    if item['completion_tokens'] != 'None')),
        api_seconds=dict(p50=percentile(durations, .50), p95=percentile(durations, .95)),
        models=dict(Counter(turn['model'] or 'unrecorded' for turn in turns)),
        failures_by_case={case['case']: [failure for turn in case['turns'] for failure in turn['failures']]
                          for case in cases if not case['passed']},
        provenance=json.loads(source.read_text(encoding='utf-8')) if source.is_file() else None,
        runner_result=json.loads(run.read_text(encoding='utf-8')) if run.is_file() else None,
        transcripts=dict(episodes=len(protocols), call_outcomes=dict(Counter(record['outcome'] for record in protocols)),
                         turns=len(protocol_turns),
                         engine_versions=dict(Counter(turn['execution_engine'] for turn in protocol_turns))) if protocols else None,
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--planned', type=int, help='Expected number of independent oracle episode files')
    parser.add_argument('--write', action='store_true')
    options = parser.parse_args()
    result = json.dumps(summary(options.run, options.planned), ensure_ascii=False, indent=2) + '\n'
    if options.write:
        (options.run / 'independent-summary.json').write_text(result, encoding='utf-8')
    else:
        print(result, end='')
