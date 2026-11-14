"""Versioned decisions on source rows; no writes into the active maintenance plan."""
from collections import Counter
import json
from uuid import UUID, uuid4
from fastapi import Depends, HTTPException, Path, Query, Response
from sqlalchemy import text
from app.catalog_decisions import assess
from app.schemas.catalog_decisions import (DecisionCommand, DecisionInput, DecisionRecord,
    DecisionProgress, DecisionHistory, BindingOptions)
from .catalog_imports import READ_ROLES
from .management import PREFIX, _guard, _edit, _audit


def sources(v, identity):
    rows = v.session.scalar(text("""SELECT jsonb_agg(jsonb_build_object('row',o->'row'))
        FROM regulation_catalog_imports c,LATERAL jsonb_array_elements(c.catalog_data->'operations') o
        WHERE c.site_id=:site AND c.import_id=:id"""),dict(site=v.principal.site_id,id=identity))
    if rows is None: raise HTTPException(404,'Каталог не найден')
    return {r['row'] for r in rows}


def latest(v, identity, numbers=None):
    condition=' AND d.row_number = ANY(CAST(:numbers AS integer[]))' if numbers is not None else ''
    return {r['row_number']:dict(r) for r in v.session.execute(text("""SELECT DISTINCT ON (d.row_number) d.*,u.full_name AS author_name
        FROM catalog_operation_decisions d JOIN users u ON u.user_id=d.created_by
        WHERE d.site_id=:site AND d.import_id=:id"""+condition+" ORDER BY d.row_number,d.revision DESC"),
        dict(site=v.principal.site_id,id=identity,numbers=numbers)).mappings()}


def bindings(v, decisions):
    ids = {UUID(str(i)) for r in decisions.values() for i in r['payload']['equipment_ids']}
    if not ids: return {}
    statement=text('''SELECT equipment_id,asset_code,name,status,revision FROM equipment
        WHERE site_id=:site AND equipment_id = ANY(CAST(:ids AS uuid[]))''')
    return {str(r['equipment_id']):dict(r) for r in v.session.execute(statement,dict(site=v.principal.site_id,ids=list(ids))).mappings()}


def records(rows, decisions, equipment, numbers=None):
    output = {}
    def build(number, *, allow_parent=True):
        current = decisions.get(number)
        payload = current['payload'] if current else DecisionInput().model_dump(mode='json')
        parent = None
        parent_number = payload.get('included_in_row')
        # Nested included steps are deliberately blocked: no cycles or hidden double counting.
        if allow_parent and parent_number in decisions and parent_number != number and decisions[parent_number]['payload']['frequency_kind'] != 'included_in':
            parent = build(parent_number,allow_parent=False)
        blockers,hours,elapsed = assess(payload,equipment,rows,current=current,parent=parent)
        confirmed = bool(current and current['confirmed'])
        return dict(row_number=number,revision=current['revision'] if current else 0,
            created_by=current['created_by'] if current else None,created_at=current['created_at'] if current else None,
            author_name=current.get('author_name') if current else None,
            confirmed=confirmed,reason=current['reason'] if current else '',decision=payload,
            equipment=[equipment[str(i)] for i in payload['equipment_ids'] if str(i) in equipment],
            blockers=blockers,prepared=confirmed and not blockers,total_person_hours=hours,elapsed_hours=elapsed,
            ready_for_real_plan=False)
    for number in sorted(rows if numbers is None else numbers): output[number]=build(number)
    return output


def load(v,identity,number=None):
    _guard(v,*READ_ROLES)
    rows=sources(v,identity)
    decisions=latest(v,identity,[number] if number is not None else None)
    if number in decisions:
        parent=decisions[number]['payload'].get('included_in_row')
        if parent and parent != number: decisions.update(latest(v,identity,[parent]))
    return rows,decisions,bindings(v,decisions)


def qualification_labels(v,ids):
    if not ids: return {}
    return {str(r['skill_id']):r['name'] for r in v.session.execute(text('SELECT skill_id,name FROM skills WHERE skill_id=ANY(CAST(:ids AS uuid[]))'),dict(ids=[UUID(str(i)) for i in ids])).mappings()}


