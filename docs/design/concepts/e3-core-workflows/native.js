// Execute as an async body through the official local Penpot MCP.
// Finish new isolated builds with finalize.js, polish.js, then full-polish.js.
// CORE_SCREEN: planning, equipment, review, executor, review-mobile,
// executor-mobile, proposal. CORE_REBUILD preserves the existing board ID.
if(penpot.currentFile.id!=='13ac3151-58c1-801c-8008-f58dd579cd50')throw Error('Use existing lightweight concepts file');
let pg=penpotUtils.getPageByName('E3 · Core Workflows');
if(!pg){pg=penpot.createPage();pg.name='E3 · Core Workflows';}await penpot.openPage(pg);
if(!storage.corePhotos&&pg.getPluginData('photo-assets'))storage.corePhotos=JSON.parse(pg.getPluginData('photo-assets'));
const key=CORE_SCREEN;
const positions={planning:[0,0],equipment:[1680,0],review:[0,1160],executor:[1680,1160],'review-mobile':[3360,1160],'executor-mobile':[3900,1160],proposal:[0,2320],'ai-context':[1680,2320]};
const names={planning:'01 · Планирование · Действующий календарь',equipment:'02 · Оборудование и регламенты',review:'03 · Приёмка · Главный инженер',executor:'04 · Исполнение · Проверить и сдать','review-mobile':'05 · Приёмка · Mobile','executor-mobile':'06 · Исполнение · Mobile',proposal:'07 · Планирование · Предложение → новая версия','ai-context':'08 · Единый AI-диалог · Контекст приёмки'};
if(!positions[key])throw Error('Unknown screen');
const mobile=key.endsWith('mobile'),W=mobile?390:1440,H=mobile?844:900;
const old=pg.getPluginData('core:'+key);
if(old&&typeof CORE_REBUILD==='undefined')return {existing:true,id:old};
if(old&&pg.getPluginData('controls-finalized')&&typeof CORE_REBUILD!=='undefined')throw Error('Finalized component masters: edit native instances or rebuild in an isolated copy');
const font=penpot.fonts.findByName('IBM Plex Sans');if(!font)throw Error('Installed IBM Plex Sans required');
const c={canvas:'#0C1D18',nav:'#091611',surface:'#142B22',raised:'#1D382D',line:'#304C3F',text:'#EDF1E7',muted:'#ACBDB0',faint:'#8FA697',accent:'#C6DEC0',ink:'#12291D',danger:'#E7AA99',warning:'#DEC08C',warnBg:'#302C1E',dangerBg:'#37271F',disabled:'#6E8678'};
const fills={};for(const [name,color] of Object.entries(c)){let a=penpot.library.local.colors.find(a=>['E · Visual Exploration','E3 · Core'].includes(a.path)&&a.name===name);if(!a){a=penpot.library.local.createColor();a.path='E3 · Core';a.name=name;a.color=color;}fills[color]=[a.asFill()];}
const typos={};for(const [size,weight] of [[40,400],[36,400],[28,400],[24,500],[22,500],[20,500],[18,500],[16,400],[16,500],[14,400],[14,500],[13,400],[12,500]]){const name=size+' / '+weight;let a=penpot.library.local.typographies.find(a=>a.path==='E3 · Type'&&a.name===name);if(!a){a=penpot.library.local.createTypography();a.path='E3 · Type';a.name=name;a.setFont(font,font.variants.find(v=>v.fontWeight===String(weight)));a.fontSize=String(size);a.lineHeight='1.25';a.letterSpacing='0';}typos[size+':'+weight]=a;}
const root=old?pg.getShapeById(old):penpot.createBoard();if(old)root.children.forEach(s=>s.remove());root.name=names[key]+' · '+W+'×'+H;root.resize(W,H);root.x=positions[key][0];root.y=positions[key][1];root.fills=fills[c.canvas];root.clipContent=true;root.setPluginData('core-screen',key);root.setPluginData('role',key.startsWith('executor')?'executor':'chief_engineer');
const tags={};
function put(s,p,x,y,w,h,name){s.name=name;s.resize(w,h);p.appendChild(s);s.x=p.x+x;s.y=p.y+y;return s;}
function b(p,x,y,w,h,name,fill=null,r=0){const s=put(penpot.createBoard(),p,x,y,w,h,name);s.fills=fill?fills[fill]||[{fillColor:fill,fillOpacity:1}]:[];s.borderRadius=r;s.clipContent=false;return s;}
function r(p,x,y,w,h,fill,radius=0,border=null,name='Surface'){const s=put(penpot.createRectangle(),p,x,y,w,h,name);s.fills=fill?fills[fill]||[{fillColor:fill,fillOpacity:1}]:[];s.borderRadius=radius;if(border)s.strokes=[{strokeColor:border,strokeWidth:1,strokeStyle:'solid',strokeAlignment:'inner'}];return s;}
function t(p,x,y,w,h,value,size=16,weight=400,color=c.text,spacing=0,align='left'){const s=penpot.createText(' ');const style=typos[size+':'+weight];if(style)style.applyToText(s);else font.applyToText(s,font.variants.find(v=>v.fontWeight===String(weight)));s.fontSize=String(size);s.lineHeight='1.25';s.letterSpacing=String(spacing);s.fills=fills[color]||[{fillColor:color,fillOpacity:1}];s.characters=value;s.align=align;s.growType='fixed';return put(s,p,x,y,w,h,value.replace(/\n/g,' / '));}
function line(p,x,y,w,col=c.line,h=1){return r(p,x,y,w,h,col,0,null,'Divider');}
function dot(p,x,y,d,col){const s=put(penpot.createEllipse(),p,x,y,d,d,'Status');s.fills=fills[col];return s;}
function path(p,x,y,w,h,commands,col=c.muted,stroke=1.5,name='Icon'){const s=penpot.createPath();s.commands=commands.map(a=>({command:{M:'move-to',L:'line-to',Z:'close-path'}[a[0]],params:a.length>1?{x:a[1],y:a[2]}:undefined}));s.fills=[];s.strokes=[{strokeColor:col,strokeWidth:stroke,strokeStyle:'solid',strokeAlignment:'center',strokeCapStart:'round',strokeCapEnd:'round'}];return put(s,p,x,y,w,h,name);}
const icons={arrow:[['M',3,12],['L',21,12],['M',15,6],['L',21,12],['L',15,18]],back:[['M',21,12],['L',3,12],['M',9,6],['L',3,12],['L',9,18]],down:[['M',5,8],['L',12,15],['L',19,8]],up:[['M',12,21],['L',12,3],['M',5,10],['L',12,3],['L',19,10]],ai:[['M',12,1],['L',15,9],['L',23,12],['L',15,15],['L',12,23],['L',9,15],['L',1,12],['L',9,9],['L',12,1]],check:[['M',3,12],['L',10,19],['L',22,4]],plus:[['M',3,12],['L',21,12],['M',12,3],['L',12,21]],menu:[['M',2,5],['L',22,5],['M',2,12],['L',22,12],['M',2,19],['L',22,19]],camera:[['M',2,7],['L',7,7],['L',9,3],['L',16,3],['L',18,7],['L',23,7],['L',23,21],['L',2,21],['L',2,7],['M',9,11],['L',16,11],['L',16,18],['L',9,18],['L',9,11]],file:[['M',4,2],['L',15,2],['L',21,8],['L',21,22],['L',4,22],['L',4,2],['M',14,2],['L',14,9],['L',21,9]],expand:[['M',3,9],['L',3,3],['L',9,3],['M',15,3],['L',21,3],['L',21,9],['M',21,15],['L',21,21],['L',15,21],['M',9,21],['L',3,21],['L',3,15]]};
function icon(p,x,y,name,size=18,col=c.muted){return path(p,x,y,size,size,icons[name],col,1.5,name);}
function wire(s,dest){s.setPluginData('destination',dest);tags['link:'+dest+':'+s.id]=s.id;return s;}
function link(p,x,y,w,label,dest=null,color=c.accent,size=14){const g=b(p,x,y,w,44,'Link / '+label);t(g,0,11,w-26,25,label,size,500,color);icon(g,w-18,16,'arrow',14,color);if(dest)wire(g,dest);return g;}
function btn(p,x,y,w,label,kind='secondary',dest=null){const g=b(p,x,y,w,44,'Button / '+label);g.setPluginData('control-kind',kind);const bg=kind==='primary'?c.accent:kind==='danger'?c.dangerBg:c.surface,col=kind==='primary'?c.ink:kind==='danger'?c.danger:kind==='disabled'?c.disabled:c.text;r(g,0,0,w,44,bg,10,kind==='secondary'?c.line:null);t(g,14,12,w-28,24,label,14,500,col,0,'center');if(dest&&kind!=='disabled')wire(g,dest);return g;}
function pill(p,x,y,w,label,color=c.accent){const g=b(p,x,y,w,28,'Status / '+label);r(g,0,0,w,28,c.surface,14);dot(g,11,11,5,color);t(g,24,5,w-30,20,label,12,500,color);return g;}
function ai(p,x,y,w=166,context='ТО-017'){const g=btn(p,x,y,w,'Спросить AI','secondary','ai-context');icon(g,12,14,'ai',16,c.accent);g.children.find(s=>s.type==='text').x=g.x+32;g.children.find(s=>s.type==='text').resize(w-42,24);g.setPluginData('context',context);return g;}
function mark(p,x,y,size=30){r(p,x,y,size,size,c.accent,7);path(p,x+8,y+7,size-16,size-14,[['M',2,18],['L',2,2],['L',16,2],['M',2,9],['L',12,9]],c.ink,2.3,'F');}
function nav(active,executor=false){const g=b(root,0,0,W,82,'01 · Global navigation');mark(g,48,26,30);t(g,91,27,180,32,'FixRate AI',22,500,c.text,-.6);const ns=executor?['Мои задания','Мой календарь','Оборудование','Мои смены']:['Рабочий день','Планирование ТО','Задания','Приёмка','Оборудование','Команда','Отчёты'];const ws=executor?[150,170,160,140]:[126,155,90,96,135,95,75];const destinations={'Рабочий день':'home','Оборудование':'equipment','Планирование ТО':'planning','Приёмка':'review','Мои задания':'executor','Задания':'tasks','Мой календарь':'executor-calendar','Мои смены':'personal-shifts','Команда':'workforce','Отчёты':'reports'};let xx=328;ns.forEach((n,i)=>{const s=t(g,xx,31,ws[i],25,n,14,n===active?500:400,n===active?c.text:c.muted);wire(s,destinations[n]);if(n===active)r(g,xx,79,ws[i]-25,2,c.accent);xx+=ws[i];});dot(g,1358,25,32,c.raised);t(g,1363,32,24,21,executor?'АМ':'АК',12,500,c.accent);line(g,48,81,1344);}
function context(executor=false){t(root,64,112,260,25,'ЖК «Сосновый парк»',16,500);icon(root,309,120,'down',10);line(root,348,117,1,c.line,20);t(root,368,114,210,23,executor?'Исполнитель':'Главный инженер',14,400,c.muted);t(root,1158,114,218,23,'17 ноября 2026 · Вторник',14,400,c.muted,0,'right');}
function header(title,sub,active,executor=false){nav(active,executor);context(executor);t(root,64,167,1090,56,title,36,400,c.text,-.8);t(root,64,230,1080,27,sub,14,400,c.muted);}
function tabs(p,x,y,entries,widths,current){const g=b(p,x,y,widths.reduce((a,b)=>a+b,0),44,'Local navigation');let xx=0;entries.forEach((e,i)=>{if(i===current)r(g,xx,0,widths[i]-8,38,c.surface,19);t(g,xx+14,10,widths[i]-28,25,e,14,i===current?500:400,i===current?c.text:c.muted);xx+=widths[i];});return g;}
function field(p,x,y,w,label,value,h=44,placeholder=false){const g=b(p,x,y,w,h+28,'Field / '+label);t(g,0,0,w,23,label,13,400,c.muted);r(g,0,28,w,h,c.nav,9,c.line);t(g,13,39,w-26,h-14,value,14,400,placeholder?c.faint:c.text);return g;}
function note(p,x,y,w,h,title,body,tone='neutral'){const g=b(p,x,y,w,h,title,tone==='warning'?c.warnBg:tone==='danger'?c.dangerBg:c.raised,14);t(g,18,14,w-36,26,title,14,500,tone==='warning'?c.warning:tone==='danger'?c.danger:c.accent);t(g,18,43,w-36,h-49,body,14,400,c.muted);return g;}
function photo(p,x,y,w,h,phase){const g=b(p,x,y,w,h,'Evidence / '+phase,c.surface,10);g.setPluginData('action','open-evidence-viewer');g.setPluginData('evidence-phase',phase);g.clipContent=true;if(storage.corePhotos?.[phase]){const s=r(g,0,0,w,h,null);s.fills=[{fillImage:{...storage.corePhotos[phase],keepAspectRatio:true},fillOpacity:1}];s.setPluginData('evidence-phase',phase);}else{icon(g,w/2-16,h/2-16,'camera',32,c.faint);}const z=b(g,w-44,h-44,44,44,'Open original / full photo hit target');r(z,7,7,30,30,c.nav,8);icon(z,15,15,'expand',14,c.text);return g;}
function mobileNav(role){const g=b(root,0,0,390,64,'01 · Mobile navigation',c.canvas);mark(g,20,18,26);t(g,57,19,186,29,'FixRate AI',20,500,c.text,-.4);const help=b(g,270,10,44,44,'Спросить AI о текущем задании');icon(help,12,12,'ai',20,c.accent);help.setPluginData('route','/assistant');help.setPluginData('context','ТО-017');const a=b(g,326,10,44,44,'Menu');icon(a,12,13,'menu',20);line(g,20,63,350);t(root,20,80,350,23,'ЖК «Сосновый парк» · '+role,13,400,c.muted);}
function mobileTitle(state){link(root,20,103,148,state==='review'?'К приёмке':'Мои задания',state==='review'?'review':'executor',c.muted,13);t(root,20,152,350,64,'Проверка температуры\nи давления',24,500,c.text,-.4);t(root,20,226,350,23,'ТО-017 · Манометр МН-01 · Попытка 1',13,400,c.muted);}

