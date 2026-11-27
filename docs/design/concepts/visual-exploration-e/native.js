// Native Penpot exploration. Run with official MCP; E_VARIANT = 1, 2 or 3.
// All design layers are editable. Existing pages are never mutated.
if (penpot.currentFile.id !== '13ac3151-58c1-801c-8008-f58dd579cd50') throw Error('Use the existing lightweight concept file');
let pg=penpotUtils.getPageByName('E · Visual Exploration · Chief Engineer');
if(!pg){pg=penpot.createPage();pg.name='E · Visual Exploration · Chief Engineer';}
await penpot.openPage(pg);
const v=E_VARIANT;
const previous=pg.getPluginData('E'+v);
if(previous && typeof E_REBUILD==='undefined')return {alreadyBuilt:true,id:previous};
const fonts={sans:penpot.fonts.findByName('IBM Plex Sans'),narrow:penpot.fonts.findByName('IBM Plex Sans Condensed')};
if(!fonts.sans||!fonts.narrow)throw Error('Verified IBM Plex fonts required');
const c={canvas:'#0C1D18',nav:'#091611',surface:'#142B22',raised:'#1D382D',line:'#304C3F',text:'#EDF1E7',muted:'#ACBDB0',faint:'#8FA697',accent:'#C6DEC0',ink:'#12291D',danger:'#E7AA99',warning:'#DEC08C'};
const fills={};
for(const [name,color] of Object.entries(c)){
 let asset=penpot.library.local.colors.find(a=>a.path==='E · Visual Exploration'&&a.name===name);
 if(!asset){asset=penpot.library.local.createColor();asset.path='E · Visual Exploration';asset.name=name;asset.color=color;}
 fills[color]=[asset.asFill()];
}
const ox=(v-1)*1680,oy=0;
const root=previous?pg.getShapeById(previous):penpot.createBoard();
if(previous)root.children.forEach(s=>s.remove());
root.name=['','E1 · Quiet Precision · 1440×900','E2 · Industrial Editorial · 1440×900','E3 · Fluid Intelligence · 1440×900'][v];root.resize(1440,900);root.x=ox;root.y=oy;root.fills=fills[c.canvas];root.clipContent=true;
root.setPluginData('direction','E'+v);root.setPluginData('scenario','chief-engineer-morning-2026-11-17');
const tags={root:root.id};
function place(s,p,x,y,w,h,name){s.name=name;s.resize(w,h);p.appendChild(s);s.x=p.x+x;s.y=p.y+y;return s;}
function rect(p,x,y,w,h,fill,r=0,border=null,name='Surface'){
 const s=place(penpot.createRectangle(),p,x,y,w,h,name);s.fills=fill?(fills[fill]||[{fillColor:fill,fillOpacity:1}]):[];s.borderRadius=r;
 if(border)s.strokes=[{strokeColor:border,strokeWidth:1,strokeStyle:'solid',strokeAlignment:'inner'}];return s;
}
function box(p,x,y,w,h,name,fill=null,r=0){const s=place(penpot.createBoard(),p,x,y,w,h,name);s.fills=fill?(fills[fill]||[{fillColor:fill,fillOpacity:1}]):[];s.borderRadius=r;s.clipContent=false;return s;}
function text(p,x,y,w,h,value,size=16,weight=400,color=c.text,family='sans',spacing=0){
 const t=penpot.createText(' ');fonts[family].applyToText(t,fonts[family].variants.find(a=>a.fontWeight===String(weight))||fonts[family].variants[0]);
 t.fontSize=String(size);t.lineHeight='1.22';t.letterSpacing=String(spacing);t.fills=fills[color]||[{fillColor:color,fillOpacity:1}];t.characters=value;t.growType='fixed';place(t,p,x,y,w,h,value.replace(/\n/g,' / '));return t;
}
function line(p,x,y,w,col=c.line,h=1){return rect(p,x,y,w,h,col,0,null,'Divider');}
function dot(p,x,y,d,col){const s=place(penpot.createEllipse(),p,x,y,d,d,'Status');s.fills=fills[col]||[{fillColor:col,fillOpacity:1}];return s;}
function path(p,x,y,w,h,commands,col=c.muted,stroke=1.5,name='Icon'){
 const s=penpot.createPath();s.commands=commands.map(a=>({command:({M:'move-to',L:'line-to',Z:'close-path'})[a[0]],params:a.length>1?{x:a[1],y:a[2]}:undefined}));s.fills=[];s.strokes=[{strokeColor:col,strokeWidth:stroke,strokeStyle:'solid',strokeAlignment:'center',strokeCapStart:'round',strokeCapEnd:'round'}];return place(s,p,x,y,w,h,name);
}
const icons={
 arrow:[['M',4,12],['L',20,12],['M',14,6],['L',20,12],['L',14,18]],
 up:[['M',12,20],['L',12,4],['M',5,11],['L',12,4],['L',19,11]],
 chevron:[['M',6,9],['L',12,15],['L',18,9]],
 plus:[['M',4,12],['L',20,12],['M',12,4],['L',12,20]],
 home:[['M',3,11],['L',12,3],['L',21,11],['L',21,21],['L',3,21],['L',3,11],['M',9,21],['L',9,14],['L',15,14],['L',15,21]],
 calendar:[['M',4,5],['L',20,5],['L',20,21],['L',4,21],['L',4,5],['M',4,10],['L',20,10],['M',8,2],['L',8,7],['M',16,2],['L',16,7]],
 task:[['M',3,6],['L',5,8],['L',9,3],['M',12,6],['L',22,6],['M',3,15],['L',5,17],['L',9,12],['M',12,15],['L',22,15],['M',12,22],['L',22,22]],
 check:[['M',4,12],['L',10,18],['L',21,5]],
 equipment:[['M',3,4],['L',21,4],['L',21,20],['L',3,20],['L',3,4],['M',8,4],['L',8,20],['M',13,9],['L',17,9],['M',13,15],['L',17,15]],
 people:[['M',4,8],['L',4,3],['L',10,3],['L',10,8],['L',4,8],['M',2,21],['L',2,13],['L',12,13],['L',12,21],['M',15,4],['L',21,4],['L',21,9],['L',15,9],['M',16,14],['L',23,14],['L',23,21]],
 report:[['M',4,21],['L',4,13],['M',12,21],['L',12,5],['M',20,21],['L',20,10]],
 ai:[['M',12,1],['L',15,9],['L',23,12],['L',15,15],['L',12,23],['L',9,15],['L',1,12],['L',9,9],['L',12,1]],
 file:[['M',8,16],['L',16,8],['L',19,8],['L',19,12],['L',10,21],['L',5,21],['L',2,18],['L',2,13],['L',14,1],['L',20,1],['L',23,4],['L',23,10]],
 clock:[['M',12,3],['L',20,7],['L',20,17],['L',12,21],['L',4,17],['L',4,7],['L',12,3],['M',12,7],['L',12,12],['L',16,14]]
};
function icon(p,x,y,name,size=18,col=c.muted){return path(p,x,y,size,size,icons[name],col,1.5,name);}
function link(p,x,y,w,label,col=c.accent,size=15){const g=box(p,x,y,w,40,'Link / '+label);text(g,0,9,w-24,24,label,size,500,col);icon(g,w-18,13,'arrow',14,col);return g;}
function button(p,x,y,w,label,fill=c.surface,col=c.text,r=8){const g=box(p,x,y,w,40,'Button / '+label);rect(g,0,0,w,40,fill,r);text(g,14,10,w-28,22,label,14,500,col);return g;}
function mark(p,x,y,size=30){const g=box(p,x,y,size,size,'FixRate / precision mark');rect(g,0,0,size,size,c.accent,7);path(g,8,7,size-16,size-14,[['M',2,18],['L',2,2],['L',16,2],['M',2,9],['L',12,9]],c.ink,2.4,'F');return g;}
function profile(p,x,y){dot(p,x,y,32,c.raised);text(p,x+5,y+6,24,22,'АК',12,500,c.accent);}
function sidebar(){
 const s=box(root,0,0,216,900,'01 · Navigation',c.nav);mark(s,24,30,30);text(s,66,31,138,30,'FixRate AI',21,500,c.text,'sans',-.6);
 line(s,24,92,168);text(s,24,118,170,20,'РАБОЧАЯ ОБЛАСТЬ',12,500,c.faint,'sans',1.1);
 const names=['Рабочий день','Планирование ТО','Задания','Приёмка работ','Оборудование','Команда и смены','Отчёты'];
 const glyphs=['home','calendar','task','check','equipment','people','report'];
 names.forEach((n,i)=>{const y=158+i*48;if(!i){rect(s,12,y-1,192,42,c.surface,7);rect(s,12,y+10,2,20,c.accent);}icon(s,25,y+11,glyphs[i],18,!i?c.accent:c.faint);text(s,55,y+10,144,24,n,14,i===0?500:400,i===0?c.text:c.muted);});
 line(s,24,546,168);icon(s,25,571,'ai',18,c.accent);text(s,55,570,144,24,'ИИ-помощник',14,400,c.muted);
 line(s,24,794,168);profile(s,24,818);text(s,66,817,138,23,'Алексей Крылов',14,500);text(s,66,842,138,20,'Личный кабинет',12,400,c.muted);
}
function topnav(style=2){
 const g=box(root,0,0,1440,82,'01 · Navigation',style===2?c.nav:null);mark(g,48,26,30);text(g,91,27,180,30,'FixRate AI',22,500,c.text,'sans',-.6);
 let xx=style===2?296:328;const labels=['Рабочий день','Планирование ТО','Задания','Приёмка','Оборудование','Команда','Отчёты'],widths=[126,155,90,96,135,95,75];
 labels.forEach((label,i)=>{text(g,xx,31,widths[i],24,label,14,i===0?500:400,i===0?c.text:c.muted);if(i===0)rect(g,xx,79,widths[i]-25,2,c.accent);xx+=widths[i];});profile(g,1358,25);line(g,48,81,1344);
}
function context(p,x,y,w=1128){const g=box(p,x,y,w,38,'02 · Object and role');text(g,0,7,270,25,'ЖК «Сосновый парк»',16,500);icon(g,246,15,'chevron',10,c.muted);line(g,284,12,1,c.line,18);text(g,304,9,210,23,'Главный инженер',14,400,c.muted);return g;}
function input(p,x,y,w,h,style){
 const g=box(p,x,y,w,h,'04 · AI composer');tags.composer=g.id;
 if(style===1){rect(g,0,0,w,h,c.surface,12,c.line);rect(g,0,20,3,h-40,c.accent,1);}
 if(style===2){rect(g,0,0,w,h,c.surface,0);rect(g,0,0,w,2,c.accent);line(g,196,24,1,c.line,h-48);}
 if(style===3){rect(g,0,0,w,h,c.raised,24);}
 const start=style===2?224:28;
 if(style===2){text(g,28,22,140,62,'AI',44,500,c.accent,'narrow',-.8);text(g,28,88,148,42,'Помощник\nглавного инженера',14,400,c.muted);}
 else{icon(g,28,22,'ai',18,c.accent);text(g,57,21,300,25,'FixRate AI',14,500,c.accent);}
 const field=text(g,start,style===2?26:60,w-start-104,42,style===3?'Что нужно сделать сегодня?':'Какую задачу разберём сегодня?',style===2?28:style===3?30:24,400,c.text,'sans',-.4);tags.placeholder=field.id;
 icon(g,start,h-42,'plus',18,c.accent);text(g,start+30,h-45,140,24,'Файл или фото',14,400,c.muted);
 text(g,style===2?460:start+200,h-45,510,24,'Контекст: текущий объект и ваша роль',13,400,c.muted);
 const send=box(g,w-76,h-69,48,48,'Send message');rect(send,0,0,48,48,c.accent,style===2?0:style===3?24:9);icon(send,16,14,'up',16,c.ink);tags.send=send.id;
 return g;
}
function prompts(p,x,y,style=1){
 const g=box(p,x,y,1128,44,'05 · AI quick actions');
 const labels=['Разобрать просрочки','Проверить загрузку','Найти оборудование'];
 const starts=style===2?[0,290,580]:[156,476,800];
 if(style===1)text(g,0,10,140,24,'Спросить AI',13,400,c.faint);
 labels.forEach((n,i)=>{if(style===3)button(g,starts[i],0,[250,240,250][i],n,c.surface,c.accent,20);else{link(g,starts[i],0,style===1?[284,288,328][i]:[240,232,250][i],n,c.muted,14);}});return g;
}
const tasks=[
 {time:'09:00',title:'Контроль параметров приборов',meta:'Индивидуальный тепловой пункт',status:'Не назначен',color:c.warning},
 {time:'10:00',title:'Протоколирование показаний счётчиков',meta:'Алексей Морозов',status:'Назначено',color:c.muted},
 {time:'11:00',title:'Проверка температуры и давления',meta:'Алексей Морозов',status:'В работе',color:c.accent}
];
function taskRows(p,x,y,w,rowH=76){const g=box(p,x,y,w,rowH*3,'07 · Next assignments');tags.agenda=g.id;
 tasks.forEach((a,i)=>{const yy=i*rowH;text(g,0,yy+10,72,28,a.time,18,500,c.text,'sans',-.5);text(g,94,yy+8,w-94-135,26,a.title,16,500);text(g,94,yy+33,w-94-130,23,a.meta,14,400,c.muted);dot(g,w-127,yy+17,5,a.color);text(g,w-111,yy+9,112,24,a.status,13,400,a.color);line(g,0,yy+rowH-1,w);});return g;
}
function urgent(p,x,y,w,style=1){const g=box(p,x,y,w,246,'06 · Attention / overdue');tags.urgent=g.id;
 if(style===1){text(g,0,0,w,32,'Требует внимания',20,500);text(g,0,54,64,68,'03',48,400,c.danger,'sans',-2);text(g,88,59,w-88,26,'Работы просрочены',16,500,c.danger);link(g,88,84,w-88,'Разобрать очередь',c.muted,13);line(g,0,133,w);text(g,0,154,w,27,'Проверка управляющего модуля',16,500);text(g,0,186,w,24,'Срок — 16 ноября · На доработке',13,400,c.muted);}
 else{text(g,0,0,w,25,'ПЕРВЫЙ ПРИОРИТЕТ',12,500,c.danger,'sans',1.5);text(g,0,40,w,60,'Проверка управляющего\nмодуля',22,500,c.text);text(g,0,113,w,24,'Срок — 16 ноября · На доработке',14,400,c.muted);link(g,0,159,w,'Разобрать 3 просрочки',c.danger,15);}
 return g;
}
if(v===1){
 sidebar();context(root,264,29);text(root,1180,44,212,23,'17 ноября 2026 · Вт',13,400,c.muted);
 const hero=box(root,264,124,1128,108,'03 · Morning overview');text(hero,0,0,790,54,'Доброе утро, Алексей.',38,500,c.text,'sans',-1.1);text(hero,0,68,700,26,'Сначала — сроки, назначения и ближайшие работы.',16,400,c.muted);
 text(hero,936,-2,80,62,'48',44,400,c.accent,'sans',-1.6);text(hero,936,62,192,42,'незавершённых\nработ на объекте',14,400,c.muted);
 input(root,264,264,1128,164,1);prompts(root,264,444,1);
 urgent(root,264,538,354,1);line(root,650,536,1,c.line,272);
 text(root,690,538,330,32,'Ближайшие задания',20,500);link(root,1202,532,190,'Открыть график · 6',c.muted,13);taskRows(root,690,582,702,76);
 line(root,264,804,354);text(root,264,823,50,39,'42',28,400,c.warning,'sans',-1);link(root,320,818,298,'Без исполнителя',c.warning,15);
 const acc=box(root,690,834,702,38,'08 · Acceptance queue');icon(acc,0,7,'check',16,c.accent);text(acc,30,3,386,25,'Приёмка · 0 новых отчётов',14,400,c.muted);link(acc,482,-7,220,'Открыть приёмку',c.muted,14);tags.acceptance=acc.id;
}
if(v===2){
 topnav(2);context(root,56,103,1328);text(root,1138,117,245,24,'Вторник, 17 ноября 2026',14,400,c.muted);
 const hero=box(root,56,171,1328,166,'03 · Editorial overview');text(hero,0,0,530,170,'Рабочий\nдень.',64,500,c.text,'narrow',-1.6);text(hero,554,12,170,24,'НА ОБЪЕКТЕ',12,500,c.faint,'sans',1.5);
 const data=[['03','Просрочены',c.danger],['42','Без исполнителя',c.warning],['06','Работ сегодня',c.accent]];
 data.forEach(([n,l,col],i)=>{const xx=554+i*260;text(hero,xx,45,175,86,n,64,500,col,'narrow',-2);text(hero,xx,135,218,25,l,15,400,c.muted);if(i<2)line(hero,xx+232,52,1,c.line,110);});
 input(root,56,361,1328,160,2);prompts(root,56,535,2);
 line(root,56,599,1328);text(root,56,618,430,34,'Ближайшие задания',26,500,c.text,'narrow',-.4);link(root,656,614,224,'Открыть график · 6',c.muted,14);taskRows(root,56,666,824,60);
 line(root,920,618,1,c.line,228);urgent(root,960,621,424,2);
 line(root,56,851,1328);text(root,56,866,540,22,'48 незавершённых работ · категории пересекаются',13,400,c.faint);link(root,670,855,320,'Приёмка · 0 новых отчётов',c.muted,14);link(root,1108,855,276,'Открыть планирование',c.accent,14);
}
if(v===3){
 topnav(3);context(root,64,105,1312);text(root,1152,117,232,23,'17 ноября 2026 · Вторник',14,400,c.muted);
 const hero=box(root,64,178,1312,158,'03 · Shared work context');text(hero,0,0,748,120,'С чего начнём\nрабочий день?',48,400,c.text,'sans',-1.5);text(hero,2,131,770,26,'48 незавершённых работ в ЖК «Сосновый парк»',15,400,c.muted);
 line(hero,870,4,2,c.line,147);text(hero,900,0,412,25,'СНАЧАЛА — СРОКИ И НАЗНАЧЕНИЯ',12,500,c.faint,'sans',.8);
 text(hero,900,39,66,55,'3',40,400,c.danger,'sans',-1);link(hero,960,39,338,'Работы просрочены',c.danger,15);
 text(hero,900,96,66,54,'42',36,400,c.warning,'sans',-1);link(hero,960,96,338,'Без исполнителя',c.warning,15);
 const ai=box(root,64,372,1312,226,'04 · Intelligence workspace',c.raised,24);tags.workspace=ai.id;
 const g=input(ai,0,0,1312,156,3);g.children.find(s=>s.type==='rectangle').remove();
 line(ai,28,155,1256,c.line);text(ai,28,178,166,24,'Можно начать с',13,400,c.muted);
 button(ai,200,169,264,'Разобрать просрочки',c.surface,c.accent,20);button(ai,480,169,250,'Проверить загрузку',c.surface,c.accent,20);button(ai,746,169,270,'Найти оборудование',c.surface,c.accent,20);
 const strip=box(root,64,620,1312,48,'06 · Priority context');dot(strip,0,19,6,c.danger);text(strip,19,10,430,26,'Проверка управляющего модуля',15,500);text(strip,462,11,400,24,'Срок — 16 ноября · На доработке',13,400,c.muted);link(strip,1010,1,302,'Разобрать очередь',c.danger,14);tags.urgent=strip.id;
 text(root,64,703,460,32,'Ближайшие задания',22,500,c.text,'sans',-.4);link(root,754,698,340,'Приёмка · 0 новых отчётов',c.muted,14);link(root,1140,698,236,'Открыть график · 6',c.muted,14);
 const ag=box(root,64,754,1312,96,'07 · Assignment horizon');tags.agenda=ag.id;line(ag,0,9,1312,c.line);
 tasks.forEach((a,i)=>{const xx=i*448;dot(ag,xx,6,7,a.color);text(ag,xx+20,-4,80,29,a.time,18,500,c.text);text(ag,xx,32,416,27,a.title,16,500);text(ag,xx,66,416,26,i===0?'Не назначен · Индивидуальный тепловой пункт':a.meta+' · '+a.status,13,400,i===0?c.warning:c.muted);});
 line(root,64,852,1312);link(root,64,856,340,'Оборудование и регламенты',c.muted,13);link(root,1120,856,256,'Открыть планирование',c.accent,13);
}
pg.setPluginData('E'+v,root.id);root.setPluginData('tags',JSON.stringify(tags));storage.eTags=storage.eTags||{};storage.eTags['E'+v]=tags;
penpot.selection=[root];penpot.viewport.zoomIntoView([root]);
return {pageId:pg.id,frameId:root.id,tags,nodes:penpotUtils.findShapes(s=>true,root).length,fontFamilies:[fonts.sans.name,fonts.narrow.name]};
