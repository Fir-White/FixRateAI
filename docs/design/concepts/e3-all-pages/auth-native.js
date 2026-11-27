// Build the existing React auth screens from measured browser geometry.
// Supply SCREEN, BACKGROUND (base64 WebP cropped to the artwork) and LOGOS (source SVGs).
const access = penpot.currentFile.pages.find(page => page.getPluginData('suite-section') === 'Access');
if (penpot.currentFile.id !== '13ac3151-58c1-801c-8008-f58dd579cd50' || !access) throw Error('Expected FixRate Concepts access page');
await penpot.openPage(access);
const key = SCREEN.key + '--' + SCREEN.device;
const target = access.root.children.find(board => board.getPluginData('suite-screen') === key);
if (!target) throw Error('Existing artboard missing: ' + key);
const existingDraft = access.root.children.find(board => board.getPluginData('auth-draft') === key);
if (existingDraft) return { key, draftId: existingDraft.id, targetId: target.id };

const font = penpot.fonts.findByName('Segoe UI') || penpot.fonts.findByName('IBM Plex Sans');
const data = Uint8Array.from(atob(BACKGROUND), character => character.charCodeAt(0));
const media = await penpot.uploadMediaData('FixRate AI · Aurora · ' + key, data, 'image/webp');
const history = penpot.history.undoBlockBegin();
let draft;
try {
  draft = penpot.createBoard();
  draft.name = 'Current app · ' + key;
  draft.setPluginData('auth-draft', key);
  draft.resize(SCREEN.width, SCREEN.height);
  draft.x = target.x + 2390;
  draft.y = target.y;
  draft.fills = [{fillColor:'#050D12',fillOpacity:1}];
  draft.clipContent = true;

  function place(shape, parent, box, name) {
    shape.name = name;
    parent.appendChild(shape);
    shape.resize(box.w, box.h);
    shape.x = draft.x + box.x;
    shape.y = draft.y + box.y;
    return shape;
  }
  function rgba(color) {
    const nums = color.match(/[\d.]+/g).map(Number);
    return {hex:'#' + nums.slice(0,3).map(n=>n.toString(16).padStart(2,'0')).join(''),opacity:nums[3] ?? 1};
  }
  function rectangle(box, name, color, radius = 0, border) {
    const shape = place(penpot.createRectangle(), draft, box, name);
    const fill = rgba(color);
    shape.fills = [{fillColor:fill.hex,fillOpacity:fill.opacity}];
    shape.borderRadius = radius;
    if (border) {
      const stroke = rgba(border);
      shape.strokes = [{strokeColor:stroke.hex,strokeOpacity:stroke.opacity,strokeWidth:1,strokeStyle:'solid',strokeAlignment:'inner'}];
    }
    return shape;
  }
  const artwork = place(penpot.createRectangle(), draft, SCREEN.artwork, 'Аврора · фон приложения');
  artwork.fills = [{fillImage:{...media,keepAspectRatio:true},fillOpacity:1}];
  if (SCREEN.device === 'desktop') {
    if (SCREEN.height > SCREEN.artwork.h) {
      rectangle({x:SCREEN.artwork.x,y:SCREEN.artwork.h,w:SCREEN.artwork.w,h:SCREEN.height-SCREEN.artwork.h},'Фон под «Авророй»','rgb(2,9,13)');
    }
    rectangle({x:459,y:0,w:1,h:SCREEN.height}, 'Граница панели', 'rgba(126,190,188,0.08)');
    if (SCREEN.heroLine.w > 0) rectangle(SCREEN.heroLine,'Линия подписи','rgb(112,221,211)');
  }
  const centers = [];
  function putText(item) {
    const color = rgba(item.color);
    const weight = Number(item.weight) >= 600 ? '600' : String(item.weight || 400);
    const shape = penpot.createText(item.text);
    font.applyToText(shape, font.variants.find(v=>v.fontWeight===weight) || font.variants[0]);
    shape.fontSize = String(item.size);
    shape.letterSpacing = String(item.spacing || 0);
    shape.lineHeight = '1.15';
    shape.growType = 'fixed';
    shape.align = item.center ? 'center' : 'left';
    shape.fills = [{fillColor:color.hex,fillOpacity:color.opacity}];
    const box = {...item,w:item.center ? item.w : Math.min(Math.max(item.w+20,item.w*1.12),SCREEN.width-item.x),h:Math.ceil(item.size*1.55)};
    place(shape,draft,box,item.text);
    centers.push({id:shape.id,y:item.y+item.h/2,x:item.center?item.x+item.w/2:null});
    return shape;
  }
  for (const item of SCREEN.images) {
    const svg = LOGOS[item.name];
    const [,,w,h] = svg.match(/viewBox="([^"]+)"/)[1].split(' ').map(Number);
    const withSize = svg.replace('<svg ','<svg width="'+w+'" height="'+h+'" ')
      .replace(/stroke-width="([\d.]+)"/g, (_, width) => 'stroke-width="'+Number(width)*item.w/w+'"');
    const group = penpot.createShapeFromSvg(withSize);
    if (!group) throw Error('Cannot render source logo');
    place(group,draft,item,item.name.endsWith('__mark')?'FixRate AI · знак':'FixRate AI · логотип');
  }
  for (const field of SCREEN.fields) {
    rectangle(field, field.id, field.bg, field.radius, field.border);
    if (field.placeholder) putText({text:field.placeholder,x:field.x+field.pad+1,y:field.y,w:field.w-2*field.pad,h:field.h,size:field.size,weight:400,color:field.color});
    if (field.icon) {
      const icon = field.icon;
      const group = penpot.createShapeFromSvg('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path fill="none" stroke="'+rgba(icon.color).hex+'" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" d="'+icon.path+'"/></svg>');
      place(group,draft,icon,'Показать пароль');
    }
  }
  if (SCREEN.button) {
    const button = rectangle(SCREEN.button, SCREEN.button.name, 'rgb(109,224,209)',9);
    button.fills = [{fillColorGradient:{type:'linear',startX:0,startY:0,endX:1,endY:1,width:1,stops:[{color:'#77E5D0',offset:0},{color:'#55D6D0',offset:1}]},fillOpacity:1}];
    button.setPluginData('auth-action','submit');
  }
  if (SCREEN.success) rectangle(SCREEN.success,'Подтверждение регистрации','rgba(116,228,212,0.07)',9,'rgba(116,228,212,0.35)');
  for (const item of SCREEN.texts) {
    if (item.text === SCREEN.button?.name) putText({...item,...SCREEN.button,text:item.text,center:true});
    else putText(item);
  }
  const link = place(penpot.createRectangle(),draft,{...SCREEN.link,y:SCREEN.link.y-(Math.max(44,SCREEN.link.h)-SCREEN.link.h)/2,h:Math.max(44,SCREEN.link.h)},SCREEN.link.name);
  link.fills=[{fillColor:'#050D12',fillOpacity:0}];
  link.setPluginData('auth-action','alternate');
  draft.setPluginData('auth-centers',JSON.stringify(centers));
  return {key,draftId:draft.id,targetId:target.id,editableTexts:centers.length,font:font.name};
} catch (error) {
  if (draft) draft.remove();
  throw error;
} finally {
  penpot.history.undoBlockFinish(history);
}
