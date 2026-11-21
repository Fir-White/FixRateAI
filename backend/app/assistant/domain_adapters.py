"""Semantic business selectors -> bounded authorized tool calls.

These adapters never infer a user process from keywords. The planner selects a
typed objective; server code resolves exact inventory codes and supplies only
that objective's data. The shared executor still validates and authorizes every
call and persists every prerequisite result.
"""
from app.schemas.assistant import AgentStep
import re


LEGACY_SUPPORTED={'equipment_read','equipment_edit','regulations_read','calendar_evidence','equipment_service_history','inventory_read','staff_edit','attachment_read','workbook_readiness','task_assign','tasks_find'}
SUPPORTED=LEGACY_SUPPORTED|{'equipment_find','staff_read','staff_find','workforce_read','operations_list','operation_read','components_read','catalog_read','profile_read','notifications_list','enrollment_read','task_read','task_start'}


def equipment_context(goal, state):
    """Reuse a verified identity explicitly named in this objective and request.

    Only current-root, complete authorized equipment results supply identities;
    arbitrary properties and model prose never do. This supplies a selector,
    not a cached business result: the final operation still runs with fresh RBAC.
    """
    request=state.get('request','').casefold();title=goal.get('title','').casefold()
    identities=set()
    for proof in state.get('evidence',[]):
        if not proof.get('complete') or not proof.get('retained') or proof.get('scope')!=state.get('scope'):continue
        value=proof.get('result')
        if proof.get('tool')=='equipment_find' and isinstance(value,dict):rows=value.get('items',[])
        elif proof.get('tool')=='equipment_read' and isinstance(value,dict):rows=[value]
        else:continue
        for row in rows:
            if not isinstance(row,dict):continue
            code=row.get('asset_code');identity=row.get('equipment_id')
            if not isinstance(code,str) or not code or not isinstance(identity,str):continue
            pattern=r'(?<!\w)'+re.escape(code.casefold())+r'(?!\w)'
            if re.search(pattern,request) and re.search(pattern,title):identities.add(identity)
    return next(iter(identities)) if len(identities)==1 else None


