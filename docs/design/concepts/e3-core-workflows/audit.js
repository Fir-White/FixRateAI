// Read-only verification for the selected E3 home and all Core Workflows boards.
const core=penpotUtils.getPageByName('E3 · Core Workflows');
const home=penpotUtils.getPageByName('E · Visual Exploration · Chief Engineer').getShapeById('ecd29d2d-0751-800b-8008-f598c0372d0b');
const roots=[...core.root.children.filter(s=>s.type==='board'),home];
const round=n=>Math.round(n*1000)/1000;
const frames=roots.map(root=>{
 const all=penpotUtils.findShapes(s=>true,root),ts=all.filter(s=>s.type==='text');
 const outside=all.filter(s=>s.x<root.x-.5||s.y<root.y-.5||s.x+s.width>root.x+root.width+.5||s.y+s.height>root.y+root.height+.5).map(s=>s.name);
 const overflow=ts.filter(s=>s.textBounds.width>s.width+1||s.textBounds.height>s.height+1).map(s=>s.characters);
 const textOverlaps=[];
 for(let i=0;i<ts.length;i++)for(let j=i+1;j<ts.length;j++){
  const a=ts[i].textBounds,b=ts[j].textBounds;
  if(Math.min(a.x+a.width,b.x+b.width)-Math.max(a.x,b.x)>3&&Math.min(a.y+a.height,b.y+b.height)-Math.max(a.y,b.y)>3)textOverlaps.push([ts[i].characters,ts[j].characters]);
 }
 const lines=all.filter(s=>s.type==='rectangle'&&s.height<=2&&s.width>50);
 const lineClashes=lines.flatMap(l=>ts.filter(t=>{const q=t.textBounds;return Math.min(q.x+q.width,l.x+l.width)-Math.max(q.x,l.x)>2&&Math.min(q.y+q.height,l.y+l.height)-Math.max(q.y,l.y)>.5;}).map(t=>t.characters));
 const smallTargets=all.filter(s=>s.interactions.length&&(s.width<44||s.height<44)).map(s=>({name:s.name,width:s.width,height:s.height}));
 const nav=root.children.find(s=>/^01 · (Global navigation|Navigation)$/.test(s.name));let underline=null;
 if(nav){const u=nav.children.find(s=>s.type==='rectangle'&&s.height===2),t=penpotUtils.findShapes(s=>s.type==='text',nav).find(s=>s.id===u.getPluginData('active-label-id')),q=t.textBounds;underline={label:t.characters,centerDelta:round(u.x+u.width/2-q.x-q.width/2),widthDelta:round(u.width-q.width)};}
 const tabCenters=all.filter(s=>s.name==='Local navigation').map(g=>{const selected=g.children.find(s=>s.type==='rectangle'),t=g.children.find(s=>s.type==='text'&&Math.abs(s.x-selected.x)<1),q=t.textBounds;return {label:t.characters,x:round(q.x+q.width/2-selected.x-selected.width/2),y:round(q.y+q.height/2-selected.y-selected.height/2)};});
 const buttonCenters=all.filter(s=>s.type==='board'&&(s.name.startsWith('Button / ')||s.component?.()?.path==='E3 · Controls')).map(g=>{
  const t=g.children.find(s=>s.type==='text'),ai=g.children.find(s=>s.name==='ai'),q=t.textBounds;
  return {label:t.characters,x:round((ai?(ai.x+q.x+q.width)/2:q.x+q.width/2)-g.x-g.width/2),y:round(q.y+q.height/2-g.y-g.height/2)};
 });
 return {key:root===home?'home':root.getPluginData('core-screen')||root.getPluginData('support-state'),id:root.id,name:root.name,width:root.width,height:root.height,texts:ts.length,nodes:all.length,outside,overflow,textOverlaps,lineClashes,smallTargets,underline,tabCenters,buttonCenters,flatUI:all.filter(s=>s.type==='svg-raw').length,interactions:all.reduce((n,s)=>n+s.interactions.length,0)};
});
return {revision:penpot.currentFile.revn,frames,timestamps:penpotUtils.findShapes(s=>s.getPluginData('message-timestamp'),core.root).map(s=>({role:s.getPluginData('message-timestamp'),value:s.characters})),components:penpot.library.local.components.filter(s=>s.path==='E3 · Controls').length,tokens:penpot.library.local.tokens.sets.find(s=>s.name==='fixrate-e3-core').tokens.length};
