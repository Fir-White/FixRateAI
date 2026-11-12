"""Deterministic daily workload and *additional* staffing lower bounds, no I/O.

Capacity is spread uniformly over 24 elapsed hours. It is a provisional planning
policy, not an assertion about legal working time or actual productivity.
"""
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from app.assignment.selection import _intersect, _merge, _subtract
from app.schemas.planning import DailyWorkload, WorkloadRequest, WorkloadResponse

ZERO = Decimal(0)


def _duration_hours(intervals):
    return sum((Decimal(str((end - start).total_seconds())) / Decimal(3600)
                for start, end in intervals), ZERO)


def calculate_workload(request: WorkloadRequest) -> WorkloadResponse:
    tz = ZoneInfo(request.timezone)
    days = []
    for number in range(1, monthrange(request.year, request.month)[1] + 1):
        day = date(request.year, request.month, number)
        start = datetime.combine(day, time.min, tz).astimezone(timezone.utc)
        end = datetime.combine(day + timedelta(days=1), time.min, tz).astimezone(timezone.utc)
        demands = sorted((d.model_copy(update={'assigned_worker_ids': sorted(d.assigned_worker_ids, key=lambda value: value.int)})
                          for d in request.demands if d.date == day), key=lambda d: d.occurrence_id.int)
        known = sum((d.person_hours for d in demands if d.person_hours is not None), ZERO)
        unknown = sum(d.person_hours is None for d in demands)
        pending = [d for d in demands if d.state in ('unassigned', 'incomplete')]
        pending_hours = (None if any(d.person_hours is None for d in pending)
                         else sum((d.person_hours for d in pending), ZERO))
        free_hours, free_workers, unknown_workers = ZERO, 0, 0
        for worker in request.workers:
            if not worker.active or not worker.membership_active or not worker.can_execute:
                continue
            if not worker.booking_data_complete or not worker.workload_data_complete or not worker.availability_data_complete:
                unknown_workers += 1
                continue
            available = _merge([(r.start_at.astimezone(timezone.utc), r.end_at.astimezone(timezone.utc))
                                for r in worker.availability if r.status == 'available'])
            excluded = [(r.start_at.astimezone(timezone.utc), r.end_at.astimezone(timezone.utc))
                        for r in worker.availability if r.status == 'unavailable']
            excluded += [(b.start_at.astimezone(timezone.utc), b.end_at.astimezone(timezone.utc))
                         for b in worker.bookings if b.blocks_time]
            free = _intersect(_subtract(available, excluded), [(start, end)])
            capacity = _duration_hours(free) * request.capacity_hours_per_24h / Decimal(24)
            free_hours += capacity
            free_workers += capacity > 0
        # Reported/assigned work is already accounted for; its reservations are
        # excluded from free capacity, so it must not be demanded a second time.
        incomplete = (end <= start or request.source_incomplete or unknown > 0 or unknown_workers > 0
                      or any(d.state == 'incomplete' for d in demands))
        bound = None
        if pending_hours is not None and end > start:
            daily_capacity = request.capacity_hours_per_24h * _duration_hours([(start, end)]) / Decimal(24)
            bound = max(int((pending_hours / daily_capacity).to_integral_value(rounding=ROUND_CEILING)),
                        max((d.crew_size for d in pending), default=0))
        deficit = None if incomplete or pending_hours is None else max(ZERO, pending_hours - free_hours)
        status = ('incomplete' if incomplete else 'no_work' if not pending else
                  'hours_deficit' if deficit and deficit > 0 else 'hours_sufficient')
        days.append(DailyWorkload(
            date=day, occurrences=demands, total_person_hours=None if unknown else known,
            known_person_hours=known, unassigned_person_hours=pending_hours,
            required_workers_lower_bound=bound, free_workers=free_workers,
            assigned_workers=len({w for d in demands if d.state == 'assigned' for w in d.assigned_worker_ids}),
            free_person_hours=None if unknown_workers else free_hours, known_free_person_hours=free_hours,
            deficit_person_hours=deficit, unknown_norms=unknown, unknown_workers=unknown_workers, status=status))
    diagnostics = [
        'Потребность — нижняя оценка для работ, ещё не обеспеченных назначениями. '
        'Достаточность часов не подтверждает квалификации, общий интервал бригады и выполнимость плана.',
        'Ёмкость распределяется пропорционально времени присутствия: при 12 ч за сутки '
        'восьмичасовой свободный интервал даёт 4 полезных часа. Политика предварительная.',
    ]
    if request.source_incomplete:
        diagnostics.append('Часть регламентов не рассчитана. Полная потребность неизвестна.')
    snapshot = request.model_dump(mode='json')
    snapshot['demands'].sort(key=lambda row: row['occurrence_id'])
    for demand in snapshot['demands']:
        demand['assigned_worker_ids'].sort()
    snapshot['workers'].sort(key=lambda row: row['worker_id'])
    for worker in snapshot['workers']:
        for key in ('availability', 'bookings', 'qualifications'):
            worker[key].sort(key=lambda row: json.dumps(row, sort_keys=True))
    return WorkloadResponse(site_id=request.site_id, year=request.year, month=request.month,
        timezone=request.timezone, calculated_at=request.as_of,
        capacity_hours_per_24h=request.capacity_hours_per_24h,
        snapshot_sha256=sha256(json.dumps(snapshot, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        source_incomplete=request.source_incomplete,
        total_occurrences=sum(len(d.occurrences) for d in days),
        unassigned_occurrences=sum(d.state in ('unassigned', 'incomplete') for row in days for d in row.occurrences),
        deficit_days=sum(d.status == 'hours_deficit' for d in days),
        incomplete_days=sum(d.status == 'incomplete' for d in days),
        diagnostics=diagnostics, days=days)
