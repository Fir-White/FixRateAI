"""Site-scoped, read-only adapter for normative workload and free resources."""
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
import json
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import ValidationError

from app.integration.assignment import workers_for_period
from app.integration.calendar import _json_value, preview_calendar
from app.schemas.planning import WorkloadRequest
from app.scheduling.workload import calculate_workload


def workload_preview(v, year, month, capacity):
    now = datetime.now(timezone.utc)
    site = v.one('sites', site_id=v.principal.site_id)
    tz = ZoneInfo(site.timezone)
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    source = preview_calendar(v, year, month, as_of=now)
    # A weekend transfer can carry an obligation from the previous source month.
    previous = first - timedelta(days=1)
    sources = [source]
    if previous.year >= 2000:
        sources.append(preview_calendar(v, previous.year, previous.month, as_of=now))
    saved_entries = [row for row in v.rows('schedule_entries') if row.status == 'planned']
    entries = {row.source_occurrence_id: row for row in saved_entries if row.source_occurrence_id}
    legacy_entries = defaultdict(list)
    for entry in saved_entries:
        if entry.binding_id:
            legacy_entries[(str(entry.binding_id), str(entry.source_date or entry.regulatory_deadline_on))].append(entry)
    orders = {row.schedule_entry_id: row for row in v.rows('work_orders')
              if row.schedule_entry_id and row.status != 'cancelled'}
    assignments = {}
    for row in v.rows('work_assignments'):
        if row.status not in ('cancelled', 'declined', 'finished'):
            assignments.setdefault(row.work_order_id, []).append(row)
    demands, ambiguous = {}, False
    for preview in sources:
        for row in preview['items']:
            identity = UUID(row['id'])
            entry = entries.get(identity)
            candidates = legacy_entries[(row['bindingId'], row.get('sourceDate', row['mandatoryDueDate']))]
            if entry is None and len(candidates) == 1:
                entry = candidates[0]
            elif entry is None and len(candidates) > 1:
                ambiguous = True
            day = entry.planned_date if entry else date.fromisoformat(row['occurrenceDate'])
            if not first <= day <= last:
                continue
            state, assigned = 'unassigned', []
            order = orders.get(entry.schedule_entry_id) if entry else None
            hours, crew_size = row['requiredPersonHours'], row['crewSize']
            if order:
                # Existing jobs keep their frozen norms, not a replacement rule's values.
                unit = order.operation_snapshot.get('norm_unit')
                hours = (order.norm_hours_snapshot * (order.required_people_snapshot if unit == 'elapsed_hour' else 1)
                         if unit in ('person_hour', 'elapsed_hour') and order.norm_hours_snapshot is not None else None)
                crew_size = order.required_people_snapshot
                booked = assignments.get(order.work_order_id, [])
                if order.status in ('completed', 'in_review'):
                    state = 'reported'
                elif order.status in ('assigned', 'in_progress', 'rework') and len({a.user_id for a in booked}) == crew_size and all(a.start_at and a.end_at for a in booked):
                    state, assigned = 'assigned', [a.user_id for a in booked]
                elif booked or order.status in ('assigned', 'in_progress', 'rework'):
                    state = 'incomplete'
            demands[identity] = dict(occurrence_id=identity, date=day,
                equipment_name=row['equipmentName'], operation_title=row['operationTitle'],
                data_origin=row['dataOrigin'], person_hours=hours, crew_size=crew_size,
                state=state, assigned_worker_ids=assigned)
    workers = workers_for_period(v, site.site_id, datetime.combine(first, time.min, tz),
                                 datetime.combine(last, time.max, tz), now)
    payload = dict(site_id=site.site_id, timezone=site.timezone,
        year=year, month=month, as_of=now, capacity_hours_per_24h=capacity,
        demands=list(demands.values()), workers=workers,
        source_incomplete=ambiguous or any(d['status'] in ('needs_input', 'manual_review')
                              for preview in sources for d in preview['diagnostics']))
    try:
        request = WorkloadRequest.model_validate_json(json.dumps(payload, default=_json_value))
    except ValidationError:
        raise HTTPException(422, 'INVALID_PLANNING_INPUT: проверьте нормы, интервалы и сведения о сотрудниках') from None
    return calculate_workload(request)
