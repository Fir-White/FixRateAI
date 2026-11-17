"""Strict write validation reports fields/types without leaking raw input."""
import json
from uuid import uuid4
import pytest
from fastapi import HTTPException
from tests.backend.test_runtime_integration import runtime
from tests.backend.test_management import managed
from tests.backend.test_assistant import assistant_case
from app.assistant.tools import available,validate_arguments


@pytest.mark.parametrize('body,field,kind',[
    ({'name':'VALID TEST NAME'},'body.expected_revision','missing'),
    ({'expected_revision':1,'revision':2},'body.revision','extra_forbidden'),
    ({'expected_revision':'TEST-SECRET-NEVER-LOG'},'body.expected_revision','int_parsing'),
    ({'expected_revision':1,'name':''},'body.name','string_too_short'),
    ({'expected_revision':1,'status':'TEST-SECRET-NEVER-LOG'},'body.status','literal_error'),
])
def test_command_error_reports_exact_shape_without_values(assistant_case,body,field,kind):
    _,app,_,_,ids=assistant_case
    with pytest.raises(HTTPException) as error:
        validate_arguments(app,available(app,'chief_engineer')['equipment_edit'],dict(path={'equipment_id':str(uuid4())},body=body))
    assert error.value.status_code==422
    detail=error.value.detail
    assert isinstance(detail,dict) and detail['code']=='INVALID_COMMAND'
    assert dict(field=field,type=kind) in detail['issues']
    assert all(set(issue)=={'field','type'} for issue in detail['issues'])
    assert 'TEST-SECRET-NEVER-LOG' not in json.dumps(detail)


def test_current_revision_edit_is_valid_without_increment(assistant_case):
    _,app,_,_,ids=assistant_case
    args=validate_arguments(app,available(app,'chief_engineer')['equipment_edit'],dict(path={'equipment_id':str(uuid4())},body=dict(expected_revision=2,name='TEST ONLY rename')))
    assert args['body']['expected_revision']==2 and args['body']['name']=='TEST ONLY rename'


@pytest.mark.parametrize('change',[
    {'name':'TEST ONLY rename'},
    {'asset_code':'RT-RENAME'},
    {'location':None},
    {'status':'under_repair'},
    {'parent_equipment_id':None},
])
def test_partial_update_preserves_field_presence_across_proposal_validation(assistant_case,change):
    _,app,_,_,_=assistant_case
    tool=available(app,'chief_engineer')['equipment_edit']
    body=dict(expected_revision=2,**change)
    first=validate_arguments(app,tool,dict(path={'equipment_id':str(uuid4())},body=body))
    assert first['body']==body,'Omitted fields must not become explicit null updates'
    second=validate_arguments(app,tool,first)
    assert second==first,'Validation -> proposal validation must preserve PATCH semantics'


@pytest.mark.parametrize('field',['system_id','asset_code','name','status','properties'])
def test_explicit_null_is_still_rejected_for_nonnullable_fields(assistant_case,field):
    _,app,_,_,_=assistant_case
    with pytest.raises(HTTPException) as error:
        validate_arguments(app,available(app,'chief_engineer')['equipment_edit'],dict(path={'equipment_id':str(uuid4())},body=dict(expected_revision=2,**{field:None})))
    assert error.value.status_code==422
    assert error.value.detail['code']=='INVALID_COMMAND'
