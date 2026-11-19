// Run in the Penpot plugin with storage.executorAssistantStage set in order
// to prepare, start, instruction, attach, attached, quality, cancel, workday.
const file = penpot.currentFile;
if (file.id !== "13ac3151-58c1-801c-8008-f58dd579cd50") throw Error("Unexpected design file");
const section = name => file.pages.find(page => page.getPluginData("suite-section") === name);
const access = section("Access"), work = section("Workspaces"), chat = section("Assistant");
const find = (page, key) => page.root.children.find(frame => frame.getPluginData("suite-screen") === key);
const login = find(access, "login--desktop");
const logoNames = ["FixRate AI · знак", "FixRate AI · логотип"];
const logo = logoNames.map(name => {
  const root = login.children.find(shape => shape.name === name);
  return {
    name, w: root.width, h: root.height,
    paths: penpotUtils.findShapes(shape => shape.type === "path", root).map(shape => ({
      x: shape.x - root.x, y: shape.y - root.y, w: shape.width, h: shape.height,
      d: shape.toD(), fills: shape.fills, strokes: shape.strokes,
    })),
  };
});
const core = file.pages.find(page => page.name === "E3 · Core Workflows");
const photo = penpotUtils.findShapes(shape => shape.id === "582936bd-dbb0-8088-8008-f5a51bf3dd84", core.root)[0];
if (!photo?.fills[0]?.fillImage || logo.some(part => !part.paths.length)) throw Error("Existing brand or photo unavailable");
const colors = {
  bg: "#0C1D18", panel: "#142B22", composer: "#1C352B", line: "#304C3F",
  ink: "#EDF1E7", muted: "#ACBDB0", mint: "#C6DEC0", dark: "#10251B", amber: "#F1CEA0",
};
const font = penpot.fonts.findByName("IBM Plex Sans");
const fill = (color, opacity = 1) => [{fillColor: color, fillOpacity: opacity}];
function place(shape, parent, name, x, y, w, h) {
  parent.appendChild(shape); shape.name = name; shape.resize(w, h);
  shape.x = parent.x + x; shape.y = parent.y + y;
  return shape;
}
function rect(parent, name, x, y, w, h, color, radius = 0, outline = false) {
  const shape = place(penpot.createRectangle(), parent, name, x, y, w, h);
  shape.fills = fill(color); shape.borderRadius = radius;
  if (outline) shape.strokes = [{strokeColor: colors.line, strokeWidth: 1, strokeOpacity: 1, strokeStyle: "solid", strokeAlignment: "inner"}];
  return shape;
}
function text(parent, value, x, y, w, size = 15, weight = 400, color = colors.ink, align = "left") {
  const shape = penpot.createText(value);
  font.applyToText(shape, font.variants.find(v => v.fontWeight === String(weight)) || font.variants[0]);
  shape.fontSize = String(size); shape.lineHeight = "1.25";
  shape.fills = fill(color); shape.align = align; shape.growType = "fixed";
  return place(shape, parent, value.replaceAll("\n", " / "), x, y, w,
    Math.ceil(size * (1.3 * value.split("\n").length + .2)));
}
function path(parent, name, d, x, y, w, h, color, stroke = 0) {
  const shape = penpot.createPath();
  shape.d = d; shape.fills = stroke ? [] : fill(color);
  if (stroke) shape.strokes = [{strokeColor: color, strokeWidth: stroke, strokeOpacity: 1, strokeStyle: "solid", strokeAlignment: "center", strokeCapStart: "round", strokeCapEnd: "round"}];
  return place(shape, parent, name, x, y, w, h);
}
function icon(parent, x, y, size = 24, color = colors.mint) {
  const p = size / 24;
  path(parent, "Assistant · speech bubble", "M2 11 C2 5 6 3 12 3 C18 3 22 6 22 11 C22 16 18 19 12 19 L8 19 L3 22 L4 17 C3 15 2 13 2 11 Z", x+2*p, y+3*p, 20*p, 19*p, color, 1.5*p);
  path(parent, "Assistant · glint", "M12 6 C12.5 9 13.5 10 17 11 C13.5 12 12.5 13 12 16 C11.5 13 10.5 12 7 11 C10.5 10 11.5 9 12 6 Z", x+7*p, y+6*p, 10*p, 10*p, color);
}
const glyphs = {
  forward: ["M4 8 L16 8 M11 3 L16 8 L11 13", 12, 10],
  back: ["M16 8 L4 8 M9 3 L4 8 L9 13", 12, 10],
  send: ["M8 16 L8 2 M2 8 L8 2 L14 8", 12, 14],
  plus: ["M8 2 L8 14 M2 8 L14 8", 12, 12],
  check: ["M2 8 L6 12 L15 3", 13, 9],
};
function glyph(parent, name, x, y, color = colors.mint) {
  const [d, w, h] = glyphs[name];
  return path(parent, name, d, x - w/2, y - h/2, w, h, color, 1.5);
}
function brand(parent, x, cy, mobile) {
  const markW = mobile ? 30 : 34, nameW = mobile ? 109 : 132;
  for (const [index, part] of logo.entries()) {
    const scale = (index ? nameW : markW) / part.w;
    const originX = x + (index ? markW + 10 : 0), originY = cy - part.h * scale / 2;
    const shapes = part.paths.map(p => {
      const shape = path(parent, "FixRate AI", p.d, originX + p.x * scale, originY + p.y * scale, p.w * scale, p.h * scale, colors.ink);
      shape.fills = p.fills;
      shape.strokes = p.strokes.map(s => ({...s, strokeWidth: s.strokeWidth * scale}));
      return shape;
    });
    const group = penpot.group(shapes);
    group.name = part.name;
  }
}
function target(parent, name, x, y, w, h) {
  const hit = rect(parent, name, x, y, w, h, colors.bg);
  hit.fills = fill(colors.bg, 0);
  hit.setPluginData("executor-assistant-hit", name);
  return hit;
}
const urls = (page, frame) => "http://localhost:9001/?screen=viewer&file-id="+file.id+"&page-id="+page.id+"&section=interactions&frame-id="+frame.id;
const jump = (hit, page, frame) => hit.addInteraction("click", {type:"open-url", url:urls(page, frame)});
const go = (hit, frame) => hit.addInteraction("click", {type:"navigate-to", destination:frame, preserveScrollPosition:false});
function button(parent, label, x, y, w, primary = false, arrow = false) {
  rect(parent, "Button · " + label, x, y, w, 46, primary ? colors.mint : colors.panel, 10, !primary);
  text(parent, label, x+10, y+13, w-(arrow ? 37 : 20), 14, 600, primary ? colors.dark : colors.ink, arrow ? "left" : "center");
  if (arrow) glyph(parent, "forward", x+w-21, y+23);
  return target(parent, label, x, y, w, 46);
}
function thumbnail(parent, x, y, w, h) {
  const shape = rect(parent, "Манометр МН-01 · фото после", x, y, w, h, colors.panel, 8);
  shape.fills = photo.fills; return shape;
}

