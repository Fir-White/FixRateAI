"""One durable human decision per exact, already authorized action proposal."""
from dataclasses import dataclass
from typing import Literal, TypedDict

from fastapi import HTTPException
from langsmith import tracing_context
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt
from sqlalchemy import text

from . import service
from .graph_persistence import thread_config


class ActionState(TypedDict, total=False):
    action_id: str
    payload_sha256: str
    decision: Literal['confirm', 'reject']
    outcome: str


@dataclass
class ActionContext:
    app: object
    session: object
    principal: object
    row: dict
    headers: dict
    secret_values: dict | None = None
    result: dict | None = None
    error: Exception | None = None


def approval(state: ActionState):
    payload = {key: state[key] for key in ('action_id', 'payload_sha256')}
    decision = interrupt(payload)
    if decision in ('confirm', 'reject'):
        return {'decision': decision}
    raise ValueError('Invalid action decision')


async def execute(state: ActionState, runtime: Runtime[ActionContext]):
    context = runtime.context
    row = context.row
    try:
        if (state['action_id'], state['payload_sha256']) != (str(row['action_id']), row['payload_sha256']):
            raise HTTPException(409, 'Состав предложения изменился')
        if row['status'] != 'proposed':
            return {'outcome': row['status']}
        if state['decision'] == 'reject':
            context.result = service.reject(context.session, context.principal, row)
        else:
            if row['expires_at'] < service.now():
                raise HTTPException(409, 'Предложение истекло. Подготовьте новое по свежим данным.')
            expected = service.fingerprint(dict(tool=row['tool_name'], arguments=row['arguments'],
                before=row['before_snapshot'], actor=str(context.principal.user_id),
                site=str(context.principal.site_id)))
            if expected != state['payload_sha256']:
                raise HTTPException(409, 'Состав предложения изменился')
            context.result = await service.confirm(context.app, context.session, context.principal, row,
                                                   context.headers, context.secret_values)
        return {'outcome': context.result['status']}
    except Exception as exc:
        # Protected fields and server exception payloads cannot enter a checkpoint.
        context.error = exc
        return {'outcome': 'blocked'}


def build_graph(saver):
    graph = StateGraph(ActionState, context_schema=ActionContext)
    graph.add_node('approval', approval)
    graph.add_node('execute', execute)
    graph.add_edge(START, 'approval')
    graph.add_edge('approval', 'execute')
    graph.add_edge('execute', END)
    return graph.compile(checkpointer=saver)


async def _arm(graph, config, context):
    snapshot = await graph.aget_state(config)
    if snapshot.interrupts:
        return
    if snapshot.next:
        # A consumed decision can survive a process crash before dispatch.
        # Discard that schedule and require a fresh authenticated HTTP decision.
        await graph.checkpointer.adelete_thread(config['configurable']['thread_id'])
    row = context.row
    with tracing_context(enabled=False):
        await graph.ainvoke(dict(action_id=str(row['action_id']), payload_sha256=row['payload_sha256']),
                            config, context=context, durability='sync')


async def arm_turn_actions(execution):
    app, principal = execution.app, execution.principal
    graph = app.state.assistant_action_graph
    with app.state.factory() as session:
        rows = session.execute(text('''
            SELECT * FROM assistant_actions
             WHERE turn_id=:turn AND conversation_id=:chat AND status='proposed' ORDER BY action_id FOR UPDATE
        '''), dict(turn=execution.turn_id, chat=execution.thread_id)).mappings()
        for row in rows:
            config = thread_config(principal, row['conversation_id'], 'action', row['action_id'])
            await _arm(graph, config, ActionContext(app, session, principal, row, {}))


async def decide(app, session, principal, row, decision, headers=None, secret_values=None):
    graph = app.state.assistant_action_graph
    context = ActionContext(app, session, principal, row, headers or {}, secret_values)
    config = thread_config(principal, row['conversation_id'], 'action', row['action_id'])
    await _arm(graph, config, context)
    with tracing_context(enabled=False):
        await graph.ainvoke(Command(resume=decision), config, context=context, durability='sync')
    if context.error:
        raise context.error
    return context.result or service.public_action(service.action(session, principal, row['action_id']))
