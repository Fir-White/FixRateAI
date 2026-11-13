"""Readiness for planning input, never staff assignment or plan publication."""
from decimal import Decimal
from app.schemas.catalog_decisions import DecisionInput


def assess(decision, equipment, source_rows, *, current=None, parent=None):
    d = DecisionInput.model_validate(decision)
    blockers = []
    if d.interpretation == 'UNKNOWN' or d.calendar_year is None or d.mark_slots == 'unconfirmed' or not d.semantics_note:
        blockers.append('NEEDS_SEMANTICS')
    if d.frequency_kind == 'unconfirmed' or (d.frequency_kind not in ('unconfirmed','event','included_in') and d.frequency_interval is None):
        blockers.append('NEEDS_FREQUENCY')
    if not d.equipment_ids or any(str(i) not in equipment or equipment[str(i)]['status'] != 'active' for i in d.equipment_ids):
        blockers.append('NEEDS_ASSET_BINDING')
    hours = elapsed = None
    if d.frequency_kind == 'included_in':
        if not d.included_in_row or d.included_in_row not in source_rows or not parent or not parent['prepared']:
            blockers.append('NEEDS_PARENT')
        elif set(map(str,d.equipment_ids)) != set(map(str,parent['decision']['equipment_ids'])):
            blockers.append('PARENT_BINDING_MISMATCH')
        elif d.calendar_year != parent['decision']['calendar_year'] or d.mark_slots != parent['decision']['mark_slots']:
            blockers.append('PARENT_CALENDAR_MISMATCH')
        elif d.splittable != parent['decision']['splittable'] or d.min_segment_minutes != parent['decision']['min_segment_minutes']:
            blockers.append('PARENT_POLICY_MISMATCH')
        else:
            hours = elapsed = Decimal(0)
        if current and current['confirmed'] and (not parent or current['parent_revision'] != parent['revision']):
            blockers.append('STALE_PARENT')
    else:
        if d.norm_value is None or d.norm_unit == 'unconfirmed' or d.norm_scope == 'unconfirmed' or d.crew_size is None or not d.norm_ref:
            blockers.append('NEEDS_DURATION')
        elif d.equipment_ids:
            quantity = len(d.equipment_ids) if d.norm_scope == 'per_asset' else 1
            hours = d.norm_value * quantity * (d.crew_size if d.norm_unit == 'elapsed_hour' else 1)
            elapsed = hours / d.crew_size
    if d.splittable is None or not d.policy_note or (d.splittable and d.min_segment_minutes is None):
        blockers.append('NEEDS_POLICY')
    elif d.splittable and elapsed is not None and elapsed > 0 and Decimal(d.min_segment_minutes) > elapsed * 60:
        blockers.append('SEGMENT_EXCEEDS_DURATION')
    if current and current['confirmed']:
        expected = {str(e['equipment_id']):(e['revision'],e['status']) for e in current['binding_snapshot']}
        actual = {str(i):(equipment[str(i)]['revision'],equipment[str(i)]['status']) for i in d.equipment_ids if str(i) in equipment}
        if actual != expected:
            blockers.append('STALE_ASSET_BINDING')
    return blockers, hours, elapsed
