// Author the 404 and 403 splash screens on the existing Access page.
const f=penpot.currentFile;
const access=f.pages.find(p=>p.getPluginData('suite-section')==='Access');
if(f.id!=='13ac3151-58c1-801c-8008-f58dd579cd50'||!access)throw Error('Expected FixRate Concepts');
await penpot.openPage(access);
const font=penpot.fonts.findByName('IBM Plex Sans');
const screens={
 'not-found':{code:'404',title:'Страница не найдена',description:['Проверьте адрес или вернитесь','в рабочее пространство.'],cta:'На главную',destination:'home-chief',route:'/'},
 'access-denied':{code:'403',title:'Раздел недоступен',description:['У вашей роли нет доступа к этому разделу.','Если он нужен для работы, обратитесь','к администратору.'],cta:'К моим заданиям',destination:'home-executor',route:'/executor'}
};
const ink='#ECF3F3',muted='#91A5AB',canvas='#050D12',accent='#70DDD3';
const fill=(color,opacity=1)=>[{fillColor:color,fillOpacity:opacity}];
const backgroundFill=[{fillOpacity:1,fillColorGradient:{type:'linear',startX:.5,startY:0,endX:.5,endY:1,width:1,stops:[
 {color:canvas,offset:0},{color:'#0B171D',offset:.46},{color:canvas,offset:1}
]}}];
const byKey=(page,key)=>page.root.children.find(r=>r.getPluginData('suite-screen')===key);
const place=(s,r,name,x,y,w,h)=>{
 s.name=name;r.appendChild(s);s.resize(w,h);s.x=r.x+x;s.y=r.y+y;return s;
};
const history=penpot.history.undoBlockBegin(),result=[];
try{
 for(const [key,spec] of Object.entries(screens))for(const device of ['desktop','mobile']){
  const mobile=device==='mobile',r=byKey(access,key+'--'+device),login=byKey(access,'login--'+device),W=r.width,H=r.height,mid=W/2;
  for(const s of [...r.children])s.remove();
  r.fills=fill(canvas);r.setPluginData('error-splash',spec.code);
  const background=place(penpot.createRectangle(),r,'Фон · градиент',0,0,W,H);
  background.fills=backgroundFill;
  const mark=login.children.find(s=>s.name==='FixRate AI · знак');
  const brand=login.children.find(s=>s.name==='FixRate AI · логотип');
  const brandW=mark.width+12+brand.width,brandX=mid-brandW/2,brandY=mobile?216:246;
  for(const [s,dx,dy] of [[mark,0,0],[brand,mark.width+12,(mark.height-brand.height)/2]]){
   const copy=s.clone();r.appendChild(copy);copy.name=s.name;copy.x=r.x+brandX+dx;copy.y=r.y+brandY+dy;
  }
  const centers=[];
  function label(value,cy,size,weight,color,letterSpacing=0,w=mobile?350:680){
   const t=penpot.createText(value);
   font.applyToText(t,font.variants.find(v=>v.fontWeight===String(weight))||font.variants[0]);
   t.fontSize=String(size);t.letterSpacing=String(letterSpacing);t.lineHeight='1.15';t.align='center';t.growType='fixed';t.fills=fill(color);
   const height=Math.ceil(size*1.45);place(t,r,value,mid-w/2,cy-height/2,w,height);
   centers.push({id:t.id,cx:r.x+mid,cy:r.y+cy});return t;
  }
  label(spec.code,mobile?336:375,mobile?104:132,500,accent,mobile?-6:-8);
  label(spec.title,mobile?426:480,mobile?25:32,500,ink,-.35);
  const descY=mobile?475:535,descSize=mobile?14:15;
  const lines=mobile?spec.description:(key==='not-found'?['Проверьте адрес или вернитесь в рабочее пространство.']:['У вашей роли нет доступа к этому разделу.','Если он нужен для работы, обратитесь к администратору.']);
  lines.forEach((line,i)=>label(line,descY+i*23,descSize,400,muted));
  const bottom=descY+(lines.length-1)*23;
  function link(labelText,y,width,destination,route){
   const h=48,b=place(penpot.createRectangle(),r,'Button / '+labelText,mid-width/2,y,width,h);
   const loginButton=login.children.find(s=>s.type==='rectangle'&&s.name==='Войти');
   b.borderRadius=11;b.fills=loginButton.fills;
   label(labelText,y+h/2,14,600,'#062E2D',0,width);
   const target=place(penpot.createRectangle(),r,labelText,mid-width/2,y,width,h);
   target.fills=fill(canvas,0);
   const destPage=f.pages.find(p=>p.getPluginData('suite-section')==='Workspaces');
   const targetFrame=byKey(destPage,destination+'--'+device);
   if(!targetFrame)throw Error('Missing existing prototype destination '+destination);
   target.setPluginData('suite-destination',destination);
   target.setPluginData('route-reference',route);
   target.setPluginData('design-reference',JSON.stringify({pageId:destPage.id,frameId:targetFrame.id,key:destination+'--'+device}));
   target.addInteraction('click',{type:'open-url',url:'http://localhost:9001/?screen=viewer&file-id='+f.id+'&page-id='+destPage.id+'&section=interactions&frame-id='+targetFrame.id});
  }
  link(spec.cta,bottom+35,key==='not-found'?156:186,spec.destination,spec.route);
  r.setPluginData('centering',JSON.stringify(centers));
  result.push({key:key+'--'+device,id:r.id,pageId:access.id});
 }
 return result;
}finally{penpot.history.undoBlockFinish(history);}
