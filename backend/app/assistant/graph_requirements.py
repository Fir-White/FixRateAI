"""Typed references to the requirement and evidence records in the workspace."""
from typing import Literal

from pydantic import BaseModel, Field

from . import workflow


class Requirement(BaseModel):
    id: str
    intent: str
    goal_ids: list[str]
    dependencies: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_statuses: list[str] = Field(default_factory=list)
    execution_status: str | None = None
    delivery_status: str | None = None


class PlanStage(BaseModel):
    id: str
    depends_on: list[str]
    kind: Literal['task', 'selection', 'projection', 'action', 'read']


def inspect_plan(state, *, has_dataflow):
    from .dependent_planning import is_dataflow_goal

    stages = []
    for goal in state['goals']:
        if state.get('task_execution'):
            kind = 'task'
        elif has_dataflow and is_dataflow_goal(goal):
            kind = 'projection' if goal['depends_on'] else 'selection'
        else:
            kind = 'action' if goal.get('mode') == 'write' or goal.get('workflow_kind') else 'read'
        stages.append(PlanStage(id=goal['id'], depends_on=goal['depends_on'], kind=kind))
    ordered = set()
    for stage in stages:
        if not set(stage.depends_on) <= ordered or stage.id in ordered:
            raise ValueError('Invalid execution dependencies')
        ordered.add(stage.id)
    return stages


def requirements(state):
    spec = state.get('request_spec')
    if spec:
        return [Requirement.model_validate(item) for item in spec['requirements']]
    return [Requirement(id=goal['id'], intent=goal.get('outcome') or goal['kind'],
                        goal_ids=[goal['id']], dependencies=goal['depends_on'],
                        evidence_ids=goal['evidence_ids'],
                        execution_status=goal['status'],
                        delivery_status=(goal.get('answer_delivery') or {}).get('status'))
            for goal in state['goals']]


def verify_evidence(state):
    evidence = {proof['id']: proof for proof in state['evidence']}
    for goal in state['goals']:
        if goal['status'] != 'completed' or goal.get('mode') != 'read':
            continue
        proofs = [evidence.get(identity) for identity in goal['evidence_ids']]
        matching = [proof for proof in proofs if proof and proof['tool'] == goal['tool']]
        meta = goal.get('semantic', {})
        bounded_list = meta.get('intent') in ('task_list', 'equipment_tasks') and any(
            proof['limitations'] == ['page_only'] and
            (meta.get('summary_only') or meta.get('limit', 0) and len(proof['result']['items']) >= meta['limit'])
            for proof in matching
        )
        if any(not proof or proof['goal_id'] != goal['id'] or proof['scope'] != state['scope']
               for proof in proofs) or not (bounded_list or workflow.can_complete(goal, state)):
            goal.update(status='partial', reason='required_evidence_kind_not_verified')
