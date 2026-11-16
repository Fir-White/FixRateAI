"""Review saved agent episodes without inference, network access or runtime edits.

The scenario oracle, reply transport and captured user-goal state are different
measurements. Failed and incomplete runs stay visible. SHA-bound review sidecars
supersede an oracle interpretation without rewriting its original artifact.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics


ROOT = Path(__file__).resolve().parents[1]
CORE_CASES = (
    'ORCH-A01-inventory-regulations-gaps',
    'ORCH-B01-nc01-period-history-manufacturer',
    'ORCH-C05-two-independent-proposals',
    'ORCH-D05-independent-goal-after-backend-failure',
)
FIXTURE_FILES = ('tests/backend/test_assistant_orchestrator_live.py',
                 'tests/backend/test_agent_redteam_live.py',
                 'tests/backend/test_management.py',
                 'tests/backend/test_runtime_integration.py')
ENVIRONMENT_FIELDS = ('python', 'python_version', 'python_executable', 'packages',
                      'platform', 'hardware', 'timeout_seconds', 'num_ctx')


def _json(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_valid(value):
    if not isinstance(value,dict) or not isinstance(value.get('files'),dict):return False
    if not all(isinstance(key,str) and isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest) for key,digest in value['files'].items()):return False
    return value.get('sha256')==hashlib.sha256(json.dumps(value['files'],sort_keys=True).encode()).hexdigest()


def _signature(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _corpus_version(files):
    """Compare fixture contents across worktrees while retaining raw input paths."""
    result = {}
    for name, digest in files.items():
        name = name.replace('\\', '/')
        relative = 'tests/' + name.split('/tests/', 1)[1] if '/tests/' in name else name
        if relative in result and result[relative] != digest:
            raise ValueError('Conflicting corpus file hashes: ' + relative)
        result[relative] = digest
    return result


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def distribution(values):
    """p95 is the nearest rank: ceil(.95*n), with failed episodes included."""
    values = sorted(float(value) for value in values if _number(value))
    return dict(n=len(values), p50=statistics.median(values) if values else None,
                p95=values[math.ceil(.95 * len(values)) - 1] if values else None,
                worst=max(values) if values else None, method='median; p95 nearest-rank ceil(0.95*n)')


def _states(record):
    return [step.get('goal_state') or step.get('workflow') or step.get('task_state')
            for step in record.get('steps', []) if isinstance(step, dict)
            and isinstance(step.get('goal_state') or step.get('workflow') or step.get('task_state'), dict)]


def _timeout(record):
    def code(value):return isinstance(value, str) and bool(re.search(r'(?:^|_)(?:TIMEOUT|TIMED_OUT)(?:$|_)', value.upper()))
    def trace(rows):
        return any(isinstance(row, dict) and
                   (any(code(row.get(key)) for key in ('error_code', 'code', 'error_type')) or trace(row.get('attempts', [])))
                   for row in rows)
    # Never inspect answer prose, user arguments or business result.code fields.
    return code(record.get('error_code')) or any(code(step.get('error_code')) or trace(step.get('trace', []))
        or code((step.get('goal_state') or {}).get('stop_reason'))
        for step in record.get('steps', []) if isinstance(step, dict))


def _episode(path):
    record = _json(path)
    if not isinstance(record, dict) or not isinstance(record.get('case'), str) or 'outcome' not in record:
        return None
    answers = [step for step in record.get('steps', []) if isinstance(step, dict) and step.get('kind') == 'answer']
    states = _states(record)
    latest = states[-1] if states else None
    calls = [call for call in record.get('model_calls', []) if isinstance(call, dict)]
    requests = [state.get('metrics', {}).get('llm_requests') for state in states]
    requests = [value for value in requests if type(value) is int and value >= 0]
    # Multiple snapshots can be cumulative. Do not sum them into invented attempts.
    attempted = requests[0] if len(states) == 1 and len(requests) == 1 and requests[0] >= len(calls) else None
    confirmations = {step.get('equipment_id') for step in record.get('steps', [])
                     if isinstance(step, dict) and step.get('kind') == 'confirmed-and-replayed' and step.get('equipment_id')}
    questions = [step['question'] for step in answers if isinstance(step.get('question'), str)]
    return dict(id=_hash(path), case=record['case'], paths=[str(path.resolve())],
                recorded_outcome=record['outcome'], effective_outcome=record['outcome'], corrections=[],
                response_completed=all(step.get('status') == 'completed' for step in answers) if answers else None,
                response_statuses=[step.get('status') for step in answers],
                error_codes=[step.get('error_code') for step in answers if step.get('error_code')],
                captured_goal_outcome=latest.get('outcome') if latest else None,
                captured_goals=[{key: goal.get(key) for key in ('id', 'tool', 'status', 'reason', 'action_id', 'pending_action_id')
                                if key in goal} for goal in latest.get('goals', [])] if latest else [],
                captured_goal_status_counts=dict(Counter(goal.get('status', 'unknown') for goal in latest.get('goals', []))) if latest else {},
                goal_metrics_observations=[state.get('metrics', {}) for state in states],
                recorded_confirmation_postconditions=len(confirmations),
                goal_snapshot_precedes_recorded_confirmations=bool(confirmations and latest and
                    not any(step.get('kind')=='final-goal-state' and isinstance(step.get('goal_state'),dict) for step in record.get('steps',[]) if isinstance(step,dict))),
                latency_seconds=record.get('latency_seconds') if _number(record.get('latency_seconds')) else None,
                timeout=_timeout(record), returned_model_requests=len(calls),
                attempted_model_requests=attempted,
                attempted_requests_lower_bound=max([len(calls), *requests]),
                attempted_request_metric_observations=requests,
                returned_request_latency=distribution(call.get('seconds') for call in calls),
                returned_prompt_tokens_known=sum(call['prompt_tokens'] for call in calls if type(call.get('prompt_tokens')) is int and call['prompt_tokens'] >= 0),
                returned_completion_tokens_known=sum(call['completion_tokens'] for call in calls if type(call.get('completion_tokens')) is int and call['completion_tokens'] >= 0),
                token_observed_requests=sum(type(call.get('prompt_tokens')) is int and type(call.get('completion_tokens')) is int for call in calls),
                case_prompt_sha256=hashlib.sha256(_signature(questions).encode()).hexdigest() if questions else None,
                actual_dataset_snapshot_sha256=record.get('actual_dataset_snapshot_sha256'),
                manufacturer_document_available=(record.get('expected_data') or {}).get('manufacturer_document_available'),
                strict_history_oracle_recorded=isinstance(record.get('history_oracle'), dict),
                injected_failures=record.get('injected_failures') if type(record.get('injected_failures')) is int else None,
                imported_service_file=record.get('imported_service_file'),
                actual_model_names=sorted({str(call['model']) for call in calls if call.get('model')}),
                declared_episode_model=record.get('model'))


def _apply_review(row, correction, source):
    if correction.get('original_sha256') != row['id']:
        raise ValueError('Oracle correction hash does not match original artifact: ' + str(source))
    if correction.get('recorded_outcome') not in (None, row['recorded_outcome']):
        raise ValueError('Oracle correction does not identify the recorded outcome: ' + str(source))
    outcome = correction.get('corrected_outcome')
    if outcome not in ('passed', 'failed', 'partial', 'blocked', 'not_run'):
        raise ValueError('Unknown corrected oracle outcome: ' + str(source))
    if row['corrections'] and row['effective_outcome'] != outcome:
        raise ValueError('Conflicting oracle corrections need explicit review: ' + str(source))
    row['effective_outcome'] = outcome
    row['corrections'].append(dict(path=str(source), sha256=_hash(source) if Path(source).is_file() else None,
                                  outcome=outcome, reason=correction.get('reason'),
                                  oracle_version=correction.get('oracle_version'), reviewed_at=correction.get('reviewed_at')))


def _goal_interpretation(row):
    outcome = row['captured_goal_outcome']
    goals = row['captured_goals']
    # A passed supported NS-01 oracle does not invent the missing manufacturer document.
    if row['case'] == CORE_CASES[1] and row['manufacturer_document_available'] is False:
        completion = 'partial'
    elif row['case'] == CORE_CASES[3] and row['injected_failures']:
        completion = 'partial'
    elif outcome == 'completed' and goals and all(goal.get('status') == 'completed' for goal in goals) and row['effective_outcome'] == 'passed':
        completion = 'completed'
    elif outcome in ('partial', 'blocked', 'planned', 'running', 'awaiting_confirmation', 'cancelled'):
        completion = outcome
    elif row['effective_outcome'] == 'failed':
        completion = 'not_achieved_by_scenario_oracle'
    else:
        completion = 'unmeasured'
    row['whole_request_completion_observed'] = completion
    row['scenario_oracle_passed'] = row['effective_outcome'] == 'passed'
    row['captured_completed_state_contradicted_by_oracle'] = outcome == 'completed' and row['effective_outcome'] != 'passed'
    row['supported_ns01_checks_passed_with_partial_whole_request'] = row['case'] == CORE_CASES[1] and row['effective_outcome'] == 'passed' and completion == 'partial'


def load_run(directory):
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise ValueError('Run directory does not exist: ' + str(directory))
    provenance = _json(directory / 'provenance.json') or {}
    summary = _json(directory / 'summary.json') or {}
    before, after = _json(directory / 'source-before.json'), _json(directory / 'source-after.json')
    episodes = [row for path in sorted((directory / 'run/agent-audit').glob('*.json')) if (row := _episode(path))]
    for source in sorted(directory.glob('*correction*.json')):
        correction = _json(source)
        if not isinstance(correction, dict) or 'corrected_outcome' not in correction:
            continue
        filename = str(correction.get('original_artifact', '')).replace('\\', '/').rsplit('/', 1)[-1]
        matches = [row for row in episodes if Path(row['paths'][0]).name == filename and row['id'] == correction.get('original_sha256')]
        if len(matches) != 1:
            raise ValueError('Correction has no unique hash-matching original in this run: ' + str(source))
        _apply_review(matches[0], correction, source)
    for row in episodes:
        _goal_interpretation(row)
    environment = {key: provenance[key] for key in ENVIRONMENT_FIELDS if key in provenance}
    saved_environment = _json(directory / 'environment.json') or {}
    environment.update({key: saved_environment[key] for key in ENVIRONMENT_FIELDS if key in saved_environment})
    computed_stable = (before.get('sha256') == after.get('sha256') and before.get('files') == after.get('files')) if before and after else None
    declared_model=(provenance.get('model') or {}).get('model')
    mismatches=[row['case'] for row in episodes if declared_model and any(name!=declared_model for name in row['actual_model_names'])]
    return dict(id=str(directory), path=str(directory), episodes=episodes,
                provenance=dict(source_root=provenance.get('source_root'), source_head=provenance.get('source_head'),
                    source_sha256=provenance.get('source_sha256'), runner_sha256=provenance.get('runner_sha256'),
                    corpus_files=provenance.get('corpus_files', {}), model=provenance.get('model'),
                    environment=environment, fixture_code_hashes={key: before.get('files', {}).get(key) for key in FIXTURE_FILES} if before else {},
                    source_stable_reported=summary.get('source_stable'), source_stable_computed=computed_stable,
                    source_manifest_integrity=_manifest_valid(before) and _manifest_valid(after),
                    source_claim_matches_manifest=provenance.get('source_sha256') == before.get('sha256') if before else None,
                    corpus_stable_reported=summary.get('corpus_stable'), actual_model_mismatch_cases=mismatches,
                    runner_exit_code=summary.get('exit_code'), terminal_runner_record=bool(summary),
                    started_at=provenance.get('started_at'), completed_at=summary.get('completed_at'),
                    local_network_guard=provenance.get('local_network_guard'), automatic_downloads=provenance.get('automatic_downloads')),
                limitations=(['No recorded Python/dependency environment; equality with another run is unmeasured.'] if not environment else []) +
                    (['Source manifest integrity is unavailable or inconsistent.'] if not _manifest_valid(before) or not _manifest_valid(after) else []) +
                    (['Declared source SHA does not match the captured source manifest.'] if before and provenance.get('source_sha256') != before.get('sha256') else []) +
                    (['Runner has no terminal summary; partial artifacts are not a completed round.'] if not summary else []) +
                    (['Source changed during the run.'] if summary.get('source_stable') is False or computed_stable is False else []) +
                    (['Corpus changed during the run.'] if summary.get('corpus_stable') is False else []) +
                    (['Returned model names disagree with the declared run model.'] if mismatches else []))


def _aggregate(rows):
    attempts = [row['attempted_model_requests'] for row in rows]
    return dict(episodes=len(rows), recorded_oracle_counts=dict(Counter(row['recorded_outcome'] for row in rows)),
                effective_oracle_counts=dict(Counter(row['effective_outcome'] for row in rows)),
                scenario_passed=sum(row['scenario_oracle_passed'] for row in rows),
                responses_completed=sum(row['response_completed'] is True for row in rows),
                response_status_unmeasured=sum(row['response_completed'] is None for row in rows),
                whole_request_completion_observed=dict(Counter(row['whole_request_completion_observed'] for row in rows)),
                captured_goal_status_counts=dict(sum((Counter(row['captured_goal_status_counts']) for row in rows), Counter())),
                corrected_oracles=sum(bool(row['corrections']) for row in rows),
                completed_state_oracle_disagreements=sum(row['captured_completed_state_contradicted_by_oracle'] for row in rows),
                returned_model_requests=sum(row['returned_model_requests'] for row in rows),
                attempted_model_requests=sum(attempts) if rows and all(value is not None for value in attempts) else None,
                attempted_metric_covered_episodes=sum(value is not None for value in attempts),
                attempted_requests_lower_bound=sum(row['attempted_requests_lower_bound'] for row in rows),
                latency_seconds=distribution(row['latency_seconds'] for row in rows),
                timeout_episodes=sum(row['timeout'] for row in rows),
                returned_prompt_tokens_known=sum(row['returned_prompt_tokens_known'] for row in rows),
                returned_completion_tokens_known=sum(row['returned_completion_tokens_known'] for row in rows),
                token_observed_requests=sum(row['token_observed_requests'] for row in rows))


def summarize(manifest, base_dir=ROOT):
    """Summarize explicit cohorts, preserving every run and non-selected artifact."""
    expected_default = manifest.get('expected_cases', list(CORE_CASES))
    runs = {}; all_rows = {}; duplicate_files = []
    def read(spec):
        path = Path(spec['path'])
        path = path.resolve() if path.is_absolute() else (Path(base_dir) / path).resolve()
        if str(path) not in runs:
            run = load_run(path)
            for row in run['episodes']:
                if row['id'] in all_rows:
                    existing = all_rows[row['id']]
                    if existing['corrections'] and row['corrections'] and existing['effective_outcome'] != row['effective_outcome']:
                        raise ValueError('Copied artifact has conflicting corrected outcomes')
                    if row['corrections'] and not existing['corrections']:
                        existing['effective_outcome']=row['effective_outcome'];existing['corrections']=row['corrections']
                        _goal_interpretation(existing)
                    duplicate_files.append(dict(path=row['paths'][0], duplicate_of=existing['paths'][0], sha256=row['id']))
                    existing['paths'].extend(row['paths'])
                else:
                    all_rows[row['id']] = row
            runs[str(path)] = run
        return runs[str(path)]
    # Load/review every physical input before calculating any cohort: a valid
    # correction attached to a copied artifact applies to that same SHA globally.
    for cohort in manifest.get('cohorts', []):
        for spec in cohort['runs']:read(spec)
    for spec in manifest.get('diagnostic_runs', []):read(spec)
    cohorts = []
    for spec in manifest.get('cohorts', []):
        rows = []; seen = set(); selections = []; selected_runs = []; expected_count = 0; duplicates = []
        expected = spec.get('expected_cases', expected_default)
        for selection in spec['runs']:
            run = read(selection); selected_runs.append(run)
            requested = selection.get('cases', expected)
            expected_count += len(requested)
            excluded = [row['case'] for row in run['episodes'] if row['case'] not in requested]
            if excluded and not selection.get('exclusion_reason'):
                raise ValueError('Case exclusions require an explicit reason: ' + run['path'])
            present = []
            for raw in run['episodes']:
                if raw['case'] not in requested:
                    continue
                row = all_rows[raw['id']]
                if row['id'] in seen:
                    duplicates.append(row['id']);continue
                seen.add(row['id']);rows.append(row);present.append(row['case'])
            selections.append(dict(run=run['id'], requested_cases=requested, selected_cases=present,
                                   missing_cases=sorted(set(requested) - set(present)), excluded_cases=excluded,
                                   exclusion_reason=selection.get('exclusion_reason')))
        hashes = {run['provenance']['source_sha256'] for run in selected_runs if run['provenance']['source_sha256']}
        models = {_signature(run['provenance']['model']) for run in selected_runs if run['provenance']['model']}
        corpus = {_signature(_corpus_version(run['provenance']['corpus_files'])) for run in selected_runs if run['provenance']['corpus_files']}
        environments = {_signature(run['provenance']['environment']) for run in selected_runs if run['provenance']['environment']}
        complete = len(rows) == expected_count and not duplicates and all(not item['missing_cases'] for item in selections)
        coherent = complete and bool(selected_runs) and len(hashes) == 1 and len(models) == 1 and len(corpus) == 1 and all(
            run['provenance']['terminal_runner_record'] and run['provenance']['source_stable_reported'] is True
            and run['provenance']['source_stable_computed'] is True and run['provenance']['corpus_stable_reported'] is True
            and run['provenance']['source_manifest_integrity'] is True
            and run['provenance']['source_claim_matches_manifest'] is True
            and run['provenance']['source_sha256'] is not None
            and not run['provenance']['actual_model_mismatch_cases']
            and re.fullmatch(r'sha256:[0-9a-f]{64}',(run['provenance']['model'] or {}).get('digest','')) is not None
            for run in selected_runs)
        limits = list(spec.get('limitations', []))
        if len(selected_runs) > 1 and any('cases' in item for item in spec['runs']):
            limits.append('Assembled from separate executions; not one frozen full-corpus run.')
            coherent = False
        if not all(run['provenance']['environment'] for run in selected_runs):
            limits.append('Environment comparability is unmeasured; do not attribute timing differences solely to architecture.')
        if not all(row['actual_dataset_snapshot_sha256'] for row in rows):
            limits.append('Fixture code/prompt hashes are not actual database snapshot hashes; random UUID fixtures are not claimed byte-identical.')
        if any(row['case'] == CORE_CASES[1] and row['scenario_oracle_passed'] and row['whole_request_completion_observed'] == 'partial' for row in rows):
            limits.append('NS-01 supported calendar/history acceptance can pass while manufacturer verification remains an explicitly unfinished goal.')
        if any(row['goal_snapshot_precedes_recorded_confirmations'] for row in rows):
            limits.append('Write goal-state snapshots precede recorded confirmation/replay SQL checks; final persisted completion was not captured.')
        cohorts.append(dict(id=spec['id'], architecture=spec.get('architecture'), expected_episodes=expected_count,
                            selections=selections, episode_ids=[row['id'] for row in rows], aggregate=_aggregate(rows),
                            complete_case_records=complete, duplicate_episode_references=duplicates,
                            one_coherent_frozen_source_and_corpus=coherent,
                            environment_consistent=(len(environments)==1) if selected_runs and all(run['provenance']['environment'] for run in selected_runs) else None,
                            source_hashes=sorted(hashes), model_configurations=[json.loads(value) for value in sorted(models)],
                            model_configuration_coverage_complete=bool(selected_runs) and all(run['provenance']['model'] for run in selected_runs),
                            corpus_versions=[json.loads(value) for value in sorted(corpus)],
                            corpus_version_coverage_complete=bool(selected_runs) and all(run['provenance']['corpus_files'] for run in selected_runs),
                            limitations=limits))
    diagnostics = []
    for spec in manifest.get('diagnostic_runs', []):
        run = read(spec)
        diagnostics.append(dict(run=run['id'], exclusion_reason=spec['reason']))
    # Corrections are interpretation, not additional inference. A copied JSON is
    # still one physical recorded episode even if referenced by multiple cohorts.
    resources=_aggregate(list(all_rows.values()))
    resources={key:resources[key] for key in ('episodes','returned_model_requests','attempted_model_requests',
        'attempted_metric_covered_episodes','attempted_requests_lower_bound','timeout_episodes',
        'returned_prompt_tokens_known','returned_completion_tokens_known','token_observed_requests')}
    comparisons=[]
    if cohorts:
        reference=cohorts[0]
        for cohort in cohorts[1:]:
            def prompts(item):
                result={}
                for identity in item['episode_ids']:
                    row=all_rows[identity]
                    result.setdefault(row['case'],set()).add(row['case_prompt_sha256'])
                return result
            left,right=prompts(reference),prompts(cohort)
            common=set(left)&set(right)
            complete_prompts=bool(common) and set(left)==set(right) and all(None not in left[key]|right[key] for key in common)
            comparisons.append(dict(reference=reference['id'],cohort=cohort['id'],
                model_configuration_equal=reference['model_configurations']==cohort['model_configurations'] if reference['model_configuration_coverage_complete'] and cohort['model_configuration_coverage_complete'] else None,
                case_prompts_equal=all(left[key]==right[key] for key in common) if complete_prompts else None,
                corpus_file_versions_equal=reference['corpus_versions']==cohort['corpus_versions'] if reference['corpus_version_coverage_complete'] and cohort['corpus_version_coverage_complete'] else None,
                actual_dataset_equality='unmeasured; fixture code hashes are not data snapshots',
                causal_latency_improvement=None,
                limitation='Code/oracle/environment/data conditions are not assumed equivalent; raw timings and acceptance counts are reported separately.'))
    return dict(version=1, generated_at_utc=datetime.now(timezone.utc).isoformat(), cohorts=cohorts, comparisons=comparisons,
                runs=[{**run, 'episodes':[row['id'] for row in run['episodes']]} for run in runs.values()],
                episodes=list(all_rows.values()), duplicate_files=duplicate_files, diagnostic_runs=diagnostics,
                all_input_unique_recorded_resources=resources,
                limitations=[
                    'Scenario acceptance, completed reply transport and resolution of every user objective are distinct measurements.',
                    'Recorded model_calls measure returned inference responses; missing attempted-request telemetry is null, not zero.',
                    'No universal groundedness, hallucination, security or industrial-readiness rate is inferred.',
                    'No automatic latency-improvement percentage is computed across differing code/corpus/environment/data conditions.',
                ])


def default_manifest(workspace=ROOT, baseline_root=None, additional_runs=()):
    workspace = Path(workspace).resolve()
    baseline_root = Path(baseline_root).resolve() if baseline_root else workspace.parents[1] if workspace.parent.name == '.worktrees' else None
    manifest = dict(version=1, expected_cases=list(CORE_CASES), cohorts=[], diagnostic_runs=[])
    if baseline_root:
        baseline = baseline_root / 'reports'
        main = baseline / 'orchestrator-baseline-compound-20261116b'
        strict = baseline / 'orchestrator-baseline-nc01-strict-20261116'
        if main.is_dir() and strict.is_dir():
            manifest['cohorts'].append(dict(id='baseline-strict-four-assembled', architecture='baseline', runs=[
                dict(path=str(main), cases=[CORE_CASES[i] for i in (0, 2, 3)],
                     exclusion_reason='The earlier NS-01 oracle was weak and contradicted by its answer; use the separate strict NS-01 execution.'),
                dict(path=str(strict), cases=[CORE_CASES[1]])],
                limitations=['A01/C05/D05 and strict NS-01 were executed separately, not as one frozen four-case baseline.']))
        for path in sorted(baseline.glob('orchestrator-baseline-*')):
            if path not in (main, strict) and path.is_dir():
                manifest['diagnostic_runs'].append(dict(path=str(path), reason='Historical setup failure or different six-case corpus; retained as diagnostic input, not a strict four-case comparison.'))
    paths = [path for path in (workspace / 'reports').glob('orchestrator-live-r*') if re.fullmatch(r'orchestrator-live-r\d+', path.name)]
    paths += [Path(path).resolve() for path in additional_runs]
    for path in sorted(set(paths), key=lambda value: (int(re.search(r'r(\d+)$', value.name)[1]) if re.search(r'r(\d+)$', value.name) else 10**9, value.name)):
        manifest['cohorts'].append(dict(id=path.name, architecture='changed', runs=[dict(path=str(path))]))
    return manifest


def markdown(result):
    lines = ['# Проверка сохранённых испытаний оркестратора', '',
             'Приёмка сценария, завершение ответа и выполнение всех пунктов поручения учитываются отдельно.', '',
             '| Когорта | Эпизоды | Приёмка passed / failed / partial | Ответ completed | Полученные inference | p50 / p95 / max, с | Тайм-ауты | Единый frozen-срез |',
             '|---|---:|---:|---:|---:|---:|---:|---|']
    def display(value):return '—' if value is None else f'{value:.3f}'
    for cohort in result['cohorts']:
        data = cohort['aggregate'];outcomes = data['effective_oracle_counts'];latency = data['latency_seconds']
        lines.append(f"| {cohort['id']} | {data['episodes']}/{cohort['expected_episodes']} | {outcomes.get('passed',0)} / {outcomes.get('failed',0)} / {outcomes.get('partial',0)} | {data['responses_completed']} | {data['returned_model_requests']} | {display(latency['p50'])} / {display(latency['p95'])} / {display(latency['worst'])} | {data['timeout_episodes']} | {'да' if cohort['one_coherent_frozen_source_and_corpus'] else 'нет'} |")
    lines += ['', 'P95: nearest-rank `ceil(0.95*n)`; задержки включают неуспешные эпизоды. Число inference относится к полученным ответам; попытки без полной телеметрии остаются неизвестными.', '']
    for cohort in result['cohorts']:
        lines += [f"**{cohort['id']}**: состояния поручений — `{_signature(cohort['aggregate']['whole_request_completion_observed'])}`."]
        lines.extend('- ' + note for note in cohort['limitations'])
        lines.append('')
    corrections = [row for row in result['episodes'] if row['corrections']]
    if corrections:
        lines += ['Исправленные oracle (оригинальные артефакты сохранены):', '']
        lines.extend(f"- `{row['case']}`: {row['recorded_outcome']} → {row['effective_outcome']}; SHA `{row['id']}`." for row in corrections)
    lines += ['', f"Уникальных входных эпизодов: {len(result['episodes'])}; копий файлов исключено из сумм: {len(result['duplicate_files'])}.",
              'Это отчёт по сохранённым проверкам, а не доказательство готовности всех пользовательских операций к промышленной эксплуатации.', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, help='Explicit cohorts/runs/case exclusions with reasons')
    parser.add_argument('--baseline-root', type=Path)
    parser.add_argument('--new-run', type=Path, action='append', default=[], help='Additional run, including a frozen repetition; existing exploratory rounds remain included')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / 'reports'):
        parser.error('Derived reports must stay under this worktree reports/')
    manifest = _json(args.manifest) if args.manifest else default_manifest(ROOT, args.baseline_root, args.new_run)
    base_dir = args.manifest.resolve().parent if args.manifest else ROOT
    # The saved manifest remains independently replayable from its new location.
    for spec in [item for cohort in manifest.get('cohorts', []) for item in cohort['runs']] + manifest.get('diagnostic_runs', []):
        path = Path(spec['path'])
        spec['path'] = str(path.resolve() if path.is_absolute() else (base_dir / path).resolve())
    result = summarize(manifest, base_dir)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (output / 'summary.md').write_text(markdown(result), encoding='utf-8')
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(output=str(output), cohorts=len(result['cohorts']), unique_episodes=len(result['episodes']),
                          duplicate_files=len(result['duplicate_files']), new_inference_requests=0), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
