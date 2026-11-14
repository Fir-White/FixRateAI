"""Undo the latest own unpublished change by appending a checked version."""
from uuid import UUID
from fastapi import Depends,HTTPException,Query,Response
from sqlalchemy import text
from app.schemas.draft_plans import UndoDraft,UndoDraftView,DraftRecord,WorkOccurrence,WorkSegment
from app.schemas.portfolio import planning_input
from app.scheduling.draft_validator import digest
from .draft_plans import BASE,EDIT_ROLES,get_version,metadata,clean,source_snapshot,generator_version,checked,persist,_lock_catalog
from .management import _guard,_edit


def state(v,identity,revision=None):
    head=get_version(v,identity,full=False)
    parent=get_version(v,identity,head['parent_revision'],full=False) if head['parent_revision'] else None
    blocker=None;explanation='Будет создана новая версия с содержимым предыдущей. История и действующие задания сохраняются.'
    if revision is not None and revision!=head['revision']:blocker='NOT_HEAD';explanation='Откройте последнюю версию перед отменой.'
    elif parent is None:blocker='NO_PARENT';explanation='У первой версии нет предыдущего изменения для отмены.'
    elif head['created_by']!=v.principal.user_id:blocker='OTHER_AUTHOR';explanation='Последнее изменение сделал другой автор. Его работу нельзя затереть отменой своего предыдущего изменения.'
    elif head['summary'].get('change_kind')=='undo':blocker='ALREADY_UNDONE';explanation='Последнее изменение уже является отменой. Исходная история доступна для просмотра.'
    published=v.session.scalar(text('SELECT EXISTS(SELECT 1 FROM draft_publications WHERE site_id=:site AND draft_id=:id)'),dict(site=v.principal.site_id,id=identity))
    if published:blocker='PUBLISHED_PLAN';explanation='План уже выпускался. Изменение действующих заданий требует отдельного согласованного перепланирования.'
    requires_unlock=False
    if parent and blocker is None:
        rows=v.session.execute(text('SELECT revision,segments FROM planning_draft_versions WHERE site_id=:site AND draft_id=:id AND revision=ANY(CAST(:revisions AS integer[]))'),
            dict(site=v.principal.site_id,id=identity,revisions=[head['revision'],parent['revision']])).mappings().all()
        segments={r['revision']:r['segments'] for r in rows};target={s['segment_id']:s for s in segments[parent['revision']]}
        requires_unlock=any(s['locked'] and target.get(s['segment_id'])!=s for s in segments[head['revision']])
    return dict(record=metadata(head),restores_revision=parent['revision'] if parent else None,restores_author_name=parent['author_name'] if parent else None,
        can_undo=blocker is None,blocker=blocker,explanation=explanation,requires_unlock=requires_unlock)


def register_routes(app,views):
    @app.get(BASE+'/{identity}/undo',response_model=UndoDraftView)
    def preview(identity:UUID,response:Response,revision:int|None=Query(None,ge=1),v=Depends(views)):
        _guard(v,*EDIT_ROLES);response.headers['Cache-Control']='private, no-store'
        return state(v,identity,revision)

    @app.post(BASE+'/{identity}/undo',response_model=DraftRecord)
    def undo(identity:UUID,command:UndoDraft,response:Response,v=Depends(views)):
        response.headers['Cache-Control']='private, no-store'
        with _edit(v,roles=EDIT_ROLES,exact_roles=True):
            _lock_catalog(v)
            sha=digest(dict(action='undo',actor=str(v.principal.user_id),draft_id=str(identity),command=command.model_dump(mode='json')))
            old=v.session.execute(text('SELECT draft_id,revision,request_sha256 FROM planning_draft_versions WHERE site_id=:site AND idempotency_key=:key'),dict(site=v.principal.site_id,key=command.idempotency_key)).mappings().first()
            if old:
                if old['request_sha256']!=sha:raise HTTPException(409,'Ключ повтора использован для другого действия')
                return metadata(get_version(v,old['draft_id'],old['revision'],full=False))
            choice=state(v,identity,command.expected_revision)
            if not choice['can_undo']:raise HTTPException(409,choice['explanation'])
            if choice['requires_unlock'] and not command.unlock:raise HTTPException(422,'Явно подтвердите отмену закрепления сегментов')
            current=get_version(v,identity);target=get_version(v,identity,choice['restores_revision'])
            snapshot=target['source_snapshot'];request=planning_input(snapshot['input'])
            if snapshot['source_digest']!=current['source_snapshot']['source_digest'] or digest(clean(source_snapshot(v,request)))!=snapshot['source_digest'] or snapshot['generator_version']!=generator_version(request):
                raise HTTPException(409,'Источник изменился. Отмена старого снимка требует нового актуального расчёта')
            roots=[WorkOccurrence.model_validate(o) for o in target['occurrences']]
            segments=[WorkSegment.model_validate(s) for s in target['segments']]
            previous=[WorkSegment.model_validate(s) for s in current['segments']]
            report,facts=checked(v,snapshot,roots,segments,previous=previous,unlock=command.unlock,capture=True)
            if report.status=='invalid':raise HTTPException(422,'Предыдущее состояние нарушает текущие ограничения: '+'; '.join(i.message for i in report.issues[:5]))
            return persist(v,draft_id=identity,revision=current['revision']+1,title=target['title'],reason=command.reason,snapshot=snapshot,
                sha=digest(dict(snapshot=snapshot,actor=str(v.principal.user_id))),occurrences=roots,segments=segments,report=report,resource_snapshot=facts,
                key=command.idempotency_key,request_sha=sha,action='undo',change_metadata=dict(change_kind='undo',undone_revision=current['revision'],restored_revision=target['revision']))
