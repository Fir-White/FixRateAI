"""Bounded search over the whole authorized dataset, not just a model's first page."""
from datetime import date,datetime,time,timedelta,timezone
from typing import Annotated, Literal
from zoneinfo import ZoneInfo
from pydantic import BaseModel,ConfigDict,Field
from uuid import UUID
from fastapi import Depends,Query,HTTPException,Request,Response
from sqlalchemy import DateTime,cast,select,func,or_,and_,text
from sqlalchemy.orm import aliased
from app.security.sessions import has_role,SQL_ROLES
from .management import equipment_response
from app.assistant.analysis_contract import Group, MAX_AGGREGATE_ROWS, Metric
from app.schemas.assistant import MAX_COLLECTION_PAGE

BASE='/api/v1/assistant/workspace'
MaintenanceTypeKey = Annotated[str, Field(pattern=r'^то[0-9]{1,3}$')]
MaintenanceTypeCode = Annotated[str, Field(min_length=1,max_length=100)]
AcceptedMaintenance = Literal['present', 'none']


def _accepted_maintenance(v, equipment_id):
    """Evidence of a linked ТО report with an explicit authorized acceptance."""
    links, orders, reports, reviews = (aliased(v.models[name]) for name in
        ('work_order_equipment', 'work_orders', 'work_reports', 'acceptance_reviews'))
    site_id = v.principal.site_id
    history = (select(reviews.acceptance_review_id).select_from(links)
        .join(orders, and_(orders.site_id == links.site_id, orders.work_order_id == links.work_order_id))
        .join(reports, and_(reports.site_id == orders.site_id, reports.work_order_id == orders.work_order_id))
        .join(reviews, and_(reviews.site_id == reports.site_id, reviews.work_order_id == orders.work_order_id,
                            reviews.work_report_id == reports.work_report_id))
        .where(links.site_id == site_id, links.equipment_id == equipment_id,
               orders.maintenance_rule_id.is_not(None), reviews.decision == 'accepted'))
    if v.principal.role == 'executor':
        assignments = aliased(v.models['work_assignments'])
        history = history.where(select(assignments.work_assignment_id).where(
            assignments.site_id == site_id, assignments.work_order_id == orders.work_order_id,
            assignments.user_id == v.principal.user_id, assignments.status.not_in(('cancelled', 'declined'))).exists())
    return history.exists()


def _accepted_scope(principal):
    return dict(source='accepted_maintenance_reports',
                visibility='assigned_orders' if principal.role == 'executor' else 'site')


def _equipment_search_filters(model, q, asset_code):
    filters = []
    if q and q.strip():
        filters.append(or_(*(column.icontains(q.strip(), autoescape=True)
                             for column in (model.name, model.asset_code, model.location))))
    if asset_code is not None:
        code = asset_code.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        filters.append(model.asset_code.ilike(code, escape='\\'))
    return filters


class AssignmentPreparation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    executor_ids:list[UUID]|None=Field(default=None,min_length=1,max_length=50)
    one_person_only:bool=False
    use_planned_day:bool=False

