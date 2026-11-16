"""Persisted user objectives, server evidence and independent action outcomes.

The model may plan and suggest tools. Only this module advances objectives from
authorized results; a final model answer never completes an unfinished objective.
"""
from __future__ import annotations

from datetime import datetime, timezone
import copy
import json
import re
from sqlalchemy import text
from .tools import fingerprint
from .objective_scope import objective_scope

VERSION = 1


def required_blocker(goal):
    if goal.get('required_evidence')=='manufacturer_document':return 'manufacturer_document_not_verified'
    if goal.get('required_evidence')=='user_decision':return 'user_decision_required'
    if goal.get('kind')=='conversation' and goal.get('required_evidence') not in (None,'conversation'):return 'plan_evidence_kind_mismatch'
    if goal.get('kind')!='conversation' and goal.get('required_evidence')=='conversation':return 'plan_evidence_kind_mismatch'
    return None


def verified_optimizer(value):
    if not isinstance(value,dict):return False
    result=value.get('result',value)
    if not isinstance(result,dict):return False
    optimized=result.get('optimized')
    return isinstance(optimized,dict) and optimized.get('model_complete') is True and isinstance(optimized.get('validation'),dict) and optimized['validation'].get('status')=='valid'


def evidence_required(goal):
    if goal.get('required_evidence') is not None:return goal['required_evidence']
    if goal.get('kind')=='conversation':return 'conversation'
    if goal.get('tool')=='calendar_evidence':return 'calendar_calculation'
    if goal.get('tool')=='attachment_read':return 'file_content'
    return 'saved_data'


def can_complete(goal,state):
    if required_blocker(goal):return False
    required=evidence_required(goal)
    if required=='conversation':return goal.get('kind')=='conversation'
    accepted={required,'calendar_calculation','optimizer_result'} if required=='saved_data' else {required}
    return any(proof['id'] in goal.get('evidence_ids',[]) and proof.get('complete') and proof.get('retained')
               and proof.get('evidence_kind') in accepted for proof in state['evidence'])


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def specialist(name):
    if name.startswith(('equipment', 'regulation', 'component', 'inventory', 'calendar_evidence')):
        return 'equipment'
    if name.startswith(('task', 'assignment', 'report', 'photo', 'calendar_read')):
        return 'operations'
    if name.startswith(('draft', 'portfolio', 'optimization', 'publication', 'requirements', 'planning')):
        return 'planning'
    if name.startswith(('staff', 'workforce', 'qualification', 'shift', 'availability', 'membership', 'application')):
        return 'workforce'
    if name.startswith(('attachment', 'catalog', 'import', 'export','workbook')):
        return 'documents'
    return 'administration'


def allowed_tools(target, tools):
    """Responsibility-scoped tools; backend authorization remains authoritative."""
    domain = specialist(target)
    common = {'equipment_find', 'equipment_read', 'tasks_find', 'task_read',
              'staff_find', 'staff_read', 'catalog_read', 'attachment_read'}
    return {name: tool for name, tool in tools.items()
            if specialist(name) == domain or name in common and tool.mode == 'read'}


