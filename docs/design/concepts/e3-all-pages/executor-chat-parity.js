// Load the shared drawing helpers from executor-assistant.js before this script.
// Run once for each stage through storage.executorChatStage.
Object.assign(colors,{bg:"#050D12",panel:"#0B171D",composer:"#10252E",line:"#30464E",
  ink:"#ECF3F3",muted:"#91A5AB",mint:"#74E4D4",dark:"#062E2D"});
const phase = storage.executorChatStage;
const devices = ["desktop","mobile"];
const workday = device => find(work,"home-executor--"+device);
const at = (key,device) => chat.root.children.find(r=>r.getPluginData("executor-assistant")===key+"--"+device);
const extra = {draft:"Черновик сообщения",models:"Модель диалога",files:"Добавить вложение",history:"Диалоги исполнителя"};
const mainStates = ["start","instruction","attach","attached","quality","cancel","draft"];
const gradient = [{fillColorGradient:{type:"linear",startX:0,startY:0,endX:1,endY:1,width:1,stops:[
  {color:"#77E5D0",offset:0},{color:"#55D6D0",offset:1}
]},fillOpacity:1}];
function overlay(hit, destination) {
  hit.addInteraction("click",{type:"open-overlay",destination,position:"center",closeWhenClickOutside:true,addBackgroundOverlay:true});
}
function close(hit) {hit.addInteraction("click",{type:"close-overlay"});}
function activeButton(parent,label,x,y,w) {
  const hit=button(parent,label,x,y,w,true);
  parent.children.findLast(s=>s.name==="Button · "+label).fills=gradient;
  return hit;
}
function centeredOverlay(key, title, device, y) {
  const mobile=device==="mobile", r=penpot.createBoard(), modal=key!=="draft";
  r.name=title+" · исполнитель · "+device;
  r.resize(modal?(mobile?350:560):(mobile?390:1440),modal?(key==="files"?328:key==="models"?455:380):(mobile?844:900));
  r.x=mobile?1680:0;r.y=y;r.fills=fill(modal?colors.panel:colors.bg);r.clipContent=true;
  if(modal)r.borderRadius=18;
  r.setPluginData("executor-assistant",key+"--"+device);r.setPluginData("role","executor");
  return r;
}
function desktopHistory(r,key) {
  rect(r,"Разделитель списка диалогов",1044,105,1,742,colors.line);
  text(r,"Диалоги",1070,109,290,21,600);
  const newChat=activeButton(r,"Новый диалог",1070,154,306);
  if(key!=="start")go(newChat,at("start","desktop"));
  const entries=[["Фотоотчёт ТО-017","17.11.2026 · 11:39","quality"],["Показания счётчиков","17.11.2026 · 10:01","instruction"]];
  for(const [i,[title,time,dest]] of entries.entries()){
    const y=225+i*77;
    const selected=dest==="instruction"?key==="instruction":!["start","instruction"].includes(key);
    rect(r,"Диалог · "+title,1070,y,306,66,selected?"#142A32":colors.bg,10,selected);
    text(r,title,1084,y+9,276,15,600,selected?colors.mint:colors.ink);
    text(r,time,1084,y+35,276,12,400,colors.muted);
    if(key!==dest)go(target(r,title,1070,y,306,66),at(dest,"desktop"));
  }
}
function historyTrigger(r,key,mobile) {
  if(mobile)overlay(button(r,"Диалоги",270,9,100),at("history","mobile"));
  else desktopHistory(r,key);
}
function editor(r,x,y,w,mobile,device,{draft=false,home=false,intro=false}={}) {
  const h=draft?(mobile?200:174):(mobile?111:118);
  rect(r,"Поле сообщения",x,y,w,h,colors.composer,16,true);
  if(draft){
    thumbnail(r,x+14,y+14,66,44);
    text(r,"МН-01 · фото «после»",x+92,y+18,w-110,15,500);
    text(r,"Снимок в личном диалоге",x+92,y+41,w-110,12,400,colors.muted);
  }
  text(r,draft?(mobile?"Прикрепи к ТО-017,\nпункт 03, «после».":"Прикрепи к ТО-017, пункт 03, фото «после»."):
    intro||home?"Чем помочь с работой?":"Сообщение помощнику",x+17,y+(draft?77:14),w-34,mobile?16:19,400,draft?colors.ink:colors.muted);
  const by=y+h-55, modelX=x+(mobile?143:174), modelW=mobile?126:151;
  glyph(r,"plus",x+22,by+22);
  text(r,"Файл или фото",x+36,by+13,100,13,500,colors.mint);
  const attach=target(r,"Файл или фото",x+6,by,mobile?130:154,44);
  text(r,"Qwen 3.5 9B",modelX+5,by+13,modelW-29,13,500,colors.muted);
  path(r,"Стрелка выбора модели","M2 3 L6 7 L10 3",modelX+modelW-19,by+20,8,4,colors.muted,1.2);
  const model=target(r,"Модель диалога",modelX,by,modelW,44);
  rect(r,"Отправить",x+w-54,by,44,44,draft?colors.mint:"#32474F",22).fills=draft?gradient:fill("#32474F");
  glyph(r,"send",x+w-32,by+22,draft?colors.dark:colors.muted);
  if(draft)go(target(r,"Отправить сообщение",x+w-54,by,44,44),at("attach",device));
  if(home){
    const launch=target(r,"Написать помощнику",x+8,y+6,w-16,44);
    jump(launch,chat,at("start",device));jump(model,chat,at("start",device));
    jump(attach,chat,at("draft",device));
  }else{
    overlay(attach,at("files",device));
    overlay(model,at("models",device));
  }
}
function addSuggestions(r,x,y,w,mobile,device,home) {
  const items=[["Инструкция по ТО","instruction"],["Прикрепить фото","draft"],["Оценить качество","quality"]];
  const cell=mobile?w:(w-24)/3;
  for(const [i,[label,key]] of items.entries()){
    const hit=button(r,label,x+(mobile?0:i*(cell+12)),y+(mobile?54*i:0),cell,false,true);
    if(home)jump(hit,chat,at(key,device));
    else if(key==="draft")overlay(hit,at("files",device));
    else go(hit,at(key,device));
  }
}
function navHeader(r,mobile,device){
  brand(r,mobile?20:48,mobile?32:41,mobile);
  rect(r,"Линия шапки",mobile?20:48,mobile?63:81,mobile?350:1344,1,colors.line);
  if(!mobile)text(r,"ЖК «Сосновый парк» · Исполнитель",1044,31,332,14,400,colors.muted,"right");
  const x=mobile?20:64,y=mobile?89:107;
  glyph(r,"back",x+8,y+10);
  text(r,"Рабочий день",x+23,y,136,14,500,colors.mint);
  jump(target(r,"Рабочий день",x,y-10,156,44),work,workday(device));
}
function updateChat(r,key,device) {
  const mobile=device==="mobile", x=mobile?20:160, w=mobile?350:860;
  if(key==="start"){
    for(const s of [...r.children])if(s.y-r.y>=158)s.remove();
    icon(r,x+w/2-19,mobile?172:219,38);
    text(r,"Помощник исполнителя",x,mobile?232:274,w,mobile?29:47,500,colors.ink,"center");
    text(r,"Ваши задания, инструкции и фотоотчёты",x,mobile?283:345,w,mobile?14:16,400,colors.muted,"center");
    editor(r,x,mobile?334:404,w,mobile,device,{intro:true});
    addSuggestions(r,x,mobile?465:548,w,mobile,device,false);
  }else if(key==="draft"){
    navHeader(r,mobile,device);
    text(r,"Фотоотчёт ТО-017",x,mobile?131:154,w,mobile?29:36,500);
    text(r,"Проверка температуры и давления",x,mobile?175:206,w,14,400,colors.muted);
    editor(r,x,mobile?622:655,w,mobile,device,{draft:true});
  }else{
    const limit=mobile?750:777;
    for(const s of [...r.children])if(s.y-r.y>=limit||(!mobile&&s.x-r.x>=1040&&s.y-r.y>=222))s.remove();
    const title=r.children.find(s=>s.type==="text"&&Math.abs(s.y-r.y-(mobile?130:154))<1);
    if(title){
      title.characters=key==="instruction"?"Показания счётчиков":"Фотоотчёт ТО-017";
      title.name=title.characters;
    }
    if(key==="instruction"){
      const context=r.children.find(s=>s.type==="text"&&s!==title&&s.characters==="Показания счётчиков");
      if(context){
        context.characters="Инструкция к заданию · 10:00";
        context.name=context.characters;
        context.resize(context.width,Math.max(context.height,27));
      }
    }
    editor(r,x,mobile?711:748,w,mobile,device);
  }
  const back=r.children.filter(s=>s.name==="Мои задания"&&s.y-r.y<130);
  for(const s of back){s.name="Рабочий день";if(s.type==="text")s.characters=s.name;}
  historyTrigger(r,key,mobile);
}
function overlayBody(r,key,device) {
  const mobile=device==="mobile", x=20,w=r.width-40;
  const title={models:"Модель диалога",files:"Добавить вложение",history:"Диалоги"}[key];
  text(r,title,x,18,w-55,23,600);
  close(button(r,"Закрыть",r.width-117,11,97));
  if(key==="models"){
    rect(r,"Поле поиска",x,72,w,46,colors.bg,10,true);
    text(r,"Название модели или провайдер",x+12,85,w-24,14,400,colors.muted);
    for(const [i,[label,caption]] of [["Qwen 3.5 9B","AI Tunnel · выбрана"],["Qwen 3 8B","Ollama · доступна"]].entries()){
      rect(r,label,x,137+i*70,w,56,i===0?"#142A32":colors.panel,10,true);
      text(r,label,x+12,143+i*70,w-24,16,600,i===0?colors.mint:colors.ink);
      text(r,caption,x+12,169+i*70,w-24,13,400,colors.muted);
      if(i===0){glyph(r,"check",r.width-42,165);}
    }
    text(r,mobile?"Модель сохраняется для вашей\nроли и объекта.":"Модель сохраняется для вашей роли и объекта.",x,289,w,14,400,colors.muted);
    close(activeButton(r,"Готово",x,383,w));
  }else if(key==="files"){
    text(r,"Фото из камеры или галереи",x,76,w,15,400,colors.muted);
    go(button(r,"Камера",x,115,w,false,true),at("draft",device));
    go(button(r,"Галерея или файл",x,173,w,false,true),at("draft",device));
    text(r,mobile?"Вложение появится в черновике\nсообщения.":"Вложение появится в черновике сообщения.",x,247,w,14,400,colors.muted);
  }else{
    go(activeButton(r,"Новый диалог",x,73,w),at("start",device));
    for(const [i,[label,time,dest]] of [["Фотоотчёт ТО-017","17.11.2026 · 11:39","quality"],["Показания счётчиков","17.11.2026 · 10:01","instruction"]].entries()){
      const y=142+i*76;
      rect(r,label,x,y,w,64,colors.bg,10,true);
      text(r,label,x+13,y+9,w-26,16,600);
      text(r,time,x+13,y+35,w-26,12,400,colors.muted);
      go(target(r,label,x,y,w,64),at(dest,device));
    }
  }
}
function updateWorkday(r,device){
  const mobile=device==="mobile",x=mobile?20:64,w=r.width-2*x,y=mobile?322:390;
  const cutoff=mobile?427:503, delta=mobile?242:140;
  const old=r.children.filter(s=>s.y-r.y>=y-.1&&s.y-r.y+s.height<=y+80+.1);
  for(const s of old)s.remove();
  for(const s of r.children)if(s.y-r.y>=cutoff-.1)s.y+=delta;
  r.resize(r.width,r.height+delta);
  const oldName=r.name;
  r.name="Рабочий день исполнителя · "+device;
  const caption=work.root.children.find(s=>s.type==="text"&&s.characters===oldName&&Math.abs(s.x-r.x)<2&&r.y-s.y<70&&s.y<r.y);
  if(caption){caption.characters=r.name;caption.name=r.name;}
  for(const s of penpotUtils.findShapes(s=>s.type==="text"&&s.characters==="Мои задания"||s.name==="Navigation / Мои задания",r)){
    if(s.type==="text"){s.characters="Рабочий день";s.name=s.characters;}else s.name="Navigation / Рабочий день";
  }
  text(r,"ИИ-помощник",x,y+5,w,20,600,colors.mint);
  editor(r,x,y+46,w,mobile,device,{home:true});
  addSuggestions(r,x,y+(mobile?169:181),w,mobile,device,true);
}

await penpot.openPage(phase==="workday"?work:chat);
const block = penpot.history.undoBlockBegin();
try {
  const result=[];
  if(phase==="prepare"){
    const max=Math.ceil(Math.max(...chat.root.children.filter(r=>r.type==="board").map(r=>r.y+r.height)))+240;
    for(const [i,[key,title]] of Object.entries(extra).entries())for(const device of devices){
      if(!at(key,device)){const r=centeredOverlay(key,title,device,max+i*1080);result.push({key:key+"--"+device,id:r.id});}
    }
  }else{
    for(const device of devices){
      const r=phase==="workday"?workday(device):at(phase,device);
      if(!r||r.getPluginData("executor-parity"))continue;
      if(phase==="workday") updateWorkday(r,device);
      else if(mainStates.includes(phase))updateChat(r,phase,device);
      else if(extra[phase])overlayBody(r,phase,device);
      else throw Error("Unknown executor stage");
      r.setPluginData("executor-parity","2026-11-18");
      result.push({key:phase+"--"+device,id:r.id,pageId:phase==="workday"?work.id:chat.id,w:r.width,h:r.height,n:r.children.length});
    }
  }
  return result;
}finally{penpot.history.undoBlockFinish(block);}
