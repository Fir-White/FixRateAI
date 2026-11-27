// Shared native support states. CORE_HELPERS is supplied from native.js.
if(penpot.currentFile.id!=='13ac3151-58c1-801c-8008-f58dd579cd50')throw Error('Concept file required');
const pg=penpotUtils.getPageByName('E3 · Core Workflows');await penpot.openPage(pg);
const sizes={'review-facts':[900,760,0,3480],'review-facts-mobile':[350,680,1040,3480],'return-confirm':[350,350,1550,3480],'apply-confirm':[350,374,2050,3480],'executor-finish':[350,680,2550,3480],'verify-document-mobile':[350,492,3100,3480]};
const key=SUPPORT_STATE,[W,H,xx,yy]=sizes[key];
const prior=pg.getPluginData('support:'+key);if(prior&&typeof CORE_REBUILD==='undefined')return {existing:true,id:prior};
const font=penpot.fonts.findByName('IBM Plex Sans'),typos={};
for(const a of penpot.library.local.typographies.filter(a=>a.path==='E3 · Type'))typos[a.fontSize+':'+a.fontWeight]=a;
const c={canvas:'#0C1D18',nav:'#091611',surface:'#142B22',raised:'#1D382D',line:'#304C3F',text:'#EDF1E7',muted:'#ACBDB0',faint:'#8FA697',accent:'#C6DEC0',ink:'#12291D',danger:'#E7AA99',warning:'#DEC08C',warnBg:'#302C1E',dangerBg:'#37271F',disabled:'#6E8678'};
const fills={};for(const [name,col] of Object.entries(c)){const a=penpot.library.local.colors.find(a=>['E · Visual Exploration','E3 · Core'].includes(a.path)&&a.name===name);fills[col]=a?[a.asFill()]:[{fillColor:col,fillOpacity:1}];}
const root=prior?pg.getShapeById(prior):penpot.createBoard();if(prior)root.children.forEach(s=>s.remove());root.name='90 · '+key;root.resize(W,H);root.x=xx;root.y=yy;root.fills=fills[c.surface];root.borderRadius=20;root.clipContent=true;root.setPluginData('support-state',key);const tags={};
/* CORE_HELPERS */
const answers=[['01 · Идентификатор прибора','МН-01'],['02 · Стекло и корпус','Осмотрены · без замечаний'],['03 · Внешнее состояние','Фотографии до/после · 2/2'],['04 · Контрольный прибор','КП-04'],['05 · Результат сверки','Расхождение 0,1 бар · допуск не задан'],['06 · Номер протокола','ПР-017'],['07 · Замечания · необязательно','Расходники не использовались']];
if(key==='review-facts'){
 t(root,24,22,852,38,'Факты и документы · ТО-017',28,400,c.text,-.5);t(root,24,73,852,25,'Попытка 1 · 6 обязательных ответов · данные исполнителя',14,400,c.muted);
 answers.forEach(([label,value],i)=>{const y=123+i*49;t(root,24,y,444,24,label,14,400,c.muted);t(root,484,y,392,24,value,14,500);line(root,24,y+35,852);});
 t(root,24,488,852,25,'Выполнено 17.11, 11:00–11:35 · 0,583 чел.-ч · Отправлено 12:05',14,400,c.muted);
 t(root,24,535,852,29,'Протокол сравнения с контрольным прибором',20,500);link(root,24,575,520,'Открыть скан · ПР-017.jpg',null,c.accent);pill(root,654,578,222,'Не проверен',c.warning);
 field(root,24,639,550,'Основание проверки документа *','Опишите результат проверки',44,true);btn(root,598,667,278,'Подтвердить проверку','disabled');
}
if(key==='review-facts-mobile'){
 t(root,20,20,310,38,'Факт и документы',24,500);t(root,20,64,310,25,'ТО-017 · Попытка 1 · Чек-лист 6/6',13,400,c.muted);
 answers.forEach(([label,value],i)=>{const y=111+i*52;t(root,20,y,310,20,label,12,400,c.faint);t(root,20,y+22,310,25,value,13,500);});
 t(root,20,492,310,43,'Факт: 11:00–11:35 · 0,583 чел.-ч\nОтправлено 17.11, 12:05',13,400,c.muted);line(root,20,550,310);
 link(root,20,561,310,'Протокол ПР-017 · не проверен','verify-document-mobile',c.warning);t(root,20,615,310,42,'Проверка документа требует отдельного\nоснования и подтверждения.',13,400,c.muted);
}
if(key==='return-confirm'){
 t(root,24,20,302,38,'Вернуть ТО-017?',24,500);t(root,24,67,302,25,'Попытка 1 · Алексей Морозов',13,400,c.muted);line(root,24,107,302);t(root,24,128,302,72,'Нужен проверенный протокол\nсравнения с контрольным\nприбором.',16,400);t(root,24,216,302,43,'Текущая попытка сохранится.\nИсполнитель начнёт новую отдельно.',14,400,c.muted);btn(root,24,282,126,'Отмена','secondary','close');btn(root,166,282,160,'Подтвердить','danger','close');
}
if(key==='apply-confirm'){
 t(root,24,20,302,63,'Сохранить новую\nверсию плана?',24,500);t(root,24,104,302,48,'Версия 4 → 5\n2 незакреплённых назначения',16,500);t(root,24,170,302,69,'Распределить незакреплённые\nсегменты по доступным сменам.',14,400,c.muted);t(root,24,251,302,42,'Утверждение и выпуск заданий\nвыполняются отдельно.',13,400,c.muted);btn(root,24,310,126,'Отмена','secondary','close');btn(root,166,310,160,'Подтвердить','primary','close');
}
if(key==='executor-finish'){
 t(root,20,20,310,37,'Проверить и сдать',24,500);t(root,20,68,310,25,'ТО-017 · Чек-лист 6/6 · Фото 1/2',13,400,c.warning);
 field(root,20,116,146,'Начало · 17.11','11:00');field(root,184,116,146,'Окончание · 17.11','11:35');field(root,20,211,310,'Фактические трудозатраты, чел.-ч','0,583');
 t(root,20,312,310,24,'Комментарий к работе',14,500);r(root,20,350,310,79,c.nav,10,c.line);t(root,32,362,286,54,'Показания внесены.\nРасходники не использовались.',14,400);
 btn(root,20,456,310,'Добавить скан протокола','secondary');t(root,20,520,310,44,'Не готово: добавьте фото «после»\nи скан обязательного протокола.',14,400,c.warning);
 btn(root,20,603,146,'К фотографиям','secondary','executor-mobile');btn(root,182,603,148,'Сдать работу','disabled');
}
if(key==='verify-document-mobile'){
 t(root,20,20,250,62,'Проверить\nпротокол',24,500);t(root,20,101,310,25,'ПР-017.jpg · ТО-017 · Попытка 1',13,400,c.muted);
 link(root,20,144,310,'Открыть скан документа',null,c.accent);
 t(root,20,206,310,47,'Проверьте документ отдельно.\nФотографии не заменяют протокол.',14,400,c.muted);
 t(root,20,276,310,25,'Основание проверки *',14,500);r(root,20,311,310,76,c.nav,12,c.line);t(root,32,323,286,50,'Опишите, что проверено',14,400,c.faint);
 btn(root,20,408,310,'Подтвердить проверку','disabled');
}
if(!['return-confirm','apply-confirm'].includes(key)){const close=b(root,W-62,14,44,44,'Закрыть');t(close,0,3,44,35,'×',24,400,c.muted,0,'center');wire(close,'close');}
root.setPluginData('tags',JSON.stringify(tags));pg.setPluginData('support:'+key,root.id);return {key,id:root.id,width:W,height:H};