if(key==='planning'){
 header('Планирование ТО','Действующий календарь · Регламент задаёт обязательный срок','Планирование ТО');
 btn(root,1116,177,260,'Параметры и черновики','secondary','proposal');
 tabs(root,64,274,['Календарь','Матрица обязательств','Нагрузка и персонал'],[140,218,214],0);ai(root,1202,270,174,'Календарь · 16–22.11.2026');
 const cal=b(root,64,339,928,417,'03 · Weekly saved calendar');tags.calendar=cal.id;
 t(cal,0,0,340,32,'16 — 22 ноября',22,500);icon(cal,316,9,'back',15);icon(cal,354,9,'arrow',15);
 tabs(cal,596,-4,['Месяц','Неделя','Список'],[104,116,100],1);
 const table=b(cal,0,53,928,364,'Week / operations and obligations');r(table,364,0,94,364,c.surface,0);line(table,0,42,928);
 t(table,0,11,260,24,'Операция / оборудование',13,400,c.muted);
 ['ПН 16','ВТ 17','СР 18','ЧТ 19','ПТ 20','СБ 21','ВС 22'].forEach((d,i)=>t(table,270+i*94,10,94,26,d,13,i===1?500:400,i===1?c.accent:c.muted,0,'center'));
 const rows=[['1.1','Контроль параметров','Тепловой пункт'],['1.2','Показания счётчиков','Тепловой пункт'],['1.3','Управляющий модуль','Контроллер отопления'],['1.5','Температура и давление','Манометр МН-01']];
 rows.forEach((a,i)=>{const yy=43+i*80;t(table,0,yy+12,39,24,a[0],13,400,c.faint);t(table,46,yy+8,224,26,a[1],15,500);t(table,46,yy+36,220,25,a[2],13,400,c.muted);line(table,0,yy+79,928);
 for(let d=0;d<5;d++){if(i===3&&d!==1)continue;const selected=i===3&&d===1,over=i===2&&d===0;const xx=278+d*94;const cell=b(table,xx,yy+12,78,48,'Calendar / '+a[0]+' / '+(16+d));r(cell,0,0,78,48,over?c.dangerBg:selected?c.raised:c.surface,8,selected?c.accent:null);t(cell,8,5,62,21,d===0&&i<2?'Принято':over?'Просроч.':selected?'В работе':'По плану',12,500,over?c.danger:selected?c.accent:c.muted);t(cell,8,26,62,18,selected?'ТО-017':a[0],12,400,c.faint);if(selected)wire(cell,'task-detail');}
 });
 const pane=b(root,1032,339,344,417,'04 · Selected task',c.surface,18);t(pane,24,21,296,22,'ВЫБРАННАЯ РАБОТА',12,500,c.faint,1);t(pane,24,62,296,60,'Проверка температуры\nи давления',22,500);t(pane,24,137,296,25,'ТО-017 · Манометр МН-01',14,400,c.muted);line(pane,24,180,296);
 [['Обязательный срок','17 ноября'],['Выполнение по плану','17 ноября · 11:00–11:35'],['Исполнитель','Алексей Морозов']].forEach(([l,v],i)=>{t(pane,24,199+i*54,296,21,l,12,400,c.faint);t(pane,24,219+i*54,296,25,v,14,500);});link(pane,24,365,296,'Открыть наряд','executor');
 const load=b(root,64,794,1312,80,'05 · Daily load');t(load,0,0,260,27,'Нагрузка · 17 ноября',18,500);link(load,1092,-8,220,'Нагрузка и персонал','planning',c.muted);
 [['А. Морозов','6 / 8 ч',.75,c.accent],['М. Орлова','8 / 8 ч',1,c.accent],['И. Кузнецов','9 / 8 ч · дефицит 1 ч',1,c.warning]].forEach(([n,val,f,col],i)=>{const xx=i*448;t(load,xx,38,170,23,n,14,400,c.muted);t(load,xx+170,38,246,23,val,14,500,col,0,'right');r(load,xx,68,416,3,c.line,1);r(load,xx,68,416*f,3,col,1);});
 t(root,64,759,928,23,'4 из 6 операций · 24 работы · 6 выполнено · 3 просрочки · ещё 2 операции в списке',13,400,c.muted);
}
if(key==='equipment'){
 header('Манометр контура отопления','МН-01 · Контрольно-измерительные приборы · ИТП, корпус 1','Оборудование');pill(root,1206,183,170,'В эксплуатации');
 tabs(root,64,274,['Обслуживание','Паспорт','Принятая история','Детали и наработка'],[180,130,214,218],0);ai(root,1202,270,174,'Оборудование МН-01');
 const service=b(root,64,350,816,140,'03 · Next service');t(service,0,0,210,23,'БЛИЖАЙШЕЕ ОБСЛУЖИВАНИЕ',12,500,c.faint,.7);t(service,0,35,270,66,'17 ноября',40,400,c.text,-1);t(service,324,35,450,30,'Проверка температуры и давления',20,500);t(service,324,76,450,25,'ТО-017 · Алексей Морозов · В работе',14,400,c.muted);link(service,324,103,450,'Открыть задание','task-detail');
 line(root,64,514,816);t(root,64,539,700,31,'Регламентные операции',22,500);link(root,646,531,234,'Настроить регламенты',null,c.muted);
 const rules=b(root,64,594,816,188,'04 · Bound maintenance operations');
 t(rules,0,0,50,26,'1.1',14,500,c.faint);t(rules,64,0,520,28,'Контроль параметров показаний приборов',18,500);pill(rules,648,-2,168,'Утверждено');t(rules,64,36,730,24,'ТО1 · Ежемесячно · 1 чел. · 15 мин. · 0,250 чел.-ч',14,400,c.muted);line(rules,0,84,816);
 t(rules,0,105,50,26,'1.5',14,500,c.faint);t(rules,64,105,550,28,'Проверка приборов измерения',18,500);pill(rules,648,103,168,'Черновик',c.warning);t(rules,64,141,730,24,'Методика не подтверждена · новое планирование заблокировано',14,400,c.warning);
 const passport=b(root,944,350,432,440,'05 · Passport and history');
 t(passport,0,0,432,31,'Паспорт',22,500);[['Инвентарный номер','МН-01'],['Ввод в эксплуатацию','17 ноября 2023'],['Расположение','ИТП · корпус 1'],['Последнее принятое ТО','17 октября · 11:10']].forEach(([l,v],i)=>{t(passport,0,57+i*67,432,23,l,13,400,c.faint);t(passport,0,82+i*67,432,26,v,16,400);});line(passport,0,340,432);link(passport,0,353,432,'Принятая история · 3 события',null,c.muted);t(passport,0,398,432,44,'Последнее выполнено 17.10, 10:25.\nПринято 17.10, 11:10 · Мария Орлова.',13,400,c.muted);
 const contextAi=b(root,64,815,1312,62,'06 · AI context',c.raised,16);icon(contextAi,20,21,'ai',20,c.accent);t(contextAi,56,12,950,25,'AI-рекомендации не изменяют утверждённый регламент',16,400);t(contextAi,56,36,950,22,'Предложение → проверка инженером → отдельное подтверждение.',12,400,c.muted);link(contextAi,1050,9,238,'Обсудить оборудование','ai-context');
}
if(key==='review'){
 header('Проверка температуры и давления','ТО-017 · Манометр МН-01 · Попытка 1 · Срок 17 ноября','Приёмка');pill(root,1206,183,170,'На проверке',c.warning);
 tabs(root,64,274,['Фото и отчёт','Факты и документы','История попыток'],[176,236,202],0);ai(root,694,270,174,'Отчёт ТО-017 · попытка 1');
 t(root,64,332,804,25,'Алексей Морозов · Выполнено 17.11, 11:00–11:35 · Отправлено 12:05',14,400,c.muted);
 t(root,64,380,390,25,'01 / До · 11:02',14,500);t(root,478,380,390,25,'02 / После · 11:35',14,500);
 photo(root,64,418,390,260,'before');photo(root,478,418,390,260,'after');
 t(root,64,690,804,24,'Пункт 03 · Внешнее состояние прибора · одинаковый ракурс',13,400,c.muted);
 const a=note(root,64,734,804,88,'AI · Нужна ручная проверка','На фото изменилось положение стрелки. Точность прибора и скрытые операции по этим снимкам не подтверждены.','warning');tags.aiFinding=a.id;
 link(root,64,834,804,'Чек-лист 6/6 · Показания · Факт · Протокол и примечания','review-facts',c.muted);
 const d=b(root,928,332,448,545,'04 · Engineer decision',c.surface,20);tags.decision=d.id;t(d,24,23,400,30,'Решение главного инженера',22,500);
 t(d,24,71,400,26,'Чек-лист 6/6 · Фото 2/2',16,500,c.accent);t(d,24,109,400,48,'Протокол сравнения приложен,\nно ещё не проверен.',15,400,c.warning);link(d,24,164,400,'Открыть и проверить протокол','review-facts',c.warning);
 t(d,24,222,400,23,'Причина решения *',14,500);r(d,24,257,400,102,c.nav,10,c.line);t(d,38,271,372,76,'Нужен проверенный протокол\nсравнения с контрольным прибором.',16,400);
 t(d,24,378,400,44,'Приёмка недоступна, пока обязательный\nпротокол не проверен.',13,400,c.warning);
 btn(d,24,436,190,'Принять работу','disabled');btn(d,230,436,194,'Вернуть','danger','return-confirm');t(d,24,496,400,26,'Далее — подтверждение точного решения',13,400,c.muted);
}
if(key==='executor'){
 header('Проверка температуры и давления','ТО-017 · Манометр МН-01 · Попытка 1 · Срок 17 ноября','Мои задания',true);pill(root,1206,183,170,'В работе');
 const aside=b(root,64,284,288,490,'03 · Task and instruction');t(aside,0,0,288,30,'Инструкция и безопасность',20,500);note(aside,0,51,288,156,'Методика не приложена','Уточните порядок и безопасность у инженера. AI не заменяет утверждённую инструкцию.','warning');
 t(aside,0,239,288,23,'Обязательный срок',13,400,c.faint);t(aside,0,266,288,29,'17 ноября 2026',18,500);t(aside,0,320,288,23,'Исполнитель',13,400,c.faint);t(aside,0,345,288,29,'Алексей Морозов',16,500);link(aside,0,394,288,'Паспорт оборудования','equipment',c.muted);ai(aside,0,455,288,'Текущее задание ТО-017');
 const form=b(root,416,284,960,490,'04 · Report preparation');tabs(form,0,0,['1 · Чек-лист','2 · Фото','3 · Проверить и сдать'],[184,154,274],2);
 t(form,0,66,512,33,'Фактическое выполнение',22,500);field(form,0,113,162,'Начало · 17.11','11:00');field(form,180,113,162,'Окончание · 17.11','11:35');field(form,360,113,200,'Трудозатраты, чел.-ч','0,583');
 line(form,0,216,560);t(form,0,237,360,27,'Чек-лист заполнен · 6 из 6',18,500,c.accent);link(form,372,227,188,'Проверить ответы',null,c.muted);
 t(form,0,293,560,24,'Комментарий к работе',14,500);r(form,0,329,560,96,c.nav,10,c.line);t(form,14,343,532,67,'Показания внесены. Расходные материалы\nне использовались.',16,400);t(form,0,447,560,43,'Фотографии не подтверждают точность прибора.\nНужен скан протокола инструментальной проверки.',13,400,c.muted);
 const evidence=b(form,608,66,352,428,'Evidence readiness');t(evidence,0,0,352,30,'Фото и документы',22,500);photo(evidence,0,49,168,112,'before');r(evidence,184,49,168,112,c.surface,10,c.line);icon(evidence,258,75,'camera',20,c.accent);t(evidence,192,112,152,24,'Добавить «после»',13,500,c.accent,0,'center');t(evidence,0,174,352,24,'Пункт 03 · Общий вид · Фото 1/2',13,400,c.warning);
 link(evidence,0,214,352,'Открыть фотоотчёт','executor-mobile',c.accent);
 line(evidence,0,280,352);t(evidence,0,302,352,26,'Скан протокола не загружен',16,500,c.warning);btn(evidence,0,348,352,'Добавить скан · JPG / PNG / WebP','secondary');
 const footer=b(root,416,812,960,72,'05 · Save and submit');line(footer,0,0,960);t(footer,0,17,494,26,'Не готово: нет фото «после» и скана протокола',14,500,c.warning);t(footer,0,44,494,24,'Текущие ответы сохранены в 11:37',13,400,c.muted);btn(footer,522,19,176,'Сохранить','disabled');btn(footer,714,19,246,'Сдать работу','disabled');
}
if(key==='review-mobile'){
 mobileNav('Главный инженер');mobileTitle('review');pill(root,20,262,150,'На проверке',c.warning);t(root,188,266,182,23,'17.11 · 12:05',13,400,c.muted,0,'right');
 const checks=link(root,20,302,350,'Чек-лист 6/6 · Факт и документы','review-facts-mobile',c.muted);tags.facts=checks.id;
 t(root,20,358,168,23,'До · 11:02',13,500);t(root,204,358,166,23,'После · 11:35',13,500);photo(root,20,391,166,111,'before');photo(root,204,391,166,111,'after');
 t(root,20,513,350,23,'Пункт 03 · Общий вид · Нажмите для увеличения',12,400,c.muted);
 note(root,20,548,350,81,'AI · Нужна ручная проверка','Фото не подтверждают точность прибора.','warning');
 t(root,20,647,350,25,'Причина решения *',14,500);r(root,20,680,350,62,c.nav,10,c.line);t(root,32,690,326,47,'Нужен проверенный протокол\nсравнения с контрольным прибором.',14,400);
 const bar=b(root,0,750,390,94,'Decision / sticky',c.canvas);line(bar,20,0,350);t(bar,20,10,350,23,'Проверьте протокол перед приёмкой',12,400,c.warning);btn(bar,20,40,166,'Принять','disabled');btn(bar,204,40,166,'Вернуть','danger','return-confirm');
}
if(key==='executor-mobile'){
 mobileNav('Исполнитель');mobileTitle('executor');pill(root,20,262,132,'В работе');t(root,196,266,174,23,'Срок · 17 ноября',13,400,c.muted,0,'right');
 tabs(root,20,310,['1 · Чек-лист','2 · Фото','3 · Сдача'],[136,104,110],1);
 const instr=link(root,20,362,350,'Инструкция · методика не приложена',null,c.warning);instr.setPluginData('missing-methodology','true');
 t(root,20,422,350,23,'Привязка фотографии',14,500);r(root,20,455,350,44,c.nav,10,c.line);t(root,32,467,308,23,'Пункт 03 · Общий вид',14,400);icon(root,342,472,'down',12);
 t(root,20,521,166,23,'До · загружено',13,500,c.accent);t(root,204,521,166,23,'После · нет фото',13,500,c.warning);photo(root,20,554,166,111,'before');r(root,204,554,166,111,c.surface,10,c.line);icon(root,276,574,'camera',22,c.accent);btn(root,218,607,138,'Добавить','secondary');
 link(root,20,678,350,'Скан протокола · не загружен',null,c.warning);
 const bar=b(root,0,742,390,102,'Save / next step',c.canvas);line(bar,20,0,350);t(bar,20,12,350,23,'Сохранено 11:37 · Ответы 6/6 · Фото 1/2',13,400,c.muted);btn(bar,20,47,350,'Далее: проверить отчёт','primary','executor-finish');
}
if(key==='proposal'){
 header('Размещение работ в черновике','План СВиК · Версия 4 · 18–22 ноября 2026 · исходный календарь не изменён','Планирование ТО');link(root,1134,177,242,'Действующий календарь','planning',c.muted);
 tabs(root,64,274,['Состав работ','Даты и бригады','Нагрузка','Утверждение и выпуск'],[176,206,150,270],1);ai(root,1202,270,174,'Черновик СВиК · версия 4');
 const compare=b(root,64,344,784,136,'03 · Algorithm variants');t(compare,0,0,784,29,'Результаты расчёта',22,500);t(compare,0,48,350,28,'Базовый вариант',18,500);t(compare,410,48,374,28,'С балансировкой · CP-SAT',18,500,c.accent);t(compare,0,85,350,44,'22 / 24 работы · 11 из 12 чел.-ч\nПиковая нагрузка — 8 ч',14,400,c.muted);t(compare,410,85,374,44,'24 / 24 работы · 12 из 12 чел.-ч\nПиковая нагрузка — 6 ч',14,400,c.muted);
 line(root,64,511,784);t(root,64,536,784,29,'Размещения выбранного варианта',20,500);
 const rows=[['18 ноя · 09:00','Контроль параметров','А. Морозов'],['18 ноя · 10:00','Показания счётчиков','М. Орлова'],['19 ноя · 11:00','Проверка приборов','А. Морозов'],['20 ноя · 09:00','Контроль параметров','И. Кузнецов']];
 rows.forEach((a,i)=>{const y=590+i*58;t(root,64,y,162,27,a[0],14,500);t(root,240,y,350,27,a[1],16,400);t(root,620,y,228,27,a[2],14,400,c.muted,0,'right');line(root,64,y+41,784);});
 link(root,64,832,784,'Параметры: шаг 60 мин. · лимит 10 с · закреплённые назначения сохранены',null,c.muted,13);
 const p=b(root,912,344,464,533,'04 · Apply proposed version',c.surface,20);t(p,24,24,416,31,'Применить в новую версию',22,500);t(p,24,75,416,51,'Версия 4 → 5\nИзменятся 2 незакреплённых назначения',16,400);t(p,24,146,416,48,'Проверенные ограничения соблюдены.\nРасчёт не является публикацией.',14,400,c.accent);line(p,24,220,416);
 t(p,24,247,416,26,'Причина применения *',14,500);r(p,24,283,416,92,c.nav,10,c.line);t(p,38,297,388,65,'Распределить незакреплённые\nсегменты по доступным сменам.',16,400);btn(p,24,399,416,'Подтвердить новую версию','primary','apply-confirm');t(p,24,462,416,48,'Утверждение и выпуск заданий —\nотдельный следующий этап.',14,400,c.muted);
}
if(key==='ai-context'){
 header('Отчёт ТО-017','Единый диалог · Контекст: текущая отправленная попытка 1','Приёмка');
 link(root,1090,177,286,'Вернуться к приёмке','review',c.muted);
 const feed=b(root,64,284,1016,410,'03 · Conversation');
 const q=b(feed,172,0,844,66,'User message',c.surface,16);t(q,20,19,804,30,'Что ещё нужно для приёмки ТО-017?',18,400);
 icon(feed,0,105,'ai',22,c.accent);t(feed,36,102,400,29,'FixRate AI',18,500,c.accent);t(feed,36,143,950,64,'Для приёмки нужно проверить обязательный протокол\nсравнения с контрольным прибором.',22,500);
 t(feed,36,221,950,62,'Заполнено 6 обязательных ответов. Есть парные фото пункта 03.\nНа фото видно изменение положения стрелки, но это не подтверждает точность прибора.',16,400,c.muted);
 link(feed,36,307,944,'Открыть отчёт, проверить факты и документ','review-facts',c.accent,16);
 t(feed,36,367,950,30,'Приёмку выполняет инженер. Изменения без вашего подтверждения не применяются.',14,400,c.muted);
 const composer=b(root,64,736,1016,140,'04 · Chat composer',c.raised,20);t(composer,24,22,920,30,'Уточните задачу или прикрепите файл',20,400);icon(composer,24,94,'plus',18,c.accent);t(composer,54,90,150,25,'Файл или фото',14,400,c.muted);t(composer,260,90,240,25,'Выбрать модель',14,400,c.muted);r(composer,944,78,48,48,c.accent,24);icon(composer,960,93,'up',16,c.ink);
 line(root,1128,284,1,c.line,592);t(root,1160,291,216,30,'Диалоги',20,500);btn(root,1160,342,216,'Новый диалог','secondary');r(root,1148,418,228,70,c.surface,12);t(root,1164,432,196,25,'Приёмка ТО-017',16,500);t(root,1164,461,196,22,'Сегодня · 12:10',13,400,c.muted);
}
root.setPluginData('tags',JSON.stringify(tags));pg.setPluginData('core:'+key,root.id);penpot.selection=[root];penpot.viewport.zoomIntoView([root]);
return {key,id:root.id,pageId:pg.id,tags,descendants:penpotUtils.findShapes(s=>true,root).length,texts:penpotUtils.findShapes(s=>s.type==='text',root).length};
