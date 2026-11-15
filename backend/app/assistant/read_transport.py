"""At most two repairs for GET reads. Never retries a dispatched write."""
import hashlib,json,re
from fastapi import HTTPException
from .tools import validate_arguments,invoke,route_for

def safe_arguments(args):
    def clean(value,key=''):
        if re.search('password|secret|token|cookie|authorization|api.?key',key,re.I):return '[redacted]'
        if isinstance(value,dict):return {str(k)[:80]:clean(v,str(k)) for k,v in list(value.items())[:30] if k!='body'}
        if isinstance(value,list):return [clean(v,key) for v in value[:25]]
        if isinstance(value,str):
            if key=='section' and value in ('summary','dates','equipment','duplicates') or key=='origin' and value in ('all','scheduled','manual','incident'):return value
            if re.fullmatch(r'[0-9a-fA-F-]{36}',value) or key=='path' and value in ('items','systems','objects','sites','workers','applications','qualifications','shifts','availability') or key in ('period','state') and value in ('upcoming','overdue','all','undated','draft','assigned'):return value
            return dict(length=len(value),sha256=hashlib.sha256(value.encode()).hexdigest())
        return value if value is None or isinstance(value,(int,float,bool)) else '[redacted]'
    return clean(args)

def result_summary(value):
    if isinstance(value,dict):
        result=dict(type='object',keys=list(value)[:30],**{k:value[k] for k in ('total','offset','limit') if isinstance(value.get(k),int)})
        if isinstance(value.get('site'),dict) and value['site'].get('status') in ('ok','access_denied'):result['site_status']=value['site']['status']
        if isinstance(value.get('complete'),bool):result['complete']=value['complete']
        for key in ('selected_tasks','scanned_tasks'):
            if isinstance(value.get(key),int):result[key]=value[key]
        if isinstance(value.get('snapshot_id'),str) and re.fullmatch('[0-9a-f]{64}',value['snapshot_id']):result['snapshot_id']=value['snapshot_id']
        return result
    if isinstance(value,list):return dict(type='array',count=len(value))
    return dict(type=type(value).__name__)

def repair(app,tool,args,inspect_projection=False):
    if tool.mode!='read' or tool.method!='GET' or not isinstance(args,dict):return None
    fixed=json.loads(json.dumps(args));view=fixed.get('view',{})
    # Omitted optional envelopes have no selector semantics. Null is never sent
    # to the strict backend; mandatory fields are still checked on the retry.
    for envelope in ('path','query'):
        if fixed.get(envelope,False) is None:
            fixed.pop(envelope);inspect_projection=True
    if not isinstance(view,dict):return None
    query_fields={f.name for f in route_for(app,tool).dependant.query_params}
    # Pagination accidentally put in the endpoint query/root belongs to projection.
    for source in (fixed,fixed.get('query',{})):
        if not isinstance(source,dict):continue
        for key in ('offset','limit'):
            if key in source and (source is fixed or key not in query_fields):
                if key in view:return None
                view[key]=source.pop(key)
    if isinstance(view.get('limit'),int) and not isinstance(view['limit'],bool) and view['limit']>25:view['limit']=25
    # A guessed projection is optional presentation, not an authorization filter.
    # Inspect the authorized root on the single repair, preserving every query
    # and path selector. This also handles compound null+projection failures.
    if inspect_projection and view.get('path'):view['path']=[]
    if view:fixed['view']=view
    return fixed if fixed!=args else None

async def read(app,tool,args,headers,trace,publish=lambda:None):
    if tool.mode!='read' or tool.method!='GET':raise ValueError('GET read required')
    current=args
    for attempt in range(3):
        entry=dict(tool=tool.name,attempt=attempt+1,retry_count=attempt,arguments=safe_arguments(current))
        checked=None
        try:
            checked=validate_arguments(app,tool,current)
            value=await invoke(app,tool,checked,headers)
            entry.update(status='completed',result=result_summary(value),error_type=None);trace.append(entry);publish()
            return checked,value
        except HTTPException as exc:
            entry.update(status='denied',code=exc.status_code,error_type='argument_validation' if exc.status_code==422 else 'access_denied' if exc.status_code in (401,403) else 'not_found' if exc.status_code==404 else 'backend_unavailable' if exc.status_code>=500 else 'tool_error')
            entry['stage']='validation' if checked is None else 'backend_or_projection'
            if isinstance(exc.detail,dict) and exc.detail.get('code')=='INVALID_VIEW':entry['validation']=exc.detail
            trace.append(entry);publish()
            projection_error=exc.detail=='Неизвестное поле результата. Используйте имена из прочитанного ответа.'
            # One envelope/pagination repair, followed only by projection recovery.
            # A normalization error and an unknown nested key may coexist.
            allowed=attempt==0 or attempt==1 and projection_error
            fixed=repair(app,tool,current,inspect_projection=projection_error) if exc.status_code==422 and allowed else None
            if fixed is None and attempt==0 and exc.status_code==422 and exc.detail=='Неизвестное поле результата. Используйте имена из прочитанного ответа.' and isinstance(current,dict) and isinstance(current.get('view'),dict) and current['view'].get('path'):
                fixed={**current,'view':{**current['view'],'path':[]}}
                entry['repair']='inspect_authorized_root_after_unknown_projection'
            if fixed is None:raise
            current=fixed
