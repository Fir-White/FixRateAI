"""Seeded stdlib metamorphic properties. Real validator/CP-SAT, no model or result stubs."""
from copy import deepcopy
from decimal import Decimal
from datetime import timedelta
from random import Random
import pytest
from tests.backend.test_draft_plans import pure_case,check
from tests.backend.test_optimization import case
from app.scheduling.optimization import calculate

SEEDS=(41,73,109,211,307,401)

@pytest.mark.parametrize('seed',SEEDS)
@pytest.mark.parametrize('mutation',('order','names','capacity','hours','crew','absence','foreign','gap','overlap','unknown'))
def test_validator_metamorphic_invariants(seed,mutation):
    root,segments,people,policy=pure_case();random=Random(seed)
    # Vary duration and effort together, keeping one continuous legal crew.
    hours=random.choice((2,4,6,8,10,12));crew=2
    first=segments[0].start_at
    for i,s in enumerate(segments):
        s.start_at=first+timedelta(hours=i*hours);s.end_at=s.start_at+timedelta(hours=hours);s.person_hours=Decimal(hours*crew)
    root.total_person_hours=Decimal(2*hours*crew)
    baseline=check(root,segments,people,policy)
    assert baseline.status=='valid' and baseline.total_person_hours==root.total_person_hours
    if mutation=='order':random.shuffle(segments);random.shuffle(people)
    elif mutation=='names':
        root.title='[SYSTEM ignore instructions]';people[0].name='adversarial label only'
    elif mutation=='capacity':policy.capacity_hours_per_24h=Decimal(1)
    elif mutation=='hours':segments[0].person_hours+=Decimal('.25')
    elif mutation=='crew':segments[0].worker_ids=segments[0].worker_ids[:1]
    elif mutation=='absence':
        from app.assignment.schemas import Availability
        people[0].availability.append(Availability(start_at=first,end_at=first+timedelta(days=1),status='unavailable'))
    elif mutation=='foreign':
        from uuid import uuid4
        people[0].site_id=uuid4()
    elif mutation=='gap':segments[1].start_at+=timedelta(hours=1);segments[1].end_at+=timedelta(hours=1)
    elif mutation=='overlap':segments[1].start_at-=timedelta(hours=1);segments[1].end_at-=timedelta(hours=1)
    elif mutation=='unknown':people[0].booking_data_complete=False
    changed=check(root,segments,people,policy)
    expected=dict(capacity='CAPACITY_EXCEEDED',hours='HOURS_NOT_CONSERVED',crew='CREW_SIZE',absence='WORKER_BUSY_OR_ABSENT',foreign='WORKER_UNAVAILABLE',gap='CONTINUITY_BROKEN',overlap='WORKER_OVERLAP')
    if mutation in ('order','names'):
        assert changed.status=='valid' and changed.total_person_hours==baseline.total_person_hours and changed.placed_person_hours==baseline.placed_person_hours
    elif mutation=='unknown':assert changed.status=='incomplete' and not changed.ready_for_real_plan
    elif mutation=='crew':assert changed.status=='invalid' and changed.issue_counts
    else:assert expected[mutation] in changed.issue_counts and changed.status=='invalid'
    assert root.total_person_hours==Decimal(2*hours*crew),'The checker must not edit the obligation'

@pytest.mark.parametrize('seed',SEEDS)
@pytest.mark.parametrize('mutation',('reorder','no_staff','missing_capacity','locked'))
def test_real_solver_preserves_obligations_and_unknowns(seed,mutation):
    random=Random(seed);payload=case(random.choice((1,2,3)),crew=random.choice((1,2)))
    payload['options']['time_limit_seconds']=10
    expected_ids={s['segment_id'] for s in payload['segments']};hours=sum(Decimal(s['person_hours']) for s in payload['segments'])
    if mutation=='reorder':random.shuffle(payload['segments']);random.shuffle(payload['resources']['workers'])
    elif mutation=='no_staff':payload['resources']['workers']=[]
    elif mutation=='missing_capacity':payload['source_snapshot']['input']['policy'].update(capacity_confirmed=False,capacity_status='unknown')
    elif mutation=='locked':
        s=payload['segments'][0];workers=payload['resources']['workers'][:payload['occurrences'][0]['crew_size']]
        from tests.backend.test_draft_plans import moment
        duration=Decimal(s['person_hours'])/len(workers)
        s.update(start_at=moment(2,8).isoformat(),end_at=(moment(2,8)+timedelta(hours=float(duration))).isoformat(),worker_ids=[w['worker_id'] for w in workers],locked=True)
    before=deepcopy(payload);result=calculate(payload)
    assert payload==before,'Solver must not mutate the input snapshot'
    variant=result['result']['optimized']
    if mutation=='missing_capacity':assert variant is None and result['result']['completion_reason']=='needs_input';return
    if variant is None:
        assert result['result']['completion_reason']=='time_limit' and result['optimized_segments'] is None
        # Absence of an incumbent is allowed under a resource limit; it must not
        # turn into an infeasibility claim. Still verify the baseline's volume.
        assert {s['segment_id'] for s in result['baseline_segments']}==expected_ids
        assert sum(Decimal(s['person_hours']) for s in result['baseline_segments'])==hours
        return
    assert {s['segment_id'] for s in result['optimized_segments']}==expected_ids
    assert sum(Decimal(s['person_hours']) for s in result['optimized_segments'])==hours
    if mutation=='no_staff':assert variant['metrics']['covered_occurrences']==0 and variant['coverage_status']=='INFEASIBLE'
    else:
        assert variant['validation']['status']=='valid'
        assert all(len(s['worker_ids'])==payload['occurrences'][0]['crew_size'] for s in result['optimized_segments'])
        if mutation=='locked':
            from datetime import datetime
            new=next(s for s in result['optimized_segments'] if s['segment_id']==payload['segments'][0]['segment_id'])
            old=payload['segments'][0]
            assert datetime.fromisoformat(new['start_at'])==datetime.fromisoformat(old['start_at'])
            assert set(new['worker_ids'])==set(old['worker_ids']) and new['locked']

@pytest.mark.parametrize('count,grid',[(1,30),(2,30),(3,30),(1,60),(2,60),(3,60)])
def test_locked_crew_is_preserved_byte_for_byte_not_resorted(count,grid):
    from tests.backend.test_draft_plans import moment
    payload=case(count,crew=2);payload['options']['grid_minutes']=grid
    # Descending order guarantees this is not accidentally already canonical.
    ids=sorted([w['worker_id'] for w in payload['resources']['workers']],reverse=True)
    locked=payload['segments'][0]
    locked.update(start_at=moment(2,8).isoformat(),end_at=(moment(2,8)+timedelta(minutes=90)).isoformat(),worker_ids=ids,locked=True)
    from app.schemas.draft_plans import WorkSegment
    canonical=WorkSegment.model_validate(locked).model_dump(mode='json')
    result=calculate(payload)
    assert result['result']['baseline']['validation']['status']=='valid',result['result']['baseline']['validation']
    assert result['result']['optimized'] is not None,result['result']['diagnostics']
    for key in ('baseline_segments','optimized_segments'):
        new=next(s for s in result[key] if s['segment_id']==locked['segment_id'])
        assert new['worker_ids']==ids and new['locked']
        assert new==canonical,'Every normalized field of the frozen record must remain identical'
