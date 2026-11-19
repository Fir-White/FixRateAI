// Run after polish.js. Refines the selected E3 home and every Core Workflows state.
// Archived alternatives and application code remain untouched. Re-running is safe.
if(penpot.currentFile.id!=='13ac3151-58c1-801c-8008-f58dd579cd50')throw Error('Existing concepts file required');
const core=penpotUtils.getPageByName('E3 · Core Workflows');
const exploration=penpotUtils.getPageByName('E · Visual Exploration · Chief Engineer');
const home=exploration.getShapeById('ecd29d2d-0751-800b-8008-f598c0372d0b');
const c={canvas:'#0C1D18',muted:'#ACBDB0',line:'#304C3F',accent:'#C6DEC0'};
const stats={};const count=k=>stats[k]=(stats[k]||0)+1;
const descendants=r=>penpotUtils.findShapes(s=>true,r);
const texts=r=>descendants(r).filter(s=>s.type==='text');
function fill(color){const a=penpot.library.local.colors.find(a=>a.name===Object.keys(c).find(k=>c[k]===color)&&['E3 · Core','E · Visual Exploration'].includes(a.path));return a?[a.asFill()]:[{fillColor:color,fillOpacity:1}];}
function centerY(s,cy){const q=s.textBounds;s.y+=cy-q.y-q.height/2;}
function stroke(s,width=1.15,color=c.muted){s.strokes=[{strokeColor:color,strokeWidth:width,strokeStyle:'solid',strokeAlignment:'center',strokeCapStart:'round',strokeCapEnd:'round'}];}
function target(parent,key,x,y,w,h,children=[],name=key){
 let g=parent.children.find(s=>s.getPluginData('hit-target-key')===key);
 if(!g){g=penpot.createBoard();parent.appendChild(g);g.setPluginData('hit-target-key',key);g.clipContent=false;}
 g.fills=[{fillColor:'#0C1D18',fillOpacity:0}];
 g.name=name;g.resize(w,h);g.x=x;g.y=y;
 for(const s of children){if(s.parent.id!==g.id){const sx=s.x,sy=s.y;g.appendChild(s);s.x=sx;s.y=sy;}}
 return g;
}
function moveInteractions(s,g){
 for(const i of [...s.interactions]){g.addInteraction(i.trigger,i.action);s.removeInteraction(i);}
 for(const k of ['destination','route','design-reference','context']){const v=s.getPluginData(k);if(v){g.setPluginData(k,v);s.setPluginData(k,'');}}
}
function rename(s,value){s.characters=value;s.name=value;}
const jobs=[{page:core,roots:core.root.children.filter(s=>s.type==='board')},{page:exploration,roots:[home]}];
for(const job of jobs){
 await penpot.openPage(job.page);await penpot.waitForLayoutUpdate();
 for(const root of job.roots){
  const nav=root.children.find(s=>/^01 · (Global navigation|Navigation)$/.test(s.name));
  if(nav){
   const labels=texts(nav).filter(s=>['Рабочий день','Планирование ТО','Задания','Приёмка','Оборудование','Команда','Отчёты','Мои задания','Мой календарь','Мои смены'].includes(s.characters));
   const underline=nav.children.find(s=>s.type==='rectangle'&&s.height===2);
   const active=underline.getPluginData('active-label-id')?job.page.getShapeById(underline.getPluginData('active-label-id')):labels.slice().sort((a,b)=>Math.abs(a.x-underline.x)-Math.abs(b.x-underline.x))[0];
   underline.setPluginData('active-label-id',active.id);const aq=active.textBounds;underline.resize(aq.width,2);underline.x=aq.x;
   for(const t of labels){
    centerY(t,nav.y+41);const q=t.textBounds;t.resize(Math.ceil(q.width)+1,t.height);
    const g=target(nav,'nav:'+t.characters,q.x-12,nav.y+19,q.width+24,44,[t],'Навигация / '+t.characters);
    if(t.interactions.length)moveInteractions(t,g);count('navigationTargets');
   }
   const avatar=nav.children.find(s=>s.type==='ellipse'&&s.width===32),initials=nav.children.find(s=>s.type==='text'&&['АК','АМ'].includes(s.characters));
   if(avatar&&initials){initials.align='center';initials.resize(32,24);initials.x=avatar.x;centerY(initials,avatar.y+16);count('avatars');}
  }
  const object=texts(root).find(s=>s.characters==='ЖК «Сосновый парк»');
  if(object){
   const q=object.textBounds;
   const caret=descendants(root).find(s=>s.type==='path'&&['down','chevron'].includes(s.name)&&Math.abs(s.y-object.y)<20);
   if(caret){
    caret.resize(7,4);caret.x=q.x+q.width+8;caret.y=q.y+(q.height-4)/2;stroke(caret);
    const contextParent=root.children.find(s=>s.name==='02 · Object and role')||root;
    const divider=contextParent.children.find(s=>s.type==='rectangle'&&s.width===1&&s.height>=18&&s.height<=20&&Math.abs(s.y-object.y)<10);
    const role=texts(root).find(s=>['Главный инженер','Исполнитель'].includes(s.characters));
    if(divider){divider.x=caret.x+caret.width+24;if(role)role.x=divider.x+20;}
    object.resize(Math.ceil(q.width)+1,25);
    const g=target(contextParent,'object-selector',q.x-8,root.y+100,caret.x+caret.width-q.x+16,44,[object,caret],'Выбрать объект');
    g.setPluginData('action','select-object');count('objectSelectors');
   }
   const date=root.children.find(s=>s.type==='text'&&s.characters==='17 ноября 2026 · Вторник');if(date)date.y=root.y+114;
  }
  for(const g of descendants(root).filter(s=>s.type==='board'&&s.name==='Local navigation')){
   const ts=g.children.filter(s=>s.type==='text').sort((a,b)=>a.x-b.x);
   const slots=g.getPluginData('tab-slots')?JSON.parse(g.getPluginData('tab-slots')):ts.map((s,i)=>({start:s.x-g.x-14,width:i<ts.length-1?ts[i+1].x-s.x:g.width-(s.x-g.x-14)}));
   g.setPluginData('tab-slots',JSON.stringify(slots));
   ts.forEach((s,i)=>{s.align='center';s.resize(slots[i].width-8,25);s.x=g.x+slots[i].start;centerY(s,g.y+19);count('tabLabels');});
  }
  for(const g of descendants(root).filter(s=>s.type==='board'&&s.name.startsWith('Status / '))){
   const t=g.children.find(s=>s.type==='text'),d=g.children.find(s=>s.type==='ellipse');if(t)centerY(t,g.y+g.height/2);if(d)d.y=g.y+(g.height-d.height)/2;count('statusPills');
  }
  const buttons=descendants(root).filter(s=>s.type==='board'&&(s.name.startsWith('Button / ')||s.component?.()?.path==='E3 · Controls')).sort((a,b)=>Number(b.isComponentMainInstance())-Number(a.isComponentMainInstance()));
  for(const g of buttons){
   const t=g.children.find(s=>s.type==='text'),bg=g.children.find(s=>s.type==='rectangle'),ai=g.children.find(s=>s.type==='path'&&s.name==='ai');if(!t)continue;
   if(g.height===40){g.resize(g.width,44);if(bg)bg.resize(g.width,44);}
   if(t.characters==='Подтвердить')rename(t,root.getPluginData('support-state')==='return-confirm'?'Вернуть работу':'Сохранить версию');
   if(t.characters==='Добавить'&&root.getPluginData('core-screen')==='executor-mobile'){
    rename(t,'Добавить фото');if(bg){bg.fills=[];bg.strokes=[];}g.name='Button / Добавить фото';
   }
   if(ai){const tw=t.textBounds.width,total=16+8+tw;ai.resize(16,16);ai.x=g.x+(g.width-total)/2;ai.y=g.y+14;t.align='left';t.resize(Math.ceil(tw)+1,24);t.x=ai.x+24;t.constraintsHorizontal='center';ai.constraintsHorizontal='center';count('aiButtonGroups');}
   else {t.align='center';t.resize(g.width-28,24);t.x=g.x+14;}
   centerY(t,g.y+g.height/2);
   const disabled=g.getPluginData('control-kind')==='disabled'||g.component?.()?.name==='Disabled';
   if(disabled&&bg){bg.fills=fill(c.canvas);bg.strokes=[{strokeColor:c.line,strokeWidth:1,strokeStyle:'solid',strokeAlignment:'inner'}];count('disabledBoundaries');}
   count('buttonLabels');
  }
  for(const g of descendants(root).filter(s=>s.type==='board'&&s.name.startsWith('Field / '))){
   const bg=g.children.find(s=>s.type==='rectangle'),value=g.children.find(s=>s.type==='text'&&s.parentY>25);if(bg&&value)centerY(value,bg.y+bg.height/2);count('fieldValues');
  }
  for(const g of descendants(root).filter(s=>s.type==='board'&&s.name.startsWith('Link / '))){
   const t=g.children.find(s=>s.type==='text'),a=g.children.find(s=>s.type==='path'&&['arrow','back'].includes(s.name));if(!t)continue;
   if(g.height===40)g.resize(g.width,44);
   centerY(t,g.y+22);
   const information=t.characters.startsWith('Параметры:')||t.characters==='Скан протокола · не загружен'||t.characters.startsWith('Инструкция · методика не приложена');
   if(information){if(a)a.remove();g.name='Information / '+t.characters;count('informationalArrowsRemoved');continue;}
   if(!a)continue;
   const isBack=['К приёмке','Мои задания','Вернуться к приёмке','Действующий календарь'].includes(t.characters);
   if(isBack){
    const ax=g.x;a.commands=[{command:'move-to',params:{x:10,y:4}},{command:'line-to',params:{x:0,y:4}},{command:'move-to',params:{x:4,y:0}},{command:'line-to',params:{x:0,y:4}},{command:'line-to',params:{x:4,y:8}}];a.resize(10,8);a.x=ax;t.x=ax+18;t.resize(g.width-18,25);a.name='back';count('backLinks');
   }else{a.resize(10,8);const q=t.textBounds;a.x=q.x+q.width+8;}
   a.y=t.textBounds.y+(t.textBounds.height-8)/2;stroke(a,1.15,t.fills[0].fillColor);count('linkArrows');
  }
  for(const s of texts(root)){
   if(s.characters.includes('Расходники не использовались'))rename(s,s.characters.replace('Расходники не использовались','Расходные материалы не использовались'));
   if(s.characters==='Факт и документы')rename(s,'Факты и документы');
   if(s.characters==='Контроль параметров показаний приборов')rename(s,'Контроль параметров по показаниям приборов');
  }
  for(const s of descendants(root).filter(s=>s.type==='path'&&s.name==='menu')){s.resize(18,12);s.x=s.parent.x+13;s.y=s.parent.y+16;stroke(s,1.4);count('menuIcons');}
  for(const s of descendants(root).filter(s=>s.type==='path'&&s.name==='down'&&s.height>4)){const cx=s.x+s.width/2,cy=s.y+s.height/2;s.resize(8,4);s.x=cx-4;s.y=cy-2;stroke(s);count('selectChevrons');}
  for(const s of descendants(root).filter(s=>s.type==='board'&&s.name==='Закрыть')){const t=s.children.find(s=>s.type==='text');if(t){t.fontSize='20';centerY(t,s.y+22);}count('closeControls');}
  await penpot.waitForLayoutUpdate();
 }
}
await penpot.openPage(core);
const roots=core.root.children.filter(s=>s.type==='board');
const get=key=>roots.find(s=>(s.getPluginData('core-screen')||s.getPluginData('support-state'))===key);
const calendar=descendants(get('planning')).find(s=>s.name==='03 · Weekly saved calendar');
for(const [key,name,x] of [['back','Предыдущая неделя',184],['arrow','Следующая неделя',228]]){
 const s=descendants(calendar).find(s=>s.type==='path'&&s.name===key&&s.parent.id===calendar.id)||descendants(calendar).find(s=>s.parent.name===name&&s.type==='path');if(!s)continue;
 const g=target(calendar,'week:'+key,calendar.x+x,calendar.y-6,44,44,[s],name);g.setPluginData('action',key==='back'?'previous-week':'next-week');
 s.resize(10,8);s.x=g.x+17;s.y=g.y+18;stroke(s);count('calendarControls');
}
const chat=get('ai-context');const history=chat.children.find(s=>s.type==='rectangle'&&s.parentY===418);if(history){history.x=chat.x+1160;history.resize(216,70);}
for(const t of chat.children.filter(s=>s.type==='text'&&['Приёмка ТО-017','Сегодня · 12:10','Сегодня · 12:11'].includes(s.characters))){t.x=chat.x+1176;t.resize(184,t.height);if(t.characters.startsWith('Сегодня'))rename(t,'Сегодня · 12:11');}
const composer=chat.children.find(s=>s.name==='04 · Chat composer');
const plus=composer.children.find(s=>s.name==='plus')||descendants(composer).find(s=>s.name==='plus'),file=texts(composer).find(s=>s.characters==='Файл или фото');
if(plus&&file){const g=target(composer,'attach',composer.x+16,composer.y+78,200,48,[plus,file],'Прикрепить файл или фото');g.setPluginData('action','attach-personal-file');plus.resize(16,16);plus.x=g.x+8;plus.y=g.y+16;stroke(plus,1.25,c.accent);centerY(file,g.y+24);}
const model=texts(composer).find(s=>s.characters==='Выбрать модель');
if(model){const g=target(composer,'model',composer.x+244,composer.y+78,180,48,[model],'Выбрать модель');g.setPluginData('action','choose-model');model.x=g.x+16;model.resize(140,25);centerY(model,g.y+24);let a=g.children.find(s=>s.type==='path');if(!a){a=penpot.createPath();g.appendChild(a);a.name='down';a.commands=[{command:'move-to',params:{x:0,y:0}},{command:'line-to',params:{x:4,y:4}},{command:'line-to',params:{x:8,y:0}}];a.fills=[];}a.resize(7,4);a.x=model.textBounds.x+model.textBounds.width+8;a.y=g.y+22;stroke(a);}
const up=composer.children.find(s=>s.name==='up')||descendants(composer).find(s=>s.name==='up'),sendBg=composer.children.find(s=>s.type==='rectangle'&&s.width===48);
if(up&&sendBg){const g=target(composer,'send',composer.x+944,composer.y+78,48,48,[sendBg,up],'Отправить сообщение');g.setPluginData('action','send-message');up.resize(14,14);up.x=g.x+17;up.y=g.y+17;stroke(up,1.35,'#12291D');}
const verify=get('verify-document-mobile');
if(!verify.getPluginData('compact-title')){
 const title=verify.children.find(s=>s.type==='text'&&s.characters==='Проверить\nпротокол');
 if(title){rename(title,'Проверка протокола');title.resize(250,37);for(const s of verify.children)if(s.id!==title.id&&s.parentY>80)s.y-=32;verify.resize(350,460);verify.setPluginData('compact-title','true');count('compactDocumentHeader');}
}
for(const root of roots){
 for(const camera of descendants(root).filter(s=>s.type==='path'&&s.name==='camera')){
  const cx=camera.x+camera.width/2,cy=camera.y+camera.height/2;
  camera.commands=[['move-to',0,4],['line-to',5,4],['line-to',7,0],['line-to',15,0],['line-to',17,4],['line-to',22,4],['line-to',22,18],['line-to',0,18],['close-path']].map(([command,x,y])=>({command,params:x===undefined?undefined:{x,y}}));
  camera.resize(20,16);camera.x=cx-10;camera.y=cy-8;stroke(camera,1.25,c.accent);
  let lens=jobSafeShape(camera.getPluginData('camera-lens-id'));if(!lens){lens=penpot.createEllipse();camera.parent.appendChild(lens);lens.name='Camera / lens';camera.setPluginData('camera-lens-id',lens.id);}lens.resize(6,6);lens.x=camera.x+7;lens.y=camera.y+6.5;lens.fills=[];stroke(lens,1.25,c.accent);count('cameraIcons');
 }
}
function jobSafeShape(id){return id?core.getShapeById(id):null;}
core.setPluginData('full-polish','2026-11-17');
await penpot.waitForLayoutUpdate();
await penpot.openPage(exploration);
const horizon=descendants(home).find(s=>s.name==='07 · Assignment horizon');
if(horizon){
 for(const s of horizon.children.filter(s=>s.type==='rectangle'&&s.height<=1))s.remove();
 const times=horizon.children.filter(s=>s.type==='text'&&/^\d{2}:\d{2}$/.test(s.characters)).sort((a,b)=>a.x-b.x),dots=horizon.children.filter(s=>s.type==='ellipse').sort((a,b)=>a.x-b.x);
 dots.forEach((d,i)=>{const q=times[i].textBounds;d.y=q.y+(q.height-d.height)/2;});
 count('timelineLineRemoved');
}
const workContext=descendants(home).find(s=>s.name==='03 · Shared work context');
for(const [number,label] of [['3','Работы просрочены'],['42','Без исполнителя']]){
 const n=texts(workContext).find(s=>s.characters===number),g=descendants(workContext).find(s=>s.name==='Link / '+label);
 const q=n.textBounds,cy=q.y+q.height/2;g.y=cy-22;const t=g.children.find(s=>s.type==='text'),a=g.children.find(s=>s.name==='arrow');centerY(t,cy);if(a)a.y=cy-4;
}
const priority=descendants(home).find(s=>s.name==='06 · Priority context');
if(priority){const t=priority.children.find(s=>s.type==='text'),d=priority.children.find(s=>s.type==='ellipse'),q=t.textBounds;d.y=q.y+(q.height-d.height)/2;}
const intelligence=descendants(home).find(s=>s.name==='04 · Intelligence workspace'),starter=texts(intelligence).find(s=>s.characters==='Можно начать с');
if(starter)centerY(starter,intelligence.y+191);
const homeComposer=descendants(home).find(s=>s.name==='04 · AI composer');
const homeFile=texts(homeComposer).find(s=>s.characters==='Файл или фото'),homePlus=descendants(homeComposer).find(s=>s.name==='plus');
if(homeFile&&homePlus){const g=target(homeComposer,'attach',homeComposer.x+20,homeComposer.y+100,196,44,[homeFile,homePlus],'Прикрепить файл или фото');g.setPluginData('action','attach-personal-file');homePlus.resize(16,16);homePlus.x=g.x+8;homePlus.y=g.y+14;stroke(homePlus,1.25,c.accent);centerY(homeFile,g.y+22);}
const brand=texts(homeComposer).find(s=>s.characters==='FixRate AI'),spark=homeComposer.children.find(s=>s.name==='ai');if(brand&&spark)centerY(brand,spark.y+spark.height/2);
home.setPluginData('full-polish','2026-11-17');
await penpot.waitForLayoutUpdate();
const tokenSet=penpot.library.local.tokens.sets.find(s=>s.name==='fixrate-e3-core');
for(const job of jobs){
 await penpot.openPage(job.page);const shapes=job.roots.flatMap(descendants);
 for(const token of tokenSet.tokens){
  if(token.type==='color'){
   const matching=shapes.filter(s=>s.fills?.length===1&&s.fills[0].fillOpacity!==0&&s.fills[0].fillColor?.toUpperCase()===String(token.value).toUpperCase());if(matching.length)token.applyToShapes(matching,['fill']);
  }else if(token.type==='fontSizes'){
   const size=String(token.value).replace('px',''),matching=shapes.filter(s=>s.type==='text'&&s.fontSize===size);if(matching.length)token.applyToShapes(matching,['fontSize']);
  }
 }
}
await penpot.openPage(core);
return stats;
