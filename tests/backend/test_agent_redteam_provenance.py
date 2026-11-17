"""Adversarial tool-result faults layered over REAL PostgreSQL reads, not positive data stubs."""
import asyncio
from types import SimpleNamespace
import pytest
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed
from tests.backend.test_assistant import assistant_case
from tests.backend.test_assistant_task_analytics import add_orders,report_principal
from app.assistant.tools import available
from app.assistant.task_report import report

FAULTS=('all_counter','unfinished_counter','due_sum','norm_sum','date_count','date_total','operation_sum','duplicate_groups','clock_date','snapshot_shape',
    'summary_shape','bool_scanned','date_row_shape','equipment_row_shape','duplicate_row_shape','page_items_shape','scope_origin','scope_cohort','stale_clock','nonfinite_hours')

@pytest.mark.parametrize('fault',FAULTS)
def test_contradictory_analysis_cannot_be_reported_as_complete(assistant_case,monkeypatch,fault):
    from app.assistant import read_transport
    add_orders(assistant_case,[dict(),dict()])
    _,app,client,_,_=assistant_case;original=read_transport.invoke
    principal=report_principal(assistant_case)
    headers={'cookie':'; '.join(f'{k}={v}' for k,v in client.cookies.items())}
    baseline=asyncio.run(report(app,available(app,'admin')['tasks_analyze'],headers,[],lambda:None,
        'Проанализируй все незавершённые задания',principal))
    assert 'Всего записей' in baseline and 'Полный анализ не выполнен' not in baseline,'Positive control must succeed before fault injection'
    async def corrupt(*args):
        value=await original(*args)
        query=args[2].get('query',{});section=query.get('section','summary')
        if section=='summary':
            if fault=='summary_shape':return []
            if fault=='bool_scanned':value['scanned_tasks']=True
            if fault=='scope_origin':value['scope']['origin']='scheduled'
            if fault=='scope_cohort':value['scope']['cohort']='in_review'
            if fault=='nonfinite_hours':value['known_person_hours']='NaN'
            if fault=='stale_clock':
                from datetime import datetime,timedelta
                from zoneinfo import ZoneInfo
                instant=datetime.fromisoformat(value['checked_at'])-timedelta(days=7)
                value['checked_at']=instant.isoformat();value['local_date']=instant.astimezone(ZoneInfo(value['timezone'])).date().isoformat()
            if fault=='all_counter':value['counters']['all_tasks']+=1
            if fault=='unfinished_counter':value['counters']['unfinished']-=1
            if fault=='due_sum':value['due']['future']=value['due'].get('future',0)+1
            if fault=='norm_sum':value['norm_checks']={}
            if fault=='duplicate_groups':value['business_duplicates']['candidate_groups']+=1
            if fault=='clock_date':value['local_date']='2026-11-07'
        if section=='dates' and value['items']:
            if fault=='date_count':value['items'][0]['tasks']-=1
            if fault=='date_total':value['total']=0
            if fault=='date_row_shape':value['items'][0]=None
            if fault=='page_items_shape':value['items']={}
        if section=='equipment' and value['items'] and fault=='equipment_row_shape':value['items'][0]=None
        if section=='duplicates' and value['items'] and fault=='duplicate_row_shape':value['items'][0]=None
        if section=='equipment' and value['items'] and fault=='operation_sum':value['items'][0]['operations'][0]['tasks']+=1
        if fault=='snapshot_shape':value['snapshot_id']='invalid-snapshot'
        return value
    monkeypatch.setattr(read_transport,'invoke',corrupt)
    trace=[]
    answer=asyncio.run(report(app,available(app,'admin')['tasks_analyze'],headers,trace,lambda:None,
        'Проанализируй все незавершённые задания',principal))
    assert 'Полный анализ не выполнен' in answer,answer
    assert 'Всего записей' not in answer
    reasons=dict(all_counter='all_counter',unfinished_counter='unfinished_counter',due_sum='due_sum',norm_sum='norm_checks_sum',
        date_count='date_sum',date_total='page_cardinality',operation_sum='operation_counts',duplicate_groups='duplicate_counts',
        clock_date='server_clock',snapshot_shape='snapshot_identity',summary_shape='incomplete_snapshot',bool_scanned='all_counter',
        date_row_shape='detail_rows',equipment_row_shape='detail_rows',duplicate_row_shape='detail_rows',page_items_shape='page_cardinality',
        scope_origin='query_scope',scope_cohort='query_scope',stale_clock='server_clock',nonfinite_hours='invalid_effort')
    assert any(row['tool']=='__evidence' and row['reason']==reasons[fault] for row in trace),trace
