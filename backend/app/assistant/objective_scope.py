"""Bind authorized read results to the selected resource and declared period."""
import re


def objective_scope(state,goal,name,arguments,value):
    selector=goal.get('selector',{});path=arguments.get('path') or {};query=arguments.get('query') or {}
    if name in ('profile_read','staff_read'):
        if goal.get('selector',{}).get('search') and name=='staff_read':
            from .domain_adapters import staff_context
            identity,_=staff_context(goal,state)
            if not identity or not isinstance(value,dict) or str(value.get('user_id'))!=identity:return 'requested_staff_search_not_verified'
        wanted=selector.get('user_id') or (state.get('scope',{}).get('user_id') if name=='profile_read' else None)
        if wanted:
            actual=value.get('user_id',value.get('userId')) if isinstance(value,dict) else None
            if str(actual)!=str(wanted) or path.get('user_id') and str(path['user_id'])!=str(wanted):return 'requested_user_mismatch'
    identities={'equipment_read':('equipment_id','equipment_id'),'calendar_evidence':('equipment_id','equipment_id'),
        'equipment_service_history':('equipment_id','equipment_id'),'components_read':('equipment_id','equipment_id'),
        'regulations_read':('equipment_id',None),'operation_read':('operation_id','operation_id'),'task_read':('task_id',None)}
    if name not in identities:return None
    key,result_key=identities[name];wanted=selector.get(key);actual=path.get(key)
    if wanted and str(actual)!=str(wanted):return 'requested_resource_mismatch'
    if result_key and isinstance(value,dict) and value.get(result_key) is not None and str(value[result_key])!=str(actual):return 'result_resource_mismatch'
    if name=='task_read' and isinstance(value,dict) and isinstance(value.get('task'),dict) and str(value['task'].get('id'))!=str(actual):return 'result_resource_mismatch'
    if name in ('calendar_evidence','equipment_service_history'):
        for field in ('starts_on','ends_on'):
            if selector.get(field) and str(query.get(field))!=str(selector[field]):return 'requested_period_mismatch'
            if isinstance(value,dict) and value.get(field) is not None and str(value[field])!=str(query.get(field)):return 'result_period_mismatch'
    if key!='equipment_id':return None
    code=selector.get('equipment_code');named=set();matching_code=set()
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
            pattern=r'(?<!\w)'+re.escape(asset.casefold())+r'(?!\w)'
            search=(proof.get('arguments',{}).get('query') or {}).get('q')
            literal_search=isinstance(search,str) and len(search.strip())>2 and search.casefold() in request and len(rows)==1 and data.get('total')==1
            if re.search(pattern,request) or literal_search:named.add(str(identity))
    if code and matching_code!={str(actual)}:return 'requested_equipment_code_not_verified'
    if name=='equipment_service_history' and not wanted and not code:
        inherited={str((proof.get('arguments',{}).get('path') or {}).get('equipment_id')) for proof in state.get('evidence',[])
            if proof.get('goal_id') in goal.get('depends_on',[]) and proof.get('complete') and proof.get('retained') and proof.get('scope')==state.get('scope')
            and (proof.get('arguments',{}).get('path') or {}).get('equipment_id')}
        if not actual or str(actual).casefold() not in request and named!={str(actual)} and inherited!={str(actual)}:
            return 'history_equipment_reference_unverified'
    return None
