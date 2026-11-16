"""Deterministic recurrence evidence from an authorized service-configuration row.

This module has no data access. Its caller must obtain the configuration through
the usual authorized API; supplying arbitrary model-created patterns is not
evidence about saved equipment. Calculated obligations are not saved work orders.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timezone as utc_timezone
import json
from typing import Any, Literal, TypedDict
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.schemas.maintenance import CalendarPattern
from app.scheduling.recurrence import occurrence_pairs, pattern_description


class Obligation(TypedDict):
    source_date: str
    effective_date: str
    shifted: bool


class CalendarEvidence(TypedDict):
    status: Literal['complete', 'partial', 'blocked', 'invalid_configuration']
    reason: str | None
    source: dict[str, Any]
    checked_at: str
    timezone: str
    configuration: dict[str, Any]
    semantics: dict[str, Any]
    requested_range: dict[str, str]
    active_range: dict[str, str] | None
    occurrences: list[Obligation]
    total_count: int | None
    returned_count: int
    has_more: bool
    complete: bool
    manufacturer_unverified: Literal[True]
    limitations: list[str]


def _date(value: date | str, name: str) -> date:
    if type(value) is date:
        return value
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
            if parsed.isoformat() == value:
                return parsed
        except ValueError:
            pass
    raise ValueError(f'{name} must be an ISO local date (YYYY-MM-DD)')


def _semantics(pattern: CalendarPattern) -> dict[str, Any]:
    """Use the generator's own explanation and expose ambiguous annual fields."""
    value: dict[str, Any] = dict(
        explanation=pattern_description(pattern),
        frequency=pattern.frequency,
        interval=pattern.interval,
        interval_unit={
            'day': 'days', 'week': 'ISO_weeks', 'month': 'months',
            'quarter': 'quarters', 'year': 'years',
            'yearly_count': 'years_between_active_cycles', 'dates': 'explicit_dates',
        }[pattern.frequency],
        anchor_date=pattern.anchor_date.isoformat(),
        weekend_policy=pattern.weekend_policy,
        public_holiday_calendar_used=False,
        excluded_dates_are_explicit_filters=True,
        range_applies_to='source_dates',
        preserves_distinct_obligations_on_same_effective_date=True,
    )
    if pattern.frequency == 'yearly_count':
        value.update(
            repetitions_per_active_cycle=pattern.count_per_year,
            years_between_active_cycles=pattern.interval,
            cycle_basis=pattern.annual_policy,
            distribution='evenly_across_eligible_days_in_active_cycle',
        )
    if pattern.frequency == 'quarter':
        value.update(quarter_policy=pattern.quarter_policy,
                     months_between_occurrences=3 * pattern.interval
                     if pattern.quarter_policy == 'rolling_months' else None)
    return value


def explain_configuration(
    configuration: Mapping[str, Any],
    start: date | str,
    end: date | str,
    *,
    timezone: str,
    checked_at: datetime | None = None,
    max_dates: int = 366,
) -> CalendarEvidence:
    """Explain one real ``regulations_read`` row using the production generator.

    The inclusive query is bounded to 3660 days. Pagination metadata describes
    calculated obligations, including separate Saturday/Sunday obligations that
    both move to Monday. ``complete`` applies only to this configuration/range;
    it never asserts completeness of work-order history or document retrieval.

    Bad query arguments raise ValueError. Missing/contradictory saved configuration
    returns explicit invalid/blocked evidence, never a claim of no maintenance.
    Completion-based recurrence requires actual accepted-work history and cannot
    be reconstructed from this API row alone.
    """
    first, last = _date(start, 'start'), _date(end, 'end')
    if last < first or (last - first).days > 3660 or last.year > 9998:
        raise ValueError('calendar query must cover 0..3660 days through year 9998')
    if type(max_dates) is not int or not 1 <= max_dates <= 3661:
        raise ValueError('max_dates must be 1..3661')
    ZoneInfo(timezone)  # Validate the caller's site zone; no host-zone fallback.
    checked = checked_at or datetime.now(utc_timezone.utc)
    if checked.tzinfo is None or checked.utcoffset() is None:
        raise ValueError('checked_at must be timezone-aware')

    raw_pattern = configuration.get('pattern')
    result: CalendarEvidence = dict(
        status='invalid_configuration', reason=None,
        source=dict(kind='saved_service_configuration',
                    binding_id=configuration.get('binding_id'),
                    revision=configuration.get('revision'),
                    rule_version=configuration.get('rule_version'),
                    calculation='app.scheduling.recurrence.occurrence_pairs'),
        checked_at=checked.isoformat(), timezone=timezone,
        configuration=dict(pattern=None, basis=configuration.get('basis', 'fixed_calendar'),
                           published=configuration.get('enabled'),
                           valid_from=configuration.get('valid_from'),
                           valid_until=configuration.get('valid_until')),
        semantics={}, requested_range=dict(start=first.isoformat(), end=last.isoformat()),
        active_range=None, occurrences=[], total_count=None, returned_count=0,
        has_more=False, complete=False, manufacturer_unverified=True,
        limitations=[
            'Calculated obligations are not saved or assigned work orders and do not prove completed work.',
            'No manufacturer document was checked; configured recurrence is not a manufacturer recommendation.',
            'Weekend shifting uses Saturday/Sunday only; no public-holiday calendar is consulted.',
            'Completeness covers one configuration and the requested source-date range only.',
        ],
    )
    try:
        pattern = CalendarPattern.model_validate_json(json.dumps(raw_pattern, default=str))
        valid_first = _date(configuration['valid_from'], 'valid_from')
        valid_last = _date(configuration['valid_until'], 'valid_until') if configuration.get('valid_until') is not None else None
        if valid_last is not None and valid_last < valid_first:
            raise ValueError('configuration validity is reversed')
        basis = configuration.get('basis', 'fixed_calendar')
        if basis not in ('fixed_calendar', 'after_accepted_completion'):
            raise ValueError('unsupported calendar basis')
    except (ValidationError, ValueError, KeyError, TypeError):
        result['reason'] = 'Saved recurrence or validity is missing or invalid; maintenance dates cannot be established.'
        return result

    result['configuration'].update(pattern=pattern.model_dump(mode='json'),
                                   valid_from=valid_first.isoformat(),
                                   valid_until=valid_last.isoformat() if valid_last else None)
    result['semantics'] = _semantics(pattern)
    if basis == 'after_accepted_completion':
        result.update(status='blocked', reason='Actual accepted-completion history is required for this calendar basis.')
        result['semantics']['range_applies_to'] = 'not_calculated_without_accepted_history'
        return result

    active_first, active_last = max(first, valid_first), min(last, valid_last) if valid_last else last
    if active_first <= active_last:
        result['active_range'] = dict(start=active_first.isoformat(), end=active_last.isoformat())
        try:
            pairs = occurrence_pairs(pattern, active_first, active_last)
        except ValueError:
            result['reason'] = 'Saved recurrence has too few eligible days for its annual count; maintenance dates cannot be established.'
            return result
    else:
        pairs = []
    result.update(
        status='partial' if len(pairs) > max_dates else 'complete',
        reason='Calculated date list was truncated; increase max_dates or narrow the range.' if len(pairs) > max_dates else None,
        occurrences=[dict(source_date=source.isoformat(), effective_date=effective.isoformat(),
                          shifted=source != effective) for source, effective in pairs[:max_dates]],
        total_count=len(pairs), returned_count=min(len(pairs), max_dates),
        has_more=len(pairs) > max_dates, complete=len(pairs) <= max_dates,
    )
    return result
