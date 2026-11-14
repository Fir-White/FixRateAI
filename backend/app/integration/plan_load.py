"""Read current resource capacity for one selected immutable draft version."""
from uuid import UUID
import json
from fastapi import Depends,Query,Response
from sqlalchemy import text
from app.assignment.schemas import Worker
from app.schemas.draft_plans import WorkOccurrence,WorkSegment
from app.schemas.portfolio import planning_input
from app.schemas.plan_load import PlanLoadPreview
from app.scheduling.plan_load import project
from app.scheduling.draft_validator import digest
from .draft_plans import BASE,get_version,metadata,clean,source_snapshot,generator_version,checked
from .catalog_imports import READ_ROLES
from .management import _guard


def preview(v,identity,revision=None):
    row=get_version(v,identity,revision);snapshot=row['source_snapshot'];request=planning_input(snapshot['input'])
    own=list(v.session.scalars(text('''SELECT t.work_order_id FROM published_catalog_tasks t JOIN draft_publications p USING(site_id,publication_id)
        WHERE p.site_id=:site AND p.draft_id=:id AND p.revision=:revision'''),dict(site=v.principal.site_id,id=identity,revision=row['revision'])))
    # A published version owns these reservations already. Exclude them from
    # competing bookings while projecting its frozen, approved placements once.
    stale=False if own else digest(clean(source_snapshot(v,request)))!=snapshot['source_digest'] or snapshot['generator_version']!=generator_version(request)
    roots=[WorkOccurrence.model_validate(o) for o in row['occurrences']];segments=[WorkSegment.model_validate(s) for s in row['segments']]
    report,facts=checked(v,snapshot,roots,segments,stale=stale,capture=True,exclude_order_ids=own)
    workers=[Worker.model_validate_json(json.dumps(w)) for w in facts['workers']]
    result=project(roots,segments,workers,request.policy,report,request.starts_on,request.ends_on,snapshot['source']['timezone'])
    return dict(record=metadata(row),timezone=snapshot['source']['timezone'],checked_at=report.checked_at,resource_sha256=report.resource_sha256,
        source_state='published_snapshot' if own else 'stale' if stale else 'current',validation_status=report.status,
        total_issues=report.total_issues,issues=report.issues,published_tasks=len(own),**result)


def register_routes(app,views):
    @app.post(BASE+'/{identity}/load-preview',response_model=PlanLoadPreview)
    def load(identity:UUID,response:Response,revision:int|None=Query(None,ge=1),v=Depends(views)):
        _guard(v,*READ_ROLES);response.headers['Cache-Control']='private, no-store'
        return preview(v,identity,revision)
