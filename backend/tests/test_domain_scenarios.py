"""Analyst fixtures execute against the same generator as the web calendar."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path

import pytest

from app.scheduling import CalendarGenerationRequest,generate_month

ROOT=Path(__file__).resolve().parents[2]
CASES=json.loads((ROOT/'docs/domain/examples/maintenance_cases.json').read_text(encoding='utf-8'))['test_fixtures']


@pytest.mark.parametrize('case',CASES,ids=lambda row:row['test_id'])
def test_analyst_calendar_fixture(case):
    request=deepcopy(json.loads((ROOT/'docs/algorithms/examples.json').read_text(encoding='utf-8'))['request'])
    values=case['input_data']
    request['query'].update(year=values['year'],month=values['month'])
    request['as_of']=f"{values['year']}-{values['month']:02d}-01T00:00:00+05:00"
    item=request['bindings'][0]
    item['binding']['effective_from']=values['active_from']
    item['equipment']['commissioned_on']=values['active_from']
    item['operation'].update(crew_size=case['expected_workers'],raw_norm_value=case['raw_norm_value'],norm_unit=case['norm_unit'],planning_duration_minutes=None,duration_basis=None)
    item['rule'].update(kind='calendar_pattern',interval=None,calendar_unit=None,anchor_date=None,basis=None,explicit_dates=[],yearly_count=None,pattern=values['pattern'])
    result=generate_month(CalendarGenerationRequest.model_validate_json(json.dumps(request)))
    assert [str(o.occurrence.occurrence_date) for o in result.bindings[0].occurrences]==case['expected_dates']
    assert all(row.crew_size==case['expected_workers'] for row in result.calendar.items)
    assert all(row.raw_norm_value==Decimal(case['raw_norm_value']) for row in result.calendar.items)


def test_domain_json_examples_share_the_canonical_contracts():
    from app.schemas.maintenance import OperationVersion,RecurrenceRule,Task,Equipment
    from app.schemas.maintenance_api import EquipmentOperationBindingResponse
    for name,model in [('operation_template',OperationVersion),('regulation',RecurrenceRule),('maintenance_task',Task)]:
        model.model_validate_json((ROOT/f'docs/domain/examples/{name}.json').read_text(encoding='utf-8'))
    relation=json.loads((ROOT/'docs/domain/examples/operation_to_equipment_links.json').read_text(encoding='utf-8'))
    operation=OperationVersion.model_validate_json(json.dumps(relation['operation']))
    rule=RecurrenceRule.model_validate_json(json.dumps(relation['rule']))
    equipment={row['equipment_id']:Equipment.model_validate_json(json.dumps(row)) for row in relation['equipment']}
    for raw in relation['bindings']:
        binding=EquipmentOperationBindingResponse.model_validate_json(json.dumps(raw))
        assert str(binding.equipment_id) in equipment
        assert binding.operation_version_id==operation.operation_version_id and binding.rule_version_id==rule.rule_version_id
