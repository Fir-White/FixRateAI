// Replace selected auth boards in place, preserving frame IDs and links from other pages.
const p=penpot.currentFile.pages.find(p=>p.getPluginData('suite-section')==='Access');
if(penpot.currentFile.id!=='13ac3151-58c1-801c-8008-f58dd579cd50'||!p)throw Error('Expected FixRate Concepts access page');
await penpot.openPage(p);
const keys=typeof REPLACE_KEYS==='undefined'?['login','register','registration-pending']:REPLACE_KEYS;
const drafts=p.root.children.filter(r=>keys.some(key=>r.getPluginData('auth-draft')?.startsWith(key+'--')));
const targets = new Map(p.root.children.map(r=>[r.getPluginData('suite-screen'),r]));
if(drafts.length!==keys.length*2||drafts.some(r=>!targets.has(r.getPluginData('auth-draft'))))throw Error('Both desktop and mobile drafts are required for each selected screen');
const undo=penpot.history.undoBlockBegin();
try{
  const results=[];
  for(const draft of drafts){
    const key=draft.getPluginData('auth-draft'),r=targets.get(key);
    const suffix=key.endsWith('--mobile')?'--mobile':'--desktop';
    const screen=key.slice(0,-suffix.length);
    const title={login:'Вход в систему',register:'Регистрация','registration-pending':'Заявка отправлена',setup:'Первоначальная настройка'}[screen];
    const coordinates=draft.children.map(child=>({id:child.id,x:child.x-draft.x,y:child.y-draft.y}));
    for(const child of [...r.children])child.remove();
    r.resize(draft.width,draft.height);
    r.name=title+' · '+suffix.slice(2);
    r.fills=draft.fills;
    r.setPluginData('auth-source','Current application · AuthLayout');
    const centers=JSON.parse(draft.getPluginData('auth-centers')).map(e=>({id:e.id,cy:r.y+e.y,cx:e.x===null?undefined:r.x+e.x}));
    r.setPluginData('centering',JSON.stringify(centers));
    r.setPluginData('content-start',suffix==='--mobile'?'96':'114');
    for(const position of coordinates){
      const shape=p.getShapeById(position.id);
      r.appendChild(shape);
      shape.x=r.x+position.x;
      shape.y=r.y+position.y;
    }
    const alternate=r.children.find(s=>s.getPluginData('auth-action')==='alternate');
    const alternateKey=key.startsWith('login')?'register':'login';
    alternate.setPluginData('suite-destination',alternateKey);
    alternate.addInteraction('click',{type:'navigate-to',destination:targets.get(alternateKey+suffix),preserveScrollPosition:false});
    if(screen==='register'||screen==='setup'){
      const destination=screen==='register'?'registration-pending':'login';
      const button=r.children.find(s=>s.getPluginData('auth-action')==='submit');
      const hit=penpot.createRectangle();
      r.appendChild(hit);hit.name=button.name;hit.resize(button.width,button.height);hit.x=button.x;hit.y=button.y;
      hit.fills=[{fillColor:'#050D12',fillOpacity:0}];
      hit.setPluginData('suite-destination',destination);
      hit.addInteraction('click',{type:'navigate-to',destination:targets.get(destination+suffix),preserveScrollPosition:false});
    }
    results.push({key,id:r.id,name:r.name,width:r.width,height:r.height});
    draft.remove();
  }
  const positions=JSON.parse(p.getPluginData('positions')||'{}');
  for(const key of keys) {
    const a=targets.get(key+'--desktop'),b=targets.get(key+'--mobile');
    positions[key]={y:a.y,maxH:Math.max(a.height,b.height)};
  }
  p.setPluginData('positions',JSON.stringify(positions));
  return results;
}finally{penpot.history.undoBlockFinish(undo);}
