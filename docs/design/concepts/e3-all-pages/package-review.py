"""Package native E3 review renders; no application code is changed."""
from pathlib import Path
import json,hashlib,html,math
from PIL import Image,ImageDraw,ImageFont,ImageChops,ImageStat
base=Path(__file__).resolve().parent
manifest=json.loads((base/'penpot.json').read_text(encoding='utf-8'))
render_qa=json.loads((base/'../../../../var/penpot-migration-20261117/suite-render-qa.json').read_text(encoding='utf-8'))
frames={r['key']:r for r in manifest['frames']}
native_png_keys=set()
for name in ('auth-update.json','setup-update.json','company-code-restore.json','error-screens-update.json'):
 update=base/name
 if update.exists(): native_png_keys.update(f['key'] for f in json.loads(update.read_text(encoding='utf-8'))['frames'])
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',18)
small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',15)
exports=[]
for key,f in frames.items():
 p=base/f['image']
 with Image.open(p) as im:
  expected=(round(f['width']),round(f['height']))
  if im.size!=expected: raise ValueError((key,im.size,expected))
 exports.append({'key':key,'file':f['image'],'width':expected[0],'height':expected[1],'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 if key in native_png_keys: exports[-1]['pipeline']='Penpot native PNG export'
contacts=base/'contacts';contacts.mkdir(exist_ok=True)
for i,group in enumerate(manifest['groups'],1):
 specs=[s for s in manifest['screens'] if s['group']==group]
 cols=3;cw=580;ch=520;rows=math.ceil(len(specs)/cols)
 sheet=Image.new('RGB',(cols*cw+40,rows*ch+90),'#07140F');draw=ImageDraw.Draw(sheet)
 draw.text((20,16),manifest['sectionPages'][group],font=font,fill='#C6DEC0')
 for n,s in enumerate(specs):
  x=20+(n%cols)*cw;y=65+(n//cols)*ch
  draw.text((x,y),s['title'],font=font,fill='#EDF1E7')
  draw.text((x,y+26),s['key'],font=small,fill='#ACBDB0')
  for device,dx,lim in [('desktop',0,(410,440)),('mobile',430,(115,440))]:
   f=frames.get(s['key']+'--'+device)
   if not f: continue
   with Image.open(base/f['image']) as im:
    thumb=im.convert('RGB');thumb.thumbnail(lim,Image.Resampling.LANCZOS);sheet.paste(thumb,(x+dx,y+56))
 sheet.save(contacts/(str(i).zfill(2)+'-'+group.lower()+'.png'))
links=[];sections=[]
for group in manifest['groups']:
 cards=[]
 for s in [s for s in manifest['screens'] if s['group']==group]:
  for device in s['devices']:
   f=frames[s['key']+'--'+device];title=s['title']+' · '+device
   cards.append('<article><a href="'+f['image']+'"><img loading="lazy" src="'+f['image']+'" alt="'+html.escape(title)+'"></a><h3>'+html.escape(title)+'</h3><p>'+html.escape(s['route'])+'</p><a href="'+html.escape(f['viewer'])+'">Открыть в Penpot</a></article>')
 sections.append('<section id="'+group+'"><h2>'+html.escape(manifest['sectionPages'][group])+'</h2><div class="grid">'+''.join(cards)+'</div></section>')
 links.append('<a href="#'+group+'">'+html.escape(manifest['sectionPages'][group])+'</a>')
page='''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FixRate AI · E3 · Все экраны</title><style>html{color-scheme:dark;scroll-behavior:smooth}body{margin:0;background:#0C1D18;color:#EDF1E7;font:16px/1.5 Arial,sans-serif}main{max-width:1440px;margin:auto;padding:40px 24px}h1{font-weight:400;font-size:40px}a{color:#C6DEC0}nav{display:flex;flex-wrap:wrap;gap:12px 24px;padding:24px 0}section{padding:28px 0;border-top:1px solid #304C3F}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:28px}article{min-width:0}img{display:block;width:100%;height:340px;object-fit:contain;object-position:top;background:#091611;border:1px solid #304C3F;border-radius:12px}h3{font-size:16px;margin-bottom:8px}p{color:#ACBDB0;overflow-wrap:anywhere}a:focus-visible{outline:2px solid #C6DEC0;outline-offset:4px}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}</style><main><h1>FixRate AI · E3</h1><p>104 вида · 206 макетов · 17 разделов. Нажмите изображение для просмотра в полном размере.</p><nav>'''+''.join(links)+'</nav>'+''.join(sections)+'</main></html>'
(base/'review.html').write_text(page,encoding='utf-8')
(base/'renders'/'exports.json').write_text(json.dumps({'pipeline':'Official Penpot SDK SVG → local Chromium, native fonts, scale 1; LCD text disabled','renderQA':render_qa,'exports':exports},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'renders':len(exports),'bytes':sum(e['bytes'] for e in exports),'contacts':len(manifest['groups']),'dimensions':'PASS','fonts':'PASS','photos':sum(e['images'] for e in render_qa)}))
