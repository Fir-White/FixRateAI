"""Package native Penpot PNGs and pixel-for-pixel review crops; no UI reconstruction."""
from pathlib import Path
import base64, hashlib, json, struct
from PIL import Image, ImageDraw, ImageFont
repo=Path(__file__).resolve().parents[4]
runtime=repo/'var/penpot-migration-20261117'
out=Path(__file__).resolve().parent/'renders'; out.mkdir(exist_ok=True)
crops={
 'e1':{'composer':(248,248,1408,488),'work':(248,526,1408,876),'type':(248,112,1408,238)},
 'e2':{'composer':(40,345,1400,579),'work':(40,603,1400,897),'type':(40,157,1400,345)},
 'e3':{'composer':(48,356,1392,614),'work':(48,612,1392,898),'type':(48,163,1392,338)}}
receipt=[]
for key,regions in crops.items():
 data=base64.b64decode((runtime/(key+'-final.b64')).read_text())
 target=out/(key+'.png');target.write_bytes(data)
 im=Image.open(target);assert im.size==(1440,900)
 receipt.append(dict(file=target.name,width=1440,height=900,sha256=hashlib.sha256(data).hexdigest(),source='official Penpot MCP export_shape'))
 for part,area in regions.items():
  name=key+'-'+part+'-100.png';im.crop(area).save(out/name)
  receipt.append(dict(file=name,crop=area,scale=1,sha256=hashlib.sha256((out/name).read_bytes()).hexdigest()))
# The comparison image is an overview only. All detail PNGs above retain native pixels.
sheet=Image.new('RGB',(1488,358),'#091611');d=ImageDraw.Draw(sheet)
font=ImageFont.truetype(str(Path(__file__).resolve().parent/'fonts/IBMPlexSans-Medium.ttf'),17)
for i,(key,title) in enumerate([('e1','E1 — Quiet Precision'),('e2','E2 — Industrial Editorial'),('e3','E3 — Fluid Intelligence')]):
 x=16+i*496;d.text((x,13),title,font=font,fill='#EDF1E7')
 sheet.paste(Image.open(out/(key+'.png')).convert('RGB').resize((480,300),Image.Resampling.LANCZOS),(x,46))
sheet.save(out/'comparison.png')
(out/'exports.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
# Verify all Russian letters against the actual uploaded font cmaps.
def coverage(data):
 n=struct.unpack_from('>H',data,4)[0];tables={}
 for i in range(n):
  tag,_,offset,length=struct.unpack_from('>4sIII',data,12+16*i);tables[tag]=(offset,length)
 base,_=tables[b'cmap'];count=struct.unpack_from('>H',data,base+2)[0];chars=set()
 for i in range(count):
  platform,enc,off=struct.unpack_from('>HHI',data,base+4+i*8)
  if platform not in (0,3):continue
  p=base+off;fmt=struct.unpack_from('>H',data,p)[0]
  if fmt==12:
   groups=struct.unpack_from('>I',data,p+12)[0]
   for j in range(groups):
    start,end,glyph=struct.unpack_from('>III',data,p+16+12*j)
    chars.update(cp for cp in range(start,end+1) if glyph+cp-start)
  elif fmt==4:
   seg=struct.unpack_from('>H',data,p+6)[0]//2
   for j in range(seg):
    end=struct.unpack_from('>H',data,p+14+2*j)[0];start=struct.unpack_from('>H',data,p+16+2*seg+2*j)[0]
    delta=struct.unpack_from('>h',data,p+16+4*seg+2*j)[0];rpos=p+16+6*seg+2*j;ro=struct.unpack_from('>H',data,rpos)[0]
    for cp in range(start,min(end,65534)+1):
     gid=struct.unpack_from('>H',data,rpos+ro+2*(cp-start))[0] if ro else cp
     if gid and ((gid+delta)&65535):chars.add(cp)
 return chars
alphabet='АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя'
fontcheck=[]
for f in (Path(__file__).resolve().parent/'fonts').glob('*.ttf'):
 missing=[c for c in alphabet if ord(c) not in coverage(f.read_bytes())]
 assert not missing,(f.name,missing)
 fontcheck.append(dict(file=f.name,russian_letters=66,missing=missing))
(out/'font-coverage.json').write_text(json.dumps(fontcheck,indent=2),encoding='utf-8')
print(json.dumps(dict(full_renders=3,native_detail_crops=9,fonts=fontcheck)))
