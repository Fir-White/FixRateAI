"""Independent expectations for assistant recurrence evidence; no LLM or DB."""
from datetime import date, datetime, timezone

import pytest

from app.assistant.calendar_evidence import explain_configuration


CHECKED = datetime(2026, 11, 16, tzinfo=timezone.utc)


def configuration(**pattern):
    return dict(binding_id='saved-binding', revision=7, rule_version=3,
                valid_from='2023-11-16', valid_until=None, enabled=True,
                basis='fixed_calendar', pattern=dict(anchor_date='2023-11-16', **pattern))


def explain(row, start='2026-11-16', end='2027-11-15', **kwargs):
    return explain_configuration(row, start, end, timezone='Asia/Yekaterinburg',
                                 checked_at=CHECKED, **kwargs)


def test_nc01_five_per_year_is_not_five_year_interval():
    result = explain(configuration(frequency='yearly_count', interval=1,
                                   count_per_year=5, annual_policy='from_anchor',
                                   weekend_policy='next_workday'))
    assert result['status'] == 'complete' and result['complete']
    assert result['total_count'] == 5
    assert [(r['source_date'], r['effective_date']) for r in result['occurrences']] == [
        ('2026-11-16', '2026-11-16'), ('2027-01-28', '2027-01-28'),
        ('2027-04-11', '2027-04-12'), ('2027-06-23', '2027-06-23'),
        ('2027-09-04', '2027-09-06'),
    ]
    assert result['semantics']['repetitions_per_active_cycle'] == 5
    assert result['semantics']['years_between_active_cycles'] == 1
    assert result['manufacturer_unverified'] is True
    assert result['source']['revision'] == 7
    assert result['checked_at'] == CHECKED.isoformat()


def test_annual_count_interval_selects_active_cycles_and_does_not_multiply_count():
    row = configuration(frequency='yearly_count', interval=2, count_per_year=5,
                        annual_policy='from_anchor')
    active = explain(row, '2025-11-16', '2026-11-15')
    inactive = explain(row, '2026-11-16', '2027-11-15')
    assert active['total_count'] == 5 and inactive['total_count'] == 0
    assert active['semantics']['years_between_active_cycles'] == 2
    assert active['semantics']['repetitions_per_active_cycle'] == 5


@pytest.mark.parametrize('frequency,extra,expected', [
    ('day', dict(interval=2), ['2026-01-01', '2026-01-03', '2026-01-05']),
    ('week', dict(interval=1), ['2026-01-01']),
    ('month', dict(interval=1), ['2026-01-01']),
    ('quarter', dict(interval=1, quarter_policy='rolling_months'), ['2026-01-01']),
    ('quarter', dict(interval=1, quarter_policy='calendar_edge', period_edge='start'), ['2026-01-01']),
    ('year', dict(interval=1), ['2026-01-01']),
    ('yearly_count', dict(interval=1, count_per_year=1), ['2026-01-01']),
    ('dates', dict(dates=['2026-01-02', '2026-01-05']), ['2026-01-02', '2026-01-05']),
])
def test_every_supported_frequency_uses_production_recurrence(frequency, extra, expected):
    row = configuration(frequency=frequency, **extra)
    row['pattern']['anchor_date'] = row['valid_from'] = '2026-01-01'
    result = explain(row, '2026-01-01', '2026-01-05')
    assert [r['source_date'] for r in result['occurrences']] == expected
    assert result['complete']


def test_weekend_obligations_stay_distinct_and_holidays_are_not_invented():
    row = configuration(frequency='day', weekend_policy='next_workday')
    result = explain(row, '2026-11-14', '2026-11-16')
    assert result['total_count'] == 3
    assert [r['effective_date'] for r in result['occurrences']] == ['2026-11-16'] * 3
    assert result['semantics']['public_holiday_calendar_used'] is False
    # Public holidays are not modeled: a weekday remains a weekday.
    holiday = explain(row, '2027-01-01', '2027-01-01')
    assert holiday['occurrences'][0]['effective_date'] == '2027-01-01'


def test_validity_is_clipped_on_source_date_even_when_shift_goes_beyond_it():
    row = configuration(frequency='day', weekend_policy='next_workday')
    row.update(valid_from='2026-11-14', valid_until='2026-11-15')
    result = explain(row, '2026-11-01', '2026-11-30')
    assert result['active_range'] == dict(start='2026-11-14', end='2026-11-15')
    assert result['total_count'] == 2
    assert all(r['effective_date'] == '2026-11-16' for r in result['occurrences'])


def test_nonoverlapping_validity_is_empty_not_a_claim_about_work_history():
    row = configuration(frequency='month')
    row['valid_until'] = '2024-01-01'
    result = explain(row)
    assert result['complete'] and result['total_count'] == 0
    assert result['active_range'] is None
    assert any('work orders' in line for line in result['limitations'])


def test_after_completion_requires_history_not_anchor_arithmetic():
    row = configuration(frequency='month')
    row['basis'] = 'after_accepted_completion'
    result = explain(row)
    assert result['status'] == 'blocked' and not result['complete']
    assert result['total_count'] is None and result['occurrences'] == []
    assert 'history' in result['reason']


@pytest.mark.parametrize('broken', [
    dict(pattern=None), dict(pattern=dict(frequency='yearly_count', anchor_date='2023-11-16')),
    dict(valid_from=None), dict(valid_until='2020-01-01'), dict(basis='guess'),
])
def test_invalid_saved_configuration_is_not_reported_as_zero_obligations(broken):
    row = configuration(frequency='day')
    row.update(broken)
    result = explain(row)
    assert result['status'] == 'invalid_configuration'
    assert result['total_count'] is None and not result['complete']
    assert result['reason']


def test_impossible_annual_count_returns_explicit_invalid_configuration():
    result = explain(configuration(frequency='yearly_count', count_per_year=366,
                                   weekdays=[1], annual_policy='from_anchor'))
    assert result['status'] == 'invalid_configuration'
    assert result['total_count'] is None and 'eligible' in result['reason']


def test_bounded_output_preserves_total_and_explicit_partial_state():
    result = explain(configuration(frequency='day'), max_dates=3)
    assert result['status'] == 'partial'
    assert result['total_count'] == 365 and result['returned_count'] == 3
    assert len(result['occurrences']) == 3 and result['has_more'] and not result['complete']


def test_draft_configuration_does_not_become_published_evidence():
    row = configuration(frequency='yearly_count', count_per_year=5)
    row['enabled'] = False
    assert explain(row)['configuration']['published'] is False


@pytest.mark.parametrize('start,end', [
    ('2027-01-02', '2027-01-01'), ('2026-01-01', '2037-01-01'),
    ('20260101', '2026-01-02'), ('2026-01-01T00:00:00', '2026-01-02'),
    ('9998-01-01', '9999-01-01'),
])
def test_invalid_query_is_rejected_before_calculation(start, end):
    with pytest.raises(ValueError):
        explain(configuration(frequency='day'), start, end)


@pytest.mark.parametrize('limit', [0, -1, 3662, True, 1.5])
def test_output_limit_is_bounded(limit):
    with pytest.raises(ValueError):
        explain(configuration(frequency='day'), max_dates=limit)


def test_naive_checked_time_is_rejected():
    with pytest.raises(ValueError, match='timezone-aware'):
        explain_configuration(configuration(frequency='day'), date(2026, 1, 1), date(2026, 1, 2),
                              timezone='Asia/Yekaterinburg', checked_at=datetime(2026, 1, 1))