def create_plan(selection, question, tools, scope):
    specs = list(selection.goals)
    from .intents import primary_document_requested
    if specs and primary_document_requested(question) and not any(goal.required_evidence=='manufacturer_document' for goal in specs):
        from app.schemas.assistant import GoalSpec
        ids={goal.id for goal in specs};identity='primary-document'
        while identity in ids:identity+='-source'
        specs.append(GoalSpec(id=identity,title='Проверить рекомендацию производителя по первичному документу',
            tool='',kind='unavailable',outcome='other',required_evidence='manufacturer_document'))
    # Old providers remain readable, but an undecomposed business request is not
    # silently certified as complete from a prerequisite search.
    goals = [dict(id=g.id, title=g.title, tool=g.tool, depends_on=g.depends_on,
                  outcome=g.outcome,requires_full_list=g.requires_full_list,kind=g.kind,selector=g.selector.model_dump(mode='json',exclude_none=True),changes=g.changes,response_style=g.response_style,workflow_kind=g.workflow_kind,required_evidence=g.required_evidence) for g in specs]
    if not goals:
        goals = [dict(id='request', title=question[:400], tool='', depends_on=[],
                      requires_full_list=False)]
    ids = [goal['id'] for goal in goals]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate objective IDs')
    seen = set()
    for goal in goals:
        if not set(goal['depends_on']) <= seen:
            raise ValueError('Objectives must be a dependency-ordered DAG')
        seen.add(goal['id'])
        target = tools.get(goal['tool'])
        from .intents import mutation_requested
        # A read annotation cannot certify a typed requested patch. Compile its
        # explicit changes to the single registered PATCH/PUT adapter, without
        # selecting a process from words or inventing any field/value.
        if target and target.mode=='read' and goal.get('changes') and mutation_requested(question):
            patches=[(name,tool) for name,tool in tools.items() if tool.mode=='write' and getattr(tool,'before',None)==goal['tool'] and getattr(tool,'method',None) in ('PATCH','PUT')]
            if len(patches)==1:
                goal['tool'],target=patches[0];goal['kind']='change'
        kind=goal.get('workflow_kind')
        if kind:
            from .production_workflow import WORKFLOW_TARGETS
            targets={'create':{'portfolio_save','optimization_start','optimization_read','optimization_apply','draft_read'},
                     'compare':{'optimization_start','optimization_read'},'optimize':{'optimization_start','optimization_read','optimization_apply','draft_changes'},
                     'prepare_approval':{'optimization_start','optimization_read','optimization_apply','publication_prepare','publication_profiles'}}
            if goal['tool'] not in targets.get(kind,{WORKFLOW_TARGETS[kind]}):
                goal['workflow_kind']=None
                goal.setdefault('plan_warnings',[]).append('ignored_incompatible_workflow_annotation')
        goal.update(specialist=specialist(goal['tool']),
                    mode=target.mode if target else 'clarification',
                    status='planned' if target else 'blocked',
                    reason=None if target else 'clarification_or_capability_required',
                    evidence_ids=[], action_id=None, attempts=0)
        goal['kind']=goal.get('kind') or ('change' if target and target.mode=='write' else 'read' if target else 'unavailable')
        selector=goal.get('selector',{})
        if goal.get('outcome')=='current_profile' and scope.get('user_id'):
            title_ids=set(re.findall(r'\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b',goal['title']))
            if any(identity.casefold()!=str(scope['user_id']).casefold() and identity.casefold() in question.casefold() for identity in title_ids):
                goal.update(status='blocked',reason='plan_outcome_tool_mismatch')
        if goal['tool'] in ('profile_read','staff_read') and goal['kind']=='read' and goal.get('outcome')!='current_profile' and not goal.get('changes'):
            ids=set(re.findall(r'\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b',question))
            named={identity for identity in ids if identity.casefold() in goal['title'].casefold()}
            selected=named if len(named)==1 else ids
            if len(selected)==1:selector['user_id']=next(iter(selected)).lower()
        if goal['tool'] in ('profile_read','profile_edit') and selector.get('user_id') and scope.get('user_id') and str(selector['user_id'])!=str(scope['user_id']):
            if goal.get('outcome')=='current_profile':goal.update(status='blocked',reason='plan_outcome_tool_mismatch')
            elif goal['tool']=='profile_read' and goal['kind']=='read' and not goal.get('changes') and 'staff_read' in tools:
                goal.update(tool='staff_read',outcome='staff_profile')
            else:goal.update(status='blocked',reason='plan_outcome_tool_mismatch')
        from .outcome_contracts import normalize_goal
        normalized=normalize_goal(goal,tools);goal.clear();goal.update(normalized)
        target=tools.get(goal['tool'])
        goal.update(specialist=specialist(goal['tool']),mode=target.mode if target else 'clarification')
        if goal['kind']=='conversation' and not goal['tool']:
            goal.update(mode='conversation',status='planned',reason=None)
        if goal['kind']=='conversation' and (mutation_requested(question) or goal.get('changes') or goal.get('selector',{}).get('equipment_code') or goal.get('selector',{}).get('equipment_id') or goal.get('selector',{}).get('attachment_ids') or goal.get('response_style')=='analysis'):
            goal.update(status='blocked',reason='plan_outcome_tool_mismatch')
        if target and ((goal['kind']=='change')!=(target.mode=='write') or target.mode=='read' and (mutation_requested(goal['title']) or bool(goal.get('changes')))):
            goal.update(status='blocked',reason='plan_outcome_tool_mismatch')
        if goal.get('required_evidence')=='manufacturer_document':
            goal.update(status='blocked',reason='manufacturer_document_not_verified',message='Соответствие рекомендации производителя не подтверждено: проверенный первичный документ с версией и страницей недоступен этому инструменту.')
        elif goal.get('required_evidence')=='user_decision':goal.update(status='blocked',reason='user_decision_required')
    # A plan containing only reads cannot fulfill an explicit mutation. This
    # detects missing work, never chooses or authorizes a write operation.
    from .intents import mutation_command_requested
    if specs and mutation_command_requested(question) and not any(goal.get('mode')=='write' or goal.get('kind')=='change' for goal in goals):
        for goal in goals:
            if goal.get('kind')=='read' and goal.get('status')=='planned':
                goal.update(status='blocked',reason='plan_outcome_tool_mismatch')
    return dict(version=VERSION, scope=scope, request=question, goals=goals,
                evidence=[], outcome='planned', revision=0, created_at=timestamp(),
                metrics=dict(llm_calls=0, llm_seconds=0, tool_calls=0, tool_seconds=0),
                stop_reason=None, decomposition_verified=bool(specs))


