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
