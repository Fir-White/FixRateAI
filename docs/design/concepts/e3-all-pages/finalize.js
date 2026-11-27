// Shared font tokens and same-page prototype links. Cross-page targets remain explicit references.
const p=penpot.currentFile.pages.find(p=>p.getPluginData('suite-section')===SECTION);await penpot.openPage(p);
const token=penpot.history.undoBlockBegin();const stats={section:SECTION,native:0,crossPage:0,roleContext:0,close:0};
try{
 const all=penpotUtils.findShapes(s=>true,p.root),set=penpot.library.local.tokens.sets.find(t=>t.name==='fixrate-e3-core');
 if(typeof BIND_FONTS==='undefined'||BIND_FONTS)for(const size of [12,13,14,15,16,18,20,22,24,28,32,36,40,48]){let tk=set.tokens.find(t=>t.name==='e3.font.size.'+size);if(!tk)tk=set.addToken({type:'fontSizes',name:'e3.font.size.'+size,value:size+'px'});const shapes=all.filter(s=>s.type==='text'&&s.fontSize===String(size));if(shapes.length)tk.applyToShapes(shapes,['fontSize']);}
 for(const r of p.root.children.filter(r=>r.getPluginData('suite-screen'))){
  const key=r.getPluginData('suite-screen'),device=key.endsWith('--mobile')?'mobile':'desktop',source=MAP[key];
  for(const s of penpotUtils.findShapes(s=>true,r)){
   for(const i of [...s.interactions])s.removeInteraction(i);
   if(s.getPluginData('suite-close')==='true'){s.addInteraction('click',r.height>(device==='mobile'?720:780)?{type:'previous-screen'}:{type:'close-overlay'});stats.close++;continue;}
   const dest=s.getPluginData('suite-destination');if(!dest||s.getPluginData('disabled')==='true')continue;
   const d=MAP[dest+'--'+device]||MAP[dest+'--mobile']||MAP[dest+'--desktop'];if(!d)throw Error('Unknown destination '+dest);
   s.setPluginData('route-reference',d.route);s.setPluginData('design-reference',JSON.stringify({pageId:d.pageId,frameId:d.id,key:d.key}));
   const roleMismatch=source.role!==d.role&&!d.public&&!['Shared'].includes(d.group);
   if(roleMismatch){s.setPluginData('prototype-context','Role must be retained by the application; this reference is a different role snapshot');stats.roleContext++;continue;}
   if(d.pageId!==p.id){s.setPluginData('prototype-context','Cross-page reference: native Penpot addInteraction rejects a board from another page');stats.crossPage++;continue;}
   if(d.id===r.id)continue;
   const board=p.getShapeById(d.id),overlay=d.presentation==='dialog'&&board.height<(device==='mobile'?720:780);
   s.addInteraction('click',overlay?{type:'open-overlay',destination:board,position:'center',closeWhenClickOutside:true,addBackgroundOverlay:true}:{type:'navigate-to',destination:board,preserveScrollPosition:false});stats.native++;
  }
 }
 const roots=p.root.children.filter(r=>r.getPluginData('suite-screen'));
 // Page frames are available in the viewer without adding flows; this server rejects createFlow with a Board proxy.
 p.setPluginData('prototype-summary',JSON.stringify(stats));return stats;
}finally{penpot.history.undoBlockFinish(token);}
