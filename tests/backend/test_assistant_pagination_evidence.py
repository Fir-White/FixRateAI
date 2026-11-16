"""No inference: actual read-transport repairs and deterministic page evidence."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.assistant import orchestrator, read_transport, tools


def page(ids,total,offset=0,*,snapshot='stable',**extra):
    result=dict(items=[dict(id=identity,equipment_id='shared-reference') for identity in ids],
                total=total,offset=offset,**extra)
    if snapshot is not None:result['snapshot_id']=snapshot
    return result


@pytest.fixture
def reader(monkeypatch):
    route=SimpleNamespace(dependant=SimpleNamespace(query_params=[SimpleNamespace(name='offset')]))
    monkeypatch.setattr(tools,'route_for',lambda *args:route)
    monkeypatch.setattr(read_transport,'route_for',lambda *args:route)
    calls=[];checks=[];responses=[]
    def validate(app,tool,args):
        if args.get('query',False) is None:raise HTTPException(422,'Null query envelope')
        if args.get('view',{}).get('limit',0)>25:raise HTTPException(422,'Projection limit exceeded')
        return deepcopy(args)
    async def invoke(app,tool,args,headers):
        calls.append(deepcopy(args))
        result=responses.pop(0)
        if isinstance(result,Exception):raise result
        return deepcopy(result)
    monkeypatch.setattr(read_transport,'validate_arguments',validate)
    monkeypatch.setattr(read_transport,'invoke',invoke)
    monkeypatch.setattr(orchestrator,'read_tool',read_transport.read)
    def run(values,*,budget=20,args=None,tool='equipment_find',full=True):
        responses[:]=values;trace=[];calls.clear();checks.clear()
        checked,result=asyncio.run(orchestrator._read_pages(None,SimpleNamespace(name=tool,mode='read',method='GET'),
            args or {},{},full=full,check=lambda:checks.append(True),trace=trace,max_reads=budget))
        return checked,result,trace,calls
    return run


def limitations(result):return result['pagination']['limitations']


def test_stable_snapshot_combines_unique_resource_ids_not_shared_references(reader):
    args,result,trace,calls=reader([page(['a','b'],4),page(['c','d'],4,2)])
    assert result['complete'] is True and [row['id'] for row in result['items']]==['a','b','c','d']
    assert result['pagination']['snapshot_verified'] is True and len(trace)==len(calls)==2
    assert calls[1]['query']['offset']==2 and args=={}


def test_unversioned_multiple_pages_retain_rows_without_claiming_atomic_full_snapshot(reader):
    _,result,trace,_=reader([page(['a'],2,snapshot=None),page(['b'],2,1,snapshot=None)])
    assert result['complete'] is False and result['pagination']['coverage_complete'] is True
    assert limitations(result)==['snapshot_unavailable'] and len(result['items'])==len(trace)==2


def test_single_complete_response_does_not_require_cross_request_snapshot(reader):
    _,result,trace,_=reader([page(['a'],1,snapshot=None)])
    assert result['complete'] is True and limitations(result)==[] and len(trace)==1


@pytest.mark.parametrize('changed,reason',[
    (dict(total=3),'total_changed'),
    (dict(snapshot='other'),'snapshot_changed'),
    (dict(timezone='UTC'),'page_scope_changed'),
    (dict(offset=0),'offset_changed'),
])
def test_changed_page_is_not_merged_or_certified(reader,changed,reason):
    second=dict(total=2,offset=1,**{key:value for key,value in changed.items() if key not in ('total','offset')})
    second.update({key:value for key,value in changed.items() if key in ('total','offset')})
    _,result,trace,_=reader([page(['a'],2),page(['b'],**second)])
    assert result['complete'] is False and reason in limitations(result)
    assert [row['id'] for row in result['items']]==['a'] and len(trace)==2


def test_duplicate_resource_id_cannot_fill_expected_count(reader):
    _,result,_,_=reader([page(['a','b'],4),page(['b','c'],4,2)])
    assert len(result['items'])==4 and result['complete'] is False
    assert 'duplicate_identity' in limitations(result)


def test_duplicate_in_single_response_is_explicitly_partial(reader):
    _,result,_,_=reader([page(['a','a'],2)])
    assert result['complete'] is False and 'duplicate_identity' in limitations(result)


def test_exact_read_budget_retains_first_page_and_no_extra_dispatch(reader):
    _,result,trace,calls=reader([page(['a'],2),page(['b'],2,1)],budget=1)
    assert len(trace)==len(calls)==1 and result['complete'] is False
    assert result['items'][0]['id']=='a' and 'read_budget' in limitations(result)


def test_validation_repair_consumes_budget_before_backend_dispatch(reader):
    _,result,trace,calls=reader([page(['a'],1)],budget=1,args=dict(query=None))
    assert calls==[] and len(trace)==1 and trace[0]['status']=='denied'
    assert result['status']=='blocked' and result['complete'] is False
    assert 'items' not in result and 'read_budget' in limitations(result)


def test_validation_repair_and_success_both_count_as_actual_attempts(reader):
    _,result,trace,calls=reader([page(['a'],2),page(['b'],2,1)],budget=2,args=dict(query=None))
    assert len(trace)==2 and len(calls)==1 and result['complete'] is False
    assert [row['id'] for row in result['items']]==['a'] and 'read_budget' in limitations(result)


@pytest.mark.parametrize('budget',[2,3])
def test_multiple_repairs_cannot_exceed_attempt_budget(reader,budget):
    projection_error=HTTPException(422,'Неизвестное поле результата. Используйте имена из прочитанного ответа.')
    _,result,trace,calls=reader([projection_error,page(['a'],1)],budget=budget,
        args=dict(view=dict(path=['unknown'],limit=100)))
    assert len(trace)==budget and len(calls)==budget-1
    assert result['complete'] is (budget==3)
    if budget==2:assert 'items' not in result and 'read_budget' in limitations(result)


def test_zero_budget_performs_no_read_and_makes_no_absence_claim(reader):
    _,result,trace,calls=reader([page([],0)],budget=0)
    assert trace==calls==[] and result['complete'] is False and 'items' not in result


def test_empty_middle_page_does_not_end_as_complete(reader):
    _,result,trace,_=reader([page(['a'],3),page([],3,1)])
    assert result['complete'] is False and 'empty_page' in limitations(result) and len(trace)==2


def test_page_bound_cannot_be_bypassed_by_large_read_budget(reader):
    _,result,trace,_=reader([page([str(i)],100,i) for i in range(30)],budget=30)
    assert len(trace)==16 and len(result['items'])==16 and result['complete'] is False
    assert 'page_budget' in limitations(result)


def test_explicit_source_partial_marker_survives_merge(reader):
    _,result,_,_=reader([page(['a'],1,complete=False)])
    assert result['complete'] is False and 'source_partial' in limitations(result)


def inventory(ids,total,*,site='one',site_total=1,offset=0,snapshot='stable'):
    return page(ids,total,offset,snapshot=snapshot,site=dict(id=site,status='ok'),site_total=site_total)


def test_inventory_respects_read_budget_within_first_site(reader):
    _,result,trace,_=reader([inventory(['a'],2),inventory(['b'],2,offset=1)],tool='inventory_read',budget=1)
    assert len(trace)==1 and result['complete'] is False
    assert 'read_budget' in limitations(result['sites'][0]) and result['sites'][0]['items'][0]['id']=='a'


def test_inventory_site_transition_preserves_filters_and_stable_snapshot(reader):
    _,result,trace,calls=reader([inventory(['a'],1,site_total=2),inventory(['b'],1,site='two',site_total=2)],
        tool='inventory_read',args=dict(query=dict(current_only=False)))
    assert result['complete'] is True and len(result['sites'])==2 and len(trace)==2
    assert calls[1]['query']==dict(current_only=False,site_offset=1,offset=0)


def test_unversioned_multiple_sites_are_observed_coverage_not_atomic_snapshot(reader):
    _,result,_,_=reader([inventory(['a'],1,site_total=2,snapshot=None),inventory(['b'],1,site='two',site_total=2,snapshot=None)],tool='inventory_read')
    assert result['complete'] is False and 'snapshot_unavailable' in limitations(result)


@pytest.mark.parametrize('second,reason',[
    (inventory(['b'],1,site='two',site_total=3),'site_total_changed'),
    (inventory(['b'],1,site='two',site_total=2,snapshot='other'),'snapshot_changed'),
    (inventory(['b'],1,site='one',site_total=2),'duplicate_site'),
])
def test_inventory_changed_or_repeated_sites_never_complete(reader,second,reason):
    _,result,_,_=reader([inventory(['a'],1,site_total=2),second],tool='inventory_read')
    assert result['complete'] is False and reason in limitations(result)


def test_inventory_empty_authorized_site_collection_is_complete(reader):
    _,result,_,_=reader([dict(site_total=0,site=None,items=[],total=0,offset=0)],tool='inventory_read')
    assert result['sites']==[] and result['returned_count']==0 and result['complete'] is True


def test_access_denial_does_not_become_empty_or_retry(reader):
    with pytest.raises(HTTPException) as caught:reader([HTTPException(403,'forbidden')],budget=1)
    assert caught.value.status_code==403
