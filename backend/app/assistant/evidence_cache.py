"""Short-lived reuse of private, persisted, authorized GET evidence.

There is no global cache and no database access. The caller must reauthenticate
before every hit, pass validated arguments, and invalidate after any dispatched
write. Approval/preflight always needs fresh API reads and must never use this
helper. Model messages and answers are not inputs to the cache.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from typing import Any


MAX_TTL_SECONDS = 60
MAX_PROOF_BYTES = 40000
MAX_ENTRIES = 64
_REQUIRED_SCOPE = ('conversation_id', 'user_id', 'site_id', 'role')
_SECRET = re.compile(r'password|passwd|secret|token|cookie|authorization|credential|api.?key', re.I)
_SECRET_VALUE = re.compile(r'\bBearer\s+[A-Za-z0-9]|\bsk-(?:proj-)?[A-Za-z0-9_-]{12,}|__[a-z_]*secret[a-z_]*__', re.I)
_MODEL_FIELDS = {'answer', 'model_answer', 'prompt', 'messages', 'reasoning'}
_BLOCKED = {'blocked', 'invalid_configuration', 'access_denied', 'unavailable',
            'failed', 'partial', 'cancelled', 'uncertain'}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


def _instant(value: Any) -> datetime | None:
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result.astimezone(timezone.utc) if result.tzinfo is not None and result.utcoffset() is not None else None
    except (ValueError, TypeError, AttributeError):
        return None


def _clock(value: datetime) -> datetime:
    result = _instant(value)
    if result is None:
        raise ValueError('Evidence-cache time must be a timezone-aware server instant')
    return result


def _scope(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(value.get(key), str) or not value[key].strip() for key in _REQUIRED_SCOPE):
        raise ValueError('Evidence cache requires conversation/user/site/role scope')
    result = deepcopy(dict(value))
    _json(result)  # Preserve timezone/extra scope conditions too, without guessing.
    return result


def _tool(name_or_tool: Any):
    from .tools import TOOLS
    name = name_or_tool if isinstance(name_or_tool, str) else getattr(name_or_tool, 'name', None)
    trusted = next((tool for tool in TOOLS if tool.name == name), None)
    if trusted is None or trusted.mode != 'read' or trusted.method != 'GET':
        return None
    # An object cannot disguise a registered write or POST as an ordinary GET.
    if not isinstance(name_or_tool, str) and (getattr(name_or_tool, 'mode', None) != trusted.mode or getattr(name_or_tool, 'method', None) != trusted.method):
        return None
    return trusted


def _safe(value: Any) -> bool:
    if isinstance(value, dict):
        return all(isinstance(key, str) and not _SECRET.search(key) and _safe(child)
                   for key, child in value.items())
    if isinstance(value, list):
        return all(_safe(child) for child in value)
    if isinstance(value, str):
        return value != '[redacted]' and not _SECRET_VALUE.search(value)
    return value is None or type(value) in (bool, int) or type(value) is float and math.isfinite(value)


def _complete(value: Any) -> bool:
    """Recheck raw retained data; a stale/incorrect complete flag is insufficient."""
    if isinstance(value, dict):
        for key in ('complete', 'retained'):
            if key in value and value[key] is not True:
                return False
        for key in ('has_more', 'truncated'):
            if key in value and value[key] is not False:
                return False
        if isinstance(value.get('status'),str) and value['status'] in _BLOCKED:
            return False
        for field in ('items', 'occurrences'):
            rows = value.get(field)
            if isinstance(rows, list):
                for key in ('total', 'total_count', 'returned_count'):
                    if key in value and (type(value[key]) is not int or value[key] != len(rows)):
                        return False
                if 'offset' in value and (type(value['offset']) is not int or value['offset'] != 0):
                    return False
        return all(_complete(child) for child in value.values())
    if isinstance(value, list):
        return all(_complete(child) for child in value)
    return True


def _has_mutation(state: Mapping[str, Any]) -> bool:
    for goal in state.get('goals', []):
        if not isinstance(goal, dict) or goal.get('mode') == 'write' or goal.get('action_id'):
            return True
    for proof in state.get('evidence', []):
        if not isinstance(proof, dict) or proof.get('action_id') or _tool(proof.get('tool')) is None:
            return True
    return False


def _fresh_snapshots(value: Any, now: datetime, ttl: float) -> bool:
    """A fresh HTTP read must not extend an older server snapshot's lifetime."""
    if isinstance(value, dict):
        if 'checked_at' in value:
            checked = _instant(value['checked_at'])
            if checked is None or not 0 <= (now - checked).total_seconds() < ttl:
                return False
        return all(_fresh_snapshots(child, now, ttl) for child in value.values())
    if isinstance(value, list):
        return all(_fresh_snapshots(child, now, ttl) for child in value)
    return True


