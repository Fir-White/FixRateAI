"""Semantic business selectors -> bounded authorized tool calls.

These adapters never infer a user process from keywords. The planner selects a
typed objective; server code resolves exact inventory codes and supplies only
that objective's data. The shared executor still validates and authorizes every
call and persists every prerequisite result.
"""
from app.schemas.assistant import AgentStep
import re


SUPPORTED={'equipment_read','equipment_edit','regulations_read','calendar_evidence','equipment_service_history','inventory_read','staff_edit','attachment_read','workbook_readiness'}


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
    if target not in SUPPORTED or goal.get('reason')=='plan_outcome_tool_mismatch':return None
    selector=goal.get('selector',{})
    def call(name,args):
        import json
        return AgentStep(answer='',calls=[dict(tool=name,arguments_json=json.dumps(args),goal_id=goal['id'],explanation='Подготовлено сервером по выбранному пункту и точным параметрам пользователя.')])
    if target=='inventory_read':
        query={}
        if selector.get('current_only') is not None:query['current_only']=selector['current_only']
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
