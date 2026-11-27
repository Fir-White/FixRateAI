"""Read and reconcile a complete analytical report through authorized API tools.

The caller has already selected the typed analytical operation. This module does
not inspect the question, choose a workflow, issue SQL or call a model. Every
section remains an actual API observation, with a common verified snapshot.
"""
from __future__ import annotations

from copy import deepcopy
import time

from fastapi import HTTPException

from app.integration import task_analytics
from .evidence import InconsistentEvidence, require, summary as verify_summary, page as verify_page, details as verify_details
from .read_transport import read
from .task_report import render
from .tools import EXPECTED_PRINCIPAL, validate_arguments

MAX_READS = 64
MAX_ROWS = 4000
MAX_SECONDS = 60
SECTIONS = ('equipment', 'dates', 'duplicates')
COMMON = ('snapshot_id', 'scope', 'local_date', 'timezone', 'complete', 'scanned_tasks',
          'selected_tasks', 'counters', 'due', 'execution_pending_due', 'scheduled',
          'norm_checks', 'known_person_hours', 'unknown_effort_tasks', 'business_duplicates')


def _duplicates(groups):
    """A duplicate page must not repeat another business group or task ID."""
    keys = set()
    task_ids = set()
    for group in groups:
        try:
            equipment = group['equipment_ids']
            require(isinstance(equipment, list) and all(isinstance(item, str) for item in equipment), 'duplicate_group_identity')
            key = (tuple(sorted(equipment)), group['operation'], group['source_or_due_date'], group['sequence'])
            require(key not in keys, 'repeated_duplicate_group')
            keys.add(key)
            ids = group['task_ids']
            require(isinstance(ids, list) and all(isinstance(item, str) for item in ids), 'duplicate_task_identity')
            require(len(set(ids)) == len(ids) and not task_ids.intersection(ids), 'repeated_duplicate_task')
            require(group.get('task_ids_truncated') is False and len(ids) == group['count'], 'duplicate_task_ids_incomplete')
            task_ids.update(ids)
        except (KeyError, TypeError):
            raise InconsistentEvidence('duplicate_group_identity') from None


def _failure(reason, status_code=None):
    if status_code in (401, 403):
        explanation = 'Доступ к данным ограничен вашей ролью или контекст доступа изменился.'
    elif status_code == 409:
        explanation = 'Данные изменились во время чтения либо снимок неполный.'
    elif status_code == 413:
        explanation = 'Объём данных превышает безопасный предел полного отчёта.'
    elif status_code is not None:
        explanation = 'Не удалось прочитать данные из backend.'
    else:
        explanation = 'Не удалось подтвердить согласованность счётчиков, страниц, области или даты снимка.'
    return ('Полный анализ не выполнен. ' + explanation +
            ' Частичный результат не выдан за полный; это не означает отсутствия заданий.')


