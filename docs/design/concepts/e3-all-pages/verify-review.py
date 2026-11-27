"""Verify the frozen E3 design delivery against its manifest and current source snapshot."""
from pathlib import Path
import hashlib,json,re
base=Path(__file__).resolve().parent;root=base.parents[3]
load=lambda name:json.loads((base/name).read_text(encoding='utf-8'))
m=load('penpot.json');q=load('qa-final.json');exports=load('renders/exports.json');browser=load('browser-qa.json');reopen=load('reopen.json');cleanup=load('cleanup.json')
expected={s['key']+'--'+d for s in m['screens'] for d in s['devices']};frames={f['key']:f for f in m['frames']}
assert set(frames)==expected and len(frames)==len(m['frames'])==206
assert len(m['screens'])==104 and len(m['legacyCoverage'])==103
assert all(r['frameKey'] in frames for r in m['legacyCoverage'])
paths=re.findall(r'path="([^"]+)"',(root/'frontend/src/app/router.tsx').read_text(encoding='utf-8'))
paths=['/executor/'+p if not p.startswith('/') and p!='*' else p for p in paths]
assert set(paths)=={r['route'] for r in m['routes']}|{r['route'] for r in m['aliases']}
assert all(hashlib.sha256((root/s['file']).read_bytes()).hexdigest()==s['sha256'] for s in m['sources'])
for f in q['frames']:
 for key in ['outside','overflow','unmeasured','overlaps','lineClashes','smallTargets','badCenters']:assert not f[key],(f['key'],key)
 assert f['flatUI']==0
assert q['revision']==m['version']['revision']==208
assert len(exports['exports'])==206 and len(exports['renderQA'])==206
for e in exports['exports']:assert hashlib.sha256((base/e['file']).read_bytes()).hexdigest()==e['sha256'],e['key']
assert all(r['fonts'] and r['faces'] and r['failedImages']==0 for r in exports['renderQA'])
assert len(browser['results'])==9 and all(r['status']=='PASS' for r in browser['results'])
assert len(reopen['sections'])==17 and all(s['count']>0 for s in reopen['sections'])
assert len(cleanup['removed'])==11 and len(cleanup['retainedNow'])==20
assert [p['name'] for p in m['finalPages'] if p['section']]==list(m['sectionPages'].values())
actual={p['id']:p['hash'] for p in q['protectedPages']}
assert actual=={'7736ee33-deb6-8079-8008-f59061ee843b':'6e2d2ad4','ecd29d2d-0751-800b-8008-f5988773752e':'a91e6ce5','582936bd-dbb0-8088-8008-f5a1cedb5ec8':'195390c1'}
print(json.dumps({'status':'PASS','views':len(m['screens']),'frames':len(frames),'routes':len(m['routes']),'aliases':len(m['aliases']),'legacy':len(m['legacyCoverage']),'sections':len(m['groups']),'viewer':len(browser['results']),'sourceHashes':len(m['sources']),'revision':q['revision'],'codeChanged':False}))