const states = [
  ["start","Помощник исполнителя"], ["instruction","Инструкция по ТО"],
  ["attach","Фото к заданию"], ["attached","Фото прикреплено"], ["quality","Визуальная оценка"],
  ["cancel","Фото осталось в диалоге"],
];
const devices = ["desktop", "mobile"];
const stage = storage.executorAssistantStage || "prepare";
const homes = Object.fromEntries(devices.map(device => [device, find(work, "home-executor--"+device)]));
const rounds = {};
const map = [];
const result = [];
const already = chat.root.children.some(shape => shape.getPluginData("executor-assistant"));
if (devices.some(device => !homes[device]) || (stage === "prepare") === already) throw Error("Unexpected executor frame state");
if (stage === "prepare") await file.saveVersion("Before executor assistant · 2026-11-18");
for (const shape of chat.root.children) {
  const key = shape.getPluginData("executor-assistant");
  if (key) rounds[key] = shape;
}

function board(key, title, device, y) {
  const mobile = device === "mobile", frame = penpot.createBoard();
  frame.name = title + " · " + device;
  frame.resize(mobile ? 390 : 1440, mobile ? 844 : 900);
  frame.x = mobile ? 1680 : 0; frame.y = y;
  frame.fills = fill(colors.bg); frame.clipContent = true;
  frame.setPluginData("executor-assistant", key + "--" + device);
  frame.setPluginData("role", "executor");
  return frame;
}
function header(frame, mobile, home) {
  const edge = mobile ? 20 : 64;
  brand(frame, mobile ? 20 : 48, mobile ? 32 : 41, mobile);
  rect(frame, "Header divider", mobile ? 20 : 48, mobile ? 63 : 81, mobile ? 350 : 1344, 1, colors.line);
  if (!mobile) text(frame, "ЖК «Сосновый парк» · Исполнитель", 1050, 32, 326, 14, 400, colors.muted, "right");
  glyph(frame, "back", edge+8, mobile ? 98 : 119);
  text(frame, "Мои задания", edge+23, mobile ? 87 : 108, 140, 14, 550, colors.mint);
  const back = target(frame, "Мои задания", edge, mobile ? 76 : 97, 155, 44);
  jump(back, work, home);
  if (mobile) text(frame, "ЖК «Сосновый парк»", 206, 89, 164, 13, 400, colors.muted, "right");
}
function compose(frame, x, y, w, mobile, intro = false) {
  const h = intro ? (mobile ? 108 : 118) : 68;
  rect(frame, intro ? "Центральный композер" : "Нижний композер", x, y, w, h, colors.composer, 17);
  if (intro) {
    text(frame, "Что нужно сделать?", x+20, y+16, w-44, mobile ? 17 : 20, 400);
    glyph(frame, "plus", x+24, y+h-30);
    text(frame, "Файл или фото", x+42, y+h-39, 140, 14, 500, colors.mint);
  } else {
    glyph(frame, "plus", x+25, y+h/2);
    text(frame, "Задайте вопрос", x+50, y+24, w-120, 15, 400, colors.muted);
  }
  const cy = intro ? y+h-32 : y+h/2;
  rect(frame, "Кнопка отправки · пустой ввод", x+w-57, cy-22, 44, 44, "#355046", 22);
  glyph(frame, "send", x+w-35, cy, colors.muted);
  return target(frame, "Файл или фото", x+4, intro ? y+h-54 : y+9, intro ? 160 : 44, 48);
}
function userMessage(frame, x, y, w, mobile, key) {
  const hasPhoto = key !== "instruction";
  const h = hasPhoto ? (mobile ? 114 : 100) : 76;
  rect(frame, "Сообщение исполнителя", x, y, w, h, colors.panel, 16);
  if (hasPhoto) thumbnail(frame, x+14, y+14, 72, 48);
  const value = {
    instruction: mobile ? "Как снять показания\nсчётчиков?" : "Как снять показания счётчиков?",
    attach: mobile ? "Прикрепи к ТО-017,\nпункт 03, «после»." : "Прикрепи фото к ТО-017, пункт 03, «после».",
    attached: mobile ? "Прикрепи к ТО-017,\nпункт 03, «после»." : "Прикрепи фото к ТО-017, пункт 03, «после».",
    cancel: mobile ? "Прикрепи к ТО-017,\nпункт 03, «после»." : "Прикрепи фото к ТО-017, пункт 03, «после».",
    quality: mobile ? "Достаточно ли этого фото\nдля проверки ТО-017?" : "Достаточно ли фото для проверки ТО-017?",
  }[key];
  const offset = hasPhoto ? 100 : 16;
  text(frame, value, x+offset, y+12, w-offset-14, mobile ? 15 : 17);
  text(frame, "17.11.2026 · " + (key === "quality" ? "11:38" : key === "instruction" ? "10:00" : "11:36"),
    x+15, y+h-25, w-30, 12, 400, colors.muted, "right");
  return y+h;
}
function response(frame, x, y, w, time) {
  icon(frame, x, y-1, 22);
  text(frame, "FixRate AI", x+32, y, 90, 15, 600, colors.mint);
  text(frame, "17.11.2026 · "+time, x+w-162, y+1, 162, 12, 400, colors.muted, "right");
}
function sidebar(frame, key) {
  rect(frame, "Разделитель контекста", 1044, 222, 1, 588, colors.line);
  text(frame, "Текущая работа", 1072, 224, 278, 16, 600, colors.mint);
  const isInstruction = key === "instruction";
  text(frame, isInstruction ? "Показания счётчиков" : "ТО-017 · МН-01", 1072, 264, 280, 20, 600);
  text(frame, isInstruction ? "Сегодня · 10:00" : "Попытка 1 · В работе", 1072, 306, 278, 14, 400, colors.muted);
  if (!isInstruction) text(frame, "Пункт 03 · Общий вид", 1072, 341, 278, 14, 400, colors.muted);
}

