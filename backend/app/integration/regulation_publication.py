"""Execution profiles come from the frozen approved regulation, never the client."""
from uuid import UUID
from fastapi import HTTPException
from pydantic import ValidationError
from app.schemas.publication import RegulationExecutionProfile


def choices(facts):
    checks={str(c['checklist_template_id']):c for c in facts.get('checklist_templates',[])}
    by_operation={}
    for check in checks.values():
        by_operation.setdefault(str(check['operation_template_id']),[]).append(check)
    result=[]
    for fact in facts.get('bindings',[]):
        rule=fact['rule'];op=fact['operation'];p=rule['schedule_parameters'];meta=p.get('operation_metadata',{})
        selected=[checks[i] for i in p['checklist_ids'] if i in checks and str(checks[i]['operation_template_id'])==str(op['operation_template_id'])] if 'checklist_ids' in p else by_operation.get(str(op['operation_template_id']),[])
        if 'checklist_ids' not in p:
            latest={}
            for c in selected:
                if c['item_code'] not in latest or c['template_version']>latest[c['item_code']]['template_version']:latest[c['item_code']]=c
            selected=list(latest.values())
        selected.sort(key=lambda c:(c['position'],str(c['checklist_template_id'])))
        metadata=p.get('checklist_metadata',{})
        checklist=[dict(text=c['prompt'],answer_kind={'checkbox':'boolean','number':'number','text':'text','photo':'boolean'}[c['input_kind']],
            unit=c['unit_code'],required=c['is_required'],visual_verifiability=metadata.get(str(c['checklist_template_id']),{}).get('visual_verifiability','not_verifiable'),
            photo_required=metadata.get(str(c['checklist_template_id']),{}).get('photo_required',c['input_kind']=='photo'),
            source_item_key=metadata.get(str(c['checklist_template_id']),{}).get('source_item_key'),source_refs=metadata.get(str(c['checklist_template_id']),{}).get('source_refs',[])) for c in selected]
        result.append(dict(binding_id=str(fact['binding']['binding_id']),rule_id=str(rule['maintenance_rule_id']),regulation_id=str(rule['regulation_edition_id']),
            equipment_id=str(fact['equipment']['equipment_id']),equipment_name=fact['equipment']['name'],
            operation_id=str(op['operation_template_id']),code=meta.get('code',op['code']),title=meta.get('title',op['title']),
            instructions=meta.get('instructions') or op.get('description') or '',safety_notes=meta.get('safety_notes') or p.get('safety_notes') or '',
            methodology_ref=p.get('methodology_ref') or '',checklist=checklist,checklist_ids=[str(c['checklist_template_id']) for c in selected],
            measurement_requirements=p.get('measurement_requirements',[]),required_acts=p.get('required_acts',[]),
            source_complete=bool(selected) and bool(meta.get('instructions') or op.get('description')) and bool(p.get('methodology_ref'))
                and ('checklist_ids' not in p or len(selected)==len(p['checklist_ids']))))
    return result


def profiles(source,roots,supplements):
    required={str(r.binding_id) for r in roots if r.source_kind=='regulation'}
    supplied={str(p.binding_id):p for p in supplements}
    if required!=set(supplied):raise HTTPException(422,'Укажите меры безопасности и примечания для каждой привязки регламента выбранного состава')
    rows={r['binding_id']:r for r in choices(source['facts']) if r['binding_id'] in required}
    result={};operations={}
    for identity in sorted(required):
        if identity not in rows:raise HTTPException(409,'Регламент выбранного состава больше недоступен')
        row=rows[identity]
        if not row['source_complete']:raise HTTPException(422,'В регламенте неполная инструкция, методика или чек-лист; уточните утверждённую версию перед выпуском')
        try:
            profile=RegulationExecutionProfile.model_validate({k:row[k] for k in ('binding_id','rule_id','regulation_id','instructions','methodology_ref','checklist','checklist_ids','measurement_requirements','required_acts')}|
                dict(safety_notes=supplied[identity].safety_notes,engineer_note=supplied[identity].engineer_note))
        except ValidationError:raise HTTPException(422,'В регламенте нет полной инструкции, методики или корректного чек-листа; уточните источник перед выпуском')
        if any(c.answer_kind=='number' and not c.unit for c in profile.checklist):raise HTTPException(422,'Числовой пункт регламента требует подтверждённой единицы')
        result[UUID(identity)]=profile.model_dump(mode='json');operations[UUID(identity)]=row['operation_id']
    return result,operations