def register_routes(app,views):
    @app.get(BASE+'/maintenance-catalog')
    def maintenance_catalog(response: Response, offset: int=Query(0,ge=0),
                            type_keys: list[MaintenanceTypeKey]|None=Query(None,max_length=12),
                            type_codes: list[MaintenanceTypeCode]|None=Query(None,max_length=12),
                            limit: int=Query(50,ge=1,le=100), v=Depends(views)):
        """Published operation definitions bound to the actor's visible equipment today."""
        response.headers['Cache-Control'] = 'private, no-store'
        day = datetime.now(ZoneInfo(v.principal.timezone)).date()
        visible = ''
        if v.principal.role == 'executor':
            visible = '''AND EXISTS (SELECT 1 FROM work_order_equipment w
                JOIN work_assignments a USING (site_id, work_order_id)
                WHERE w.site_id=e.site_id AND w.equipment_id=e.equipment_id
                  AND a.user_id=:user_id AND a.status NOT IN ('declined','cancelled'))'''
        rows = v.session.execute(text(f'''WITH operations AS MATERIALIZED (
            SELECT DISTINCT op.operation_template_id AS operation_id, mt.code AS type_code, mt.name AS type_name,
                COALESCE(NULLIF(r.schedule_parameters->'operation_metadata'->>'code',''), op.code) AS code,
                COALESCE(NULLIF(r.schedule_parameters->'operation_metadata'->>'title',''), op.title) AS title
            FROM rule_equipment b
            JOIN equipment e USING (site_id, equipment_id)
            JOIN maintenance_rules r USING (site_id, maintenance_rule_id)
            JOIN regulation_editions ed USING (site_id, regulation_edition_id)
            JOIN operation_templates op USING (site_id, operation_template_id)
            JOIN maintenance_types mt USING (maintenance_type_id)
            WHERE b.site_id=:site AND e.status<>'retired' AND op.is_active
              AND (NOT :filtered OR CAST(:type_keys AS text[]) && ARRAY[
                  translate(regexp_replace(mt.code,'[[:space:]‑–-]','','g'),'TOТОto','тотото'),
                  translate(regexp_replace(mt.name,'[[:space:]‑–-]','','g'),'TOТОto','тотото')])
              AND (NOT :coded OR mt.code=ANY(CAST(:type_codes AS text[])))
              AND r.publication_status='published' AND ed.is_approved
              AND COALESCE(r.schedule_parameters->>'superseded_binding','') IN ('','false')
              AND b.valid_from<=:day AND (b.valid_to IS NULL OR b.valid_to>=:day)
              AND r.active_from<=:day AND (r.active_until IS NULL OR r.active_until>=:day)
              AND ed.effective_from<=:day AND (ed.effective_to IS NULL OR ed.effective_to>=:day)
              {visible}
        ), page AS (
            SELECT * FROM operations ORDER BY type_code,code,title,operation_id OFFSET :offset LIMIT :limit
        ) SELECT (SELECT count(*) FROM operations) AS total,
                 (SELECT COALESCE(jsonb_agg(to_jsonb(page) ORDER BY type_code,code,title,operation_id),'[]') FROM page) AS items,
                 (SELECT encode(sha256(convert_to(COALESCE(jsonb_agg(to_jsonb(o)
                      ORDER BY type_code,code,title,operation_id),'[]')::text,'UTF8')),'hex') FROM operations o) AS snapshot_id,
                 (SELECT COALESCE(jsonb_agg(to_jsonb(kinds) ORDER BY type_code,type_name),'[]') FROM (
                     SELECT type_code,type_name,count(*) AS operations FROM operations GROUP BY type_code,type_name
                 ) kinds) AS types'''), dict(site=v.principal.site_id,user_id=v.principal.user_id,
                                              filtered=bool(type_keys),type_keys=type_keys or [],
                                              coded=bool(type_codes),type_codes=type_codes or [],
                                              day=day,offset=offset,limit=limit)).mappings().one()
        return dict(**rows, date=day,offset=offset,limit=limit,type_keys=type_keys or [],type_codes=type_codes or [])

    @app.get(BASE+'/work-order-analytics')
    def work_order_analytics(
        group_by: Group,
        metric: Metric,
        limit: int=Query(5, ge=1, le=MAX_AGGREGATE_ROWS),
        offset: int=Query(0, ge=0),
        as_of: date|None=None,
        starts_on: date|None=None,
        ends_on: date|None=None,
        second_starts_on: date|None=None,
        second_ends_on: date|None=None,
        include_overdue_tasks: bool=False,
        include_assignments: bool=False,
        first_equipment_code: str|None=Query(None,min_length=1,max_length=128),
        second_equipment_code: str|None=Query(None,min_length=1,max_length=128),
        tie_breaker: Literal['uuid']|None=None,
        v=Depends(views),
    ):
        from app.assistant.analysis_contract import AggregateQuery, Window
        from .work_order_analytics import aggregate

        pairs = [(starts_on, ends_on), (second_starts_on, second_ends_on)]
        if second_starts_on and not starts_on:
            raise HTTPException(422, 'Сначала укажите первый период.')
        try:
            windows = [Window(starts_on=start, ends_on=end) for start,end in pairs if start or end]
            query = AggregateQuery(group_by=group_by, metric=metric, limit=limit, offset=offset, as_of=as_of,
                                   windows=windows, include_overdue_tasks=include_overdue_tasks,
                                   include_assignments=include_assignments, first_equipment_code=first_equipment_code,
                                   second_equipment_code=second_equipment_code, tie_breaker=tie_breaker)
        except ValueError:
            raise HTTPException(422, 'Выберите допустимую группировку, метрику и периоды.') from None
        return aggregate(v, query)

    @app.get(BASE+'/tasks/{task_id}/acceptance-evidence')
    def acceptance_evidence(task_id: UUID, expected_revision: int=Query(...,ge=1),
                            execution_id: UUID|None=None,v=Depends(views)):
        from .task_acceptance_evidence import inspect
        return inspect(v, task_id, expected_revision, execution_id, app.state.settings.photo_storage_root)

    @app.get(BASE+'/workbook-readiness')
    def workbook_readiness(conversation_id:UUID,attachment_ids:list[UUID]=Query(...,min_length=1,max_length=20),v=Depends(views)):
        from app.assistant.service import conversation
        from app.assistant.attachments import SCOPE,owned
        from app.assistant.workbooks import context
        from app.assistant.workbook_readiness import fact,report
        conversation(v.session,v.principal,conversation_id)
        SCOPE.set((conversation_id,v.principal.user_id,v.principal.site_id,v.principal.role))
        if len(set(attachment_ids))!=len(attachment_ids):raise HTTPException(422,'Файл указан повторно')
        files=[owned(app,identity) for identity in attachment_ids]
        if any(row['mime_type']!='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' for row in files):raise HTTPException(422,'Для проверки нормативов выберите XLSX')
        books=context(app,files)
        return dict(status='blocked',complete=all(book.get('complete') for book in books),fact=fact(books),report=report(books),workbooks=books)

    @app.get(BASE+'/equipment/{equipment_id}/history')
    def equipment_history(equipment_id:UUID,starts_on:date|None=None,ends_on:date|None=None,
                          offset:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=MAX_COLLECTION_PAGE),
                          only_accepted:bool=True,latest_only:bool=False,v=Depends(views)):
        from sqlalchemy import text
        from .management import _equipment
        _equipment(v,equipment_id)
        if v.principal.role=='executor' and equipment_id not in v.visible_equipment_ids():raise HTTPException(404,'Оборудование не найдено')
        bounded = starts_on is not None and ends_on is not None
        if ((starts_on is None) != (ends_on is None) or
                bounded and (ends_on < starts_on or (ends_on-starts_on).days > 3660) or
                not bounded and not latest_only or latest_only and (offset or not only_accepted)):
            raise HTTPException(422,'Выберите корректный период истории либо запросите последний принятый отчёт.')
        # Fixed-count SQL, filtering dates in the object's actual timezone. A
        # report is a fact of submission; accepted_only additionally requires
        # the explicit acceptance record for that exact report attempt.
        from .work_order_analytics import performed_sql
        review_actual=performed_sql('a.performed_text')
        report_actual=performed_sql("r.execution_context->>'performed_at'")
        actual='COALESCE('+review_actual+','+report_actual+')'
        conflict='''((%s) IS NOT NULL AND (%s) IS NOT NULL AND (%s)<>(%s))
                 OR COALESCE(f.actual_at>a.accepted_at,false)''' % (review_actual,report_actual,review_actual,report_actual)
        period_filter='AND timezone(:timezone,COALESCE(f.actual_at,r.submitted_at))::date BETWEEN :start AND :end'
        scope='''FROM work_reports r JOIN work_orders o USING(work_order_id)
          JOIN work_order_equipment e ON e.site_id=o.site_id AND e.work_order_id=o.work_order_id AND e.equipment_id=:equipment
          LEFT JOIN LATERAL (SELECT reviewed_at accepted_at,decision_context->>'performed_at' performed_text FROM acceptance_reviews a
            WHERE a.site_id=r.site_id AND a.work_order_id=r.work_order_id AND a.work_report_id=r.work_report_id AND a.decision='accepted' ORDER BY reviewed_at DESC,acceptance_review_id DESC LIMIT 1) a ON true
          CROSS JOIN LATERAL (SELECT '''+actual+''') f(actual_at)
          WHERE o.site_id=:site AND r.site_id=:site
          AND (:accepted=false OR a.accepted_at IS NOT NULL)
          '''
        if v.principal.role=='executor':
            scope+=''' AND EXISTS(SELECT 1 FROM work_assignments w WHERE w.site_id=o.site_id AND w.work_order_id=o.work_order_id
                       AND w.user_id=:user AND w.status NOT IN ('cancelled','declined'))'''
        params=dict(equipment=equipment_id,site=v.principal.site_id,timezone=v.principal.timezone,
                    user=v.principal.user_id,start=starts_on,end=ends_on,accepted=only_accepted,offset=offset)
        selected_scope = scope + (period_filter if bounded else '')
        columns = '''SELECT o.work_order_id task_id,r.work_report_id report_id,
            f.actual_at performed_at,r.submitted_at,a.accepted_at,
            (f.actual_at IS NOT NULL AND NOT ('''+conflict+''')) actual_date_verified,
            CASE WHEN f.actual_at IS NULL THEN 'submission_only' ELSE 'actual_performed' END date_basis,
            ('''+conflict+''') actual_date_conflict,r.status report_state,o.status task_state '''
        if latest_only:
            # The candidate and the completeness checks must describe the same
            # snapshot, including accepted reports with missing or disputed dates.
            window = ('timezone(:timezone,COALESCE(performed_at,submitted_at))::date BETWEEN :start AND :end'
                      if bounded else 'true')
            row = dict(v.session.execute(text(f"""WITH scoped_reports AS ({columns + scope}),
              totals AS (
                SELECT count(*) FILTER (WHERE {window}) matched_reports,
                       count(*) FILTER (WHERE performed_at IS NULL AND submitted_at IS NULL) undated_count,
                       count(*) FILTER (WHERE performed_at IS NULL) actual_date_unknown_count,
                       coalesce(bool_or(actual_date_conflict),false) actual_date_conflict
                FROM scoped_reports
              )
              SELECT totals.*, item.payload FROM totals LEFT JOIN LATERAL (
                SELECT to_jsonb(r) payload FROM scoped_reports r WHERE {window}
                ORDER BY performed_at DESC NULLS LAST,report_id LIMIT 1
              ) item ON true"""),params).mappings().one())
            item = row.pop('payload')
            return dict(equipment_id=str(equipment_id),starts_on=starts_on,ends_on=ends_on,only_accepted=True,
                        latest_only=True,items=[item] if item else [],**row,
                        complete=not (row['actual_date_unknown_count'] or row['actual_date_conflict']),
                        checked_at=datetime.now(timezone.utc),timezone=v.principal.timezone,
                        source='saved_work_reports_and_acceptance_reviews',date_basis='verified_actual_date',
                        manufacturer_unverified=True)
        total=v.session.scalar(text('SELECT count(*) '+selected_scope),params)
        undated=v.session.scalar(text('SELECT count(*) '+scope+' AND COALESCE(f.actual_at,r.submitted_at) IS NULL'),params)
        unknown_actual=v.session.scalar(text('SELECT count(*) '+scope+' AND f.actual_at IS NULL'),params)
        rows=v.session.execute(text(columns+selected_scope+
            ' ORDER BY COALESCE(f.actual_at,r.submitted_at) DESC,r.work_report_id LIMIT :limit OFFSET :offset'),
            {**params, 'limit': limit}).mappings().all()
        return dict(equipment_id=str(equipment_id),starts_on=starts_on,ends_on=ends_on,only_accepted=only_accepted,
                    items=[dict(row) for row in rows],total=total,offset=offset,limit=limit,page_complete=offset==0 and len(rows)==total,
                    undated_count=undated,actual_date_unknown_count=unknown_actual,complete=offset==0 and len(rows)==total and undated==0 and unknown_actual==0 and not any(row['actual_date_conflict'] for row in rows),
                    checked_at=datetime.now(timezone.utc),timezone=v.principal.timezone,
                    source='saved_work_reports_and_acceptance_reviews',date_basis='per_report_actual_or_explicit_submission_fallback',
                    manufacturer_unverified=True)

    @app.get(BASE+'/equipment/{equipment_id}/calendar-evidence')
    def calendar_evidence(equipment_id:UUID,starts_on:date,ends_on:date,approved_only:bool=False,
                          next_only:bool=False,v=Depends(views)):
        from .management import _equipment,service_configurations
        from app.assistant.calendar_evidence import explain_configuration
        _equipment(v,equipment_id)
        if v.principal.role=='executor' and equipment_id not in v.visible_equipment_ids():raise HTTPException(404,'Оборудование не найдено')
        if ends_on<starts_on or (ends_on-starts_on).days>3660 or ends_on.year>9998:
            raise HTTPException(422,'Укажите корректный ограниченный период календаря')
        rows=service_configurations(v,equipment_id)
        if approved_only:
            rows = [row for row in rows if row['enabled'] and row['valid_from'] <= ends_on
                    and (row['valid_until'] is None or row['valid_until'] >= starts_on)]
        if next_only:
            rows = [row for row in rows if row['valid_from'] <= starts_on and
                    (row['valid_until'] is None or row['valid_until'] >= starts_on)]
        try:
            results=[explain_configuration(row,starts_on,ends_on,timezone=v.principal.timezone,
                                           next_only=next_only) for row in rows]
        except ValueError:raise HTTPException(422,'Укажите корректный ограниченный период календаря') from None
        return dict(equipment_id=str(equipment_id),starts_on=starts_on,ends_on=ends_on,approved_only=approved_only,
                    configurations=results,complete=all(row['complete'] for row in results),
                    **({'next_only': True} if next_only else {}),
                    manufacturer_unverified=True,source='saved_service_configurations',timezone=v.principal.timezone)

    @app.get(BASE+'/task-analysis')
    def task_analysis(request:Request,section:Literal['summary','dates','equipment','duplicates']='summary',offset:int=Query(0,ge=0),
                      origin:Literal['all','scheduled','manual','incident']='all',starts_on:date|None=None,ends_on:date|None=None,
                      cohort:Literal['unfinished','execution_pending','in_review']='unfinished',v=Depends(views)):
        from .task_analytics import analyze
        if set(request.query_params)-{'section','offset','origin','starts_on','ends_on','cohort'}:
            raise HTTPException(422,'Неизвестный параметр аналитического запроса')
        return analyze(v,section,offset,origin,starts_on,ends_on,cohort)

    @app.get(BASE+'/draft-changes')
    def draft_changes(identity:UUID,before_revision:int=Query(...,ge=1),after_revision:int=Query(...,ge=1),offset:int=Query(0,ge=0),v=Depends(views)):
        from sqlalchemy import text
        from .management import _guard
        _guard(v,'director','chief_engineer','engineer','dispatcher','admin')
        records=v.session.execute(text('SELECT revision,segments,occurrences FROM planning_draft_versions WHERE site_id=:site AND draft_id=:id AND revision=ANY(:revisions)'),dict(site=v.principal.site_id,id=identity,revisions=[before_revision,after_revision])).mappings().all()
        versions={r['revision']:r for r in records}
        if before_revision not in versions or after_revision not in versions:raise HTTPException(404,'Версия черновика не найдена')
        old={s['segment_id']:s for s in versions[before_revision]['segments']};new={s['segment_id']:s for s in versions[after_revision]['segments']}
        titles={o['occurrence_id']:o['title'] for r in records for o in r['occurrences']}
        def fingerprint(s):
            if s is None:return None
            return tuple(datetime.fromisoformat(s[k]).astimezone(timezone.utc) if s.get(k) else None for k in ('start_at','end_at'))+(tuple(sorted(s['worker_ids'])),s['person_hours'],s['locked'])
        changed=[dict(segment_id=key,title=titles.get((new.get(key) or old[key])['occurrence_id'],'Работа'),before=old.get(key),after=new.get(key)) for key in sorted(old.keys()|new.keys()) if fingerprint(old.get(key))!=fingerprint(new.get(key))]
        selected=changed[offset:offset+25]
        people={worker for row in selected for side in ('before','after') for worker in (row[side] or {}).get('worker_ids',[])}
        users=v.session.execute(text('SELECT u.user_id,u.full_name FROM users u JOIN site_memberships m USING(user_id) WHERE m.site_id=:site AND u.user_id=ANY(CAST(:ids AS uuid[]))'),dict(site=v.principal.site_id,ids=list(people))).mappings().all()
        return dict(items=selected,total=len(changed),offset=offset,limit=25,worker_labels={str(u['user_id']):u['full_name'] for u in users})

    @app.get(BASE+'/drafts')
    def drafts(offset:int=Query(0,ge=0),v=Depends(views)):
        from sqlalchemy import text
        from .management import _guard
        _guard(v,'director','chief_engineer','engineer','dispatcher','admin')
        params=dict(site=v.principal.site_id,offset=offset)
        rows=v.session.execute(text('''SELECT d.draft_id,d.revision,d.title,d.starts_on,d.ends_on,d.import_id FROM
            (SELECT DISTINCT ON (draft_id) * FROM planning_draft_versions WHERE site_id=:site ORDER BY draft_id,revision DESC) d
            ORDER BY d.created_at DESC,d.draft_id LIMIT 25 OFFSET :offset'''),params).mappings().all()
        total=v.session.scalar(text('SELECT count(DISTINCT draft_id) FROM planning_draft_versions WHERE site_id=:site'),params)
        return dict(items=[dict(r) for r in rows],total=total,offset=offset,limit=25)

    @app.get(BASE+'/planning-context')
    def planning_context(starts_on:date,ends_on:date,v=Depends(views)):
        from sqlalchemy import text
        from app.schemas.requirements import RequirementsRequest
        from app.schemas.draft_plans import DraftPolicy,GenerationInput
        from . import requirements,catalog_decisions,draft_plans
        from .registry import registry_payload
        from .management import _guard
        _guard(v,'director','chief_engineer','engineer','dispatcher','admin')
        try:request=RequirementsRequest(starts_on=starts_on,ends_on=ends_on)
        except ValueError:raise HTTPException(422,'Выберите корректный период не более 366 дней') from None
        registry=registry_payload(v)
        drafts=v.session.execute(text('''SELECT DISTINCT ON (draft_id) draft_id,revision,title,starts_on,ends_on,import_id FROM planning_draft_versions
            WHERE site_id=:site AND starts_on=:start AND ends_on=:end ORDER BY draft_id,revision DESC LIMIT 26'''),dict(site=v.principal.site_id,start=starts_on,end=ends_on)).mappings().all()
        policy=DraftPolicy(format_version=2,capacity_status='unknown',capacity_confirmed=False,access_status='unknown')
        if len(drafts)==1:
            version=draft_plans.get_version(v,drafts[0]['draft_id'])
            policy=DraftPolicy.model_validate(version['source_snapshot']['input']['policy'])
        catalogs=[]
        imports=v.session.execute(text('SELECT import_id,filename FROM regulation_catalog_imports WHERE site_id=:site ORDER BY created_at DESC LIMIT 11'),dict(site=v.principal.site_id)).mappings().all()
        for catalog in imports[:10]:
            rows,decisions,equipment=catalog_decisions.load(v,catalog['import_id'])
            records=catalog_decisions.records(rows,decisions,equipment)
            ready=[n for n,r in records.items() if r['prepared'] and r['decision'].get('frequency_kind')!='included_in']
            from collections import Counter
            catalogs.append(dict(id=str(catalog['import_id']),filename=catalog['filename'],total=len(rows),prepared_rows=ready,
                frequencies={str(n):dict(kind=r['decision']['frequency_kind'],interval=r['decision']['frequency_interval']) for n,r in records.items() if r['prepared']},
                blockers=dict(Counter(b for r in records.values() for b in r['blockers']))))
        if len(catalogs)==1 and catalogs[0]['prepared_rows']:
            request.catalog=GenerationInput(import_id=catalogs[0]['id'],starts_on=starts_on,ends_on=ends_on,row_numbers=catalogs[0]['prepared_rows'],expansion='source_january' if starts_on.month==1 and ends_on.month==1 else 'confirmed_rule',policy=policy)
        ledger= requirements.preview(v,request)
        return dict(site=dict(id=str(v.principal.site_id),name=v.principal.site_name),registry=registry,requirements=ledger,
            catalogs=catalogs,catalogs_truncated=len(imports)>10,drafts=[dict(d) for d in drafts],drafts_truncated=len(drafts)>25,
            policy=policy.model_dump(mode='json'),portfolio_input=dict(kind='portfolio',requirements=request.model_dump(mode='json'),policy=policy.model_dump(mode='json')))

    @app.get(BASE+'/inventory')
    def inventory(site_offset:int=Query(0,ge=0),offset:int=Query(0,ge=0),current_only:bool=False,v=Depends(views)):
        from sqlalchemy import text
        from app.security.sessions import Principal
        from .projections import Views
        from .registry import registry_payload
        scope=' AND s.site_id=:site' if current_only else ''
        sites=v.session.execute(text('''SELECT s.site_id,s.name,s.timezone,m.role FROM sites s JOIN site_memberships m USING(site_id)
            WHERE m.user_id=:user AND m.is_active AND s.is_active'''+scope+' ORDER BY s.name,s.site_id'),dict(user=v.principal.user_id,site=v.principal.site_id)).mappings().all()
        if site_offset>=len(sites):return dict(site_total=len(sites),site=None,items=[],total=0,offset=offset)
        site=sites[site_offset];role=SQL_ROLES.get(site['role'])
        meta=dict(id=str(site['site_id']),name=site['name'],role=role)
        if role not in ('director','admin','chief_engineer','engineer','dispatcher'):
            return dict(site_total=len(sites),site=dict(meta,status='access_denied'),items=[],total=None,offset=offset)
        who=Principal(v.principal.user_id,site['site_id'],role,v.principal.name,v.principal.email,site['name'],site['timezone'])
        scoped=Views(v.session,v.models,who);registry=registry_payload(scoped)
        scoped.prefetch('work_order_equipment','equipment_id');scoped.prefetch('work_orders','work_order_id')
        orders={r.work_order_id:r for r in scoped.rows('work_orders')}
        items=[]
        for eq in registry['items'][offset:offset+25]:
            services=eq['services'];active=[s for s in services if s['enabled']]
            gaps=[]
            if eq['status']!='active':gaps.append('Оборудование не активно')
            if not active:gaps.append('Нет опубликованных операций ТО')
            if any(s['norm_value'] is None or s['norm_unit']=='unconfirmed' for s in active):gaps.append('Норма или единица трудозатрат не подтверждена')
            if any(s['duration_minutes'] is None for s in active):gaps.append('Длительность операции не подтверждена')
            from .task_analytics import PENDING,UNFINISHED
            pending=[orders[l.work_order_id] for l in scoped.rows('work_order_equipment',equipment_id=eq['equipment_id']) if l.work_order_id in orders and orders[l.work_order_id].status in UNFINISHED]
            items.append(dict(id=str(eq['equipment_id']),name=eq['name'],asset_code=eq['asset_code'],system_id=str(eq['system_id']),data_origin=eq['properties'].get('data_origin'),operations=len(services),published_operations=len(active),pending_tasks=len(pending),execution_pending_tasks=sum(o.status in PENDING for o in pending),in_review_tasks=sum(o.status=='in_review' for o in pending),planning_gaps=gaps))
        return dict(site_total=len(sites),site=dict(meta,status='ok'),systems=registry['systems'],items=items,total=len(registry['items']),offset=offset,limit=25,assessment='Configuration gaps only; does not certify schedule feasibility')

    @app.post(BASE+'/tasks/{task_id}/prepare-assignment')
    def prepare_assignment(task_id:UUID,command:AssignmentPreparation,v=Depends(views)):
        from .assignment import assignment_context,assignment_preview
        if not has_role(v.principal.role,('dispatcher',)):raise HTTPException(403,'Действие недоступно для текущей роли')
        order=v.task(task_id);context=assignment_context(v,order)
        if command.use_planned_day and order.status in ('in_progress','rework') and v.principal.role!='chief_engineer':
            return dict(status='needs_input',code='CHIEF_HANDOFF_REQUIRED',command=None,context=context,
                        explanation='Переназначение начатой работы подтверждает главный инженер.')
        if context.get('status')!='ready':return dict(status='needs_input',explanation=context.get('explanation'),context=context,command=None)
        if command.one_person_only and context.get('crewSize')!=1:
            return dict(status='needs_input',explanation=f"Для этого задания требуется {context.get('crewSize')} исполнителей; одного недостаточно.",context=context,command=None)
        day=None
        if command.use_planned_day:
            zone=ZoneInfo(context['timezone'])
            if order.planned_start_at is not None:
                day=order.planned_start_at.astimezone(zone).date()
            elif order.schedule_entry_id is not None:
                day=v.one('schedule_entries',schedule_entry_id=order.schedule_entry_id).planned_date
            if day is None:
                return dict(status='needs_input',code='PLANNED_DAY_UNKNOWN',command=None,context=context,
                            explanation='У наряда нет подтверждённой плановой даты. Обязательный срок не заменяет дату выполнения.')
            start=datetime.combine(day,time.min);end=start+timedelta(days=1)
            if order.planned_start_at is not None and order.planned_end_at is not None:
                start=order.planned_start_at.astimezone(zone).replace(tzinfo=None)
                end=order.planned_end_at.astimezone(zone).replace(tzinfo=None)
        else:
            start=datetime.fromisoformat(context['defaultStartLocal']);end=datetime.fromisoformat(context['defaultEndLocal'])
        result=assignment_preview(v,order,start,end,executor_ids=command.executor_ids,
                                  individual_only=True, prefer_low_load=command.use_planned_day)
        result['taskTitle']=v.operation(order)[1] if command.use_planned_day else order.operation_snapshot.get('label') or 'Задание'
        if day is not None:
            result.update(plannedDay=day,windowStartLocal=start,windowEndLocal=end)
        return result

    @app.get(BASE+'/equipment')
    def equipment(q:str=Query('',max_length=200),offset:int=Query(0,ge=0),asset_code:str|None=Query(None,min_length=1,max_length=128),
                  accepted_maintenance:AcceptedMaintenance|None=None,limit:int=Query(25,ge=1,le=25),v=Depends(views)):
        import json
        from sqlalchemy import cast,Text,literal
        from sqlalchemy.dialects.postgresql import JSONB,aggregate_order_by
        cls=v.models['equipment'];filters=[cls.site_id==v.principal.site_id]
        if v.principal.role=='executor':
            # Assignment visibility belongs to the same MVCC snapshot.
            assignments=v.models['work_assignments'];links=v.models['work_order_equipment']
            visible=select(links.equipment_id).join(assignments,and_(
                assignments.work_order_id==links.work_order_id,assignments.site_id==links.site_id)).where(
                links.site_id==v.principal.site_id,assignments.site_id==v.principal.site_id,
                assignments.user_id==v.principal.user_id,assignments.status.not_in(('cancelled','declined')))
            filters.append(cls.equipment_id.in_(visible))
        filters.extend(_equipment_search_filters(cls, q, asset_code))
        if accepted_maintenance is not None:
            accepted = _accepted_maintenance(v, cls.equipment_id)
            filters.append(accepted if accepted_maintenance == 'present' else ~accepted)
            filters.append(cls.status != 'retired')
        # Exactly equipment_response fields. Count, complete digest and selected
        # page use one statement, with no ORM hydration or per-row SQL.
        fields=('equipment_id','site_id','system_id','parent_equipment_id','equipment_type_id',
                'asset_code','name','serial_number','commissioned_on','location','properties','status','revision')
        authorized=select(*(getattr(cls,key) for key in fields)).where(*filters).cte('authorized_equipment').prefix_with('MATERIALIZED')
        payload=func.jsonb_build_object(*(item for key in fields for item in (literal(key),authorized.c[key])))
        projected=select(authorized.c.equipment_id,authorized.c.asset_code,payload.label('payload')).cte('projected_equipment')
        empty=cast(literal('[]'),JSONB)
        summary=select(func.count().label('total'),func.coalesce(func.jsonb_agg(
            aggregate_order_by(projected.c.payload,projected.c.equipment_id)),empty).label('rows')).cte('equipment_summary')
        selected=select(projected).order_by(projected.c.asset_code,projected.c.equipment_id).offset(offset).limit(limit).cte('equipment_page')
        items=select(func.coalesce(func.jsonb_agg(aggregate_order_by(selected.c.payload,
            selected.c.asset_code,selected.c.equipment_id)),empty)).scalar_subquery()
        scope=dict(user_id=str(v.principal.user_id),site_id=str(v.principal.site_id),role=v.principal.role,timezone=v.principal.timezone)
        applied=dict(q=q.strip(),asset_code=asset_code)
        source = {}
        if accepted_maintenance is not None:
            applied.update(accepted_maintenance=accepted_maintenance, exclude_retired=True)
            source['history_basis'] = _accepted_scope(v.principal)
        context=func.jsonb_build_object('scope',cast(literal(json.dumps(scope)),JSONB),
                                      'filters',cast(literal(json.dumps(applied)),JSONB))
        document=func.jsonb_build_object('context',context,'rows',summary.c.rows)
        digest=func.encode(func.sha256(func.convert_to(cast(document,Text),'UTF8')),'hex')
        result=v.session.execute(select(summary.c.total,items.label('items'),digest.label('snapshot_id'))).mappings().one()
        return dict(items=result['items'],total=result['total'],offset=offset,limit=limit,
                    snapshot_id=result['snapshot_id'],scope=scope,filters=applied,timezone=v.principal.timezone, **source)

    @app.get(BASE+'/staff')
    def staff(q:str=Query('',max_length=200),offset:int=Query(0,ge=0),v=Depends(views)):
        if not has_role(v.principal.role,('director','admin','dispatcher','engineer')):raise HTTPException(403,'Нет доступа к команде')
        members=v.models['site_memberships'];users=v.models['users']
        filters=[members.site_id==v.principal.site_id]
        if q.strip():filters.append(or_(users.full_name.ilike('%'+q.strip()+'%'),users.email.ilike('%'+q.strip()+'%')))
        source=select(members.user_id,users.full_name,users.email,members.role,and_(members.is_active,users.is_active).label('is_active'),members.revision,members.employed_from,members.employed_until).join(users,users.user_id==members.user_id).where(*filters)
        count=v.session.scalar(select(func.count()).select_from(source.subquery()))
        rows=v.session.execute(source.order_by(users.full_name,members.user_id).offset(offset).limit(25)).mappings().all()
        return dict(items=[dict(r,role=SQL_ROLES.get(r['role'],r['role'])) for r in rows],total=count,offset=offset,limit=25)

    @app.get(BASE+'/staff/{user_id}')
    def person(user_id:UUID,v=Depends(views)):
        if not has_role(v.principal.role,('director','admin','dispatcher','engineer')):raise HTTPException(403,'Нет доступа к сотруднику')
        member=v.one('site_memberships',user_id=user_id);user=v.one('users',user_id=user_id)
        return dict(user_id=user_id,full_name=user.full_name,email=user.email,role=SQL_ROLES.get(member.role,member.role),is_active=member.is_active and user.is_active,
            membership_is_active=member.is_active,account_is_active=user.is_active,revision=member.revision,
            employed_from=member.employed_from,employed_until=member.employed_until,
            qualifications=[dict(skill_id=r.skill_id,verified_at=r.verified_at,valid_until=r.valid_until,revision=r.revision) for r in v.rows('user_skills',user_id=user_id)],
            shifts=[dict(shift_rule_id=r.shift_rule_id,label=r.label,pattern=r.calendar_pattern,valid_from=r.valid_from,valid_until=r.valid_until,starts_local=r.starts_local,ends_local=r.ends_local,status=r.status,is_active=r.is_active,revision=r.revision) for r in v.rows('employee_shift_rules',user_id=user_id)],
            availability=[dict(availability_id=r.availability_id,starts_at=r.starts_at,ends_at=r.ends_at,status=r.status,reason=r.reason,revision=r.revision) for r in v.rows('availability_slots',user_id=user_id)])

    @app.get(BASE+'/tasks')
    def tasks(period:Literal['upcoming','overdue','undated','all']='upcoming',state:Literal['draft','assigned','clarification','rework','in_progress','in_review','completed','cancelled']|None=None,active_only:bool=True,q:str=Query('',max_length=200),offset:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=MAX_COLLECTION_PAGE),scheduled_only:bool=False,
              equipment_id:UUID|None=None,unfinished_only:bool=False,starts_on:date|None=None,ends_on:date|None=None,
              maintenance_only:bool=False, unassigned_only:bool=False,
              type_keys:list[MaintenanceTypeKey]|None=Query(None,max_length=12),
              type_codes:list[MaintenanceTypeCode]|None=Query(None,max_length=12),
              equipment_accepted_maintenance:AcceptedMaintenance|None=None,
              equipment_ids:list[UUID]|None=Query(None,min_length=1,max_length=25),
              equipment_q:str|None=Query(None,min_length=1,max_length=200),
              equipment_asset_code:str|None=Query(None,min_length=1,max_length=128),
              on_days:list[date]|None=Query(None,max_length=31),
               sort:Literal['earliest','latest']|None=None,attention_only:bool=False,use_planned_date:bool=False,
              v=Depends(views)):
        from .task_analytics import UNFINISHED
        orders=v.models['work_orders'];assignments=v.models['work_assignments'];rules=v.models['maintenance_rules'];operations=v.models['operation_templates']
        entries=v.models['schedule_entries']
        zone=ZoneInfo(v.principal.timezone)
        instant=func.coalesce(orders.planned_start_at,orders.regulatory_deadline_at);now=datetime.now(timezone.utc)
        schedule_basis=use_planned_date and period!='overdue'
        deadline_basis=period=='overdue' or (unfinished_only and period=='upcoming' and not schedule_basis)
        if schedule_basis:
            instant=func.coalesce(orders.planned_start_at,func.timezone(v.principal.timezone,cast(entries.planned_date,DateTime)))
        elif deadline_basis:
            instant=(orders.regulatory_deadline_at if period=='overdue' else
                     func.coalesce(orders.regulatory_deadline_at,orders.planned_start_at))
        def task_instant(order):
            if period=='overdue':return order.regulatory_deadline_at
            if deadline_basis:return order.regulatory_deadline_at or order.planned_start_at
            if schedule_basis:
                return order.planned_start_at or (v.one('schedule_entries',schedule_entry_id=order.schedule_entry_id).planned_date
                                                  if order.schedule_entry_id else None)
            return order.planned_start_at or order.regulatory_deadline_at
        active_states=['draft','assigned','clarification','rework']
        if period=='overdue':
            instant=orders.regulatory_deadline_at
            active_states.extend(('in_progress','in_review'))
        filters=[orders.site_id==v.principal.site_id]
        if maintenance_only:
            filters.append(orders.maintenance_rule_id.is_not(None))
        if type_keys or type_codes:
            kinds = v.models['maintenance_types']
            def type_key(column):
                return func.translate(func.regexp_replace(column, '[[:space:]‑–-]', '', 'g'), 'TOТОto', 'тотото')
            selected_types = select(kinds.maintenance_type_id).where(kinds.maintenance_type_id==operations.maintenance_type_id)
            if type_keys:
                selected_types = selected_types.where(or_(type_key(kinds.code).in_(type_keys),type_key(kinds.name).in_(type_keys)))
            if type_codes:
                selected_types = selected_types.where(kinds.code.in_(type_codes))
            filters.append(selected_types.exists())
        has_assignment=select(assignments.work_assignment_id).where(assignments.site_id==orders.site_id,
                assignments.work_order_id==orders.work_order_id,
                assignments.status.not_in(('cancelled','declined'))).exists()
        if unassigned_only:
            filters.append(~has_assignment)
        if attention_only:
            filters.extend((orders.status.in_(UNFINISHED), or_(~has_assignment, orders.regulatory_deadline_at<now,
                            orders.status.in_(('clarification','rework')))))
        if equipment_id is not None:
            from .management import _equipment
            _equipment(v,equipment_id)
            if v.principal.role=='executor' and equipment_id not in v.visible_equipment_ids():
                raise HTTPException(404,'Оборудование не найдено')
            links=v.models['work_order_equipment']
            filters.append(select(links.work_order_id).where(links.site_id==orders.site_id,
                links.work_order_id==orders.work_order_id,links.equipment_id==equipment_id).exists())
        if equipment_ids is not None:
            if equipment_id is not None:
                raise HTTPException(422,'Укажите одну форму выборки оборудования.')
            links = v.models['work_order_equipment']
            filters.append(select(links.work_order_id).where(links.site_id==orders.site_id,
                links.work_order_id==orders.work_order_id, links.equipment_id.in_(equipment_ids)).exists())
        if equipment_accepted_maintenance is not None or equipment_q is not None or equipment_asset_code is not None:
            links = v.models['work_order_equipment']; assets = v.models['equipment']
            linked = (select(links.work_order_id).select_from(links)
                      .join(assets, and_(assets.site_id == links.site_id, assets.equipment_id == links.equipment_id))
                      .where(links.site_id == orders.site_id, links.work_order_id == orders.work_order_id))
            if equipment_accepted_maintenance is not None:
                accepted = _accepted_maintenance(v, links.equipment_id)
                linked = linked.where(assets.status != 'retired',
                                      accepted if equipment_accepted_maintenance == 'present' else ~accepted)
            linked = linked.where(*_equipment_search_filters(assets, equipment_q, equipment_asset_code))
            if equipment_id is not None:
                linked = linked.where(links.equipment_id == equipment_id)
            if equipment_ids is not None:
                linked = linked.where(links.equipment_id.in_(equipment_ids))
            filters.append(linked.exists())
        if starts_on and ends_on and ends_on<starts_on:
            raise HTTPException(422,'Конец периода раньше начала.')
        local_day=func.date(func.timezone(v.principal.timezone,instant))
        if starts_on or ends_on:
            if starts_on:filters.append(local_day>=starts_on)
            if ends_on:filters.append(local_day<=ends_on)
        if on_days:
            filters.append(local_day.in_(on_days))
        if scheduled_only:
            filters.append(orders.planned_start_at.is_not(None))
        if unfinished_only:
            filters.append(orders.status.in_(UNFINISHED))
        if state:filters.append(orders.status==state)
        elif active_only and not unfinished_only:filters.append(orders.status.in_(active_states))
        if v.principal.role=='executor':filters.append(select(assignments.work_order_id).where(assignments.work_order_id==orders.work_order_id,assignments.user_id==v.principal.user_id,assignments.status.not_in(('cancelled','declined'))).exists())
        if period=='upcoming':
            filters.append(or_(orders.planned_start_at>=now,
                               and_(orders.planned_start_at.is_(None),entries.planned_date>=now.astimezone(zone).date()))
                           if schedule_basis else instant>=now)
        elif period=='overdue':filters.extend((instant<now,orders.status.not_in(('completed','cancelled'))))
        elif period=='undated':filters.append(instant.is_(None))
        source=select(orders).outerjoin(rules,and_(rules.maintenance_rule_id==orders.maintenance_rule_id,rules.site_id==v.principal.site_id)).outerjoin(operations,operations.operation_template_id==rules.operation_template_id)
        if schedule_basis:
            source=source.outerjoin(entries,and_(entries.site_id==orders.site_id,entries.schedule_entry_id==orders.schedule_entry_id))
        if q.strip():
            filters.append(or_(*(column.icontains(q.strip(), autoescape=True) for column in (
                orders.operation_snapshot['title'].astext, orders.operation_snapshot['label'].astext,
                operations.title, operations.code))))
        source=source.where(*filters)
        count=v.session.scalar(select(func.count()).select_from(source.subquery()))
        day_counts = {}
        if on_days:
            grouping = source.with_only_columns(local_day.label('day'), func.count()).group_by(local_day)
            day_counts = {day.isoformat(): total for day, total in v.session.execute(grouping)}
        ordering = (instant.asc().nulls_last() if sort == 'earliest' or (sort is None and period != 'overdue')
                    else instant.desc().nulls_last())
        selected=v.session.scalars(source.order_by(ordering,orders.work_order_id).offset(offset).limit(limit)).all()
        v.prepare_task_views(selected)
        scope = {}
        if equipment_id is not None:scope['equipment_id']=str(equipment_id)
        if equipment_ids is not None:scope['equipment_ids']=sorted({str(identity) for identity in equipment_ids})
        if equipment_q is not None:scope['equipment_q']=equipment_q
        if equipment_asset_code is not None:scope['equipment_asset_code']=equipment_asset_code
        if q:scope['q']=q
        if unfinished_only:scope['unfinished_only']=True
        if attention_only:scope['attention_only']=True
        if use_planned_date:scope['date_basis']='deadline' if period=='overdue' else 'planned'
        if starts_on is not None:scope['starts_on']=starts_on
        if ends_on is not None:scope['ends_on']=ends_on
        if on_days:scope['on_days']=sorted(set(on_days))
        if sort:scope['sort']=sort
        if type_keys:scope['type_keys']=sorted(set(type_keys))
        if type_codes:scope['type_codes']=sorted(set(type_codes))
        if equipment_accepted_maintenance is not None:
            scope.update(equipment_accepted_maintenance=equipment_accepted_maintenance)
        items = [v.task_view(order, checked_at=now) for order in selected]
        for item, order in zip(items, selected, strict=True):
            item['matchedAt'] = task_instant(order)
            item['rawStatus'] = order.status
            item['overdueMinutes'] = int((now-order.regulatory_deadline_at).total_seconds()//60) if item['isOverdue'] else None
        if equipment_id is not None or maintenance_only:
            for item, order in zip(items, selected, strict=True):
                if equipment_id is not None:
                    item['equipmentIds'] = [str(link.equipment_id) for link in
                                            v.rows('work_order_equipment', work_order_id=order.work_order_id)]
                item['regulatoryDeadlineAt'] = (order.regulatory_deadline_at.astimezone(ZoneInfo(v.principal.timezone))
                                                if maintenance_only and order.regulatory_deadline_at else order.regulatory_deadline_at)
        if on_days:
            for item, order in zip(items, selected, strict=True):
                instant_value = task_instant(order)
                item['matchedDay'] = (instant_value.astimezone(zone).date() if isinstance(instant_value,datetime) else instant_value).isoformat()
        return dict(items=items,total=count,period=period,timezone=v.principal.timezone,checked_at=now,offset=offset,limit=limit,
            filters=dict(state=state,active_only=active_only,states=[state] if state else list(UNFINISHED) if unfinished_only else active_states if active_only else 'all_including_completed_and_cancelled',
                         **({'scheduled_only': True} if scheduled_only else {}),
                         **({'maintenance_only': True} if maintenance_only else {}),
                         **({'unassigned_only': True} if unassigned_only else {}),**scope),
            **({'day_counts': day_counts} if on_days else {}),
            **({'history_basis': _accepted_scope(v.principal)} if equipment_accepted_maintenance is not None else {}),
            page_complete=offset==0 and len(selected)==count,analysis_tool='tasks_analyze')
