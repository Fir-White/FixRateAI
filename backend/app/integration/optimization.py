"""Authenticated calculation requests and explicit adoption into a draft version."""
from uuid import UUID,uuid4
import json
from fastapi import Depends,HTTPException,Query,Response,Request
from sqlalchemy import text
from app.schemas.optimization import (StartOptimization,OptimizationRun,OptimizationRunList,OptimizationPlacements,ApplyOptimization)
from app.schemas.draft_plans import DraftRecord,GenerationInput,WorkOccurrence,WorkSegment
from app.scheduling.draft_validator import digest
from .draft_plans import BASE,EDIT_ROLES,get_version,source_snapshot,clean,checked,persist,metadata,_lock_catalog
from .catalog_imports import READ_ROLES
from .management import _guard,_edit,_audit

PUBLIC='run_id,draft_id,base_revision,created_by,created_at,started_at,finished_at,state,options,input_sha256,error_code,applied_revision,applied_kind'


def get_run(v,identity,*,full=False,lock=False):
    columns='*' if full else PUBLIC+',result'
    row=v.session.execute(text('SELECT '+columns+' FROM draft_optimization_runs WHERE site_id=:site AND run_id=:id'+(' FOR UPDATE' if lock else '')),
        dict(site=v.principal.site_id,id=identity)).mappings().first()
    if not row: raise HTTPException(404,'Расчёт не найден')
    return dict(row)


def public(row): return {key:row.get(key) for key in (*PUBLIC.split(','),'result')}


