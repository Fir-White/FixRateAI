// Run after native.js and support.js; binds shared assets and review-only navigation.
// Apply polish.js and full-polish.js afterward; never regenerate finalized component masters in place.
const p=penpotUtils.getPageByName('E3 · Core Workflows');await penpot.openPage(p);
const roots=p.root.children.filter(s=>s.type==='board');
const all=()=>penpotUtils.findShapes(s=>true,p.root);
const colors={canvas:'#0C1D18',nav:'#091611',surface:'#142B22',raised:'#1D382D',line:'#304C3F',text:'#EDF1E7',muted:'#ACBDB0',faint:'#8FA697',accent:'#C6DEC0',ink:'#12291D',danger:'#E7AA99',warning:'#DEC08C',warnBg:'#302C1E',dangerBg:'#37271F',disabled:'#6E8678'};
for(const s of all()){
 const radius=s.borderRadius;
 if(radius===9||radius===10)s.borderRadius=12;
 else if(radius===18)s.borderRadius=20;
 else if(radius===14&&s.height!==28)s.borderRadius=16;
}
function label(g){return g.children?.find(s=>s.type==='text');}
function bg(g){return g.children?.find(s=>s.type==='rectangle');}
let replaced=0;
if(!p.getPluginData('controls-finalized')){
 const groups=all().filter(s=>s.type==='board'&&s.name.startsWith('Button / '));
 function kind(g){if(g.getPluginData('context'))return 'ContextAI';const col=bg(g)?.fills?.[0]?.fillColor?.toUpperCase();return g.getPluginData('control-kind')||(label(g)?.fills?.[0]?.fillColor?.toUpperCase()===colors.disabled?'disabled':col===colors.accent?'primary':col===colors.dangerBg?'danger':'secondary');}
 const byKind={};for(const g of groups){const k=kind(g);(byKind[k]??=[]).push(g);}
 for(const k of ['primary','secondary','danger','disabled','ContextAI']){
  const shapes=byKind[k]||[];if(!shapes.length)continue;
  const componentName={primary:'Primary',secondary:'Secondary',danger:'Danger',disabled:'Disabled',ContextAI:'Context AI'}[k];
  let component=penpot.library.local.components.find(c=>c.path==='E3 · Controls'&&c.name===componentName);
  if(!component){component=penpot.library.local.createComponent([shapes[0]]);component.path='E3 · Controls';component.name=componentName;component.annotation='44 px target; IBM Plex Sans 14/500; radius 12. Context and role remain server scoped.';}
  const main=component.mainInstance();bg(main).constraintsHorizontal='leftright';label(main).constraintsHorizontal='leftright';
  for(const g of shapes){if(g.id===main.id||g.component()?.id===component.id)continue;
   const rec={x:g.x,y:g.y,w:g.width,h:g.height,parent:g.parent,index:g.parentIndex,name:g.name,text:label(g).characters,destination:g.getPluginData('destination'),context:g.getPluginData('context')};
   const instance=component.instance();rec.parent.appendChild(instance);instance.resize(rec.w,rec.h);instance.x=rec.x;instance.y=rec.y;instance.name=rec.name;instance.setParentIndex(rec.index);
   const background=bg(instance),caption=label(instance);background.resize(rec.w,rec.h);background.x=rec.x;background.y=rec.y;caption.characters=rec.text;caption.resize(rec.w-(k==='ContextAI'?42:28),24);caption.x=rec.x+(k==='ContextAI'?32:14);caption.y=rec.y+12;
   instance.setPluginData('destination',rec.destination||'');if(rec.context)instance.setPluginData('context',rec.context);instance.setPluginData('control-kind',k);g.remove();replaced++;
  }
 }
 p.setPluginData('controls-finalized','true');
}
const catalog=penpot.library.local.tokens;
let set=catalog.sets.find(s=>s.name==='fixrate-e3-core');if(!set)set=catalog.addSet({name:'fixrate-e3-core',active:true});
const tokens={};function token(type,name,value){let v=set.tokens.find(t=>t.name===name);if(!v)v=set.addToken({type,name,value});tokens[name]=v;return v;}
for(const [n,value] of Object.entries(colors)){
 const tk=token('color','e3.color.'+n,value);const matching=all().filter(s=>Array.isArray(s.fills)&&s.fills.length===1&&s.fills[0].fillColor?.toUpperCase()===value);if(matching.length)tk.applyToShapes(matching,['fill']);
}
for(const size of [12,13,14,15,16,18,20,22,24,28,36,40]){
 const tk=token('fontSizes','e3.font.size.'+size,size+'px');const matching=all().filter(s=>s.type==='text'&&s.fontSize===String(size));if(matching.length)tk.applyToShapes(matching,['fontSize']);
}
for(const size of [4,8,12,16,20,24,32,48,64])token('spacing','e3.space.'+size,size+'px');
for(const size of [7,8,12,14,16,20,24]){const tk=token('borderRadius','e3.radius.'+size,size+'px');const matching=all().filter(s=>s.borderRadius===size);if(matching.length)tk.applyToShapes(matching,['borderRadiusTopLeft','borderRadiusTopRight','borderRadiusBottomLeft','borderRadiusBottomRight']);}
token('fontFamilies','e3.font.family','IBM Plex Sans');token('sizing','e3.control.height','44px');
const frames={};for(const b of roots){const key=b.getPluginData('core-screen')||b.getPluginData('support-state');if(key)frames[key]=b;}
frames.home=penpotUtils.findShape(s=>s.id==='ecd29d2d-0751-800b-8008-f598c0372d0b');
let links=0;const unsupported=[];
for(const s of all()){
 const dest=s.getPluginData('destination');if(!dest)continue;
 for(const i of [...s.interactions])s.removeInteraction(i);
 let ancestor=s;while(ancestor.parent&&ancestor.parent.id!==p.root.id)ancestor=ancestor.parent;
 const source=ancestor.getPluginData('core-screen')||ancestor.getPluginData('support-state');
 if(dest==='close'){s.addInteraction('click',{type:'close-overlay'});links++;continue;}
 if(dest==='home'){s.setPluginData('route','/chief-engineer');s.setPluginData('design-reference',frames.home.id);continue;}
 if(dest===source)continue;
 if(dest==='ai-context'&&!['review'].includes(source)){s.setPluginData('route','/assistant');continue;}
 if(source.startsWith('executor')&&frames[dest]?.getPluginData('role')==='chief_engineer'){s.setPluginData('route',dest==='equipment'?'/equipment/:equipmentId':'/'+dest);unsupported.push({source,destination:dest});continue;}
 if(dest==='executor'&&!source.startsWith('executor')){unsupported.push({source,destination:dest});continue;}
 if(!frames[dest]){s.setPluginData('route',({tasks:'/tasks','task-detail':'/tasks/:taskId',reports:'/reports',workforce:'/settings/workforce','personal-shifts':'/my-shifts','executor-calendar':'/calendar'})[dest]||dest);continue;}
 const overlay=['review-facts','review-facts-mobile','return-confirm','apply-confirm','executor-finish','verify-document-mobile'].includes(dest);
 s.addInteraction('click',overlay?{type:'open-overlay',destination:frames[dest],position:'center',closeWhenClickOutside:true,addBackgroundOverlay:true}:{type:'navigate-to',destination:frames[dest],preserveScrollPosition:false});links++;
}
await penpot.waitForLayoutUpdate();
return {replaced,components:penpot.library.local.components.filter(c=>c.path==='E3 · Controls').map(c=>({id:c.id,name:c.name})),tokenSet:{id:set.id,name:set.name,count:set.tokens.length},prototypeLinks:links,roleCrossingsBlocked:unsupported};
