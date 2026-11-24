"""Prepare a reviewable assignment from the same domain policy as the web UI."""
from fastapi import HTTPException
from sqlalchemy import text

from . import service, workflow
from .maintenance_dialogue import ASSIGN, CONTEXT, PREVIEW, TASKS, _line, _preview_facts, _task_facts, _task_line, _window


CANDIDATE_LIMIT = 7


def _pending(execution, goal):
    with execution.app.state.factory() as session:
        prior = session.scalar(text('''SELECT action_id FROM assistant_actions
            WHERE workflow_root_turn_id=:root AND workflow_goal_id=:goal AND conversation_id=:chat'''),
            dict(root=execution.state['root_turn_id'], goal=goal['id'], chat=execution.thread_id))
        if prior:
            return service.action(session, execution.principal, prior)
    return None


def _existing(source, action):
    goal = source.goal
    identity = str(action['action_id'])
    status = action['status']
    if status == 'proposed' and action['expires_at'] >= service.now():
        goal.update(action_id=identity, status='awaiting_confirmation', reason='human_confirmation_required')
        return 'Карточка назначения уже готова в этом диалоге. Проверьте состав и время, затем подтвердите её.'
    if status == 'succeeded':
        goal.update(action_id=identity, status='completed', reason=None)
        return 'По этой команде назначение уже выполнено. Результат доступен в карточке.'
    goal.update(action_id=identity, status='blocked', reason='assignment_decision_required')
    return ('По прежней карточке нужно проверить результат или подготовить новое назначение. '
            'Для новой карточки повторите явную команду назначения.')


async def _candidate(source, intent, task):
    path = dict(task_id=task['id'])
    context = await source.read(CONTEXT, dict(path=path))
    if context['expectedRevision'] != task['revision']:
        raise HTTPException(409, 'Наряд изменился между чтением и расчётом')
    if context['status'] != 'ready':
        return None, context['explanation']
    if intent.get('individual') and context['crewSize'] != 1:
        return None, f'По регламенту требуется состав из {context["crewSize"]} человек.'
    start, end = _window(context, task, intent.get('day'))
    preview = await source.read(PREVIEW, dict(path=path, body=dict(expected_revision=context['expectedRevision'],
                                start_local=start, end_local=end)), retain=_preview_facts)
    return (preview, '') if preview['status'] == 'ok' and preview['command'] else (None, preview['explanation'])


async def prepare(source, intent):
    execution, goal = source.execution, source.goal
    execution.check()
    if not all(name in execution.tools for name in (ASSIGN, PREVIEW, CONTEXT, TASKS)):
        goal.update(status='blocked', reason='assignment_permission_required')
        return 'Подготовка назначения недоступна вашей роли на текущем объекте.'
    if original := _pending(execution, goal):
        return _existing(source, original)
    query = dict(period='upcoming', maintenance_only=True, unassigned_only=True, limit=CANDIDATE_LIMIT)
    if intent.get('day'):
        query.update(starts_on=intent['day'], ends_on=intent['day'])
    if intent.get('type_keys'):
        query['type_keys'] = intent['type_keys']
    data = await source.read(TASKS, dict(query=query), retain=_task_facts)
    constraints = []
    for task in data['items']:
        preview, reason = await _candidate(source, intent, task)
        if not preview:
            constraints.append(f'- {_task_line(task)}. {_line(reason)}')
            continue
        names = ', '.join(_line(worker['name']) for worker in preview['selectedWorkers'])
        label = f'{_task_line(task)}. Состав — {names}.'
        args = dict(path=dict(task_id=task['id']), body={**preview['command'], 'crew_id': preview['crewId']})
        tool = execution.tools[ASSIGN]
        execution.check()
        service.progress(execution.app, execution.turn_id, execution.trace, ASSIGN)
        with execution.app.state.factory() as session:
            action = await service.propose(execution.app, session, execution.principal, execution.thread, tool,
                args, label, execution.headers, execution.turn_id, workflow_goal_id=goal['id'],
                workflow_root_turn_id=execution.state['root_turn_id'])
        if action['status'] != 'proposed':
            return _existing(source, action)
        intent['task_id'] = task['id']
        identity = str(action['action_id'])
        source.retain(ASSIGN, args, dict(status='awaiting_confirmation', action_id=identity), action_id=identity)
        execution.trace.append(dict(tool=ASSIGN, status='proposed', at=workflow.timestamp()))
        answer = f'Подготовил карточку назначения. {label}\n\nПроверьте состав и время в карточке, затем подтвердите назначение.'
        if constraints:
            answer += '\n\nДля более ранних нарядов подбор не прошёл:\n' + '\n'.join(constraints)
        return answer
    goal.update(status='blocked', reason='assignment_candidate_unavailable')
    if not data['items']:
        return 'В проверенном периоде нет доступных свободных нарядов ТО. Карточка назначения не создана.'
    answer = f'Проверил ближайшие свободные наряды ТО · {len(data["items"])} из {data["total"]}. Подтверждённого состава нет.'
    return answer + '\n\n' + '\n'.join(constraints)
