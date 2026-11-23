"""LangGraph scheduling for the application's authorized assistant stages."""
from __future__ import annotations

import time
import traceback
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command
from langsmith import tracing_context
from sqlalchemy import text

from . import service, workflow
from .graph_context import comparison_request, comparison_result
from .graph_persistence import register_thread, thread_config
from .graph_requirements import inspect_plan, requirements, verify_evidence
from .graph_trace import trace_turn
from .orchestrator import TurnExecution


class AgentState(TypedDict, total=False):
    schema_version: Literal[1]
    request_id: str
    plan: list[dict]
    requirement_registry: list[dict]
    visited: list[str]
    current_step: str | None
    tool_calls: int
    execution_status: str
    workspace_revision: int


async def _prepare(runtime, state):
    execution = runtime.context
    if not hasattr(execution, 'turn'):
        await execution.plan()
        if execution.answer is None:
            execution.prepare_execution()
            execution.calls_used = state.get('tool_calls', 0)
    execution.check()
    return execution


async def plan(state: AgentState, runtime: Runtime[TurnExecution]):
    execution = await _prepare(runtime, state)
    if execution.answer is not None:
        # The answer remains in private chat storage, outside the checkpoint.
        execution.finish()
        return Command(update={'execution_status': 'completed'}, goto=END)
    stages = inspect_plan(execution.state, has_dataflow=execution.has_dataflow)
    return Command(update=dict(plan=[stage.model_dump() for stage in stages],
                               workspace_revision=execution.state['revision'],
                               requirement_registry=[r.model_dump() for r in requirements(execution.state)]),
                   goto='next_requirement')


def next_requirement(state: AgentState):
    completed = set(state['visited'])
    remaining = [stage for stage in state['plan'] if stage['id'] not in completed]
    if not remaining:
        return Command(goto='quality_gate')
    stage = next(item for item in remaining if set(item['depends_on']) <= completed)
    return Command(update={'current_step': stage['id']}, goto=stage['kind'])


async def _execute(state, runtime, method):
    execution = await _prepare(runtime, state)
    goal = next(goal for goal in execution.state['goals'] if goal['id'] == state['current_step'])
    await method(execution, goal)
    execution.save()
    return dict(visited=[*state['visited'], goal['id']], tool_calls=execution.calls_used,
                workspace_revision=execution.state['revision'],
                requirement_registry=[r.model_dump() for r in requirements(execution.state)])


async def read(state: AgentState, runtime: Runtime[TurnExecution]):
    return await _execute(state, runtime, TurnExecution.execute_goal)


async def action(state: AgentState, runtime: Runtime[TurnExecution]):
    return await _execute(state, runtime, TurnExecution.execute_goal)


async def selection(state: AgentState, runtime: Runtime[TurnExecution]):
    return await _execute(state, runtime, TurnExecution.execute_dataflow)


async def projection(state: AgentState, runtime: Runtime[TurnExecution]):
    return await _execute(state, runtime, TurnExecution.execute_dataflow)


async def task(state: AgentState, runtime: Runtime[TurnExecution]):
    return await _execute(state, runtime, TurnExecution.execute_task)


async def quality_gate(state: AgentState, runtime: Runtime[TurnExecution]):
    execution = await _prepare(runtime, state)
    service.progress(execution.app, execution.turn_id, execution.trace, '__quality_gate')
    with execution.app.state.factory() as session:
        workflow.refresh_actions(session, execution.state)
    verify_evidence(execution.state)
    if not execution.state.get('llm_dynamic') and comparison_request(execution.question) and not comparison_result(execution.state):
        for goal in execution.state['goals']:
            if goal['status'] == 'completed' and goal.get('semantic', {}).get('intent') == 'equipment_tasks':
                goal.update(status='partial', reason='comparison_evidence_inconsistent')
    execution.quality_gate()
    execution.save()
    return dict(requirement_registry=[r.model_dump() for r in requirements(execution.state)],
                workspace_revision=execution.state['revision'])


async def compose(state: AgentState, runtime: Runtime[TurnExecution]):
    from .graph_actions import arm_turn_actions

    execution = await _prepare(runtime, state)
    service.progress(execution.app, execution.turn_id, execution.trace, '__responding')
    await arm_turn_actions(execution)
    await execution.compose()
    execution.finish()
    return dict(execution_status=execution.state['outcome'],
                requirement_registry=[requirement.model_dump() for requirement in requirements(execution.state)],
                workspace_revision=execution.state['revision'])


