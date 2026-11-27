"""Package official native Penpot exports, 1:1 detail crops and a review overview."""
from pathlib import Path
import base64, json, hashlib
from PIL import Image, ImageDraw, ImageFont
base=Path(__file__).resolve().parent; repo=base.parents[3]
runtime=repo/'var/penpot-migration-20261117'; out=base/'renders';out.mkdir(exist_ok=True)
manifest=json.loads((base/'penpot.json').read_text(encoding='utf-8'));exports=[]
for f in manifest['frames']:
 key=f['key'];data=base64.b64decode((runtime/('core-'+key+'-final.b64')).read_text())
 target=out/(key+'.png');target.write_bytes(data)
 assert Image.open(target).size==(f['width'],f['height']),key
 exports.append(dict(file=target.name,width=f['width'],height=f['height'],scale=1,sha256=hashlib.sha256(data).hexdigest(),source='official Penpot MCP export_shape'))
if manifest.get('selectedHome'):
 f=manifest['selectedHome'];data=base64.b64decode((runtime/'core-home-final.b64').read_text());target=out/'home.png';target.write_bytes(data)
 assert Image.open(target).size==(f['width'],f['height'])
 exports.append(dict(file=target.name,width=f['width'],height=f['height'],scale=1,sha256=hashlib.sha256(data).hexdigest(),source='official Penpot MCP export_shape'))
crops={
 'planning-grid':('planning',(48,326,1392,884)),
 'equipment-regulations':('equipment',(48,332,1392,886)),
 'review-photos':('review',(48,318,886,831)),
 'review-decision':('review',(912,316,1392,890)),
 'executor-report':('executor',(400,270,1392,892)),
 'review-mobile-actions':('review-mobile',(0,632,390,844)),
 'executor-mobile-photos':('executor-mobile',(0,414,390,844)),
 'proposal-apply':('proposal',(896,328,1392,890)),
 'ai-context':('ai-context',(48,270,1096,892))}
for name,(key,area) in crops.items():
 target=out/(name+'-100.png');Image.open(out/(key+'.png')).crop(area).save(target)
 exports.append(dict(file=target.name,source=key+'.png',crop=area,scale=1,sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
font=ImageFont.truetype(str(repo/'docs/design/concepts/visual-exploration-e/fonts/IBMPlexSans-Medium.ttf'),17)
sheet=Image.new('RGB',(1464,720),'#091611');d=ImageDraw.Draw(sheet)
for key,title,x,y in [('planning','Планирование',16,12),('equipment','Оборудование',512,12),('review','Приёмка',16,368),('executor','Исполнение',512,368)]:
 d.text((x,y),title,font=font,fill='#EDF1E7');sheet.paste(Image.open(out/(key+'.png')).convert('RGB').resize((480,300),Image.Resampling.LANCZOS),(x,y+30))
for key,title,x in [('review-mobile','Приёмка · Mobile',1016),('executor-mobile','Исполнение · Mobile',1248)]:
 d.text((x,12),title,font=font,fill='#EDF1E7');sheet.paste(Image.open(out/(key+'.png')).convert('RGB').resize((195,422),Image.Resampling.LANCZOS),(x,42))
sheet.save(out/'overview.png');(out/'exports.json').write_text(json.dumps(exports,indent=2),encoding='utf-8')
qa=json.loads((runtime/'core-full-polish-r3.result.json').read_text(encoding='utf-8'))['value']
(base/'browser-qa.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf-8')
photos=[]
for name in ['1793644737686-1-case_01_before.jpg','1793644737686-0-case_01_after.jpg']:
 source=repo/'var/yougile-migration-20261117/attachments/FRAI-63'/name
 photos.append(dict(source_file=name,sha256=hashlib.sha256(source.read_bytes()).hexdigest(),original_in_git=False))
(base/'photo-provenance.json').write_text(json.dumps(dict(authorization='Explicit owner approval in conversation for these two photos in the local Penpot concept file',destination_file=manifest['fileId'],photos=photos),indent=2),encoding='utf-8')
print(json.dumps(dict(native_renders=len(manifest['frames'])+bool(manifest.get('selectedHome')),native_detail_crops=len(crops),browser_checks=qa['results'],overview=[1464,720])))