if (stage !== "workday") {
await penpot.openPage(chat);
const chatBlock = penpot.history.undoBlockBegin();
try {
  if (stage === "prepare") {
  const bottom = Math.ceil(Math.max(...chat.root.children.filter(s => s.type === "board").map(s => s.y + s.height))) + 240;
  for (const [index, [key, title]] of states.entries()) {
    for (const device of devices) {
      const frame = board(key, title, device, bottom+index*1130);
      rounds[key+"--"+device] = frame;
      result.push({key:key+"--"+device, pageId:chat.id, id:frame.id, w:frame.width, h:frame.height});
    }
  }
  return {frames:result};
  }
  if (!states.some(([key]) => key === stage)) throw Error("Unknown executor assistant stage");
  for (const [key, title] of states) for (const device of devices) {
    if (key !== stage) continue;
    const mobile = device === "mobile", r = rounds[key+"--"+device];
    if (!r || r.children.length) throw Error("Expected empty assistant frame " + key + " / " + device);
    result.push({key:key+"--"+device, pageId:chat.id, id:r.id, w:r.width, h:r.height});
    const get = name => rounds[name+"--"+device];
    const x = mobile ? 20 : 160, w = mobile ? 350 : 860;
    header(r, mobile, homes[device]);
    if (key === "start") {
      icon(r, r.width/2-19, mobile ? 166 : 216, 38);
      text(r, "Помощник исполнителя", x, mobile ? 227 : 278, mobile ? w : 1120, mobile ? 29 : 48, 500, colors.ink, "center");
      text(r, "Доступ к вашим заданиям и фотоотчётам", x, mobile ? 282 : 354, mobile ? w : 1120, mobile ? 14 : 16, 400, colors.muted, "center");
      const left = mobile ? 20 : 240, width = mobile ? 350 : 960;
      go(compose(r,left,mobile ? 340 : 414,width,mobile,true),get("attach"));
      for (const [i, label, to] of [[0,"Инструкция по ТО","instruction"],[1,"Прикрепить фото","attach"],[2,"Оценить качество","quality"]]) {
        const cell = (width-24)/3;
        go(button(r,label,left+(mobile ? 0 : i*(cell+12)),(mobile ? 480+i*58 : 558),mobile ? width : cell,false,true),get(to));
      }
      continue;
    }
    text(r, title, x, mobile ? 130 : 154, w, mobile ? 29 : 36, 500);
    text(r, key === "instruction" ? "Показания счётчиков" : "ТО-017 · Проверка температуры и давления",
      x,mobile ? 175 : 204,w,mobile ? 13 : 14,400,colors.muted);
    if (!mobile) sidebar(r,key);
    const msgW = mobile ? 328 : 500;
    const end = userMessage(r,x+w-msgW,mobile ? 216 : 248,msgW,mobile,key);
    const from = end + (mobile ? 22 : 26);
    response(r,x,from,w,key === "quality" ? "11:39" : key === "attached" || key === "cancel" ? "11:37" : key === "attach" ? "11:36" : "10:01");
    const body = from+37;
    if (key === "instruction") {
      text(r,"Снятие показаний",x,body,w, mobile ? 21 : 26,600);
      const steps = [
        "Сверьте номер прибора с заданием.",
        mobile ? "Запишите показание\nи единицу измерения." : "Запишите показание и единицу измерения.",
        "Приложите фото шкалы или дисплея.",
      ];
      for (const [i, step] of steps.entries()) {
        const y = body+(mobile ? 48 : 55)+i*(mobile ? 53 : 49);
        rect(r,"Номер шага",x,y,28,28,colors.panel,8);
        text(r,String(i+1),x,y+4,28,13,600,colors.mint,"center");
        text(r,step,x+41,y+4,w-41,mobile ? 15 : 17,400);
      }
      const y = body+(mobile ? 219 : 215);
      rect(r,"Источник инструкции",x,y,w,61,colors.panel,12,true);
      text(r,"Инструкция к работе · редакция 2",x+14,y+9,w-28,14,600,colors.mint);
      text(r,"Пункт «Фиксация показаний»",x+14,y+31,w-28,13,400,colors.muted);
    } else if (key === "attach") {
      rect(r,"Подтверждение назначения фото",x,body,w,mobile ? 255 : 236,colors.panel,15,true);
      text(r,"Куда прикрепить фото",x+16,body+14,w-32,mobile ? 20 : 23,600);
      text(r,"ТО-017 · Манометр МН-01",x+16,body+57,w-32,mobile ? 16 : 17,600);
      text(r,"Попытка 1 · Пункт 03 «Общий вид»",x+16,body+88,w-32,mobile ? 14 : 16,400,colors.muted);
      text(r,"Фото «после» · подтверждение работы",x+16,body+114,w-32,mobile ? 14 : 16,400,colors.muted);
      const y = body + (mobile ? 157 : 156);
      go(button(r,"Прикрепить фото",x+16,y,mobile ? 197 : 201,true),get("attached"));
      go(button(r,"Отмена",x+(mobile ? 225 : 230),y,100),get("cancel"));
      text(r,"Фотоотчёт останется черновиком.",x+16,y+57,w-32,13,400,colors.muted);
    } else if (key === "attached") {
      rect(r,"Фото сохранено в отчёте",x,body,w,130,colors.panel,15,true);
      glyph(r,"check",x+26,body+27);
      text(r,"Фото прикреплено",x+45,body+14,w-61,mobile ? 20 : 24,600);
      text(r,"ТО-017 · Пункт 03 · Фото «после»",x+16,body+58,w-32,mobile ? 15 : 16,500);
      text(r,"Сохранено в черновике фотоотчёта.",x+16,body+89,w-32,14,400,colors.muted);
      go(button(r,"Оценить качество",x,body+150,mobile ? w : 220,false,true),get("quality"));
    } else if (key === "cancel") {
      text(r,"Фото осталось в диалоге",x,body,w,mobile ? 21 : 26,600);
      text(r,"Прикрепление к заданию отменено.",x,body+45,w,15,400,colors.muted);
      go(button(r,"Выбрать назначение",x,body+96,mobile ? w : 220,false,true),get("attach"));
    } else {
      text(r,"Снимок подходит для отчёта",x,body,w,mobile ? 21 : 26,600);
      text(r,mobile ? "Циферблат и положение стрелки\nвидны на фотографии." : "Циферблат и положение стрелки видны на фотографии.",
        x,body+41,w,mobile ? 15 : 17,400,colors.muted);
      const y = body+(mobile ? 106 : 95);
      rect(r,"Что нужно проверить",x,y,w,mobile ? 153 : 132,colors.panel,15,true);
      text(r,mobile ? "Для оценки работы\nнужен протокол" : "Для оценки работы нужен протокол",x+16,y+14,w-32,mobile ? 18 : 21,600,colors.amber);
      text(r,mobile ? "По фото нельзя проверить точность\nприбора. Приложите протокол\nсравнения перед сдачей отчёта." :
        "По фото нельзя проверить точность прибора. Приложите протокол\nсравнения перед сдачей отчёта.",x+16,y+(mobile ? 69 : 57),w-32,15,400,colors.ink);
    }
    const attachment = compose(r,x,mobile ? 754 : 780,w,mobile);
    if (key !== "attach") go(attachment,get("attach"));
  }
} finally {
  penpot.history.undoBlockFinish(chatBlock);
}
return {frames:result};
}

