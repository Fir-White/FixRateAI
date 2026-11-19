// Align the shared auth shell while keeping all existing forms and prototype targets.
const file=penpot.currentFile;
const page=file.pages.find(p=>p.getPluginData('suite-section')==='Access');
if(file.id!=='13ac3151-58c1-801c-8008-f58dd579cd50'||!page)throw Error('Expected FixRate Concepts access page');
await penpot.openPage(page);
const screens=['login','register','registration-pending','setup'];
const artworkName='Аврора · фон приложения',dividerName='Граница панели',tailName='Фон под «Авророй»';
const find=(key,device)=>page.root.children.find(r=>r.getPluginData('suite-screen')===key+'--'+device);
const helpNames=new Set(['Не получается войти?','Нужна помощь с регистрацией?','Нужна помощь с настройкой?']);
const titles={login:'Вход в систему',register:'Регистрация','registration-pending':'Регистрация',setup:'Первоначальная настройка'};
const result=[];
const undo=penpot.history.undoBlockBegin();
try{
 for(const device of ['desktop','mobile']){
  const mobile=device==='mobile',height=mobile?844:900;
  const left=mobile?24:52,panel=mobile?390:460,fieldW=mobile?342:355;
  const reference=find('login',device),children=reference.children;
  const bgFill=children.find(s=>s.name===artworkName).fills;
  const shell=children.filter(s=>s.name.startsWith('FixRate AI ·')||!mobile&&s.x-reference.x>=460&&s.name!==artworkName)
    .map(s=>({name:s.name,x:s.x-reference.x,y:s.y-reference.y}));
  const dividerFill=mobile?null:children.find(s=>s.name===dividerName).fills;
  for(const screen of screens){
   const headingY=screen==='login'?(mobile?220:240):screen==='registration-pending'?(mobile?282:315):(mobile?97:115);
   const r=find(screen,device),original=[...r.children];
   const title=original.find(s=>s.type==='text'&&s.fontSize==='28'&&s.characters===(screen==='setup'&&mobile?'Первоначальная':titles[screen]));
   const help=original.find(s=>s.type==='text'&&helpNames.has(s.characters));
   if(!title||!help)throw Error('Missing form heading or footer '+screen+' '+device);
   const formDelta=headingY-(title.y-r.y),helpStart=help.y;
   const footer=original.filter(s=>s.type==='text'&&s.x-r.x<panel&&s.y>=helpStart-.1).sort((a,b)=>a.y-b.y);
   const form=original.filter(s=>s.x-r.x<panel&&!footer.includes(s)&&!s.name.startsWith('FixRate AI ·')&&![artworkName,dividerName,tailName].includes(s.name));
   const formY=new Map(form.map(s=>[s.id,s.y-r.y+formDelta]));
   const formBottom=Math.max(...form.map(s=>formY.get(s.id)+s.height));
   const footerY=Math.ceil(Math.max(height-97,formBottom+24));
   const finalH=footerY+97;
   r.resize(r.width,finalH);

   for(const d of shell){
    const s=original.find(s=>s.name===d.name);
    if(!s)throw Error('Missing shared shell layer '+d.name);
    if(screen==='setup'&&s.type==='text'&&d.x>=460){
     const copy=children.find(t=>t.name===d.name).clone();
     r.appendChild(copy);copy.x=r.x+d.x;copy.y=r.y+d.y;
     s.remove();
    }else{s.x=r.x+d.x;s.y=r.y+d.y;}
   }
   for(const s of form)s.y=r.y+formY.get(s.id);
   for(const s of form.filter(s=>s.type==='text'&&s.x-r.x>=left+15&&s.x-r.x<=left+18&&s.width>fieldW-16)){
    const matching=form.find(field=>field.type==='rectangle'&&field.name.startsWith('login-')&&s.y>=field.y&&s.y<field.y+field.height)
      || form.find(field=>field.type==='rectangle'&&/^(register|setup)-/.test(field.name)&&s.y>=field.y&&s.y<field.y+field.height);
    if(matching)s.resize(fieldW-68,s.height);
   }
   footer.forEach((s,index)=>{s.y=r.y+footerY+[0,26,46][index];});
   const bg=original.find(s=>s.name===artworkName);
   bg.resize(mobile?390:980,height);bg.x=r.x+(mobile?0:460);bg.y=r.y;bg.fills=bgFill;
   const divider=original.find(s=>s.name===dividerName);
   if(divider){divider.resize(1,finalH);divider.x=r.x+459;divider.y=r.y;divider.fills=dividerFill;}
   let tail=original.find(s=>s.name===tailName);
   if(!mobile&&finalH>height){
    if(!tail){tail=penpot.createRectangle();r.appendChild(tail);tail.name=tailName;}
    tail.resize(980,finalH-height);tail.x=r.x+460;tail.y=r.y+height;
    tail.fills=[{fillColor:'#02090D',fillOpacity:1}];
   }else if(tail)tail.remove();

   const centers=JSON.parse(r.getPluginData('centering')||'[]');
   for(const e of centers){if(formY.has(e.id)&&e.cy!==undefined)e.cy+=formDelta;}
   r.setPluginData('centering',JSON.stringify(centers));
   r.setPluginData('content-start',String(headingY));
   r.setPluginData('auth-shell','shared-aurora-v1');
   result.push({key:screen+'--'+device,id:r.id,pageId:page.id,bodyOffset:formDelta,height:finalH,helpY:footerY});
  }
 }
 const positions=JSON.parse(page.getPluginData('positions')||'{}');
 for(const screen of screens){
  const a=find(screen,'desktop'),b=find(screen,'mobile');
  positions[screen]={y:a.y,maxH:Math.max(a.height,b.height)};
 }
 page.setPluginData('positions',JSON.stringify(positions));
 return result;
}finally{penpot.history.undoBlockFinish(undo);}