def _stage(node):
    async def run(state: AgentState, runtime: Runtime[TurnExecution]):
        started = time.monotonic()
        try:
            return await node(state, runtime)
        except Exception as exc:
            # LangGraph may checkpoint a node error. Keep exception details in
            # memory and put only the stage name in the checkpoint.
            runtime.context.error = exc
            raise RuntimeError(f'ASSISTANT_GRAPH_{node.__name__.upper()}') from None
        finally:
            service.logger.info('assistant_graph_node turn=%s node=%s seconds=%.4f',
                                runtime.context.turn_id, node.__name__, time.monotonic() - started)
    return run


def build_graph(saver):
    graph = StateGraph(AgentState, context_schema=TurnExecution)
    graph.add_node('plan', _stage(plan), destinations=('next_requirement', END))
    graph.add_node('next_requirement', next_requirement,
                   destinations=('read', 'action', 'selection', 'projection', 'task', 'quality_gate'))
    for node in (read, action, selection, projection, task):
        graph.add_node(node.__name__, _stage(node))
        graph.add_edge(node.__name__, 'next_requirement')
    graph.add_node('quality_gate', _stage(quality_gate))
    graph.add_node('compose', _stage(compose))
    graph.add_edge(START, 'plan')
    graph.add_edge('quality_gate', 'compose')
    graph.add_edge('compose', END)
    return graph.compile(checkpointer=saver)


async def run(app, principal, conversation_id, turn_id, headers):
    execution = TurnExecution(app, principal, conversation_id, turn_id, headers, graph_version='v3')
    execution.bind_scope()
    graph = app.state.assistant_turn_graph
    try:
        execution.check()
        with app.state.factory.begin() as session:
            service.conversation(session, principal, conversation_id)
            row = session.execute(text('''
                SELECT t.workflow, t.resume_turn_id, p.error_code
                  FROM assistant_turns t LEFT JOIN assistant_turns p ON p.turn_id=t.resume_turn_id
                 WHERE t.turn_id=:turn AND t.conversation_id=:chat
            '''), dict(turn=turn_id, chat=conversation_id)).mappings().one()
            root = (row['workflow'] or {}).get('root_turn_id') or row['resume_turn_id'] or turn_id
            config = thread_config(principal, conversation_id, 'turn', root)
            register_thread(session, config, conversation_id)
        inputs = AgentState(schema_version=1, request_id=str(turn_id), plan=[], requirement_registry=[],
                            visited=[], current_step=None, tool_calls=0, execution_status='running')
        if row['error_code'] == 'ASSISTANT_INTERRUPTED' and row['workflow']:
            snapshot = await graph.aget_state(config)
            if (snapshot.next and snapshot.values.get('schema_version') == 1
                    and snapshot.values.get('workspace_revision', 0) <= row['workflow']['revision']):
                # Reuse the original checkpoint only when its verified plan
                # still matches the continuation's private workspace.
                expected = {goal['id'] for goal in row['workflow']['goals']}
                if {step['id'] for step in snapshot.values.get('plan', [])} == expected:
                    with app.state.factory() as session:
                        workflow.refresh_actions(session, row['workflow'])
                    reusable = {goal['id'] for goal in row['workflow']['goals']
                                if goal['status'] in ('completed', 'answered')}
                    if set(snapshot.values.get('visited', [])) <= reusable:
                        inputs = None
        recovery = ('checkpoint' if inputs is None else 'workspace' if row['resume_turn_id'] else 'new')
        service.logger.info('assistant_graph_start turn=%s version=v3 role=%s recovery=%s',
                            turn_id, principal.role, recovery)
        with trace_turn(turn_id), tracing_context(enabled=False):
            async for update in graph.astream(inputs, config, context=execution,
                                              stream_mode='updates', durability='sync'):
                service.logger.debug('assistant_graph_update turn=%s nodes=%s', turn_id, tuple(update))
        final_state = execution.state or {}
        service.logger.info('assistant_graph_end turn=%s outcome=%s reason=%s',
                            turn_id, final_state.get('outcome') or 'response_only', final_state.get('stop_reason'))
    except Exception as exc:
        failure = getattr(execution, 'error', exc)
        frame = traceback.extract_tb(failure.__traceback__)[-1]
        service.logger.warning('assistant_graph_failed turn=%s type=%s function=%s line=%s',
                               turn_id, type(failure).__name__, frame.name, frame.lineno)
        execution.fail(failure)