def bind_explicit(state,question,tools):
    """A strict single-command grammar is authoritative over model guesses.

    The parser deliberately rejects multiple mutations, ambiguous selectors and
    explicit revision conditions. It cannot capture a compound request and
    finish it early: only its one fully specified mutation goal is replaced;
    independent read goals remain in the same persisted plan.
    """
    from .explicit_draft import specification
    from .intents import mutation_requested
    spec=specification(question)
    if not spec or spec['tool'] not in tools:return state
    candidates=[goal for goal in state['goals'] if goal['mode']=='write' or mutation_requested(goal['title'])]
    previous=candidates[0] if len(candidates)==1 else None
    if len(candidates)>1:return state
    if previous is None and any(required_blocker(goal) for goal in state['goals']):return state
    identity=previous['id'] if previous else 'explicit-command'
    selector=dict(spec['path'])
    bound=dict(id=identity,title=question[:400],tool=spec['tool'],
               depends_on=previous['depends_on'] if previous else [],requires_full_list=False,kind='change',selector=selector,
               changes=spec['changes'],response_style='facts',specialist=specialist(spec['tool']),mode='write',status='planned',
               outcome='other',required_evidence=previous.get('required_evidence') if previous else 'saved_data',
               reason=None,evidence_ids=[],action_id=None,attempts=0)
    blocker=required_blocker(bound)
    if blocker:bound.update(status='blocked',reason=blocker)
    if previous:state['goals'][state['goals'].index(previous)]=bound
    else:state['goals'].append(bound)
    return state


def preserve_constraints(previous, revised,tools=None):
    """A repair may fix tools, never erase previously planned requirements."""
    old={goal['id']:goal for goal in previous['goals']}
    new={goal['id']:goal for goal in revised['goals']}
    if set(old)!=set(new):return False
    for identity,goal in new.items():
        prior=old[identity]
        goal.update(title=prior['title'],depends_on=list(prior['depends_on']),
                    selector={**goal.get('selector',{}),**prior.get('selector',{})},
                    requires_full_list=prior.get('requires_full_list',False) or goal.get('requires_full_list',False))
        if prior.get('required_evidence') is not None:goal['required_evidence']=prior['required_evidence']
        if prior.get('outcome') not in (None,'other'):goal['outcome']=prior['outcome']
        if prior.get('changes'):goal['changes']=copy.deepcopy(prior['changes'])
        if prior.get('kind')=='change':goal['kind']='change'
        if prior.get('workflow_kind'):
            if goal.get('workflow_kind')!=prior['workflow_kind']:return False
        if prior.get('response_style')=='analysis':goal['response_style']='analysis'
        blocker=required_blocker(goal)
        if blocker:goal.update(status='blocked',reason=blocker)
        if tools is not None:
            from .outcome_contracts import normalize_goal
            normalized=normalize_goal(goal,tools);goal.clear();goal.update(normalized)
            target=tools.get(goal.get('tool'))
            goal.update(specialist=specialist(goal.get('tool')),mode=target.mode if target else 'clarification')
            if (goal.get('kind')=='change' or goal.get('changes')) and (target is None or target.mode!='write'):
                goal.update(status='blocked',reason='plan_outcome_tool_mismatch')
    return True


