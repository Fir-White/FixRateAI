"""Pure projection of a reviewed scenario into a finite set of task additions."""
from collections import defaultdict
from uuid import UUID,uuid5
from app.scheduling.draft_validator import digest


def additions(occurrences,segments,profiles,*,regulations=None,regulation_operations=None):
    by_root=defaultdict(list)
    for s in segments:by_root[s.occurrence_id].append(s)
    config={p.row_number:p.model_dump(mode='json') for p in profiles}
    items=[];keys=[]
    for root in occurrences:
        parts=by_root[root.occurrence_id]
        groups=[parts] if root.interpretation=='CONTINUOUS_WORK' else [[s] for s in parts]
        for group in groups:
            ordered=sorted(group,key=lambda s:(s.start_at is None,s.start_at,str(s.segment_id)))
            ids=[str(s.segment_id) for s in ordered]
            identity=uuid5(root.occurrence_id,':'.join(sorted(ids)))
            items.append(dict(item_id=str(identity),occurrence_id=str(root.occurrence_id),segment_ids=ids,
                row_number=root.source_row,operation_code=root.operation_code,title=root.title,
                equipment_ids=sorted({str(a) for s in group for a in s.equipment_ids}),
                worker_ids=sorted(map(str,ordered[0].worker_ids)),start_at=ordered[0].start_at,end_at=ordered[-1].end_at,
                person_hours=str(sum(s.person_hours for s in group)),execution=regulations[root.binding_id] if root.source_kind=='regulation' else config[root.source_row]))
            if root.source_kind=='regulation':items[-1]['source_kind']='regulation'
        if root.source_kind=='regulation':
            for asset in root.equipment_ids:
                key=digest(dict(source_kind='regulation',operation=regulation_operations[root.binding_id],asset=str(asset),source_date=root.source_date))
                keys.append(dict(key=key,occurrence_id=str(root.occurrence_id),equipment_id=str(asset)))
            continue
        for row_number in [root.source_row,*root.included_rows]:
            for asset in root.equipment_ids:
                key=digest(dict(source_sha=root.source_sha256,row=row_number,source_date=root.source_date,slot=root.source_slot,asset=str(asset)))
                keys.append(dict(key=key,occurrence_id=str(root.occurrence_id),equipment_id=str(asset)))
    owners={sid:i['item_id'] for i in items for sid in i['segment_ids']}
    indexed={str(s.segment_id):s for s in segments}
    for item in items:
        item['depends_on_item_ids']=sorted({owners[str(d)] for sid in item['segment_ids'] for d in indexed[sid].depends_on_segment_ids if str(d) not in item['segment_ids']})
    return items,keys