async def read_analysis(app, tool, args, headers, trace, check, principal, *, max_reads=MAX_READS):
    """Return checked summary arguments and a verified full-report bundle.

    ``reads`` contains each validated real response, including empty sections;
    callers may persist those separately and omit them from the compact bundle.
    A blocked bundle never exposes a partial summary as a completed report.
    Authentication/context checks run before every read. All API attempts,
    including existing bounded read repairs, remain visible in ``trace``.
    """
    if tool.name != 'tasks_analyze' or tool.mode != 'read' or tool.method != 'GET':
        raise ValueError('A registered analytical GET tool is required')
    if type(max_reads) is not int or not 1 <= max_reads <= MAX_READS:
        raise ValueError('Analysis read budget must be between one and 64')
    started = time.monotonic()
    reads = []
    attempts = 0
    checked_args = None
    expected = None
    query = {}
    actor = {field: str(getattr(principal, field)) for field in ('user_id', 'site_id', 'role', 'timezone')
             if getattr(principal, field, None) is not None}
    totals = {}
    rows_used = 0
    first = None

    def blocked(reason, status_code=None):
        trace.append(dict(tool='__evidence', status='denied', error_type='inconsistent_results' if status_code is None else 'analysis_unavailable',
                          reason=reason, **({'code': status_code} if status_code is not None else {})))
        return checked_args, dict(status='blocked', complete=False, report=_failure(reason, status_code),
                                  summary=None, sections={}, reason=reason, reads=reads,
                                  read_count=attempts, section_totals=totals,
                                  provenance=dict(actor=actor, filters=expected, snapshot_id=first.get('snapshot_id') if first else None))

    async def fetch(section, offset=0):
        nonlocal attempts, checked_args, first
        check()
        if attempts >= max_reads or time.monotonic() - started >= MAX_SECONDS:
            raise HTTPException(413, 'Analysis read budget exhausted')
        request = dict(query=dict(query, section=section, offset=offset))
        before = len(trace)
        pin = EXPECTED_PRINCIPAL.set((principal.user_id, principal.site_id, principal.role))
        try:
            checked, data = await read(app, tool, request, headers, trace)
        finally:
            EXPECTED_PRINCIPAL.reset(pin)
            # Count actual transport attempts, not just successful pages.
            observed = sum(row.get('tool') == tool.name and row.get('status') in ('completed', 'denied')
                           for row in trace[before:] if isinstance(row, dict))
            attempts += max(1, observed)
        if section == 'summary':
            checked_args = checked
        if attempts > max_reads:
            raise HTTPException(413, 'Analysis read budget exhausted')
        verify_summary(data, principal, task_analytics.server_time(principal.timezone))
        require(data['scope'].get('visibility') == ('assigned_to_user' if principal.role == 'executor' else 'whole_site'), 'principal_visibility')
        for key, value in expected.items():
            require(data['scope'].get(key) == value, 'query_scope')
        if first is not None:
            if data['snapshot_id'] != first['snapshot_id']:
                raise HTTPException(409, 'Analysis snapshot changed')
            require(all(data.get(key) == first.get(key) for key in COMMON), 'section_summary_mismatch')
        else:
            first = data
        if section != 'summary':
            verify_page(data, offset)
        reads.append(dict(arguments=deepcopy(checked), result=deepcopy(data)))
        return data

    async def all_rows(section):
        nonlocal rows_used
        result = []
        offset = 0
        total = None
        while True:
            data = await fetch(section, offset)
            items = verify_page(data, offset)
            if total is None:
                total = data['total']
                totals[section] = total
                if total > MAX_ROWS:
                    raise HTTPException(413, 'Analysis row budget exhausted')
            require(data['total'] == total, 'page_total_changed')
            rows_used += len(items)
            if rows_used > MAX_ROWS:
                raise HTTPException(413, 'Analysis row budget exhausted')
            result.extend(items)
            offset += len(items)
            if offset >= total:
                return result

    try:
        require(len(actor) == 4, 'authenticated_principal_required')
        checked_args = validate_arguments(app, tool, args)
        require(not checked_args.get('view'), 'analysis_projection_not_supported')
        query = dict(checked_args.get('query', {}))
        require(query.pop('section', 'summary') == 'summary', 'analysis_summary_required')
        require(query.pop('offset', 0) == 0, 'analysis_start_offset')
        expected = {'origin':'all', 'cohort':'unfinished', 'starts_on':None, 'ends_on':None, **query}
        # Query keys/types are validated against the actual endpoint, not copied
        # from a model's description of a filter.
        summary = await fetch('summary')
        sections = {section: await all_rows(section) for section in SECTIONS}
        verify_details(summary, sections['equipment'], sections['dates'], sections['duplicates'])
        require(not any(row.get('operations_truncated') for row in sections['equipment']), 'operation_details_incomplete')
        _duplicates(sections['duplicates'])
        report = render(summary, sections['equipment'], sections['dates'], sections['duplicates'])
    except InconsistentEvidence as exc:
        return blocked(str(exc))
    except HTTPException as exc:
        return blocked('tool_error_' + str(exc.status_code), exc.status_code)
    except (KeyError, TypeError, ValueError, AttributeError):
        return blocked('invalid_analysis_result_shape')
    return checked_args, dict(status='complete', complete=True, report=report, summary=summary,
                              sections=sections, snapshot_id=summary['snapshot_id'], reads=reads,
                              read_count=attempts, section_totals=totals,
                              provenance=dict(actor=actor, filters=expected, snapshot_id=summary['snapshot_id'],
                                  checked_at=summary['checked_at'], local_date=summary['local_date'], timezone=summary['timezone'],
                                  scope=deepcopy(summary['scope']), page_size=25, source='authorized_task_analysis_api'))
