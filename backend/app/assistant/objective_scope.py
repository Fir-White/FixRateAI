"""Bind authorized read results to the selected resource and declared period."""
import re


def objective_scope(state,goal,name,arguments,value):
    selector=goal.get('selector',{});path=arguments.get('path') or {};query=arguments.get('query') or {}
    site_id = state.get('scope', {}).get('site_id')
    if site_id and name == 'equipment_find' and isinstance(value, dict):
        rows = value.get('items')
        if not isinstance(rows, list) or any(not isinstance(row, dict) or str(row.get('site_id')) != str(site_id) for row in rows):
            return 'result_resource_mismatch'
    if name == 'tasks_find' and goal.get('semantic', {}).get('intent') == 'equipment_tasks':
        filters = value.get('filters', {}) if isinstance(value, dict) else {}
        identity = query.get('equipment_id')
        period = goal['semantic']['period']
        if (not isinstance(filters, dict) or not identity or filters.get('equipment_id') != identity
                or query.get('unfinished_only') is not True or filters.get('unfinished_only') is not True
                or query.get('period') != period or value.get('period') != period):
            return 'requested_task_scope_not_verified'
        if any(identity not in row.get('equipmentIds', []) or period == 'overdue' and row.get('isOverdue') is not True
               for row in value.get('items', []) if isinstance(row, dict)):
            return 'requested_task_row_scope_mismatch'
        if any(str(query.get(field)) != str(filters.get(field)) or
               str(query.get(field)) != str(selector.get(field)) for field in ('starts_on', 'ends_on')):
            return 'requested_period_mismatch'
    if name in ('profile_read','staff_read'):
        if goal.get('selector',{}).get('search') and name=='staff_read':
            from .domain_adapters import staff_context
            identity,_=staff_context(goal,state)
            if not identity or not isinstance(value,dict) or str(value.get('user_id'))!=identity:return 'requested_staff_search_not_verified'
        if name=='staff_read' and goal.get('outcome')=='staff_profile' and not selector.get('search'):
            request=state.get('request','').casefold()
            references=[str(value.get(key,'')) for key in ('user_id','email','full_name')] if isinstance(value,dict) else []
            if not any(len(item.strip())>=3 and item.casefold() in request for item in references):return 'requested_user_reference_unverified'
        wanted=selector.get('user_id') or (state.get('scope',{}).get('user_id') if name=='profile_read' else None)
        if wanted:
            actual=value.get('user_id',value.get('userId')) if isinstance(value,dict) else None
            if str(actual)!=str(wanted) or path.get('user_id') and str(path['user_id'])!=str(wanted):return 'requested_user_mismatch'
    identities={'equipment_read':('equipment_id','equipment_id'),'calendar_evidence':('equipment_id','equipment_id'),
        'equipment_service_history':('equipment_id','equipment_id'),'components_read':('equipment_id','equipment_id'),
        'regulations_read':('equipment_id',None),'operation_read':('operation_id','operation_id'),'task_read':('task_id',None)}
    if name not in identities and not (name == 'tasks_find' and query.get('equipment_id')):return None
    key,result_key=identities.get(name, ('equipment_id',None));wanted=selector.get(key);actual=path.get(key) or query.get(key)
    if wanted and str(actual)!=str(wanted):return 'requested_resource_mismatch'
    if site_id and name == 'equipment_read' and isinstance(value, dict) and str(value.get('site_id')) != str(site_id):
        return 'result_resource_mismatch'
    if result_key and isinstance(value,dict) and value.get(result_key) is not None and str(value[result_key])!=str(actual):return 'result_resource_mismatch'
    if name=='task_read' and isinstance(value,dict) and isinstance(value.get('task'),dict) and str(value['task'].get('id'))!=str(actual):return 'result_resource_mismatch'
    if name=='operation_read' and goal.get('outcome')=='maintenance_definition':
        request=state.get('request','').casefold()
        references=[str(actual or ''),str(value.get('code','')),str(value.get('title',''))] if isinstance(value,dict) else []
        if not any(len(item.strip())>=3 and re.search(r'(?<!\w)'+re.escape(item.casefold())+r'(?!\w)',request) for item in references):return 'requested_operation_reference_unverified'
    if name in ('calendar_evidence','equipment_service_history'):
        for field in ('starts_on','ends_on'):
            if selector.get(field) and str(query.get(field))!=str(selector[field]):return 'requested_period_mismatch'
            if isinstance(value,dict) and value.get(field) is not None and str(value[field])!=str(query.get(field)):return 'result_period_mismatch'
            if goal.get('semantic', {}).get('intent') in ('latest_maintenance', 'maintenance_calendar') and (
                    not isinstance(value, dict) or str(value.get(field)) != str(query.get(field))):
                return 'result_period_mismatch'
    if key!='equipment_id':return None
    code=selector.get('equipment_code');named=set();matching_code=set()
    semantic_subject=goal.get('semantic', {}).get('subject')
    if isinstance(value,dict) and code and str(value.get('equipment_id'))==str(actual) and str(value.get('asset_code','')).casefold()==code.casefold():matching_code.add(str(actual))
    request=state.get('request','').casefold()
    for proof in state.get('evidence',[]):
        if not proof.get('complete') or not proof.get('retained') or proof.get('scope')!=state.get('scope'):continue
        data=proof.get('result')
        rows=data.get('items',[]) if proof.get('tool')=='equipment_find' and isinstance(data,dict) else [data] if proof.get('tool')=='equipment_read' and isinstance(data,dict) else []
        for row in rows:
            if not isinstance(row,dict):continue
            identity=row.get('equipment_id');asset=row.get('asset_code')
            if not identity or not isinstance(asset,str) or not asset:continue
            if code and asset.casefold()==code.casefold():matching_code.add(str(identity))
            own_proof = (goal.get('id') is not None and proof.get('goal_id') == goal['id'] or
                         goal.get('identity_evidence_id') is not None and proof.get('id') == goal['identity_evidence_id'])
            if own_proof and semantic_subject and semantic_subject.casefold() == str(row.get('name') or '').casefold():
                named.add(str(identity))
            pattern=r'(?<!\w)'+re.escape(asset.casefold())+r'(?!\w)'
            search=(proof.get('arguments',{}).get('query') or {}).get('q')
            literal_search=isinstance(search,str) and len(search.strip())>2 and search.casefold() in request and len(rows)==1 and data.get('total')==1
            if (not semantic_subject or own_proof) and (
                    re.search(pattern,request) or literal_search):named.add(str(identity))
    if code and matching_code!={str(actual)}:return 'requested_equipment_code_not_verified'
    if semantic_subject and not code and not wanted and goal.get('semantic', {}).get('intent') != 'reference_details' and name in (
            'tasks_find','regulations_read','calendar_evidence','equipment_service_history','equipment_read') and named!={str(actual)}:
        return 'requested_equipment_code_not_verified'
    if name=='equipment_service_history' and not wanted and not code:
        inherited={str((proof.get('arguments',{}).get('path') or {}).get('equipment_id')) for proof in state.get('evidence',[])
            if proof.get('goal_id') in goal.get('depends_on',[]) and proof.get('complete') and proof.get('retained') and proof.get('scope')==state.get('scope')
            and (proof.get('arguments',{}).get('path') or {}).get('equipment_id')}
        if not actual or str(actual).casefold() not in request and named!={str(actual)} and inherited!={str(actual)}:
            return 'history_equipment_reference_unverified'
    return None
