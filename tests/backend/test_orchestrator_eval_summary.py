"""Evaluation cannot turn completed replies, copied files or weak oracles green."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.summarize_orchestrator_eval import CORE_CASES, default_manifest, distribution, markdown, summarize


MODEL=dict(provider='ollama',model='installed:local',digest='sha256:'+'a'*64)


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def episode(case='A',outcome='passed',status='completed',goals=None,requests=1,**extra):
    state=dict(outcome=status,goals=goals or [dict(id='g',tool='inventory_read',status=status)],metrics=dict(llm_requests=requests))
    value=dict(case=case,outcome=outcome,latency_seconds=1,model='installed:local',
        model_calls=[dict(model='installed:local',seconds=.5,prompt_tokens=10,completion_tokens=2) for _ in range(requests)],
        steps=[dict(kind='answer',status='completed',question='TEST fixed business question',goal_state=state)])
    value.update(extra)
    return value


def run(tmp_path,name,records,*,terminal=True,stable=True,environment=None,exit_code=0):
    root=tmp_path/name;root.mkdir()
    before=dict(files={'tests/test_corpus.py':'c'*64})
    before['sha256']=hashlib.sha256(json.dumps(before['files'],sort_keys=True).encode()).hexdigest()
    after=deepcopy(before)
    if not stable:
        after['files']['tests/test_corpus.py']='d'*64
        after['sha256']=hashlib.sha256(json.dumps(after['files'],sort_keys=True).encode()).hexdigest()
    provenance=dict(source_head='commit',source_sha256=before['sha256'],corpus_files={'tests/test_corpus.py':'c'*64},model=MODEL)
    if environment:provenance.update(environment)
    write(root/'provenance.json',provenance)
    write(root/'source-before.json',before)
    write(root/'source-after.json',after)
    if terminal:write(root/'summary.json',dict(exit_code=exit_code,source_stable=stable,corpus_stable=True))
    for index,record in enumerate(records):write(root/'run/agent-audit'/f'{index}.json',record)
    return root


def manifest(*paths,expected=('A',)):
    return dict(expected_cases=list(expected),cohorts=[dict(id='cohort',runs=[dict(path=str(p)) for p in paths])])


def correction(root,outcome='partial',**extra):
    original=root/'run/agent-audit/0.json'
    value=dict(original_artifact=str(original),original_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
        recorded_outcome='passed',corrected_outcome=outcome,reason='Independent history check rejected an old false positive',oracle_version=2)
    value.update(extra);write(root/'ns01-oracle-correction.json',value)


def test_reply_completion_and_supported_ns01_success_do_not_complete_manufacturer_goal(tmp_path):
    goals=[dict(id='calendar',tool='calendar_evidence',status='completed'),dict(id='history',tool='equipment_service_history',status='completed'),dict(id='manufacturer',tool='',status='blocked')]
    path=run(tmp_path,'ns',[episode(CORE_CASES[1],status='partial',goals=goals,expected_data=dict(manufacturer_document_available=False))])
    result=summarize(manifest(path,expected=(CORE_CASES[1],)))
    row=result['episodes'][0];aggregate=result['cohorts'][0]['aggregate']
    assert row['response_completed'] and row['scenario_oracle_passed']
    assert row['whole_request_completion_observed']=='partial'
    assert row['supported_ns01_checks_passed_with_partial_whole_request']
    assert aggregate['captured_goal_status_counts']=={'completed':2,'blocked':1}


def test_sha_bound_correction_supersedes_raw_pass_without_rewriting_source(tmp_path):
    path=run(tmp_path,'r1',[episode(CORE_CASES[1],status='partial')]);original=path/'run/agent-audit/0.json';before=original.read_bytes()
    correction(path)
    result=summarize(manifest(path,expected=(CORE_CASES[1],)))
    assert result['episodes'][0]['recorded_outcome']=='passed'
    assert result['episodes'][0]['effective_outcome']=='partial'
    assert result['cohorts'][0]['aggregate']['scenario_passed']==0
    assert result['cohorts'][0]['aggregate']['corrected_oracles']==1
    assert original.read_bytes()==before


def test_mismatched_correction_fails_closed(tmp_path):
    path=run(tmp_path,'r1',[episode()]);correction(path,original_sha256='0'*64)
    with pytest.raises(ValueError,match='hash-matching'):
        summarize(manifest(path))


def test_copied_episodes_are_not_counted_as_independent_repetitions(tmp_path):
    value=episode(requests=2)
    first=run(tmp_path,'r1',[value]);second=run(tmp_path,'r2',[deepcopy(value)])
    result=summarize(manifest(first,second))
    assert len(result['episodes'])==1 and len(result['duplicate_files'])==1
    assert result['all_input_unique_recorded_resources']['returned_model_requests']==2
    cohort=result['cohorts'][0]
    assert not cohort['complete_case_records'] and not cohort['one_coherent_frozen_source_and_corpus']


def test_review_attached_to_one_copy_updates_all_cohorts_before_aggregation(tmp_path):
    first=run(tmp_path,'r1',[episode()]);second=run(tmp_path,'r2',[episode()]);correction(second)
    config=dict(expected_cases=['A'],cohorts=[dict(id='r1',runs=[dict(path=str(first))]),dict(id='r2',runs=[dict(path=str(second))])])
    result=summarize(config)
    assert all(c['aggregate']['effective_oracle_counts']=={'partial':1} for c in result['cohorts'])


def test_failed_frozen_round_is_retained_and_latency_includes_failures(tmp_path):
    records=[episode('A',latency_seconds=1),episode('B','failed',latency_seconds=2),episode('C','failed',latency_seconds=3),episode('D','failed',latency_seconds=100)]
    records[-1]['steps'][0]['error_code']='OLLAMA_TIMEOUT'
    path=run(tmp_path,'failed',records,exit_code=1)
    result=summarize(manifest(path,expected=('A','B','C','D')));cohort=result['cohorts'][0]
    assert cohort['aggregate']['effective_oracle_counts']=={'passed':1,'failed':3}
    assert cohort['aggregate']['latency_seconds']['p50']==2.5
    assert cohort['aggregate']['latency_seconds']['p95']==100
    assert cohort['aggregate']['timeout_episodes']==1
    assert cohort['one_coherent_frozen_source_and_corpus']
    assert result['runs'][0]['provenance']['runner_exit_code']==1


def test_timeout_is_not_inferred_from_prose_or_business_code(tmp_path):
    value=episode();value['steps'][0].update(answer='Do not invent OLLAMA_TIMEOUT',actions=[dict(arguments=dict(body=dict(code='TIMEOUT')))])
    result=summarize(manifest(run(tmp_path,'r',[value])))
    assert not result['episodes'][0]['timeout']


def test_attempts_use_state_telemetry_and_never_sum_cumulative_snapshots(tmp_path):
    value=episode(requests=1);value['steps'][0]['goal_state']['metrics']['llm_requests']=3
    result=summarize(manifest(run(tmp_path,'r',[value])))
    assert result['episodes'][0]['returned_model_requests']==1 and result['episodes'][0]['attempted_model_requests']==3
    value['steps'].append(deepcopy(value['steps'][0]))
    result=summarize(manifest(run(tmp_path,'r2',[value])))
    assert result['episodes'][0]['attempted_model_requests'] is None
    assert result['episodes'][0]['attempted_requests_lower_bound']==3
    assert result['cohorts'][0]['aggregate']['returned_model_requests']==1


def test_no_attempt_telemetry_is_unknown_not_zero(tmp_path):
    value=episode();value['steps'][0].pop('goal_state')
    result=summarize(manifest(run(tmp_path,'r',[value])))
    assert result['cohorts'][0]['aggregate']['attempted_model_requests'] is None
    assert result['episodes'][0]['whole_request_completion_observed']=='unmeasured'


def test_missing_cases_and_nonterminal_run_are_explicit(tmp_path):
    path=run(tmp_path,'interrupted',[episode()],terminal=False)
    result=summarize(manifest(path,expected=('A','B')));cohort=result['cohorts'][0]
    assert cohort['selections'][0]['missing_cases']==['B']
    assert not cohort['complete_case_records'] and not cohort['one_coherent_frozen_source_and_corpus']
    assert result['episodes'][0]['returned_model_requests']==1


def test_case_exclusion_requires_reason_and_excluded_costs_remain_visible(tmp_path):
    path=run(tmp_path,'r',[episode('A'),episode('B','failed')])
    config=manifest(path);config['cohorts'][0]['runs'][0]['cases']=['A']
    with pytest.raises(ValueError,match='exclusions require'):
        summarize(config)
    config['cohorts'][0]['runs'][0]['exclusion_reason']='Separate stronger oracle execution is the selected B cohort'
    result=summarize(config)
    assert result['cohorts'][0]['aggregate']['returned_model_requests']==1
    assert result['all_input_unique_recorded_resources']['returned_model_requests']==2
    assert result['cohorts'][0]['selections'][0]['excluded_cases']==['B']


def test_failed_data_oracle_overrules_incorrect_completed_goal_state(tmp_path):
    result=summarize(manifest(run(tmp_path,'r',[episode(outcome='failed')])))
    row=result['episodes'][0]
    assert row['captured_completed_state_contradicted_by_oracle']
    assert row['whole_request_completion_observed']!='completed'


def test_preconfirmation_state_is_not_misrepresented_after_sql_receipts(tmp_path):
    value=episode(CORE_CASES[2],status='awaiting_confirmation')
    value['steps'] += [dict(kind='confirmed-and-replayed',equipment_id=identity) for identity in ('one','two')]
    result=summarize(manifest(run(tmp_path,'r',[value]),expected=(CORE_CASES[2],)))
    row=result['episodes'][0]
    assert row['scenario_oracle_passed'] and row['recorded_confirmation_postconditions']==2
    assert row['goal_snapshot_precedes_recorded_confirmations'] and row['whole_request_completion_observed']=='awaiting_confirmation'


def test_unknown_environment_is_not_assumed_equal_and_fixture_hash_is_not_data_snapshot(tmp_path):
    first=run(tmp_path,'r1',[episode()],environment=dict(python_version='3.11'))
    value=episode();value['at']='another independent episode'
    second=run(tmp_path,'r2',[value])
    result=summarize(manifest(first,second));cohort=result['cohorts'][0]
    assert cohort['environment_consistent'] is None
    assert any('random UUID' in note for note in cohort['limitations'])
    assert all(row['actual_dataset_snapshot_sha256'] is None for row in result['episodes'])


def test_measured_environment_difference_is_preserved(tmp_path):
    first=run(tmp_path,'r1',[episode()],environment=dict(python_version='3.11'))
    value=episode();value['at']='different'
    second=run(tmp_path,'r2',[value],environment=dict(python_version='3.14'))
    result=summarize(manifest(first,second))
    assert result['cohorts'][0]['environment_consistent'] is False
    assert {r['provenance']['environment']['python_version'] for r in result['runs']}=={'3.11','3.14'}


def test_model_mismatch_and_source_drift_cannot_be_frozen(tmp_path):
    value=episode();value['model_calls'][0]['model']='other:model'
    path=run(tmp_path,'r',[value],stable=False)
    result=summarize(manifest(path))
    assert result['runs'][0]['provenance']['actual_model_mismatch_cases']==['A']
    assert not result['cohorts'][0]['one_coherent_frozen_source_and_corpus']


def test_equal_but_tampered_source_manifests_are_not_a_frozen_proof(tmp_path):
    path=run(tmp_path,'r',[episode()])
    value=json.loads((path/'source-before.json').read_text());value['files']['tests/test_corpus.py']='0'*64
    write(path/'source-before.json',value);write(path/'source-after.json',value)
    result=summarize(manifest(path))
    assert result['runs'][0]['provenance']['source_stable_computed']
    assert not result['runs'][0]['provenance']['source_manifest_integrity']
    assert not result['cohorts'][0]['one_coherent_frozen_source_and_corpus']


def test_known_injected_failure_keeps_unfinished_point_without_old_goal_state(tmp_path):
    value=episode(CORE_CASES[3],injected_failures=1);value['steps'][0].pop('goal_state')
    result=summarize(manifest(run(tmp_path,'r',[value]),expected=(CORE_CASES[3],)))
    assert result['episodes'][0]['scenario_oracle_passed']
    assert result['episodes'][0]['whole_request_completion_observed']=='partial'


def test_source_claim_must_match_captured_manifest(tmp_path):
    path=run(tmp_path,'r',[episode()])
    value=json.loads((path/'provenance.json').read_text());value['source_sha256']='0'*64
    write(path/'provenance.json',value)
    result=summarize(manifest(path))
    assert result['runs'][0]['provenance']['source_manifest_integrity']
    assert not result['runs'][0]['provenance']['source_claim_matches_manifest']
    assert not result['cohorts'][0]['one_coherent_frozen_source_and_corpus']


def test_worktree_paths_do_not_turn_equal_fixture_content_into_different_versions(tmp_path):
    first=run(tmp_path,'r1',[episode()]);value=episode();value['at']='independent'
    second=run(tmp_path,'r2',[value])
    for root,prefix in ((first,'C:/baseline'),(second,'D:/changed')):
        provenance=json.loads((root/'provenance.json').read_text())
        provenance['corpus_files']={prefix+'/tests/test_corpus.py':'c'*64}
        write(root/'provenance.json',provenance)
    config=dict(expected_cases=['A'],cohorts=[dict(id='old',runs=[dict(path=str(first))]),dict(id='new',runs=[dict(path=str(second))])])
    result=summarize(config)
    assert result['comparisons'][0]['corpus_file_versions_equal'] is True
    provenance=json.loads((first/'provenance.json').read_text());provenance['corpus_files']={}
    write(first/'provenance.json',provenance)
    assert summarize(config)['comparisons'][0]['corpus_file_versions_equal'] is None


def test_case_prompt_comparison_does_not_assert_dataset_equality(tmp_path):
    first=run(tmp_path,'r1',[episode()]);value=episode();value['at']='new execution'
    second=run(tmp_path,'r2',[value])
    result=summarize(dict(expected_cases=['A'],cohorts=[dict(id='before',runs=[dict(path=str(first))]),dict(id='after',runs=[dict(path=str(second))])]))
    comparison=result['comparisons'][0]
    assert comparison['case_prompts_equal'] is True and comparison['model_configuration_equal'] is True
    assert comparison['causal_latency_improvement'] is None and 'unmeasured' in comparison['actual_dataset_equality']


def test_default_discovery_keeps_all_exploratory_rounds(tmp_path):
    workspace=tmp_path/'work';reports=workspace/'reports';reports.mkdir(parents=True)
    for n in (1,2,3):(reports/f'orchestrator-live-r{n}').mkdir()
    config=default_manifest(workspace)
    assert [row['id'] for row in config['cohorts']]==['orchestrator-live-r1','orchestrator-live-r2','orchestrator-live-r3']


def test_report_is_explicit_about_limits_and_p95_method(tmp_path):
    result=summarize(manifest(run(tmp_path,'r',[episode()])))
    text=markdown(result)
    assert 'промышленной' in text and 'nearest-rank' in text
    assert distribution(range(1,21))['p95']==19
