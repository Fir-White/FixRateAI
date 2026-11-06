"""Compare only protected pixels from deterministic live captures; no screenshot mutation."""
import json
from pathlib import Path
from PIL import Image, ImageChops

root = Path(__file__).resolve().parents[1] / 'reports/redesign-v2'
results = []
for role in ('executor', 'engineer', 'chief_engineer', 'director'):
    for state, width, box in (
        ('home',1440,(0,0,224,900)),
        ('home',1440,(224,0,1440,68)),
        ('sidebar-collapsed',1440,(0,0,72,900)),
        ('notifications',1440,(0,0,1440,68)),
        ('notifications',1440,(945,76,1343,338)),
        ('profile',1440,None),
        ('profile',390,None),
        ('anchor',390,(0,0,390,60)),
    ):
        filename = f'{role}-{state}-{width}-y0.png'
        before = Image.open(root/'before'/filename).convert('RGB')
        after = Image.open(root/'after-foundation'/filename).convert('RGB')
        if box:
            before,after = before.crop(box),after.crop(box)
        delta = ImageChops.difference(before,after)
        changed = sum(pixel != (0,0,0) for pixel in delta.getdata())
        results.append(dict(role=role,state=state,width=width,region=box or 'full viewport',file=filename,
                            status='passed' if changed==0 else 'failed',changedPixels=changed,totalPixels=before.width*before.height))
(root/'protected-foundation.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(results,ensure_ascii=False,indent=2))