await penpot.openPage(work);
const workBlock = penpot.history.undoBlockBegin();
try {
  for (const device of devices) {
    const mobile = device === "mobile", r = homes[device];
    const nav = r.children.find(s => s.name === "Global navigation");
    const launcher = nav.children.find(s => s.name === "ИИ-помощник");
    for (const s of [...nav.children]) {
      if (s.name === "FixRate mark" || s.name === "FixRate AI" ||
        (s.name === "Surface" && s.x-r.x < 60 && Math.abs(s.width-30)<1)) s.remove();
    }
    brand(nav,mobile ? 20 : 48,mobile ? 32 : 41,mobile);
    for (const s of [...launcher.children]) s.remove();
    rect(launcher,"Assistant trigger",3,3,38,38,colors.composer,11,true);
    icon(launcher,10,9,24);
    const top = target(launcher,"Открыть ИИ-помощник из шапки",0,0,44,44);
    for (const interaction of launcher.interactions) launcher.removeInteraction(interaction);
    jump(top,chat,rounds["start--"+device]);
    map.push({device,frame:r.id,hit:top.id,name:top.name});

    if (mobile) {
      const cols = [20,139,258];
      for (const [i, label] of ["Сегодня","В работе","На доработке"].entries()) {
        const caption = r.children.find(s => s.name === label);
        const number = r.children.find(s => s.type === "text" && /^[13]$/.test(s.characters) &&
          Math.abs(s.x-caption.x)<.5 && Math.abs(caption.y-s.y-53)<.5);
        if (!number) throw Error("Cannot find workday metric");
        number.resize(112,number.height); caption.resize(112,caption.height);
        number.x=r.x+cols[i]; caption.x=number.x;
        number.y=r.y+233; caption.y=r.y+286;
      }
    }
    const delta = mobile ? -20 : 114;
    const dividerY = mobile ? 447 : 389;
    for (const s of r.children) if (s.y-r.y>=dividerY-.5) s.y += delta;
    r.resize(r.width,r.height+delta);
    const edge = mobile ? 20 : 64, y = mobile ? 322 : 390, w = mobile ? 350 : 1312, h = 80;
    rect(r,"Помощник · вход с рабочего дня",edge,y,w,h,colors.panel,15,true);
    rect(r,"Подложка иконки помощника",edge+14,y+18,44,44,colors.composer,12);
    icon(r,edge+24,y+27,24);
    text(r,"ИИ-помощник",edge+70,y+13,w-(mobile ? 114 : 280),19,600);
    text(r,mobile ? "Инструкции, фото и оценка" : "Инструкции к работам, фотоотчёт и оценка снимков",
      edge+70,y+43,w-(mobile ? 104 : 270),mobile ? 14 : 15,400,colors.muted);
    if (!mobile) text(r,"Открыть помощника",edge+w-240,y+27,180,16,600,colors.mint,"right");
    glyph(r,"forward",edge+w-(mobile ? 22 : 34),y+40);
    const hit = target(r,"Открыть ИИ-помощник",edge,y,w,h);
    jump(hit,chat,rounds["start--"+device]);
    map.push({device,frame:r.id,hit:hit.id,name:hit.name});
    result.push({key:"home-executor--"+device,pageId:work.id,id:r.id,w:r.width,h:r.height});
    r.setPluginData("executor-assistant-entry", rounds["start--"+device].id);
  }
} finally {
  penpot.history.undoBlockFinish(workBlock);
}
return {frames:result,entryLinks:map};