def register_routes(app,views):
    base=PREFIX+'/catalog-imports/{identity}'

    @app.get(base+'/binding-options',response_model=BindingOptions)
    def options(identity:UUID,response:Response,q:str=Query('',max_length=320),offset:int=Query(0,ge=0,le=1000000),v=Depends(views)):
        _guard(v,*READ_ROLES); sources(v,identity)
        needle='%'+q.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
        where="site_id=:site AND status='active' AND (name ILIKE :q OR asset_code ILIKE :q)"
        params=dict(site=v.principal.site_id,q=needle,offset=offset)
        rows=v.session.execute(text('SELECT equipment_id,asset_code,name,status,revision FROM equipment WHERE '+where+' ORDER BY asset_code,equipment_id LIMIT 25 OFFSET :offset'),params).mappings().all()
        total=v.session.scalar(text('SELECT count(*) FROM equipment WHERE '+where),params)
        response.headers['Cache-Control']='private, no-store'
        return dict(items=[dict(r) for r in rows],total=total)

    @app.get(base+'/preparation',response_model=DecisionProgress)
    def progress(identity:UUID,response:Response,v=Depends(views)):
        rows,decisions,equipment=load(v,identity)
        data=records(rows,decisions,equipment)
        response.headers['Cache-Control']='private, no-store'
        return dict(total=len(rows),prepared_count=sum(r['prepared'] for r in data.values()),
            confirmed_count=sum(r['confirmed'] for r in data.values()),
            blocker_counts=dict(Counter(b for r in data.values() for b in r['blockers'])),
            items=[{k:r[k] for k in ('row_number','revision','confirmed','prepared','blockers')} for r in data.values()])

    @app.get(base+'/operations/{number}/decision',response_model=DecisionRecord)
    def read(identity:UUID,response:Response,number:int=Path(ge=1,le=1048576),v=Depends(views)):
        rows,decisions,equipment=load(v,identity,number)
        if number not in rows: raise HTTPException(404,'Строка каталога не найдена')
        response.headers['Cache-Control']='private, no-store'
        result=records(rows,decisions,equipment,[number])[number]
        result['qualification_labels']=qualification_labels(v,result['decision'].get('qualification_ids',[]))
        return result

    @app.post(base+'/operations/{number}/decision',response_model=DecisionRecord)
    def write(identity:UUID,command:DecisionCommand,response:Response,number:int=Path(ge=1,le=1048576),v=Depends(views)):
        roles=('chief_engineer',) if command.confirm else ('chief_engineer','admin')
        with _edit(v,roles=roles,exact_roles=True):
            # Same lock order as equipment administration; membership was rechecked in _edit.
            v.session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),dict(key=f'catalog:{v.principal.site_id}'))
            rows=sources(v,identity)
            if number not in rows: raise HTTPException(404,'Строка каталога не найдена')
            decisions=latest(v,identity,[n for n in (number,command.decision.included_in_row) if n is not None])
            old=decisions.get(number)
            revision=old['revision'] if old else 0
            if command.expected_revision != revision:
                raise HTTPException(409,'REVISION_CONFLICT: строка изменена. Откройте актуальную версию; введённые значения сохранены в форме')
            payload=command.decision.model_dump(mode='json')
            proposed=dict(payload=payload,confirmed=False,revision=revision+1,created_by=v.principal.user_id,
                          author_name=v.one('users',user_id=v.principal.user_id).full_name,
                          created_at=None,reason=command.reason,parent_revision=None,binding_snapshot=[])
            decisions[number]=proposed
            equipment=bindings(v,decisions)
            if any(str(i) not in equipment for i in command.decision.equipment_ids):
                raise HTTPException(422,'Оборудование не найдено в текущем здании')
            if command.decision.qualification_ids:
                skills=v.session.scalar(text('SELECT count(*) FROM skills WHERE skill_id=ANY(CAST(:ids AS uuid[]))'),
                    dict(ids=command.decision.qualification_ids))
                if skills != len(command.decision.qualification_ids): raise HTTPException(422,'Выбран неизвестный допуск')
            assessment=records(rows,decisions,equipment,[number])[number]
            if command.confirm and assessment['blockers']:
                raise HTTPException(422,'Нельзя подтвердить строку: '+', '.join(assessment['blockers']))
            parent=decisions.get(command.decision.included_in_row)
            snapshot=[equipment[str(i)] for i in command.decision.equipment_ids]
            decision_id=uuid4()
            saved=v.session.execute(text('''INSERT INTO catalog_operation_decisions
                (decision_id,site_id,import_id,row_number,revision,created_by,confirmed,reason,payload,binding_snapshot,parent_revision)
                VALUES (:id,:site,:catalog,:row,:revision,:actor,:confirmed,:reason,CAST(:payload AS jsonb),CAST(:bindings AS jsonb),:parent)
                RETURNING created_at'''),dict(id=decision_id,site=v.principal.site_id,catalog=identity,row=number,
                    revision=revision+1,actor=v.principal.user_id,confirmed=command.confirm,reason=command.reason,
                    payload=json.dumps(payload),bindings=json.dumps(snapshot,default=str),parent=parent['revision'] if parent else None)).scalar_one()
            _audit(v,'catalog_operation_decisions',decision_id,'confirm' if command.confirm else 'save_draft',
                   dict(import_id=str(identity),row_number=number,revision=revision+1))
            proposed.update(confirmed=command.confirm,created_at=saved,binding_snapshot=snapshot,parent_revision=parent['revision'] if parent else None)
            result=records(rows,decisions,equipment,[number])[number]
            result['qualification_labels']=qualification_labels(v,command.decision.qualification_ids)
        response.headers['Cache-Control']='private, no-store'
        return result

    @app.get(base+'/operations/{number}/decision/history',response_model=DecisionHistory)
    def history(identity:UUID,response:Response,number:int=Path(ge=1,le=1048576),offset:int=Query(0,ge=0,le=1000000),v=Depends(views)):
        _guard(v,*READ_ROLES)
        if number not in sources(v,identity): raise HTTPException(404,'Строка каталога не найдена')
        params=dict(site=v.principal.site_id,id=identity,row=number,offset=offset)
        found=v.session.execute(text('''SELECT d.revision,d.created_by,u.full_name AS author_name,d.created_at,d.confirmed,d.reason,
            d.payload AS decision,d.binding_snapshot AS equipment,d.parent_revision
            FROM catalog_operation_decisions d JOIN users u ON u.user_id=d.created_by
            WHERE d.site_id=:site AND d.import_id=:id AND d.row_number=:row
            ORDER BY d.revision DESC LIMIT 25 OFFSET :offset'''),params).mappings().all()
        total=v.session.scalar(text('SELECT count(*) FROM catalog_operation_decisions WHERE site_id=:site AND import_id=:id AND row_number=:row'),params)
        response.headers['Cache-Control']='private, no-store'
        return dict(items=[dict(r) for r in found],total=total)
