// Apply after finalize.js in the existing local file. Safe to run again.
// Small native edits only: board IDs, components and interactions are preserved.
if(penpot.currentFile.id!=='13ac3151-58c1-801c-8008-f58dd579cd50')throw Error('Use the existing concepts file');
const p=penpotUtils.getPageByName('E3 · Core Workflows');
if(!p||p.id!=='582936bd-dbb0-8088-8008-f5a1cedb5ec8')throw Error('Expected finalized E3 page');
if(p.getPluginData('full-polish'))return {existing:true,stage:'full-polish.js'};
await penpot.openPage(p);
await penpot.waitForLayoutUpdate();
const roots=p.root.children.filter(s=>s.type==='board');
const all=()=>penpotUtils.findShapes(s=>true,p.root);
const stats={underlines:0,linkArrows:0,removedScanArrows:0,objectChevrons:0};
for(const root of roots){
 const nav=root.children.find(s=>s.name==='01 · Global navigation');
 if(nav){
  const underline=nav.children.find(s=>s.type==='rectangle'&&s.height===2);
  const active=nav.children.filter(s=>s.type==='text'&&Math.abs(s.parentY-31)<1).sort((a,b)=>Math.abs(a.x-underline.x)-Math.abs(b.x-underline.x))[0];
  const q=active.textBounds;
  underline.resize(q.width,2);underline.x=q.x;stats.underlines++;
 }
 const object=root.children.find(s=>s.type==='text'&&s.characters==='ЖК «Сосновый парк»');
 const caret=root.children.find(s=>s.type==='path'&&s.name==='down'&&Math.abs(s.parentY-120)<5);
 if(object&&caret){
  const q=object.textBounds;
  caret.resize(7,4);caret.x=q.x+q.width+8;caret.y=q.y+(q.height-4)/2;
  caret.strokes=[{strokeColor:'#ACBDB0',strokeWidth:1.15,strokeStyle:'solid',strokeAlignment:'center',strokeCapStart:'round',strokeCapEnd:'round'}];stats.objectChevrons++;
 }
}
for(const g of all().filter(s=>s.type==='board'&&s.name.startsWith('Link / '))){
 const caption=g.children.find(s=>s.type==='text'),arrow=g.children.find(s=>s.type==='path'&&s.name==='arrow');
 if(!caption||!arrow)continue;
 if(caption.characters.startsWith('Открыть скан')){arrow.remove();stats.removedScanArrows++;continue;}
 const q=caption.textBounds;
 arrow.resize(10,8);arrow.x=q.x+q.width+8;arrow.y=q.y+(q.height-8)/2;
 arrow.strokes=[{strokeColor:caption.fills[0].fillColor,strokeWidth:1.15,strokeStyle:'solid',strokeAlignment:'center',strokeCapStart:'round',strokeCapEnd:'round'}];
 stats.linkArrows++;
}
for(const s of all().filter(s=>s.type==='text')){
 const replacements={'3 · Проверить и сдать':'3 · Итоговый отчёт','3 · Сдача':'3 · Итоговый отчёт','Проверить и сдать':'Итоговый отчёт','Далее: проверить отчёт':'Далее: итоговый отчёт'};
 if(replacements[s.characters]){s.characters=replacements[s.characters];s.name=s.characters;}
}
const desktop=roots.find(s=>s.getPluginData('core-screen')==='executor');
desktop.name=desktop.name.replace('Проверить и сдать','Итоговый отчёт');
const mobile=roots.find(s=>s.getPluginData('core-screen')==='executor-mobile');
const tabs=penpotUtils.findShape(s=>s.name==='Local navigation',mobile);
const labels=tabs.children.filter(s=>s.type==='text').sort((a,b)=>a.x-b.x);
const widths=[112,84,154];let xx=0;
for(let i=0;i<labels.length;i++){
 const s=labels[i];s.x=tabs.x+xx+14;s.resize(widths[i]-28,25);s.fontSize='13';xx+=widths[i];
}
const selected=tabs.children.find(s=>s.type==='rectangle');selected.resize(widths[1]-8,38);selected.x=tabs.x+widths[0];
const chat=roots.find(s=>s.getPluginData('core-screen')==='ai-context');
const feed=chat.children.find(s=>s.name==='03 · Conversation');
const bubble=feed.children.find(s=>s.name==='User message');
bubble.resize(844,80);
const question=bubble.children.find(s=>s.type==='text'&&!s.getPluginData('message-timestamp'));question.y=bubble.y+14;
const author=feed.children.find(s=>s.type==='text'&&s.characters==='FixRate AI');
const font=penpot.fonts.findByName('IBM Plex Sans');
const typo=penpot.library.local.typographies.find(s=>s.path==='E3 · Type'&&s.name==='13 / 400');
const muted=penpot.library.local.colors.find(s=>s.path==='E3 · Core'&&s.name==='muted')||penpot.library.local.colors.find(s=>s.name==='muted');
function timestamp(parent,role,x,y,w,value,align='left'){
 let s=parent.children.find(s=>s.getPluginData('message-timestamp')===role);
 if(!s){s=penpot.createText(' ');parent.appendChild(s);s.setPluginData('message-timestamp',role);}
 if(typo)typo.applyToText(s);else font.applyToText(s,font.variants.find(v=>v.fontWeight==='400'));
 s.characters=value;s.name='Message timestamp / '+role;s.fontSize='13';s.lineHeight='1.25';s.letterSpacing='0';s.align=align;s.growType='fixed';
 s.fills=muted?[muted.asFill()]:[{fillColor:'#ACBDB0',fillOpacity:1}];s.resize(w,22);s.x=parent.x+x;s.y=parent.y+y;
 const tokenSet=penpot.library.local.tokens.sets.find(s=>s.name==='fixrate-e3-core');
 tokenSet?.tokens.find(t=>t.name==='e3.color.muted')?.applyToShapes([s],['fill']);
 tokenSet?.tokens.find(t=>t.name==='e3.font.size.13')?.applyToShapes([s],['fontSize']);
 return s;
}
timestamp(bubble,'user',20,48,804,'17.11.2026 · 12:10','right');
const aq=author.textBounds;
timestamp(feed,'assistant',aq.x+aq.width-feed.x+16,107,220,'17.11.2026 · 12:11');
p.setPluginData('polish','2026-11-17 · navigation, arrows, message timestamps, final report');
await penpot.waitForLayoutUpdate();
return {...stats,timestamps:all().filter(s=>s.getPluginData('message-timestamp')).length,page:p.id};
