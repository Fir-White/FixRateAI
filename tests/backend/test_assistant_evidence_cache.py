"""Persisted proof reuse never substitutes for authorization or fresh approval."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from types import SimpleNamespace

import pytest

from app.assistant.evidence_cache import EvidenceCache, from_workflows


NOW = datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc)
SCOPE = dict(conversation_id='private-chat', user_id='user', site_id='site', role='engineer', timezone='Asia/Yekaterinburg')
ARGS = dict(path=dict(equipment_id='equipment-1'), query={})


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def proof(result=None, **changes):
    value = dict(name='Stored equipment', revision=3) if result is None else result
    row = dict(id='e1', goal_id='read', tool='equipment_read', checked_at=NOW.isoformat(),
               scope=deepcopy(SCOPE), arguments=deepcopy(ARGS), result=value, sha256=digest(value),
               complete=True, retained=True, limitations=[])
    row.update(changes)
    return row


def state(*proofs, **changes):
    row = dict(scope=deepcopy(SCOPE), goals=[dict(mode='read', action_id=None)], evidence=list(proofs))
    row.update(changes)
    return row


def test_same_authorized_read_reuses_verbatim_proof_with_original_time():
    original = proof()
    cache = from_workflows([state(original)], SCOPE, NOW + timedelta(seconds=10))
    hit = cache.lookup('equipment_read', ARGS, NOW + timedelta(seconds=20))
    assert hit == original and hit is not original
    assert hit['checked_at'] == NOW.isoformat()
    assert cache.lookup('equipment_read', ARGS, NOW + timedelta(seconds=60)) is None


def test_argument_fingerprint_is_order_independent_but_preserves_exact_values():
    cache = from_workflows([state(proof())], SCOPE, NOW)
    assert cache.lookup('equipment_read', dict(query={}, path=dict(equipment_id='equipment-1')), NOW)
    for args in ({}, dict(path=dict(equipment_id='equipment-1')), dict(path=dict(equipment_id='equipment-2'), query={}),
                 {**ARGS, 'query': {'q': None}}, {**ARGS, 'view': {'limit': 25}}):
        assert cache.lookup('equipment_read', args, NOW) is None


@pytest.mark.parametrize('claimed,actual', [(True, 1), (1, 1.0), (False, 0)])
def test_python_equal_values_do_not_bypass_canonical_argument_identity(claimed, actual):
    actual_args = dict(query=dict(value=actual))
    claimed_args = dict(query=dict(value=claimed))
    assert not EvidenceCache(SCOPE).record('equipment_read', actual_args, proof(arguments=claimed_args), NOW)


@pytest.mark.parametrize('field', ['conversation_id', 'user_id', 'site_id', 'role', 'timezone'])
def test_foreign_context_proof_cannot_be_loaded(field):
    foreign = {**SCOPE, field: 'another'}
    cache = from_workflows([state(proof(scope=foreign), scope=foreign)], SCOPE, NOW)
    assert cache.lookup('equipment_read', ARGS, NOW) is None


@pytest.mark.parametrize('field', ['site_id', 'role', 'conversation_id', 'user_id'])
def test_context_change_clears_cache_and_old_context_does_not_resurrect(field):
    cache = from_workflows([state(proof())], SCOPE, NOW)
    foreign = {**SCOPE, field: 'another'}
    assert cache.lookup('equipment_read', ARGS, NOW, scope=foreign) is None
    assert cache.lookup('equipment_read', ARGS, NOW, scope=SCOPE) is None


@pytest.mark.parametrize('seconds,accepted', [(-1, False), (0, True), (59.999, True), (60, False), (61, False)])
def test_ttl_uses_aware_server_time_and_rejects_future_proofs(seconds, accepted):
    cache = EvidenceCache(SCOPE)
    assert cache.record('equipment_read', ARGS, proof(), NOW + timedelta(seconds=seconds)) is accepted


@pytest.mark.parametrize('checked', ['2026-11-16T10:00:00', 'not-a-date', None])
def test_invalid_or_naive_proof_time_is_not_reusable(checked):
    cache = from_workflows([state(proof(checked_at=checked))], SCOPE, NOW)
    assert cache.lookup('equipment_read', ARGS, NOW) is None


def test_aware_offset_timestamp_preserves_same_instant():
    cache = from_workflows([state(proof(checked_at='2026-11-16T15:00:00+05:00'))], SCOPE, NOW)
    assert cache.lookup('equipment_read', ARGS, NOW)


@pytest.mark.parametrize('changed', [dict(complete=False), dict(retained=False), dict(retained=None),
                                    dict(limitations=['page_only']), dict(sha256='0' * 64),
                                    dict(action_id='proposal'), dict(answer='Model prose')])
def test_complete_retained_hash_verified_server_proof_is_required(changed):
    assert not EvidenceCache(SCOPE).record('equipment_read', ARGS, proof(**changed), NOW)


def test_old_persisted_proofs_without_retained_marker_fail_closed():
    old = proof()
    old.pop('retained')
    assert not EvidenceCache(SCOPE).record('equipment_read', ARGS, old, NOW)


@pytest.mark.parametrize('result', [
    {'items': [1], 'total': 2}, {'items': [1, 2], 'total': 1},
    {'items': [1], 'total': 1, 'offset': 1}, {'items': [], 'has_more': True},
    {'nested': {'truncated': True}}, {'nested': {'complete': False}},
    {'retained': False, 'reason': 'evidence_budget'}, {'status': 'blocked'},
    {'status': 'invalid_configuration'}, {'status': 'failed'},
    {'occurrences': [1], 'total_count': 5, 'returned_count': 1},
])
def test_raw_incomplete_or_failed_results_do_not_reuse_even_with_true_top_flag(result):
    assert not EvidenceCache(SCOPE).record('equipment_read', ARGS, proof(result), NOW)


def test_complete_combined_pages_can_be_reused():
    value = dict(items=[dict(id=i) for i in range(30)], total=30, returned_count=30, complete=True, has_more=False)
    cache = from_workflows([state(proof(value))], SCOPE, NOW)
    assert cache.lookup('equipment_read', ARGS, NOW)['result'] == value


@pytest.mark.parametrize('result', [
    {'nested': {'api_key': 'SECRET'}}, {'preview_token': '[redacted]'},
    {'password_hash': 'HASH'}, {'authorization': 'Bearer SECRET'},
    {'value': '__human_confirmation_secret__'}, {'value': 'Bearer AAAAAAAAAAAAA'},
])
def test_secret_or_redacted_data_is_never_kept_in_cache(result):
    assert not EvidenceCache(SCOPE).record('equipment_read', ARGS, proof(result), NOW)


def test_body_and_secret_query_cannot_be_cached_even_if_proof_matches():
    cache = EvidenceCache(SCOPE)
    for args in ({**ARGS, 'body': {}}, {**ARGS, 'body': None}, {**ARGS, 'query': {'api_key': 'secret'}}):
        assert not cache.record('equipment_read', args, proof(arguments=args), NOW)


@pytest.mark.parametrize('tool', ['equipment_edit', 'forecast_run', 'assignment_prepare', 'unknown',
                                  SimpleNamespace(name='equipment_read', mode='write', method='GET')])
def test_no_write_post_unknown_or_disguised_tool_is_cache_eligible(tool):
    assert not EvidenceCache(SCOPE).record(tool, ARGS, proof(), NOW)


@pytest.mark.parametrize('purpose', ['preflight', 'approval', 'postcondition', 'reconciliation'])
def test_approvals_and_postconditions_require_fresh_reads(purpose):
    cache = from_workflows([state(proof())], SCOPE, NOW)
    assert cache.lookup('equipment_read', ARGS, NOW, purpose=purpose) is None
    assert not cache.record('equipment_read', ARGS, proof(), NOW, purpose=purpose)


@pytest.mark.parametrize('status', ['awaiting_confirmation', 'completed', 'uncertain', 'blocked'])
def test_mutation_history_invalidates_reuse_without_guessing_dispatch_time(status):
    writes = state(goals=[dict(mode='write', status=status, action_id='proposal')])
    cache = from_workflows([state(proof()), writes], SCOPE, NOW)
    assert cache.lookup('equipment_read', ARGS, NOW) is None
    # New authorized reads can be cached after invalidation in the current turn.
    assert cache.record('equipment_read', ARGS, proof(), NOW)


def test_any_scope_switch_in_history_invalidates_old_reads():
    foreign = state(scope={**SCOPE, 'site_id': 'different'})
    cache = from_workflows([state(proof()), foreign], SCOPE, NOW)
    assert cache.lookup('equipment_read', ARGS, NOW) is None


def test_invalidate_clears_existing_entries_after_a_write():
    cache = from_workflows([state(proof())], SCOPE, NOW)
    cache.invalidate()
    assert cache.lookup('equipment_read', ARGS, NOW) is None


def test_mutating_input_or_hit_cannot_poison_next_lookup():
    original = proof()
    cache = from_workflows([state(original)], SCOPE, NOW)
    original['result']['name'] = 'Changed after recording'
    first = cache.lookup('equipment_read', ARGS, NOW)
    first['result']['name'] = 'Changed by consumer'
    assert cache.lookup('equipment_read', ARGS, NOW)['result']['name'] == 'Stored equipment'


def test_history_order_does_not_replace_newer_evidence_with_older_data():
    recent = proof(dict(name='New'), checked_at=(NOW + timedelta(seconds=5)).isoformat())
    old = proof(dict(name='Old'))
    for states in ([state(recent), state(old)], [state(old), state(recent)]):
        cache = from_workflows(states, SCOPE, NOW + timedelta(seconds=10))
        assert cache.lookup('equipment_read', ARGS, NOW + timedelta(seconds=10))['result']['name'] == 'New'


def test_reuse_does_not_extend_ttl_when_proof_is_recorded_again():
    cache = from_workflows([state(proof())], SCOPE, NOW)
    hit = cache.lookup('equipment_read', ARGS, NOW + timedelta(seconds=50))
    assert cache.record('equipment_read', ARGS, hit, NOW + timedelta(seconds=50))
    assert cache.lookup('equipment_read', ARGS, NOW + timedelta(seconds=60)) is None


def test_http_retrieval_does_not_extend_an_older_server_snapshot_ttl():
    value = dict(complete=True, checked_at=(NOW - timedelta(seconds=50)).isoformat(), items=[], total=0)
    cache = from_workflows([state(proof(value))], SCOPE, NOW)
    assert cache.lookup('equipment_read', ARGS, NOW + timedelta(seconds=9))
    assert cache.lookup('equipment_read', ARGS, NOW + timedelta(seconds=10)) is None


@pytest.mark.parametrize('checked', [None, '2026-11-16T10:00:00', (NOW + timedelta(seconds=1)).isoformat()])
def test_invalid_or_future_underlying_snapshot_time_is_not_reused(checked):
    assert not EvidenceCache(SCOPE).record('equipment_read', ARGS, proof({'checked_at': checked}), NOW)


def test_oversized_retained_data_is_not_cached():
    assert not EvidenceCache(SCOPE).record('equipment_read', ARGS, proof({'text': 'x' * 40000}), NOW)


@pytest.mark.parametrize('ttl', [0, -1, 61, float('nan'), float('inf'), True])
def test_ttl_cannot_be_extended_or_malformed(ttl):
    with pytest.raises(ValueError):
        EvidenceCache(SCOPE, ttl_seconds=ttl)


def test_cache_requires_complete_scope_and_aware_caller_clock():
    for field in ('conversation_id', 'user_id', 'site_id', 'role'):
        incomplete = {key: value for key, value in SCOPE.items() if key != field}
        with pytest.raises(ValueError):
            EvidenceCache(incomplete)
    with pytest.raises(ValueError):
        from_workflows([], SCOPE, datetime(2026, 11, 16))
