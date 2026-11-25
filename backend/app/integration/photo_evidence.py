"""Evidence labels describe photo suitability, never final acceptance."""
from decimal import Decimal,InvalidOperation

def classify_evidence(result,manual_evidence_required=False):
    visible=[i for i in result.item_results if i.verdict!='not_verifiable']
    if result.status in ('failed','unavailable') or not visible:return 'manual_review'
    if any(i.visual_assessment and i.visual_assessment.evidence_class=='rejected' for i in visible):return 'rejected'
    if any(not i.visual_assessment and ('Переснимите' in i.observation or 'Нельзя сопоставить' in i.observation) for i in visible):return 'rejected'
    if manual_evidence_required:return 'manual_review'
    if all(i.visual_assessment and i.visual_assessment.evidence_class=='approved' and all(getattr(i.visual_assessment,k)=='yes' for k in ('subject_matches_task','same_subject','comparable')) for i in visible):return 'approved'
    return 'manual_review'

def compare_readings(protocol,result):
    observations=[r for item in result.item_results if item.visual_assessment for r in item.visual_assessment.visible_readings]
    compared=[]
    for reading in protocol:
        matches=[r for r in observations if r.get('phase')==reading['phase'] and r.get('parameter_code',r.get('label'))==reading['parameter_code'] and r.get('unit')==reading['unit'] and r.get('readable') is True]
        status='unreadable';observed=None
        if len(matches)==1:
            try:
                value=Decimal(str(matches[0].get('value')))
                if value.is_finite():status='match' if value==Decimal(reading['value']) else 'mismatch';observed=str(value)
            except (InvalidOperation,ValueError):pass
        compared.append(dict(**reading,observed=observed,status=status))
    return compared


def has_photo_pair(photos):
    """Only a same-item, same-equipment, same-view before/after pair is eligible."""
    keys={(p.checklist_item_id,p.equipment_id,p.view_key,p.stage) for p in photos
          if p.checklist_item_id and p.equipment_id and p.view_key and p.stage in ('before','after')}
    return any((item,equipment,view,'after') in keys for item,equipment,view,stage in keys if stage=='before')


def validate_submission_evidence(checklist_snapshot, answers, photos, order_equipment_ids):
    """Enforce required answers and per-item equipment/view-matched before/after photo pairs."""
    from fastapi import HTTPException

    valid_item_ids = {item["id"] for item in checklist_snapshot}
    for p in photos:
        if p.stage in ("before", "after") and order_equipment_ids and (
            p.equipment_id is None or p.equipment_id not in order_equipment_ids
        ):
            raise HTTPException(422, "Фотография относится к другому оборудованию")
    for item in checklist_snapshot:
        answer = answers.get(item["id"])
        if item["required"] and (not answer or (item["answerKind"] == "boolean" and answer != "done")):
            raise HTTPException(422, "Заполните все обязательные пункты чек-листа")
        if item["photoRequired"]:
            pairs = {
                (p.stage, (p.view_key or "").strip(), p.equipment_id)
                for p in photos
                if str(p.checklist_item_id) == item["id"]
                and str(p.checklist_item_id) in valid_item_ids
                and (p.view_key or "").strip()
                and p.equipment_id is not None
                and p.equipment_id in order_equipment_ids
            }
            if not any(("after", key, eq_id) in pairs for stage, key, eq_id in pairs if stage == "before"):
                raise HTTPException(422, "Требуется пара фото до/после одного ракурса")
