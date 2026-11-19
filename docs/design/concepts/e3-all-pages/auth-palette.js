// Run the Penpot plugin script per page/batch with storage.authPaletteBatch.
const file = penpot.currentFile;
if (file.id !== "13ac3151-58c1-801c-8008-f58dd579cd50") throw Error("Unexpected design document");
const batch = storage.authPaletteBatch;
const page = file.pages.find(p => p.id === batch.pageId);
if (!page) throw Error("Unexpected page");
const access = file.pages.find(p => p.getPluginData("suite-section") === "Access");
const assistant = file.pages.find(p => p.getPluginData("suite-section") === "Assistant");
const login = access.root.children.find(r => r.getPluginData("suite-screen") === "login--desktop");
const logo = ["FixRate AI · знак","FixRate AI · логотип"].map(name => {
  const root = login.children.find(s => s.name === name);
  return {name, w:root.width, h:root.height, paths:penpotUtils.findShapes(s => s.type === "path",root).map(s => ({
    x:s.x-root.x,y:s.y-root.y,w:s.width,h:s.height,d:s.toD(),fills:s.fills,strokes:s.strokes,
  }))};
});
const palette = {
  "#0c1d18":"#050d12", "#142b22":"#0b171d", "#1d382d":"#142630", "#1c352b":"#10252e",
  "#091611":"#03090d", "#304c3f":"#30464e", "#355046":"#32474f", "#142820":"#0b171d",
  "#edf1e7":"#ecf3f3", "#acbdb0":"#91a5ab", "#c6dec0":"#74e4d4",
  "#8fa697":"#80959d", "#6e8678":"#81969d", "#12291d":"#062e2d", "#10251b":"#062e2d",
  "#1e2a26":"#0b171d", "#edf3ef":"#ecf3f3", "#a4b5ac":"#91a5ab", "#31413a":"#30464e",
  "#ade4ca":"#74e4d4", "#17211f":"#050d12", "#10251c":"#062e2d",
};
const buttonGradient = {type:"linear",startX:0,startY:0,endX:1,endY:1,width:1,
  stops:[{color:"#77e5d0",offset:0},{color:"#55d6d0",offset:1}]};
