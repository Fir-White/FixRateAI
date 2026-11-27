"""Export and audit role-aware tool coverage without opening a database."""
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT)]
from fastapi.routing import APIRoute
from app.main import create_app
from app.assistant.tools import TOOLS,file_fields,describe,route_for
from app.assistant.capabilities import excluded_routes
from app.assistant.erp_operator import exposure
from app.assistant.workflow import specialist

def manifest(app):
    actual={(m,r.path) for r in app.routes if isinstance(r,APIRoute) and r.include_in_schema and r.path.startswith('/api/') for m in r.methods}
    covered={(t.method,t.path) for t in TOOLS};excluded=excluded_routes()
    missing=actual-covered-set(excluded)
    if missing:raise AssertionError('User API is missing assistant tools: '+str(sorted(missing)))
    tools=[]
    for tool in TOOLS:
        arguments=describe(app,tool)['inputSchema']
        handler=route_for(app,tool).endpoint
        operation=app.openapi()['paths'][tool.path][tool.method.lower()]
        schema_fields={key: sorted(value.get('properties', {})) for key,value in arguments['properties'].items()}
        responses={code: {mime: data['schema'] for mime,data in details.get('content', {}).items() if 'schema' in data}
                   for code,details in operation['responses'].items()}
        operator=exposure(tool) if 'assistant' in tool.agents else 'unavailable'
        tools.append(dict(name=tool.name,title=tool.title,method=tool.method,path=tool.path,roles=list(tool.roles),agents=list(tool.agents),requires_confirmation=tool.mode=='write',file_fields=sorted(file_fields(app,tool)),protected_inputs=list(tool.secrets),optional_protected_inputs=list(tool.optional_secrets),
                          domain=specialist(tool.name),handler=f'{handler.__module__}:{handler.__qualname__}',
                          operation_id=operation['operationId'],argument_fields=schema_fields,response_schemas=responses,
                          before_read=tool.before,operator=operator))
    return dict(format_version=1,tools=tools,excluded=[dict(method=m,path=p,reason=reason) for (m,p),reason in sorted(excluded.items())],infrastructure_exclusion='Only the exact transport, pre-login and compatibility routes listed above; no blanket path-prefix exclusion')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--write',action='store_true');args=parser.parse_args()
    result=manifest(create_app());path=ROOT/'contracts/assistant-tools.json'
    if args.write:path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    assert json.loads(path.read_text(encoding='utf-8'))==result,'Run scripts/assistant_capabilities.py --write'
    print('Assistant API coverage verified:',len(result['tools']),'tools; no unaccounted user routes')
