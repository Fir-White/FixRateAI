// Copies the live chief engineer frames and adapts the copy to executor permissions.
const f=penpot.currentFile;
if(f.id!=="13ac3151-58c1-801c-8008-f58dd579cd50")throw Error("Unexpected design file");
const work=f.pages.find(p=>meta(p,"suite-section")==="Workspaces");
const app=f.pages.find(p=>meta(p,"suite-section")==="Assistant");
const shared=f.pages.find(p=>meta(p,"suite-section")==="Shared");
const executors=f.pages.find(p=>meta(p,"suite-section")==="Executor");
const core=f.pages.find(p=>p.name==="E3 · Core Workflows");
const find=(p,k)=>p.root.children.find(s=>meta(s,"suite-screen")===k);
const chat=(k,d)=>app.root.children.find(s=>meta(s,"executor-assistant")===k+"--"+d);
const begin=storage.cloneChiefStage;
const photo=penpotUtils.findShapes(s=>s.id==="582936bd-dbb0-8088-8008-f5a51bf3dd84",core.root)[0];
const font=penpot.fonts.findByName("IBM Plex Sans");
const all=r=>penpotUtils.findShapes(()=>true,r);
const clean=s=>{for(const i of [...s.interactions])s.removeInteraction(i);};
function invoke(s,page,dest,sourcePage){
  if(!s||!dest)return;
  clean(s);
  for(let ancestor=s;ancestor;ancestor=ancestor.parent)if(ancestor.id===dest.id)return;
  if(page.id===sourcePage.id)s.addInteraction("click",{type:"navigate-to",destination:dest,preserveScrollPosition:false});
  else s.addInteraction("click",{type:"open-url",url:"http://localhost:9001/?screen=viewer&file-id="+f.id+"&page-id="+page.id+"&section=interactions&frame-id="+dest.id});
}
function openPanel(s,dest){
  if(!s||!dest)return;
  clean(s);
  s.addInteraction("click",{type:"open-overlay",destination:dest,position:"center",addBackgroundOverlay:true,closeWhenClickOutside:true});
}
function detachCopiedComponents(shape){
  if(shape.isComponentHead?.()&&shape.isComponentCopyInstance?.())shape.detach();
  for(const child of shape.children||[])detachCopiedComponents(child);
}
function cloneInto(src,dst){
  const children=[...src.children].sort((a,b)=>a.parentIndex-b.parentIndex);
  for(const child of [...dst.children])child.remove();
  dst.resize(src.width,src.height);dst.fills=src.fills;dst.clipContent=src.clipContent;
  const copies=new Map();
  for(const s of children){
    const x=s.x-src.x,y=s.y-src.y,i=s.parentIndex,c=s.clone();
    dst.appendChild(c);c.x=dst.x+x;c.y=dst.y+y;
    copies.set(s.id,c);c.setParentIndex(i);
    detachCopiedComponents(c);
  }
  for(const s of all(dst))if(s.interactions?.length)clean(s);
  return copies;
}
function alter(s,copy,lines=1){
  if(!s)return;
  if(s.type==="text"){
    const parent=s.parent, x=s.x,y=s.y,index=s.parentIndex;
    const t=penpot.createText(copy);
    parent.appendChild(t);
    font.applyToText(t,font.variants.find(v=>v.fontWeight===s.fontWeight)||font.variants[0]);
    t.fills=s.fills;t.fontSize=s.fontSize||"14";t.lineHeight=s.lineHeight||"1.25";t.letterSpacing=s.letterSpacing||"0";
    t.align=s.align||"left";t.growType="fixed";t.name=copy.replaceAll("\n"," / ");
    const min=Math.ceil(Number(s.fontSize||14)*(lines*1.36+.3));
    t.resize(s.width,Math.max(s.height,min));t.x=x;t.y=y;
    s.remove();t.setParentIndex(index);
    return t;
  }else{
    const label=s.children?.find(c=>c.type==="text");
    if(label)alter(label,copy,lines);
    s.name=s.name.split(" / ")[0]+" / "+copy;
  }
  return s;
}
function adaptNav(r,d,page){
  const mobile=d==="mobile", nav=r.children.find(s=>s.name==="Global navigation");
  if(!nav)return;
  for(const t of all(r).filter(s=>s.type==="text")){
    if(t.characters.includes("Главный инженер"))alter(t,t.characters.replace("Главный инженер","Исполнитель"));
    if(t.characters==="АК")alter(t,"АМ");
  }
  const allowed={
    "Рабочий день":[work,find(work,"home-executor--"+d)],
    "Планирование ТО":[f.pages.find(p=>meta(p,"suite-section")==="Calendar"),null,"Мой календарь"],
    "Оборудование":[f.pages.find(p=>meta(p,"suite-section")==="Equipment"),null],
    "Задания":[f.pages.find(p=>meta(p,"suite-section")==="Shifts"),null,"Мои смены"],
  };
  const destNames={"Мой календарь":"my-calendar","Оборудование":"equipment-list","Мои смены":"my-shifts"};
  const tabOrder=["Рабочий день","Планирование ТО","Оборудование","Задания"];
  let x=316;
  for(const s of [...nav.children].filter(n=>/^Navigation \//.test(n.name)).sort((a,b)=>
    tabOrder.indexOf(a.name.split(" / ")[1])-tabOrder.indexOf(b.name.split(" / ")[1]))){
    const name=s.name.split(" / ")[1], target=allowed[name];
    if(!target){s.remove();continue;}
    const label=target[2]||name;
    if(target[2]){
      const labelShape=s.children.find(c=>c.type==="text");
      if(name==="Задания"&&labelShape){s.resize(106,s.height);labelShape.resize(88,labelShape.height);}
      alter(s,label);
    }
    s.x=r.x+x; x+=s.width+8;
    if(target[1]?.id!==r.id)invoke(s,target[0],target[1]||find(target[0],destNames[label]+"--"+d),page);
  }
  const agent=nav.children.find(s=>s.name==="ИИ-помощник");
  if(agent&&r.id!==chat("start",d).id)invoke(agent,app,chat("start",d),page);
  const notifications=nav.children.find(s=>s.name==="Уведомления");
  if(notifications)invoke(notifications,shared,find(shared,"notifications--"+d),page);
  const menu=nav.children.find(s=>s.name==="Открыть меню");
  if(mobile&&menu)invoke(menu,shared,find(shared,"mobile-menu-executor--mobile"),page);
  const profile=nav.children.find(s=>s.name==="Мой профиль");
  if(profile){
    const p=f.pages.find(p=>meta(p,"suite-section")==="Profile");
    invoke(profile,p,find(p,"profile--"+d),page);
  }
}
function mapped(src,dst,copies,pattern,label){
  const part=src.children.find(s=>typeof pattern==="string"?s.name===pattern:pattern.test(s.name));
  const shape=part&&copies.get(part.id);
  if(shape&&label)alter(shape,label,label.split("\n").length);
  return shape;
}
function installActions(r,d,page,mode){
  const isHome=page.id===work.id;
  const host=r.children.find(s=>s.name==="AI workspace"||s.name==="Chat composer");
  if(!host)return;
  const items=all(host);
  const pick=items.find(s=>s.name==="Выбрать модель"&&s.type!=="text");
  const send=items.find(s=>s.name==="Отправить сообщение"&&s.type!=="text");
  const file=items.find(s=>/Файл или фото|Прикрепить файл/.test(s.name)&&s.type!=="text");
  if(isHome){invoke(pick,app,chat("start",d),page);invoke(file,app,chat("draft",d),page);}
  else {openPanel(pick,chat("models",d));openPanel(file,chat("files",d));}
  if(send)invoke(send,app,chat(mode==="draft"?"attach":"instruction",d),page);
  if(isHome)invoke(host,app,chat("start",d),page);
  if(!file){
    const label=items.find(s=>s.type==="text"&&/Файл или фото/.test(s.characters));
    if(label){
      if(isHome)invoke(label,app,chat("draft",d),page);
      else openPanel(label,chat("files",d));
    }
  }
}
const prompts=[["Разобрать просрочки","Инструкция по ТО","instruction"],["Проверить загрузку","Прикрепить фото","draft"],["Найти оборудование","Оценить качество","quality"]];
function promptButtons(src,r,copies,d,page){
  const allCopies=[...copies.values()];
  for(const [old,label,state] of prompts){
    const match=src.children.find(s=>s.name==="Button / "+old);
    const node=(match&&copies.get(match.id))||allCopies.flatMap(s=>s.children||[]).find(s=>s.name==="Button / "+old||s.name==="Suggestion / "+old);
    if(!node)continue;
    alter(node,label);
    invoke(node,app,chat(state,d),page);
  }
}
function updateHome(r,d){
  const src=find(work,"home-chief--"+d),c=cloneInto(src,r);
  adaptNav(r,d,work);
  const mobile=d==="mobile";
  mapped(src,r,c,/^С чего начнём/,mobile?"С чего начнём\nрабочий день?":"С чего начнём\nрабочий день?");
  mapped(src,r,c,/^48 незавершённых/,"Ваши задания в ЖК «Сосновый парк»");
  mapped(src,r,c,"СРОКИ И НАЗНАЧЕНИЯ","МОИ ЗАДАНИЯ");
  const assigned=mapped(src,r,c,"3");
  if(!mobile&&assigned)assigned.fills=[{fillColor:"#74e4d4",fillOpacity:1}];
  const priority=mapped(src,r,c,"Priority context");
  if(priority){
    for(const t of all(priority).filter(s=>s.type==="text")){
      if(t.characters.includes("управляющего модуля"))alter(t,"Проверка температуры и давления");
      else if(t.characters.startsWith("Срок"))alter(t,"Фотоотчёт · 1 из 2 снимков");
      else if(t.characters.includes("Разобрать очередь"))alter(t,"Открыть фотоотчёт");
    }
    invoke(priority,executors,find(executors,"executor-photos--"+d),work);
  }
  mapped(src,r,c,"Link / Работы просрочены","Задания на сегодня");
  mapped(src,r,c,"42","1");
  mapped(src,r,c,"Link / Без исполнителя","На доработке");
  mapped(src,r,c,"48","3");
  if(mobile){
    const nums=src.children.filter(s=>s.type==="text"&&s.name==="3");
    for(const n of nums)alter(c.get(n.id),"1");
    mapped(src,r,c,"Незавершённых работ","Сегодня");
    mapped(src,r,c,"Просрочено","В работе");
    mapped(src,r,c,"Без исполнителя","На доработке");
    const row=mapped(src,r,c,/^Row \/ Отчёт ТО-017/);
    if(row){
      const labels=row.children.filter(s=>s.type==="text");
      for(const s of labels){
        if(s.characters==="На проверке")alter(s,"В работе");
        if(s.characters.includes("Фотографии"))alter(s,"Фотоотчёт · 1 из 2 снимков");
      }
    }
  }
  const attention=mapped(src,r,c,"Link / Приёмка · 2 новых отчёта","Открыть фотоотчёт");
  if(attention)invoke(attention,executors,find(executors,"executor-photos--"+d),work);
  const calendar=mapped(src,r,c,"Link / Открыть график","Мой календарь");
  if(calendar){
    const p=f.pages.find(p=>meta(p,"suite-section")==="Calendar");
    invoke(calendar,p,find(p,"my-calendar--"+d),work);
  }
  const settings=mapped(src,r,c,"Link / Открыть планирование","Мои смены");
  if(settings){
    const p=f.pages.find(p=>meta(p,"suite-section")==="Shifts");
    invoke(settings,p,find(p,"my-shifts--"+d),work);
  }
  for(const node of r.children.filter(s=>/Проверка температуры|Row \/ Отчёт ТО-017/.test(s.name)))
    invoke(node,executors,find(executors,"executor-assigned--"+d),work);
  for(const n of all(r).filter(s=>s.type==="text")){
    if(/^Не назначен/.test(n.characters))alter(n,"Назначено вам");
    if(n.characters.startsWith("AI помогает сопоставить факты."))alter(n,"Помощник сверит фотоотчёт.\nРаботу принимает инженер.",2);
  }
  promptButtons(src,r,c,d,work);
  installActions(r,d,work,"start");
  r.name="Рабочий день исполнителя · "+d;
}
const cases={
  instruction:["Показания счётчиков","Инструкция к заданию · 10:00","Как снять показания\nсчётчиков?","Снятие показаний","Сверьте номер прибора.\nЗапишите показание и единицу.\nПриложите фото шкалы.","К рабочему дню","home","10:00","10:01"],
  attach:["Фотоотчёт ТО-017","Манометр МН-01 · Попытка 1","Прикрепи к ТО-017,\nпункт 03, «после».","Подтвердите место для фото","Пункт 03 «Общий вид» · фото «после».\nФайл сохранится в черновике отчёта.","Прикрепить фото","attached","11:36","11:36"],
  attached:["Фотоотчёт ТО-017","Манометр МН-01 · Попытка 1","Прикрепи к ТО-017,\nпункт 03, «после».","Фото прикреплено","ТО-017 · Пункт 03 · Фото «после».\nСнимок сохранён в черновике отчёта.","Оценить качество","quality","11:36","11:37"],
  quality:["Фотоотчёт ТО-017","Манометр МН-01 · Попытка 1","Достаточно ли этого фото\nдля проверки ТО-017?","Снимок читается","Циферблат и стрелка видны.\nДля оценки точности нужен\nпротокол сравнения.","К рабочему дню","home","11:38","11:39"],
  cancel:["Фотоотчёт ТО-017","Манометр МН-01 · Попытка 1","Прикрепи к ТО-017,\nпункт 03, «после».","Фото осталось в диалоге","Прикрепление к заданию отменено.","Выбрать назначение","attach","11:36","11:37"],
};
function roleStarter(r,d,mode){
  const src=find(app,"assistant-new--"+d),copies=cloneInto(src,r);
  adaptNav(r,d,app);
  mapped(src,r,copies,"Один помощник для доступных задач вашей роли.","Инструкции, фото и вопросы по вашим заданиям.");
  const first=mapped(src,r,copies,"Row / Приёмка ТО-017","Фотоотчёт ТО-017");
  if(first){
    alter(first.children.find(s=>s.type==="text"&&s.characters.includes("Что ещё")),"Оценка снимка манометра");
    alter(first.children.find(s=>s.type==="text"&&s.characters.startsWith("17.11")),"17.11.2026 · 11:39");
    invoke(first,app,chat("quality",d),app);
  }
  const second=mapped(src,r,copies,"Row / Размещение работ","Показания счётчиков");
  if(second){
    alter(second.children.find(s=>s.type==="text"&&s.characters.includes("СВиК")),"Инструкция к заданию");
    alter(second.children.find(s=>s.type==="text"&&s.characters.startsWith("16.11")),"17.11.2026 · 10:01");
    invoke(second,app,chat("instruction",d),app);
  }
  if(mode==="draft"){
    mapped(src,r,copies,"С чего начнём?","Фото к заданию");
    const host=r.children.find(s=>s.name==="AI workspace");
    const prompt=all(host).find(s=>s.type==="text"&&s.characters.includes("Что нужно"));
    const copy=d==="mobile"?"ТО-017 · пункт 03\nФото «после»":"Прикрепи выбранное фото к ТО-017, пункт 03, «после».";
    alter(prompt,copy,copy.split("\n").length);
    if(photo){
      const img=penpot.createRectangle();host.appendChild(img);img.name="Фото «после»";
      img.resize(60,40);img.x=host.x+host.width-78;img.y=host.y+15;img.fills=photo.fills;img.borderRadius=6;
    }
  }
  promptButtons(src,r,copies,d,app);
  installActions(r,d,app,mode);
}
function roleConversation(r,d,key){
  const src=find(app,"assistant-chat--"+d),c=cloneInto(src,r),mobile=d==="mobile";
  adaptNav(r,d,app);
  const spec=cases[key];
  mapped(src,r,c,"Приёмка ТО-017",spec[0]);
  mapped(src,r,c,/^Единый диалог/,spec[1]);
  const message=mapped(src,r,c,"User message");
  const raw=message?.children.find(s=>s.type==="text"&&!s.characters.startsWith("17.11"));
  const mobileCopy=key==="quality"?"Подходит ли это фото\nдля ТО-017?":key==="instruction"?spec[2]:"Фото «после» к ТО-017,\nпункт 03.";
  const prompt=alter(raw,mobile?mobileCopy:spec[2].replaceAll("\n"," "),mobile?2:1);
  alter(message?.children.find(s=>s.type==="text"&&s.characters.startsWith("17.11")),"17.11.2026 · "+spec[7]);
  if(key!=="instruction"&&message&&photo){
    const img=penpot.createRectangle();message.appendChild(img);img.name="Фото «после»";
    img.resize(60,40);img.x=message.x+message.width-75;img.y=message.y+13;img.fills=photo.fills;img.borderRadius=7;
    if(prompt)prompt.resize(message.width-105,Math.max(prompt.height,mobile?70:prompt.height));
  }
  mapped(src,r,c,/^FixRate AI · 17/,"FixRate AI · 17.11.2026 · "+spec[8]);
  const head=mobile&&spec[3].length>24?spec[3].replace("для фото","\nдля фото"):spec[3];
  mapped(src,r,c,/^Для приёмки нужно/,head);
  mapped(src,r,c,/^Заполнено 6 обязательных/,mobile?spec[4]:spec[4].replaceAll("\n"," "));
  const button=mapped(src,r,c,"Button / Проверить факты и документ",spec[5]);
  if(spec[6]==="home")invoke(button,work,find(work,"home-executor--"+d),app);
  else invoke(button,app,chat(spec[6],d),app);
  const history=mapped(src,r,c,"Button / История диалогов",key==="attach"?"Отмена":null);
  if(key==="attach")invoke(history,app,chat("cancel",d),app);
  else openPanel(history,chat("history",d));
  installActions(r,d,app,"chat");
}
function rolePanel(r,d,key){
  const aliases={models:"model-picker",history:"chat-history"};
  const src=find(app,aliases[key]+"--"+d),copies=cloneInto(src,r);
  if(key==="models"){
    for(const s of r.children.filter(x=>/^Button \/ (Выбрать модель|Отмена|Закрыть)/.test(x.name)))
      s.addInteraction("click",{type:"close-overlay"});
    return;
  }
  const first=mapped(src,r,copies,"Row / Приёмка ТО-017","Фотоотчёт ТО-017");
  const second=mapped(src,r,copies,"Row / Размещение работ","Показания счётчиков");
  if(first){
    alter(first.children.find(s=>s.type==="text"&&s.characters.includes("приёмки")),"Оценка снимка манометра");
    invoke(first,app,chat("quality",d),app);
  }
  if(second){
    alter(second.children.find(s=>s.type==="text"&&s.characters.includes("СВиК")),"Инструкция к заданию");
    invoke(second,app,chat("instruction",d),app);
  }
  for(const s of r.children){
    if(s.name==="Button / Новый диалог")invoke(s,app,chat("start",d),app);
    if(/Button \/ Удалить/.test(s.name)){
      alter(s,"Закрыть");
      s.addInteraction("click",{type:"close-overlay"});
    }
  }
}
const results=[];
if(begin==="mobile-menu"){
  await penpot.openPage(shared);
  const r=find(shared,"mobile-menu-executor--mobile");
  const node=r.children.find(s=>["Row / Мои задания","Row / Рабочий день"].includes(s.name));
  if(node){alter(node,"Рабочий день");invoke(node,work,find(work,"home-executor--mobile"),shared);}
  return [];
}
const stage=begin==="home"?work:app;
await penpot.openPage(stage);
const undo=penpot.history.undoBlockBegin();
try{
  for(const d of ["desktop","mobile"]){
    const r=begin==="home"?find(work,"home-executor--"+d):chat(begin,d);
    if(!r||meta(r,"chief-interface-copy")==="2026-11-19r2")continue;
    if(begin==="home")updateHome(r,d);
    else if(begin==="start"||begin==="draft")roleStarter(r,d,begin);
    else if(begin==="models"||begin==="history")rolePanel(r,d,begin);
    else roleConversation(r,d,begin);
    r.setPluginData("chief-interface-copy","2026-11-19r2");
    results.push({id:r.id,device:d,stage:begin,w:r.width,h:r.height,pageId:stage.id});
  }
  return results;
}finally{penpot.history.undoBlockFinish(undo);}