function replacement(value) {return value && palette[value.toLowerCase()];}
function recolor(shape) {
  const fs = shape.fills || [], ss = shape.strokes || [];
  const matched = fs.some(f => !f.fillImage && (replacement(f.fillColor) || f.fillColorGradient?.stops.some(s=>replacement(s.color))));
  if (matched) {
    shape.fills = fs.map(f => {
      if (f.fillImage) return f;
      const color = replacement(f.fillColor);
      if (!color && !f.fillColorGradient) return f;
      const primary = color === "#74e4d4" && shape.type === "rectangle" && shape.width>=75 && shape.height>=36 && shape.height<=64 && shape.borderRadius>=5;
      const gradient = primary ? buttonGradient : f.fillColorGradient && {...f.fillColorGradient,
        stops:f.fillColorGradient.stops.map(s=>({...s,color:replacement(s.color)||s.color}))};
      return {...f,fillColor:primary ? null : color||f.fillColor,fillColorGradient:gradient,
        fillColorRefId:null,fillColorRefFile:null};
    });
  }
  const matchedStroke = ss.some(s => replacement(s.strokeColor));
  if (matchedStroke) shape.strokes = ss.map(s => {
    const color = replacement(s.strokeColor);
    return color ? {...s,strokeColor:color,strokeColorRefId:null,strokeColorRefFile:null}:s;
  });
  return Number(matched)+Number(matchedStroke);
}
function path(parent,name,d,x,y,w,h,fills,strokes) {
  const shape = penpot.createPath();
  parent.appendChild(shape); shape.name=name; shape.d=d; shape.fills=fills;shape.strokes=strokes;
  shape.resize(w,h);shape.x=x;shape.y=y;
  return shape;
}
function brand(parent,x,cy,mobile) {
  const markW=mobile?30:34, wordW=mobile?109:132;
  for (const [i,part] of logo.entries()) {
    const scale=(i?wordW:markW)/part.w, x0=x+(i?markW+10:0), y0=cy-part.h*scale/2;
    const paths=part.paths.map(p=>path(parent,part.name,p.d,x0+p.x*scale,y0+p.y*scale,p.w*scale,p.h*scale,p.fills,p.strokes.map(s=>({...s,strokeWidth:s.strokeWidth*scale}))));
    penpot.group(paths).name=part.name;
  }
}
const bellD="M5 17.5h14l-1.2-1.7a4 4 0 0 1-.8-2.4V10a5 5 0 0 0-10 0v3.4a4 4 0 0 1-.8 2.4L5 17.5Z M10 20a2.2 2.2 0 0 0 4 0M12 3v2";
function outline(color,width) {
  return [{strokeColor:color,strokeWidth:width,strokeOpacity:1,strokeStyle:"solid",strokeAlignment:"center",strokeCapStart:"round",strokeCapEnd:"round"}];
}
function swapBell(shape) {
  const parent=shape.parent;
  const isButton=parent.name==="Уведомления";
  const cx=isButton?parent.x+parent.width/2:shape.x+shape.width/2;
  const cy=isButton?parent.y+parent.height/2:shape.y+shape.height/2;
  const size=20/24;
  shape.d=bellD;
  shape.fills=[];
  shape.strokes=outline("#ecf3f3",1.7*size);
  shape.resize(shape.width*size,shape.height*size);
  shape.x=cx-shape.width/2;
  shape.y=cy+(3-12)*size;
  shape.setPluginData("notification-glyph","react:Icon.bell/20");
}
function replaceLockup(mark,frame,removals) {
  const parent=mark.parent;
  const label=parent.children.find(s=>s.type==="text" && s.name==="FixRate AI" && Math.abs(s.y-mark.y)<14 && s.x>mark.x && s.x-mark.x<72);
  if (!label) return false;
  const tile=parent.children.find(s=>s.type==="rectangle" && s.x<=mark.x && s.y<=mark.y &&
    s.width>=28 && s.width<=35 && Math.abs(s.height-s.width)<1 && s.x+s.width>=mark.x+mark.width && s.y+s.height>=mark.y+mark.height);
  brand(parent,tile?.x??mark.x,tile?tile.y+tile.height/2:mark.y+mark.height/2,frame.width<=500);
  removals.push(mark,label); if(tile&&!tile.interactions.length) removals.push(tile);
  return true;
}
function connect(shape,dest) {
  for (const i of shape.interactions) shape.removeInteraction(i);
  const url="http://localhost:9001/?screen=viewer&file-id="+file.id+"&page-id="+assistant.id+"&section=interactions&frame-id="+dest.id;
  shape.addInteraction("click",{type:"open-url",url});
  shape.setPluginData("suite-destination","executor-assistant");
}

await penpot.openPage(page);
const block = penpot.history.undoBlockBegin();
try {
  const results=[];
  const frames = page.root.children.filter(r=>r.type==="board" && (!batch.frames||batch.frames.includes(r.id)));
  for (const frame of frames) {
    if(frame.getPluginData("auth-palette")==="2026-11-18")continue;
    const report={id:frame.id,name:frame.name,paints:0,brand:0,bells:0,executorLinks:0};
    const nodes=penpotUtils.findShapes(s=>true,frame);
    const removals=[];
    const key=frame.getPluginData("suite-screen")||"";
    const device=frame.width<=500?"mobile":"desktop";
    const isExecutor=frame.getPluginData("suite-role")==="executor"||/^executor-|home-executor|mobile-menu-executor|my-calendar|my-shifts|equipment-detail-executor/.test(key);
    const dest=assistant.root.children.find(r=>r.getPluginData("executor-assistant")==="start--"+device);
    for (const s of [frame,...nodes]) report.paints+=recolor(s);
    for (const s of nodes) {
      if(s.type==="path"&&["FixRate mark","F"].includes(s.name)&&replaceLockup(s,frame,removals))report.brand++;
      if(s.type==="path"&&/^(Notifications|bell|notification)$/i.test(s.name)&&!s.getPluginData("notification-glyph")){swapBell(s);report.bells++;}
      if(isExecutor && dest && s.getPluginData("suite-destination")==="assistant-new"&&
        !s.children?.some(k=>k.getPluginData("executor-assistant-hit"))){connect(s,dest);report.executorLinks++;}
    }
    for(const s of removals)s.remove();
    frame.setPluginData("auth-palette","2026-11-18");
    results.push(report);
  }
  return results;
}finally{penpot.history.undoBlockFinish(block);}
