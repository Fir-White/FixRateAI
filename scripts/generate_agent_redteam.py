"""Generate distinct capability/ACL/ownership/schema boundary cases from the committed registry."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
ROLES=('director','chief_engineer','engineer','dispatcher','admin','executor')

def generate():
    manifest=json.loads((ROOT/'contracts/assistant-tools.json').read_text(encoding='utf-8'))
    cases=[]
    def add(kind,group,tool,role,expected):
        cases.append(dict(id=f'{group}-{kind}-{tool["name"]}',group=group,surface='mcp-api' if kind!='schema_refs' else 'exposed-schema',
            kind=kind,tool=tool['name'],role=role,expected=expected,requirement_ids=['PLN-12','PLN-15','AT-10','AT-17'],
            independence='A distinct capability and contract/security boundary; not a reworded prompt'))
    for tool in manifest['tools']:
        role=next(r for r in ('chief_engineer','admin','engineer','dispatcher','director','executor') if r in tool['roles'])
        add('invalid_root','C',tool,role,'Reject an undeclared root property without dispatch or domain mutation')
        add('schema_refs','C',tool,role,'Every local JSON reference in the exposed schema resolves against that schema')
        forbidden=next((r for r in ('executor','director','engineer','dispatcher','chief_engineer','admin') if r not in tool['roles']),None)
        if forbidden:add('forbidden_role','G',tool,forbidden,'A valid authenticated session cannot call this capability under a forbidden role')
        if tool['requires_confirmation']:
            add('foreign_conversation','G',tool,role,'Even an authorized operation cannot use another owner or role conversation')
        if tool['method']=='GET':
            add('invalid_query','C',tool,role,'An undeclared query filter is rejected; required path values are supplied')
    assert len({c['id'] for c in cases})==len(cases)
    return dict(format_version=1,seed=83105,baseline='f8178754433d57cf5cfeb2690eb64b2fe0207ec2',
        scope='Real authenticated MCP and schema boundaries; these are not LLM generations',cases=cases)

if __name__=='__main__':
    output=ROOT/'tests/fixtures/assistant/red_team_cases.json'
    data=generate();output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"Generated {len(data['cases'])} independent capability/boundary cases")