def register_routes(app,views):
    @app.post(BASE+'/{identity}/optimization-runs',response_model=OptimizationRun,status_code=202)
    def start(identity:UUID,command:StartOptimization,response:Response,request:Request,v=Depends(views)):
        response.headers['Cache-Control']='private, no-store'
        with _edit(v,roles=EDIT_ROLES,exact_roles=True):
            _lock_catalog(v)
            request_sha=digest(dict(draft_id=str(identity),actor=str(v.principal.user_id),command=command.model_dump(mode='json')))
            existing=v.session.execute(text('SELECT '+PUBLIC+',result,request_sha256 FROM draft_optimization_runs WHERE site_id=:site AND idempotency_key=:key'),dict(site=v.principal.site_id,key=command.idempotency_key)).mappings().first()
            if existing:
                if existing['request_sha256']!=request_sha: raise HTTPException(409,'Ключ повтора использован для другого расчёта')
                response.status_code=200;return public(existing)
            manager=getattr(request.app.state,'optimizer',None)
            if not manager or not manager.alive(): raise HTTPException(503,'Фоновый расчёт временно недоступен. Ручной режим продолжает работать')
            row=get_version(v,identity)
            if row['revision']!=command.expected_revision: raise HTTPException(409,'Версия изменилась; откройте актуальную перед расчётом')
            snapshot=row['source_snapshot'];generation=GenerationInput.model_validate(snapshot['input'])
            if digest(clean(source_snapshot(v,generation)))!=snapshot['source_digest']: raise HTTPException(409,'Источник изменился. Сначала создайте актуальный черновик')
            active=v.session.scalar(text("SELECT count(*) FROM draft_optimization_runs WHERE site_id=:site AND state IN ('queued','running','cancel_requested')"),dict(site=v.principal.site_id))
            if active>=2: raise HTTPException(429,'У объекта уже есть два незавершённых расчёта. Дождитесь результата или отмените один')
            duplicate=v.session.scalar(text("SELECT count(*) FROM draft_optimization_runs WHERE site_id=:site AND draft_id=:id AND state IN ('queued','running','cancel_requested')"),dict(site=v.principal.site_id,id=identity))
            if duplicate: raise HTTPException(409,'Расчёт этого черновика уже выполняется')
            occurrences=[WorkOccurrence.model_validate(o) for o in row['occurrences']];segments=[WorkSegment.model_validate(s) for s in row['segments']]
            report,facts=checked(v,snapshot,occurrences,segments,capture=True)
            payload=dict(source_snapshot=snapshot,occurrences=row['occurrences'],segments=row['segments'],resources=facts,options=command.options.model_dump(mode='json'),resource_sha256=report.resource_sha256)
            serialized=json.dumps(payload,default=str)
            if len(serialized.encode())>24*1024*1024: raise HTTPException(422,'Снимок слишком велик: сократите горизонт или состав сценария')
            v.session.execute(text('SELECT pg_advisory_xact_lock(:key)'),dict(key=268413094625719))
            queued=v.session.scalar(text("SELECT count(*) FROM draft_optimization_runs WHERE state IN ('queued','running','cancel_requested')"))
            if queued>=16: raise HTTPException(429,'Очередь расчётов заполнена. Повторите запрос после завершения текущих задач')
            identity_run=uuid4()
            v.session.execute(text('''INSERT INTO draft_optimization_runs
                (run_id,site_id,draft_id,base_revision,created_by,options,input_snapshot,input_sha256,request_sha256,idempotency_key)
                VALUES (:id,:site,:draft,:revision,:actor,CAST(:options AS jsonb),CAST(:input AS jsonb),:sha,:request_sha,:key)'''),
                dict(id=identity_run,site=v.principal.site_id,draft=identity,revision=row['revision'],actor=v.principal.user_id,
                    options=command.options.model_dump_json(),input=serialized,sha=digest(clean(payload)),request_sha=request_sha,key=command.idempotency_key))
            _audit(v,'draft_optimization_runs',identity_run,'enqueue',dict(draft_id=str(identity),revision=row['revision']))
            result=public(get_run(v,identity_run))
        manager.wake()
        return result

    @app.get(BASE+'/{identity}/optimization-runs',response_model=OptimizationRunList)
    def history(identity:UUID,response:Response,offset:int=Query(0,ge=0,le=1000000),v=Depends(views)):
        _guard(v,*READ_ROLES);get_version(v,identity,full=False)
        params=dict(site=v.principal.site_id,id=identity,offset=offset)
        rows=v.session.execute(text('SELECT '+PUBLIC+''' FROM draft_optimization_runs WHERE site_id=:site AND draft_id=:id ORDER BY created_at DESC,run_id LIMIT 25 OFFSET :offset'''),params).mappings().all()
        total=v.session.scalar(text('SELECT count(*) FROM draft_optimization_runs WHERE site_id=:site AND draft_id=:id'),params)
        response.headers['Cache-Control']='private, no-store'
        return dict(items=[public(r) for r in rows],total=total)

    path='/api/v1/maintenance/optimization-runs/{run_id}'
    @app.get(path,response_model=OptimizationRun)
    def detail(run_id:UUID,response:Response,v=Depends(views)):
        _guard(v,*READ_ROLES);response.headers['Cache-Control']='private, no-store';return public(get_run(v,run_id))

    @app.post(path+'/cancel',response_model=OptimizationRun)
    def cancel(run_id:UUID,response:Response,v=Depends(views)):
        with _edit(v,roles=EDIT_ROLES,exact_roles=True):
            row=get_run(v,run_id,lock=True)
            state='cancelled' if row['state']=='queued' else 'cancel_requested' if row['state']=='running' else row['state']
            if state!=row['state']:
                v.session.execute(text("UPDATE draft_optimization_runs SET state=:state,finished_at=CASE WHEN :state='cancelled' THEN now() ELSE finished_at END WHERE site_id=:site AND run_id=:id"),dict(state=state,site=v.principal.site_id,id=run_id))
                _audit(v,'draft_optimization_runs',run_id,'cancel_request',dict(state=state))
            result=public(get_run(v,run_id))
        response.headers['Cache-Control']='private, no-store';return result

    @app.get(path+'/placements',response_model=OptimizationPlacements)
    def placements(run_id:UUID,response:Response,kind:str=Query(...,pattern='^(baseline|optimized)$'),offset:int=Query(0,ge=0,le=1000000),v=Depends(views)):
        _guard(v,*READ_ROLES);run=get_run(v,run_id)
        params=dict(site=v.principal.site_id,id=run_id,offset=offset)
        # Column name is constrained by the enum above; all values remain bound.
        column=kind+'_segments'
        rows=v.session.execute(text('SELECT s FROM draft_optimization_runs r,LATERAL jsonb_array_elements(r.'+column+") s WHERE r.site_id=:site AND r.run_id=:id ORDER BY s->>'segment_id' LIMIT 25 OFFSET :offset"),params).scalars().all()
        total=v.session.scalar(text('SELECT coalesce(jsonb_array_length('+column+'),0) FROM draft_optimization_runs WHERE site_id=:site AND run_id=:id'),params)
        ids={UUID(w) for s in rows for w in s['worker_ids']}
        labels={str(r['user_id']):r['full_name'] for r in v.session.execute(text('''SELECT u.user_id,u.full_name FROM users u JOIN site_memberships m USING(user_id)
            WHERE m.site_id=:site AND u.user_id=ANY(CAST(:ids AS uuid[]))'''),dict(site=v.principal.site_id,ids=list(ids))).mappings()}
        root_ids=list({s['occurrence_id'] for s in rows})
        roots=v.session.execute(text('''SELECT s->>'occurrence_id' AS id,(s->>'operation_code')||' · '||(s->>'title') AS label
            FROM planning_draft_versions r,LATERAL jsonb_array_elements(r.occurrences) s
            WHERE r.site_id=:site AND r.draft_id=:draft AND r.revision=:revision
              AND s->>'occurrence_id'=ANY(CAST(:ids AS text[]))'''),dict(site=v.principal.site_id,draft=run['draft_id'],revision=run['base_revision'],ids=root_ids)).mappings()
        response.headers['Cache-Control']='private, no-store';return dict(items=rows,total=total,worker_labels=labels,occurrence_labels={r['id']:r['label'] for r in roots})

    @app.post(path+'/apply',response_model=DraftRecord)
    def apply(run_id:UUID,command:ApplyOptimization,response:Response,v=Depends(views)):
        response.headers['Cache-Control']='private, no-store'
        with _edit(v,roles=EDIT_ROLES,exact_roles=True):
            _lock_catalog(v);run=get_run(v,run_id,full=True,lock=True)
            if run['applied_revision'] is not None:
                if run['applied_kind']!=command.kind: raise HTTPException(409,'Этот расчёт уже применён с другим вариантом')
                return metadata(get_version(v,run['draft_id'],run['applied_revision'],full=False))
            if run['state']!='succeeded': raise HTTPException(409,'Расчёт ещё не завершён или был отменён')
            variant=(run['result'] or {}).get(command.kind)
            if not variant or not variant['applicable']: raise HTTPException(422,'Этот вариант не содержит допустимых изменений для применения')
            row=get_version(v,run['draft_id'])
            if row['revision']!=command.expected_revision or row['revision']!=run['base_revision']: raise HTTPException(409,'Черновик изменился после расчёта. Запустите новый расчёт')
            snapshot=row['source_snapshot'];request=GenerationInput.model_validate(snapshot['input'])
            if digest(clean(source_snapshot(v,request)))!=snapshot['source_digest']: raise HTTPException(409,'Источник изменился после расчёта. Нужен новый черновик')
            segments=[WorkSegment.model_validate(s) for s in run[command.kind+'_segments']]
            occurrences=[WorkOccurrence.model_validate(o) for o in row['occurrences']]
            previous=[WorkSegment.model_validate(s) for s in row['segments']]
            report,facts=checked(v,snapshot,occurrences,segments,previous=previous,capture=True)
            if report.resource_sha256!=run['input_snapshot']['resource_sha256']: raise HTTPException(409,'Доступность, допуски или занятость изменились после расчёта. Пересчитайте вариант')
            if report.status=='invalid': raise HTTPException(409,'Вариант больше не проходит общий валидатор. Пересчитайте его')
            result=persist(v,draft_id=run['draft_id'],revision=row['revision']+1,title=row['title'],reason=command.reason,snapshot=snapshot,sha=row['input_sha256'],
                occurrences=occurrences,segments=segments,report=report,resource_snapshot=facts,action='apply_optimization')
            v.session.execute(text('UPDATE draft_optimization_runs SET applied_revision=:revision,applied_kind=:kind WHERE run_id=:id AND site_id=:site'),dict(revision=result['revision'],kind=command.kind,id=run_id,site=v.principal.site_id))
            _audit(v,'draft_optimization_runs',run_id,'apply_to_draft',dict(revision=result['revision'],kind=command.kind))
        response.headers['Cache-Control']='private, no-store';return result
