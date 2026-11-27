// Native E3 section polish. Supply SECTION and ORDER (catalog screens for that section).
const p=penpot.currentFile.pages.find(p=>p.getPluginData('suite-section')===SECTION);
if(!p)throw Error('Missing section '+SECTION);
await penpot.openPage(p);
const block=penpot.history.undoBlockBegin(),stats={section:SECTION,frames:0,centers:0,carets:0,lenses:0,passwords:0};
try{
 let yy=0;const positions={};
 for(const spec of ORDER){
  const roots=spec.devices.map(d=>p.root.children.find(s=>s.getPluginData('suite-screen')===spec.key+'--'+d)).filter(Boolean);
  const hh=Math.max(...roots.map(s=>s.height));positions[spec.key]={y:yy,maxH:hh};
  for(const r of roots){
   if(typeof ONLY_KEYS!=='undefined'&&!ONLY_KEYS.includes(r.getPluginData('suite-screen')))continue;
   const dx=(r.getPluginData('suite-screen').endsWith('--mobile')?1680:0)-r.x,dy=yy-r.y;
   const centers=JSON.parse(r.getPluginData('centering')||'[]');if(dx)r.x+=dx;if(dy)r.y+=dy;
   for(const item of centers){if(item.cx!==undefined)item.cx+=dx;if(item.cy!==undefined)item.cy+=dy;}
   r.setPluginData('centering',JSON.stringify(centers));
   for(const item of centers){const t=p.getShapeById(item.id);if(!t||t.type!=='text')continue;const q=t.textBounds;if(!q.width||!q.height)throw Error('Unmeasured '+t.id);if(item.cx!==undefined)t.x+=item.cx-q.x-q.width/2;if(item.cy!==undefined)t.y+=item.cy-q.y-q.height/2;stats.centers++;}
   const all=penpotUtils.findShapes(s=>true,r);
   for(const u of all.filter(s=>s.getPluginData('underline-for'))){const t=p.getShapeById(u.getPluginData('underline-for')),q=t.textBounds;u.resize(q.width,2);u.x=q.x;}
   const obj=all.find(s=>s.type==='board'&&s.name==='Выбрать объект');
   if(obj){const t=obj.children.find(s=>s.type==='text'),a=obj.children.find(s=>s.type==='path'),q=t.textBounds;t.y+=obj.y+22-q.y-q.height/2;a.resize(7,4);a.x=q.x+q.width+8;a.y=obj.y+20;obj.resize(Math.ceil(a.x+a.width+8-obj.x),44);const divider=r.children.find(s=>s.type==='rectangle'&&s.width===1&&s.height===20);if(divider){divider.x=a.x+a.width+24;const role=r.children.find(s=>s.type==='text'&&Math.abs(s.y-r.y-114)<3&&s.x<600);if(role)role.x=divider.x+20;}stats.carets++;}
   for(const g of all.filter(s=>s.type==='board'&&s.name.startsWith('Link / '))){const t=g.children.find(s=>s.type==='text'),a=g.children.find(s=>s.type==='path');if(!t||!a)continue;const q=t.textBounds;if(a.name==='arrow')a.x=q.x+q.width+8;a.y=q.y+(q.height-a.height)/2;}
   if(r.getPluginData('suite-screen')==='home-chief--desktop'){const s=r.children.find(s=>s.type==='text'&&s.characters.startsWith('48 незавершённых'));if(s)s.y=r.y+324;}
   for(const a of all.filter(s=>s.type==='path'&&s.name==='camera'&&!s.getPluginData('camera-lens'))){const e=penpot.createEllipse();a.parent.appendChild(e);e.name='Camera lens';e.resize(a.width*.3,a.width*.3);e.x=a.x+a.width*.35;e.y=a.y+a.height*.38;e.fills=[];e.strokes=[{strokeColor:'#C6DEC0',strokeWidth:1.25,strokeStyle:'solid',strokeAlignment:'center'}];a.setPluginData('camera-lens',e.id);stats.lenses++;}
   for(const t of all.filter(s=>s.type==='text'&&/^•+$/.test(s.characters))){
    const bg=t.parent.children.find(s=>s.type==='rectangle'&&s.height===44&&t.x>=s.x&&t.x<s.x+s.width&&t.y>=s.y-1&&t.y<s.y+s.height);
    if(!bg||bg.getPluginData('password-control'))continue;
    const g=penpot.createBoard();t.parent.appendChild(g);g.name='Показать пароль';g.resize(44,44);g.x=bg.x+bg.width-44;g.y=bg.y;g.fills=[{fillColor:'#0C1D18',fillOpacity:0}];g.clipContent=false;g.setPluginData('action','toggle-password');t.resize(bg.width-72,t.height);
    for(const [name,w,h,ox,oy,filled] of [['Eye',16,8,14,18,false],['Pupil',3,3,20.5,20.5,true]]){const e=penpot.createEllipse();g.appendChild(e);e.name=name;e.resize(w,h);e.x=g.x+ox;e.y=g.y+oy;e.fills=filled?[{fillColor:'#ACBDB0',fillOpacity:1}]:[];e.strokes=filled?[]:[{strokeColor:'#ACBDB0',strokeWidth:1.15,strokeStyle:'solid',strokeAlignment:'center'}];}
    bg.setPluginData('password-control',g.id);stats.passwords++;
   }
   for(const g of all.filter(s=>s.type==='board'&&['Chat composer','AI workspace'].includes(s.name))){g.setPluginData('layout-behavior',g.name==='Chat composer'?'sticky-bottom; safe-area; keyboard-aware':'central-wide-input');const a=g.children.find(s=>s.name==='Прикрепить файл или фото');if(a){a.setPluginData('suite-destination','');a.setPluginData('action','select-file');}}
   if(/^assistant-(chat|working)--/.test(r.getPluginData('suite-screen'))&&!r.getPluginData('composer-gap-fixed')){r.resize(r.width,r.height-28);r.setPluginData('composer-gap-fixed','true');}
   r.setPluginData('viewport-width',String(r.width));r.setPluginData('scroll-behavior',r.getPluginData('presentation')==='dialog'?'Constrain to viewport; scroll dialog body; retain title and actions':'Native document scroll; retain global shell');
   r.setPluginData('visual-polish','measured-v1');stats.frames++;
  }
  yy+=hh+240;
 }
 p.setPluginData('positions',JSON.stringify(positions));p.setPluginData('cursors',JSON.stringify({[SECTION]:yy}));p.setPluginData('canonical-order',JSON.stringify(ORDER.map(s=>s.key)));
 return stats;
}finally{penpot.history.undoBlockFinish(block);}
