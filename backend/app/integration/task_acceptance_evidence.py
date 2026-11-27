"""Read the current report material and quality gates for one authorized task."""
from fastapi import HTTPException
from sqlalchemy import select

from app.assistant.task_execution import missing_report
from app.security.permissions import permission_profile
from app.storage import safe_storage_path


def inspect(views, task_id, revision, execution_id, storage_root):
    order = views.task(task_id)
    bundle = views.bundle(order)
    task = bundle['task']
    report = bundle['execution']
    if (task['revision'] != revision or
            (report and report['id'] or None) != (str(execution_id) if execution_id else None)):
        raise HTTPException(409, 'Карточка или попытка изменилась после чтения. Повторите анализ.')
    checklist = report['checklist'] if report else [
        {**item, 'answer': None} for item in order.operation_snapshot.get('checklist', [])
    ]
    material = report or dict(checklist=checklist, photos=[], actual={}, readings=[], acts=[])
    proof_files = views.rows('evidence_files', work_report_id=execution_id) if execution_id else []
    absent = {str(item.evidence_file_id) for item in proof_files
              if not safe_storage_path(storage_root, item.storage_key).is_file()}
    material = {**material, 'photos': [p for p in material['photos'] if p['id'] not in absent],
                'acts': [p for p in material['acts'] if p['id'] not in absent]}
    gaps = missing_report({**task, 'actualRequired': bundle['actualRequired']}, material)
    if report is None:
        gaps.insert(0, 'Фактический отчёт отсутствует')
    gaps.extend(f'Файл {identity} зарегистрирован, но отсутствует в хранилище' for identity in sorted(absent))

    assignees = task['assignees']
    reports = sorted(views.rows('work_reports', work_order_id=task_id), key=lambda item: item.revision_no)
    submission = []
    if order.status == 'in_review' and report and report['state'] == 'submitted':
        submission.append('Текущая попытка уже передана на приёмку')
    elif order.status != 'in_progress' or not report or report['state'] != 'draft':
        submission.append('Для передачи нужна текущая работа в исполнении с черновиком отчёта')
    else:
        draft = next((item for item in reports
                      if item.work_report_id == execution_id), None)
        if draft is None or str(draft.submitted_by) not in {person['executorId'] for person in assignees}:
            submission.append('Автор черновика не подтверждён как назначенный исполнитель')
    links = views.models['work_order_equipment']
    assets = views.models['equipment']
    linked_equipment = [dict(id=str(identity), code=code, name=name) for identity, code, name in views.session.execute(
        select(assets.equipment_id, assets.asset_code, assets.name)
        .join(links, (links.site_id == assets.site_id) & (links.equipment_id == assets.equipment_id))
        .where(links.site_id == views.principal.site_id, links.work_order_id == task_id)
        .order_by(assets.asset_code, assets.equipment_id))]

    acceptance = []
    if order.status != 'in_review' or not report or report['state']!='submitted':
        acceptance.append('Текущая попытка не находится на приёмке')
    elif 'review' not in bundle['allowedActions']:
        acceptance.append('Текущему пользователю недоступно решение по этой попытке')
    verified = {item['kind'] for item in material['acts'] if item['verified']}
    present = {item['kind'] for item in material['acts']}
    acceptance.extend(f'Контролёр ещё не проверил акт «{kind}»'
                      for kind in sorted((set(task['requiredActs']) & present) - verified))
    if task['lateAcceptanceBlocked']:
        acceptance.append('Просроченная приёмка требует отдельного согласования вне оперативного профиля MVP'
                          if permission_profile() == 'mvp' else 'Для просроченной приёмки требуется разрешение главного инженера с причиной')
    orders = views.models['work_orders']
    current = views.session.scalar(select(orders.revision).where(
        orders.site_id==views.principal.site_id,orders.work_order_id==task_id))
    if current!=revision:
        raise HTTPException(409, 'Задание изменилось во время проверки. Повторите анализ.')
    return dict(task_id=str(task_id), revision=revision, execution_id=report['id'] if report else None,
                task_state=task['state'], report_state=report['state'] if report else None,
                submitted_at=report['submittedAt'] if report else None,
                checklist=checklist, photos=[dict(id=p['id'], phase=p['phase'], view=p['viewKey'],
                                               checklist_item_id=p['checklistItemId']) for p in material['photos']],
                missing_materials=gaps, acceptance_blocks=acceptance,
                saved_photo_analysis=bundle['photoAnalysisStatus'],
                photo_classification=(bundle['review'] or {}).get('classification'),
                ready=not gaps and not acceptance,linked_equipment=linked_equipment,assignees=assignees,
                submission_blocks=submission,submission_ready=not gaps and not submission,
                saved_reports=[dict(id=str(item.work_report_id), state=item.status,
                    submitted_at=item.submitted_at.isoformat() if item.submitted_at else None) for item in reports])