def next_step(goal,state):
    target=goal['tool']
    if target not in SUPPORTED or goal.get('reason') in ('plan_outcome_tool_mismatch','tool_error_422'):return None
    if target not in LEGACY_SUPPORTED and goal.get('outcome') is None:return None
    selector=goal.get('selector',{})
    # Bind a single user-provided UUID before accepting a model's wrong ID slot.
    fields={'staff_profile':'user_id','maintenance_definition':'operation_id','task_card':'task_id','equipment_card':'equipment_id'}
    identity_key=fields.get(goal.get('outcome'))
    if target=='task_start':identity_key='task_id'
    if identity_key:
        pattern=r'\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b'
        requested=set(re.findall(pattern,state.get('request','')))
        named={value for value in requested if value.casefold() in goal.get('title','').casefold()}
        selected=named if len(named)==1 else requested
        if len(selected)==1:selector[identity_key]=next(iter(selected)).lower()
    def call(name,args):
        import json
        return AgentStep(answer='',calls=[dict(tool=name,arguments_json=json.dumps(args),goal_id=goal['id'],explanation='Подготовлено сервером по выбранному пункту и точным параметрам пользователя.')])
    if target in ('workforce_read','operations_list','catalog_read','profile_read','notifications_list','enrollment_read'):
        return call(target,{})
    if target=='staff_read':
        search=selector.get('search')
        if search:
            identity,searched=staff_context(goal,state)
            if not searched:return call('staff_find',dict(query=dict(q=search)))
            if not identity:return None
            declared=selector.get('user_id')
            if declared and declared.casefold() in state.get('request','').casefold() and declared!=identity:return None
            selector['user_id']=identity
        return call(target,dict(path=dict(user_id=selector['user_id']))) if selector.get('user_id') else None
    if target=='staff_find':
        return call(target,dict(query=dict(q=selector['search']))) if selector.get('search') else None
    if target=='operation_read':
        return call(target,dict(path=dict(operation_id=selector['operation_id']))) if selector.get('operation_id') else None
    if target=='task_read':
        return call(target,dict(path=dict(task_id=selector['task_id']))) if selector.get('task_id') else None
    if target=='tasks_find':
        query={}
        search=(selector.get('search') or '').strip()
        if search and not re.fullmatch(r'(?:ближайш\w*|предстоящ\w*|активн\w*|просрочен\w*|все|то|работ\w*|задан\w*|план\w*|список)',search,re.I):
            query['q']=search
        query['period']='all' if re.search(r'\b(?:все|просрочен\w*|истори\w*|прошл\w*)\b',state.get('request',''),re.I) else 'upcoming'
        return call(target,dict(query=query))
    if target=='task_start':
        changes=goal.get('changes') or {}
        if not selector.get('task_id') or set(changes)-{'expected_revision'}:return None
        revision=changes.get('expected_revision')
        if revision is not None and type(revision) is not int:return None
        return call(target,dict(path=dict(task_id=selector['task_id']),body={} if revision is None else dict(expected_revision=revision)))
    if target=='task_assign':
        evidence=[proof for proof in state.get('evidence',[]) if proof['goal_id']==goal['id'] or proof['goal_id'] in goal.get('depends_on',[])]
        task_id=selector.get('task_id')
        found_in_goal=any(proof.get('tool')=='tasks_find' and proof.get('goal_id')==goal['id'] for proof in evidence)
        if task_id and not found_in_goal:
            return None
        if not task_id:
            finds=[proof for proof in evidence if proof.get('tool')=='tasks_find']
            if not finds:
                return call('tasks_find',dict(query=dict(period='upcoming')))
            last_find=finds[-1]
            last_result=last_find.get('result') if isinstance(last_find.get('result'),dict) else {}
            items=last_result.get('items') if isinstance(last_result.get('items'),list) else []
            if not items and (last_find.get('arguments',{}).get('query') or {}).get('period','upcoming')!='all':
                return call('tasks_find',dict(query=dict(period='all')))
            if not items:
                return None
            drafts=[item for item in items if isinstance(item,dict) and item.get('state')=='draft' and item.get('id')]
            active=[item for item in items if isinstance(item,dict) and item.get('state') in ('draft','assigned','rework') and item.get('id')]
            candidates=drafts or active
            if not candidates:
                return None
            if len(candidates)==1 or re.search(r'ближайш',state.get('request',''),re.I):
                task_id=str(candidates[0]['id'])
            else:
                return None
        prep=next((proof for proof in reversed(evidence) if proof.get('tool')=='assignment_prepare' and (proof.get('arguments',{}).get('path') or {}).get('task_id')==task_id),None)
        if prep is None:
            request_text=state.get('request','')
            one_person=bool(re.search(r'\b(?:одного|1\s+человек\w*|самого\s+\w+\s+работника|одного\s+работника|одного\s+исполнителя)\b',request_text,re.I)
                            and not re.search(r'\b(?:бригад\w*|сотрудников|работников|исполнителей)\b',request_text,re.I))
            body=dict(one_person_only=True) if one_person else {}
            return call('assignment_prepare',dict(path=dict(task_id=task_id),body=body))
        prep_result=prep.get('result') if isinstance(prep.get('result'),dict) else {}
        if prep_result.get('status') in ('ok','ready') and isinstance(prep_result.get('command'),dict):
            cmd=prep_result['command']
            body={key:cmd[key] for key in ('expected_revision','executor_ids','start_at','end_at') if key in cmd}
            if cmd.get('crew_id'):body['crew_id']=cmd['crew_id']
            body['reason']=str((goal.get('changes') or {}).get('reason') or goal.get('title') or 'Назначение исполнителей')[:500]
            return call('task_assign',dict(path=dict(task_id=task_id),body=body))
        return None
    if target=='equipment_find':
        query={}
        if selector.get('equipment_code'):query['asset_code']=selector['equipment_code']
        elif selector.get('search'):query['q']=selector['search']
        elif goal.get('outcome') not in (None,'equipment_search'):return None
        return call(target,dict(query=query))
    if target=='inventory_read':
        query={}
        if selector.get('current_only') is not None:query['current_only']=selector['current_only']
        elif goal.get('outcome')=='equipment_inventory':query['current_only']=True
        return call(target,dict(query=query))
    if target=='staff_edit':
        if not selector.get('user_id') or not goal.get('changes'):return None
        return call(target,dict(path=dict(user_id=selector['user_id']),body=dict(goal['changes'])))
    if target in ('attachment_read','workbook_readiness'):
        selected=selector.get('attachment_ids') or []
        if not selected:return None
        conversation=state['scope']['conversation_id']
        if target=='workbook_readiness':
            return call(target,dict(query=dict(conversation_id=conversation,attachment_ids=selected)))
        read={proof.get('arguments',{}).get('path',{}).get('attachment_id') for proof in state['evidence']
              if proof['goal_id']==goal['id'] and proof['tool']=='attachment_read' and proof.get('complete')}
        identity=next((identity for identity in selected if identity not in read),None)
        return call(target,dict(path=dict(identity=conversation,attachment_id=identity),query=dict(full_book=True))) if identity else None
    identity=selector.get('equipment_id')
    code=selector.get('equipment_code')
    evidence=[proof for proof in state['evidence'] if proof['goal_id']==goal['id'] or proof['goal_id'] in goal['depends_on']]
    if code:
        found=[]
        for proof in reversed(evidence):
            args=proof.get('arguments',{}).get('query',{})
            if proof['tool']=='equipment_find' and args.get('asset_code')==code:
                result=proof.get('result',{})
                if isinstance(result,dict):
                    found=[row for row in result.get('items',[]) if row.get('asset_code','').casefold()==code.casefold()]
                break
        if len(found)!=1:
            return call('equipment_find',dict(query=dict(asset_code=code)))
        # An explicit ID and exact code must resolve to the same resource.
        if identity and identity!=str(found[0]['equipment_id']):return None
        identity=str(found[0]['equipment_id'])
    if not identity:
        # Only a declared data dependency can inherit an already resolved ID.
        inherited={proof.get('arguments',{}).get('path',{}).get('equipment_id') for proof in evidence
                   if proof['goal_id'] in goal['depends_on'] and proof.get('arguments',{}).get('path',{}).get('equipment_id')}
        if len(inherited)==1:identity=inherited.pop()
    if not identity and not code:identity=equipment_context(goal,state)
    if not identity:return None
    args=dict(path=dict(equipment_id=identity))
    if target in ('calendar_evidence','equipment_service_history'):
        if not selector.get('starts_on') or not selector.get('ends_on'):return None
        args['query']={key:selector[key] for key in ('starts_on','ends_on')}
    if target=='equipment_edit':
        if not goal.get('changes'):return None
        args['body']=dict(goal['changes'])
    return call(target,args)


def staff_context(goal,state):
    """Resolve one literal requested identity from complete scoped API evidence."""
    search=(goal.get('selector',{}).get('search') or '').strip().casefold()
    if not search or search not in state.get('request','').casefold():return None,True
    for proof in reversed(state.get('evidence',[])):
        if proof.get('goal_id') not in [goal['id'],*goal.get('depends_on',[])]:continue
        if proof.get('tool')!='staff_find' or (proof.get('arguments',{}).get('query') or {}).get('q','').strip().casefold()!=search:continue
        if not proof.get('complete') or not proof.get('retained') or proof.get('scope')!=state.get('scope'):return None,True
        value=proof.get('result',{});rows=value.get('items',[]) if isinstance(value,dict) else []
        matches=[row for row in rows if isinstance(row,dict) and row.get('user_id')
            and (str(row.get('email','')).casefold()==search if '@' in search
                 else search in (str(row.get('full_name',''))+' '+str(row.get('email',''))).casefold())]
        return (str(matches[0]['user_id']) if len(matches)==1 else None),True
    return None,False
