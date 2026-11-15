"""Aggregate a single live artifact directory; never infer unmeasured quality rates."""
import argparse,json,statistics
from pathlib import Path

def ratio(n,d,method):return dict(numerator=n,denominator=d,value=n/d if d else None,method=method)

def summarize(directory):
    records=[json.loads(p.read_text(encoding='utf-8')) for p in sorted(directory.glob('*.json'))]
    records=[r for r in records if 'case' in r and 'outcome' in r]
    if not records:raise ValueError('No completed live episode artifacts')
    calls=[call for row in records for call in row.get('model_calls',[])]
    tools=[]
    for row in records:
        for step in row['steps']:
            previous=None
            for entry in step.get('trace',[]):
                if entry['tool'].startswith('__'):continue
                if entry.get('attempt',1)>1 and previous is not None:
                    previous['status']=entry['status'];previous['retried']=True;continue
                previous=dict(tool=entry['tool'],status=entry['status'],retried=len(entry.get('attempts',[]))>1)
                tools.append(previous)
    repaired=[t for t in tools if t['retried']]
    latency=sorted(r['latency_seconds'] for r in records)
    forbidden=[]
    for row in records:
        actions=[a for s in row['steps'] if s.get('kind')=='answer' for a in s.get('actions',[])]
        expected={'create':'equipment_create','rename':'equipment_edit','staff':'staff_edit','component':'component_install'}.get(row['kind'])
        if any(a['tool_name']!=expected for a in actions):forbidden.append(row['case'])
    cross=[r for r in records if r['kind'] in ('reset','followup')]
    replay=[r for r in records if r['kind'] in ('create','rename','staff','component')]
    return dict(episodes=len(records),unique_case_ids=len({r['case'] for r in records}),
        model_episodes=sum(bool(r.get('model_calls')) for r in records),inference_requests=len(calls),
        task_completion=ratio(sum(r['outcome']=='passed' for r in records),len(records),'Per-episode test oracle; not every sentence independently verified'),
        tool_call_success=ratio(sum(t['status'] in ('completed','proposed') for t in tools),len(tools),'Logical calls in recorded traces; proposal success is not domain execution'),
        recovery=ratio(sum(t['status']=='completed' for t in repaired),len(repaired),'GET repairs visible in trace, not provider inference retries'),
        unexpected_proposal_rate=ratio(len(forbidden),len(records),'Unexpected action cards, distinct from executed unauthorized changes'),
        cross_turn=ratio(sum(r['outcome']=='passed' for r in cross),len(cross),'Context reset and explicit referent episodes'),
        replay_oracle=ratio(sum(r['outcome']=='passed' for r in replay),len(replay),'Create/edit/install/role, confirm and replay with independent SQL state checks'),
        average_logical_tool_calls=len(tools)/len(records),
        latency=dict(n=len(latency),p50=statistics.median(latency),p95=latency[min(len(latency)-1,int(len(latency)*.95))],maximum=max(latency)),
        tokens=dict(prompt=sum(c.get('prompt_tokens') or 0 for c in calls),completion=sum(c.get('completion_tokens') or 0 for c in calls)),
        grounded_answer_rate=None,hallucination_rate=None,unauthorized_execution_rate=None,constraint_violation_rate=None,
        unmeasured_reason='No independent claim-by-claim adjudication; complete state/constraint rates require their separate suites. Selected core facts and domain fingerprints are tested, not universal correctness.',
        monetary_cost=None)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args();value=summarize(args.directory)
    if args.output:args.output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    else:print(json.dumps(value,ensure_ascii=False,indent=2))