class EvidenceCache:
    def __init__(self, scope: Mapping[str, Any], *, ttl_seconds: float = MAX_TTL_SECONDS):
        if type(ttl_seconds) not in (int, float) or not math.isfinite(ttl_seconds) or not 0 < ttl_seconds <= MAX_TTL_SECONDS:
            raise ValueError('Evidence-cache TTL must be greater than zero and at most 60 seconds')
        self.scope = _scope(scope)
        self.ttl_seconds = ttl_seconds
        self._entries: dict[tuple[str, str], dict[str, Any]] = {}

    def invalidate(self, new_scope: Mapping[str, Any] | None = None) -> None:
        """Call on writes/uncertain writes or context switches; never replay writes."""
        self._entries.clear()
        if new_scope is not None:
            self.scope = _scope(new_scope)

    def _key(self, tool, arguments, purpose):
        trusted = _tool(tool)
        if purpose != 'read' or trusted is None or not isinstance(arguments, dict) or 'body' in arguments or not _safe(arguments):
            return None
        try:
            return trusted.name, _digest(arguments)
        except (ValueError, TypeError):
            return None

    def _valid(self, tool, arguments, proof, now) -> bool:
        if not isinstance(proof, dict) or set(proof) & _MODEL_FIELDS:
            return False
        if proof.get('scope') != self.scope or proof.get('complete') is not True or proof.get('retained') is not True or proof.get('action_id'):
            return False
        if proof.get('tool') != (_tool(tool).name if _tool(tool) else None) or 'result' not in proof or proof.get('limitations'):
            return False
        checked = _instant(proof.get('checked_at'))
        if checked is None or not 0 <= (now - checked).total_seconds() < self.ttl_seconds:
            return False
        result = proof['result']
        if not _safe(result) or not _complete(result) or not _fresh_snapshots(result, now, self.ttl_seconds):
            return False
        try:
            return (_digest(proof.get('arguments')) == _digest(arguments) and proof.get('sha256') == _digest(result)
                    and len(_json(proof).encode('utf-8')) <= MAX_PROOF_BYTES)
        except (ValueError, TypeError):
            return False

    def record(self, tool, arguments, proof, now: datetime, *, purpose='read', scope=None) -> bool:
        """Record a server proof verbatim, retaining its original retrieval time."""
        instant = _clock(now)
        if scope is not None and dict(scope) != self.scope:
            self.invalidate(scope)
        key = self._key(tool, arguments, purpose)
        if key is None or not self._valid(tool, arguments, proof, instant):
            return False
        current = self._entries.get(key)
        if current is None or _instant(proof['checked_at']) >= _instant(current['checked_at']):
            if len(self._entries) >= MAX_ENTRIES and key not in self._entries:
                self._entries.pop(next(iter(self._entries)))
            self._entries[key] = deepcopy(proof)
        return True

    def lookup(self, tool, arguments, now: datetime, *, purpose='read', scope=None):
        """Return a private proof copy, or miss; this never refreshes its TTL."""
        instant = _clock(now)
        if scope is not None and dict(scope) != self.scope:
            self.invalidate(scope)
            return None
        key = self._key(tool, arguments, purpose)
        proof = self._entries.get(key) if key is not None else None
        if proof is None:
            return None
        if not self._valid(tool, arguments, proof, instant):
            self._entries.pop(key, None)
            return None
        return deepcopy(proof)


def from_workflows(states, scope: Mapping[str, Any], now: datetime, *, ttl_seconds=MAX_TTL_SECONDS) -> EvidenceCache:
    """Load only same-context, retained read proofs, independently of history order.

    Mutation proposal timestamps do not prove when dispatch occurred. If supplied
    history includes a mutation/uncertain action or a scope switch, reuse starts
    empty instead of guessing that another read happened after the write. Fresh
    authorized reads can be recorded normally in the new turn.
    """
    instant = _clock(now)
    cache = EvidenceCache(scope, ttl_seconds=ttl_seconds)
    workflows = [state for state in states if isinstance(state, Mapping)]
    if any(state.get('scope') != cache.scope or _has_mutation(state) for state in workflows):
        return cache
    for state in workflows:
        for proof in state.get('evidence', []):
            cache.record(proof.get('tool'), proof.get('arguments'), proof, instant)
    return cache