def safe_evidence(value):
    """Private evidence can contain business data, never credentials or prompts."""
    if isinstance(value, dict):
        return {str(k): ('[redacted]' if re.search(r'password|secret|token|cookie|authorization|api.?key', str(k), re.I)
                         else safe_evidence(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [safe_evidence(v) for v in value]
    return value


def completeness(value):
    """A successful page is evidence, but cannot prove a complete registry."""
    reasons = []
    def visit(node):
        if isinstance(node, dict):
            if node.get('complete') is False or node.get('has_more') is True or node.get('truncated') is True:
                reasons.append('partial_result')
            if node.get('status') in ('blocked', 'invalid_configuration', 'access_denied', 'unavailable'):
                reasons.append('blocked_result')
            if node.get('undated_count',0) or node.get('actual_date_unknown_count',0):
                reasons.append('undated_facts')
            if node.get('actual_date_conflict') is True:
                reasons.append('conflicting_facts')
            items = node.get('items')
            total = node.get('total', node.get('total_count'))
            if isinstance(items, list) and type(total) is int and total > len(items):
                reasons.append('page_only')
            for item in node.values():
                visit(item)
        elif isinstance(node, list):
            for item in node:
                visit(item)
    visit(value)
    return not reasons, sorted(set(reasons))


def record_result(state, goal, name, arguments, value, *, action_id=None, elapsed=0,count_call=True):
    complete, reasons = completeness(value)
    if name=='notifications_list' and isinstance(value,list) and len(value)>=100:
        complete=False;reasons.append('notification_limit_cannot_prove_full_list')
    if name==goal.get('tool') and goal.get('mode')=='read':
        from .outcome_contracts import validate_result
        valid,reason=validate_result(goal,name,value)
        if not valid:complete=False;reasons.append(reason)
        reason=objective_scope(state,goal,name,arguments,value)
        if reason:complete=False;reasons.append(reason)
    if name=='attachment_read' and (goal.get('outcome')=='file_analysis' or goal.get('response_style')=='analysis' or goal.get('requires_full_list')):
        book=value.get('workbook') if isinstance(value,dict) else None
        if not isinstance(book,dict) or book.get('complete') is not True or book.get('status')!='read' or (arguments.get('query') or {}).get('full_book') is not True:
            complete=False;reasons.append('full_workbook_not_verified')
    proof = dict(id=f'e{len(state["evidence"])+1}', goal_id=goal['id'], tool=name,
                 checked_at=timestamp(), scope=state['scope'],
                 arguments=safe_evidence(arguments), sha256=fingerprint(value),
                 complete=complete, retained=True, limitations=reasons, result=safe_evidence(value))
    kind='calendar_calculation' if name in ('calendar_evidence','planning_context') else 'file_content' if name=='attachment_read' else 'optimizer_result' if name=='optimization_read' and verified_optimizer(value) else 'saved_data'
    proof['evidence_kind']=kind
    if isinstance(value,dict) and value.get('status')=='awaiting_confirmation' and value.get('action_id'):
        proof.update(evidence_kind='action_proposal',complete=False)
    # Large reads stay explicitly incomplete, instead of losing rows silently.
    encoded = json.dumps(proof, default=str, ensure_ascii=False)
    if len(encoded) > 40000 or sum(len(json.dumps(e, default=str)) for e in state['evidence']) > 100000:
        proof['result'] = {'retained': False, 'reason': 'evidence_budget'}
        proof['retained'] = False
        proof['complete'] = False
        proof['limitations'].append('evidence_budget')
    state['evidence'].append(proof)
    goal['evidence_ids'].append(proof['id'])
    state['metrics']['tool_calls'] += int(count_call)
    state['metrics']['tool_seconds'] += round(elapsed, 4)
    if action_id:
        goal.update(action_id=str(action_id), status='awaiting_confirmation', reason='human_confirmation_required')
    elif name == goal['tool'] and goal['mode'] == 'read':
        # An explicit incomplete marker is always respected. For a requested
        # full list, even a valid first page cannot settle the objective.
        goal.update(status='completed' if proof['complete'] else 'partial',
                    reason=None if proof['complete'] else ','.join(proof['limitations']))
        if isinstance(value,dict) and value.get('status')=='blocked':goal.update(status='blocked',reason='domain_blocker')
        required=evidence_required(goal)
        if required and required!=kind and not (required=='saved_data' and kind in ('calendar_calculation','optimizer_result')):
            goal.update(status='blocked',reason='required_evidence_kind_not_verified')
        if name=='attachment_read' and proof['complete']:
            selected=set(goal.get('selector',{}).get('attachment_ids',[]))
            read={item.get('arguments',{}).get('path',{}).get('attachment_id') for item in state['evidence']
                  if item['goal_id']==goal['id'] and item['tool']==name and item.get('complete')}
            if selected-read:goal.update(status='running',reason='remaining_files')
    update_outcome(state)
    return proof


def update_outcome(state):
    for goal in state['goals']:
        blocker=required_blocker(goal)
        if blocker:goal.update(status='blocked',reason=blocker)
    statuses = {goal['status'] for goal in state['goals']}
    if statuses == {'completed'} and state.get('decomposition_verified'):
        result = 'completed'
    elif statuses == {'answered'}:
        result = 'response_only'
    elif 'running' in statuses:
        result = 'running'
    elif 'awaiting_confirmation' in statuses or 'uncertain' in statuses:
        result = 'awaiting_confirmation' if 'uncertain' not in statuses else 'partial'
    elif statuses <= {'cancelled'}:
        result = 'cancelled'
    elif statuses & {'completed', 'partial'}:
        result = 'partial'
    elif 'planned' in statuses:
        result = 'planned'
    else:
        result = 'blocked'
    state['outcome'] = result
    return result


def save(app, turn_id, state, *, require_running=True):
    state['revision'] += 1
    update_outcome(state)
    with app.state.factory() as session:
        changed = session.execute(text("UPDATE assistant_turns SET workflow=CAST(:state AS jsonb) WHERE turn_id=:id" +
                                  (" AND status='running'" if require_running else '')),
                                  dict(id=turn_id, state=json.dumps(state, ensure_ascii=False, default=str))).rowcount
        session.commit()
    return bool(changed)


def refresh_actions(session, state, rows=None):
    """A transport-success receipt alone does not settle a mutation objective."""
    ids = [goal['action_id'] for goal in state['goals'] if goal.get('action_id')]
    if rows is None:
        records = session.execute(text('SELECT action_id,status,result,workflow_goal_id,expires_at,created_at FROM assistant_actions WHERE action_id=ANY(CAST(:ids AS uuid[])) OR workflow_root_turn_id=CAST(:root AS uuid) ORDER BY created_at,action_id'), dict(ids=ids, root=state.get('root_turn_id'))).mappings().all() if ids or state.get('root_turn_id') else []
        rows = {str(row['action_id']): row for row in records}
    by_goal = {row.get('workflow_goal_id'): row for row in rows.values() if row.get('workflow_goal_id')}
    for goal in state['goals']:
        blocker=required_blocker(goal)
        if blocker:
            goal.update(status='blocked',reason=blocker)
            continue
        if goal.get('workflow_kind'):
            phases=sorted((row for row in rows.values() if str(row.get('workflow_goal_id') or '').startswith(goal['id']+'::')),key=lambda row:(row['created_at'],str(row['action_id'])))
            if phases:
                latest=phases[-1];goal['phase_action_ids']=[str(row['action_id']) for row in phases]
                goal['pending_action_id']=str(latest['action_id'])
                if latest['status']=='uncertain':goal.update(status='uncertain',reason='read_only_reconciliation_required')
                elif latest['status'] in ('failed','rejected','stale'):goal.update(status='blocked',reason='action_'+latest['status'])
                elif latest['status']=='proposed' and latest.get('expires_at') and latest['expires_at']<datetime.now(timezone.utc):goal.update(status='blocked',reason='action_expired_request_fresh_proposal')
                elif latest['status'] in ('proposed','executing'):goal.update(status='awaiting_confirmation',reason='human_confirmation_required' if latest['status']=='proposed' else 'action_executing')
                elif latest['status']=='succeeded' and goal['status']!='completed':goal.update(status='planned',reason='continue_workflow_from_verified_api')
            continue
        recovered = by_goal.get(goal['id'])
        if recovered and not goal.get('action_id'):
            goal['action_id'] = str(recovered['action_id'])
        if not goal.get('action_id'):
            continue
        row = rows.get(goal['action_id'])
        if not row:
            goal.update(status='blocked', reason='action_unavailable')
            continue
        status = row['status']
        verification = (row['result'] or {}).get('verification', {})
        if status == 'succeeded' and verification.get('status') == 'confirmed' and goal.get('required_evidence') in (None,'saved_data'):
            goal.update(status='completed', reason=None)
        elif status == 'succeeded':
            goal.update(status='partial', reason='postcondition_unverified')
        elif status=='proposed' and row.get('expires_at') and row['expires_at']<datetime.now(timezone.utc):
            goal.update(status='blocked',reason='action_expired_request_fresh_proposal')
        elif status in ('proposed', 'executing'):
            goal.update(status='awaiting_confirmation', reason='human_confirmation_required' if status == 'proposed' else 'action_executing')
        elif status == 'uncertain':
            goal.update(status='uncertain', reason='read_only_reconciliation_required')
        else:
            goal.update(status='blocked', reason='action_' + status)
    return update_outcome(state)


def sanitize_workflow(state):
    """Remove known legacy structured credential outputs before model/history reuse.

    Only exact credentials linked to known structured enrollment outputs are
    masked in free text. Unlinked old disclosures still require an audit.
    """
    if state is None:return None
    state=copy.deepcopy(state)
    from .tools import protected_result,workflow_enrollment_values,mask_known_outputs
    known=workflow_enrollment_values(state)
    for proof in state.get('evidence',[]):
        if proof.get('tool') in ('enrollment_read','enrollment_create'):
            proof['result']=protected_result(proof['tool'],proof.get('result'))
            # Never retain a digest of the old raw credential/projection.
            proof['sha256']=fingerprint(proof['result'])
    return mask_known_outputs(state,known)


def resume(state):
    state = sanitize_workflow(state)
    for goal in state['goals']:
        blocker=required_blocker(goal)
        if blocker:
            goal.update(status='blocked',reason=blocker);continue
        # Never recreate/replay an existing mutation, regardless of its result.
        if not goal.get('action_id') and goal['status'] not in ('completed', 'cancelled','uncertain') and not (goal.get('pending_action_id') and str(goal.get('reason') or '').startswith('action_')):
            goal.update(status='planned' if goal['tool'] else 'blocked', reason=None)
    state['stop_reason'] = None
    update_outcome(state)
    return state


def public_state(state):
    if state is None:
        return None
    result={key: state[key] for key in ('version', 'outcome', 'goals', 'metrics', 'stop_reason', 'revision')}
    if state.get('answer_format')=='facts':result['answer_format']='facts'
    return result


def unfinished_text(state):
    pending = [goal for goal in state['goals'] if goal['status'] not in ('completed','answered')]
    if not pending:
        return ''
    labels = {'awaiting_confirmation': 'ожидает подтверждения', 'uncertain': 'результат изменения требует проверки',
              'blocked': 'есть препятствие', 'partial': 'проверено частично', 'cancelled': 'остановлено'}
    return '\n\nНезавершённые пункты:\n' + '\n'.join(
        '- ' + goal['title'] + ' — ' + labels.get(goal['status'], 'ещё не выполнено') + '.' for goal in pending)
