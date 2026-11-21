import {test,expect} from '@playwright/test';
import {writeFileSync} from 'node:fs';

// Production SPA, explicit API fixtures: never changes a user's conversations.
for(const width of [1440,390,320])test(`history controls and message attachments at ${width}px`,async({page,context},info)=>{
  test.skip(!process.env.FIXRATE_BASE_URL,'Requires the production SPA');
  await page.setViewportSize({width,height:900});
  const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
  const profile={userId:'composer-qa',siteId:'composer-site',role:width===390?'executor':'chief_engineer',name:'QA',email:'qa@example.test',siteName:'QA',timezone:'UTC'};
  const id='00000000-0000-4000-8000-000000000001',fileId='00000000-0000-4000-8000-000000000002',oldId='00000000-0000-4000-8000-000000000003';
  const now='2026-11-15T10:00:00Z';
  const conversation=(key:string)=>({conversation_id:key,title:key===oldId?'QA long history':'QA photo',agent:'assistant',created_at:now,updated_at:now});
  const attachment={attachment_id:fileId,original_name:'photo.png',mime_type:'image/png',size_bytes:100,sha256:'a'.repeat(64),created_at:now};
  let pending:typeof attachment[]=[],turns:Record<string,unknown>[]=[],listReads=0,overviewReads=0;
  let releaseOldConversation!: () => void;
  const waitForOldConversation = new Promise<void>(resolve => {releaseOldConversation=resolve;});
  const sent:{content:string;attachment_ids:string[]}[]=[];
  await context.route('**/api/**',async route=>{
    const request=route.request(),path=new URL(request.url()).pathname;
    if(path==='/api/v1/auth/session')return route.fulfill({json:{profile}});
    if(path==='/api/v1/auth/sites')return route.fulfill({json:[]});
    if(path==='/api/v1/maintenance/overview'){overviewReads++;return route.fulfill({json:[]});}
    if(path.endsWith('/assistant/capabilities'))return route.fulfill({json:{available:true,model_ref:'fixture',prompt_version:'qa',agents:[],tools:{assistant:[],planner:[],photo:[]}}});
    if(path.endsWith('/assistant/models'))return route.fulfill({json:{providers:[]}});
    if(path.endsWith('/assistant/conversations')){
      if(request.method()==='POST')return route.fulfill({json:conversation(id)});
      listReads++;return route.fulfill({json:{items:[conversation(oldId),...(turns.length||pending.length?[conversation(id)]:[])],total:turns.length||pending.length?2:1}});
    }
    if(path.endsWith('/attachments')&&request.method()==='POST'){pending=[attachment];return route.fulfill({json:attachment});}
    if(path.endsWith('/messages')){
      const body=request.postDataJSON();sent.push(body);
      turns.push({turn_id:crypto.randomUUID(),content:body.content||'Проанализируй прикреплённые файлы.',answer:'QA image received\n\n### Анализ исходных данных\n\n| Работа | Часы |\n|---|---|\n| Насос | 12 |\n\n- Проверить периодичность\n- Уточнить единицы норм',status:'completed',trace:[],created_at:now,finished_at:now,error_code:null,model_ref:'fixture',attachments:body.attachment_ids.length?[attachment]:[]});
      pending=[];return route.fulfill({json:{turn_id:turns.at(-1)!.turn_id,status:'completed'}});
    }
    if(path===`/api/v1/assistant/conversations/${id}`)return route.fulfill({json:{conversation:conversation(id),turns,total:turns.length,actions:[],attachments:[attachment],pending_attachments:pending}});
    if(path===`/api/v1/assistant/conversations/${oldId}`&&request.method()==='DELETE')return route.fulfill({json:{deleted:true}});
    if(path===`/api/v1/assistant/conversations/${oldId}`)await waitForOldConversation;
    if(path===`/api/v1/assistant/conversations/${oldId}`)return route.fulfill({json:{conversation:conversation(oldId),total:25,actions:[],attachments:[],pending_attachments:[],turns:Array.from({length:25},(_,i)=>({turn_id:`old-${i}`,content:`QA question ${i}`,answer:'QA answer '.repeat(50),trace:i===24?[{tool:'tasks_find',status:'completed',fact:{total:30,shown:25}},{tool:'staff_find',status:'denied',code:422}]:[],status:'completed',created_at:now,finished_at:now,error_code:null,model_ref:'fixture'}))}});
    return route.fulfill({json:[]});
  });
  await page.goto('/assistant');
  const input=page.getByLabel('Сообщение помощнику'),toolbar=page.getByRole('group',{name:'Управление чатом'});
  await expect(input).toBeVisible();await expect(page.getByText('Enter — отправить',{exact:false})).toHaveCount(0);
  expect(await page.evaluate(()=>performance.getEntriesByType('resource')
    .some(entry=>/\/AssistantAnswer-[\w-]+\.js$/.test(entry.name)))).toBe(false);
  await expect(toolbar.getByRole('button',{name:'Новый чат'})).toHaveCSS('cursor','pointer');
  await expect(page.getByRole('button',{name:'Отправить',exact:true})).toBeDisabled();
  if(width>=1280){
    const history=page.getByRole('complementary',{name:'История диалогов'}),workspace=page.locator('.workspace-root');
    await expect(page.getByRole('heading',{name:'Недавние диалоги'})).toBeVisible();
    await page.getByRole('button',{name:'Развернуть историю чатов'}).click();
    await expect(history).toBeVisible();await input.fill('QA draft');
    const before=await workspace.evaluate(el => getComputedStyle(el).background),reads=listReads;
    await page.getByRole('button',{name:'Свернуть историю чатов'}).click();
    await expect(history).toBeHidden();await expect(input).toHaveValue('QA draft');
    expect(await workspace.evaluate(el => getComputedStyle(el).background)).toEqual(before);expect(listReads).toBe(reads);
    await page.reload();await expect(page.getByRole('button',{name:'Развернуть историю чатов'})).toBeVisible();
    await page.screenshot({path:info.outputPath(`collapsed-${width}.png`)});
    await page.getByRole('button',{name:'Развернуть историю чатов'}).click();await expect(history).toBeVisible();
  }else{
    const open=page.getByRole('button',{name:'Открыть историю чатов'});
    await open.click();await expect(page.getByRole('dialog',{name:'История диалогов'})).toBeVisible();
    await page.keyboard.press('Escape');await expect(open).toBeFocused();
  }
  await page.screenshot({path:info.outputPath(`welcome-${width}.png`)});
  await page.goto(width===390?'/executor':'/chief-engineer');
  await input.fill('QA draft with a workday attachment');
  const attachmentControl = page.locator('.assistant-attach');
  const chooser = await context.newCDPSession(page);
  await chooser.send('Page.setInterceptFileChooserDialog',{enabled:true,cancel:true});
  await attachmentControl.click();
  await expect(input).toBeFocused();
  await expect(attachmentControl).toHaveCSS('outline-style','none');
  await expect(input).toHaveValue('QA draft with a workday attachment');
  await chooser.detach();
  await page.getByLabel('Прикрепить файл').setInputFiles({name:'photo.png',mimeType:'image/png',buffer:Buffer.from('fixture; upload body is explicitly mocked')});
  await expect(page).toHaveURL(new RegExp(`chat=${id}`));
  await expect(page.getByRole('list',{name:'Вложения к сообщению'})).toContainText('photo.png');
  await expect(input).toHaveValue('QA draft with a workday attachment');
  await input.fill('');
  await page.getByRole('button',{name:'Отправить',exact:true}).click();
  await expect(page.getByRole('list',{name:'Отправленные файлы'})).toContainText('photo.png');
  const composer=page.getByRole('form',{name:'Написать помощнику'});
  const modelTrigger = composer.getByRole('button',{name:'Выбрать модель',exact:true});
  await expect(modelTrigger.locator('.assistant-model-chevron')).toBeVisible();
  const initialTrigger = await modelTrigger.boundingBox();
  const initialComposer = await composer.boundingBox();
  await modelTrigger.click();
  const modelDialog = page.getByRole('dialog',{name:'Используемая модель'});
  await expect(modelDialog).toBeVisible();
  const menuBox = (await modelDialog.boundingBox())!, triggerBox = (await modelTrigger.boundingBox())!;
  expect(triggerBox).toEqual(initialTrigger);
  expect(await composer.boundingBox()).toEqual(initialComposer);
  expect(menuBox.y+menuBox.height).toBeLessThanOrEqual(triggerBox.y);
  expect(menuBox.y).toBeGreaterThanOrEqual(0);
  expect(menuBox.y+menuBox.height).toBeLessThanOrEqual(900);
  await page.keyboard.press('Escape');
  await expect(modelTrigger).toBeFocused();
  expect(await modelTrigger.boundingBox()).toEqual(initialTrigger);
  const compactHeight=(await composer.boundingBox())!.height;
  expect(compactHeight).toBeLessThanOrEqual(110);
  await input.fill('Первая строка\nВторая строка\nТретья строка\nЧетвёртая строка');
  await expect.poll(async()=>(await composer.boundingBox())!.height).toBeGreaterThan(compactHeight+20);
  const longDraft = 'Проверить состояние оборудования и записать показания. '.repeat(230).slice(0, 11990);
  await input.fill(longDraft);
  await input.press('Control+End');
  await page.keyboard.insertText(' Проверено.');
  await expect(input).toHaveValue((longDraft + ' Проверено.').slice(0, 12000));
  expect(await input.evaluate(el => el.clientHeight <= 180 && el.scrollHeight > el.clientHeight)).toBe(true);
  await input.fill('');await expect.poll(async()=>(await composer.boundingBox())!.height).toBeLessThanOrEqual(110);
  await expect(page.getByLabel('Время выполнения: 0 мин 0 сек')).toBeVisible();
  await expect(page.getByRole('heading',{name:'Анализ исходных данных'})).toBeVisible();
  await expect(page.getByRole('table')).toContainText('Насос');
  expect(sent[0]).toMatchObject({content:'',attachment_ids:[fileId]});
  await expect(page.getByRole('list',{name:'Вложения к сообщению'})).toHaveCount(0);
  await expect(page.getByRole('link',{name:'photo.png'})).toHaveCSS('cursor','pointer');
  await page.reload();await expect(page.getByRole('list',{name:'Отправленные файлы'})).toContainText('photo.png');
  await input.fill('QA next message');await input.press('Enter');
  await expect(page.getByText('QA image received',{exact:true})).toHaveCount(2);expect(sent[1].attachment_ids).toEqual([]);
  await page.screenshot({path:info.outputPath(`sent-${width}.png`)});
  if(width<1280)await page.getByRole('button',{name:'Открыть историю чатов'}).click();
  await page.getByRole('button',{name:/^QA long history/}).click();
  try {
    await expect(page.getByRole('status',{name:'Загрузка диалога'})).toBeAttached();
    const [upper,lower]=await page.locator('.workspace-root').evaluate(element=>
      ['::before','::after'].map(layer=>Number(getComputedStyle(element,layer).opacity)));
    expect(lower).toBeGreaterThan(upper);
  } finally {
    releaseOldConversation();
  }
  const region=page.getByRole('region',{name:'Сообщения'});
  await expect(region.locator('article')).toHaveCount(25);
  await expect.poll(()=>region.evaluate(el=>el.scrollHeight-el.clientHeight-el.scrollTop)).toBeLessThan(3);
  const progress=region.locator('article').last().locator('.assistant-progress');
  await expect(progress.locator('summary')).toContainText('Ответ завершён за 0 секунд');
  await progress.locator('summary').focus();await page.keyboard.press('Enter');
  await expect(progress.getByText(/по условиям найдено 30, проверено на странице: 25/)).toBeVisible();
  await expect(progress.getByText(/содержал неверные параметры/)).toBeVisible();
  await page.screenshot({path:info.outputPath(`progress-${width}.png`)});
  await page.emulateMedia({reducedMotion:'reduce'});
  expect(await progress.locator('.assistant-progress-chevron').evaluate(el=>parseFloat(getComputedStyle(el).transitionDuration))).toBeLessThan(.001);
  await page.keyboard.press('Enter');await expect(progress).not.toHaveAttribute('open','');
  await page.emulateMedia({reducedMotion:'no-preference'});
  const jump=page.getByRole('button',{name:'К последним сообщениям'});
  await region.evaluate(el=>{el.scrollTop=el.scrollHeight-el.clientHeight-120;});
  await expect.poll(()=>region.evaluate(el=>el.scrollHeight-el.clientHeight-el.scrollTop)).toBeGreaterThan(100);
  await expect(jump).toBeHidden();
  await input.fill('QA reading');
  await expect.poll(()=>region.evaluate(el=>el.scrollHeight-el.clientHeight-el.scrollTop)).toBeGreaterThan(100);
  await region.evaluate(el=>{el.scrollTop=el.scrollHeight-el.clientHeight-600;});
  await expect(jump).toBeVisible();await jump.click();
  await expect.poll(()=>region.evaluate(el=>el.scrollHeight-el.clientHeight-el.scrollTop)).toBeLessThan(3);
  await expect(jump).toBeHidden();
  const metrics:unknown[]=[];
  const cdp=await context.newCDPSession(page);
  for(const rate of [1,4]){
    await cdp.send('Emulation.setCPUThrottlingRate',{rate});
    const inputMs=await input.evaluate(async el=>{
      const times:number[]=[];
      for(let i=0;i<12;i++){
        const start=performance.now();
        Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value')!.set!.call(el,`QA draft ${i}`);
        el.dispatchEvent(new Event('input',{bubbles:true}));
        await new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve())));times.push(performance.now()-start);
      }
      return times.sort((a,b)=>a-b)[Math.floor(times.length*.95)];
    });
    await region.evaluate(el=>{el.scrollTop=0;});
    await page.mouse.move(width>=1280?700:width/2,400);
    const frames=region.evaluate(async()=>{
      const intervals:number[]=[],longTasks:number[]=[];let last=performance.now();
      const observer=new PerformanceObserver(list=>list.getEntries().forEach(entry=>longTasks.push(entry.duration)));
      observer.observe({type:'longtask',buffered:false});
      await new Promise<void>(resolve=>{const until=performance.now()+1000;const frame=(now:number)=>{intervals.push(now-last);last=now;if(now<until)requestAnimationFrame(frame);else resolve();};requestAnimationFrame(frame);});
      observer.disconnect();intervals.shift();intervals.sort((a,b)=>a-b);
      return {frameP95:intervals[Math.floor(intervals.length*.95)],longTasks};
    });
    await page.mouse.wheel(0,700);
    const scroll=await frames;
    expect(await region.evaluate(el=>el.scrollTop)).toBeGreaterThan(0);
    const historyToggleP95=width<1280?null:await toolbar.evaluate(async el=>{
      const samples:number[]=[];
      for(let i=0;i<12;i++){
        const start=performance.now();(el.querySelector('button') as HTMLButtonElement).click();
        await new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve())));samples.push(performance.now()-start);
      }
      return samples.sort((a,b)=>a-b)[Math.floor(samples.length*.95)];
    });
    metrics.push({width,cpuRate:rate,inputP95:inputMs,historyToggleP95,...scroll});
  }
  await cdp.send('Emulation.setCPUThrottlingRate',{rate:1});
  await input.fill('QA draft for another conversation');
  if(width<1280)await page.getByRole('button',{name:'Открыть историю чатов'}).click();
  await page.getByRole('button',{name:/^QA photo/}).click();
  await expect(input).toHaveValue('');
  await page.goBack();
  await expect(input).toHaveValue('QA draft for another conversation');
  if(width<1280)await page.getByRole('button',{name:'Открыть историю чатов'}).click();
  await page.getByRole('button',{name:'Удалить чат QA long history'}).click();
  await expect(page.getByRole('dialog',{name:'Удалить чат?'})).toBeVisible();
  await page.getByRole('button',{name:'Отмена'}).click();
  if(width<1280)await page.getByRole('button',{name:'Открыть историю чатов'}).click();
  await page.getByRole('button',{name:'Удалить чат QA long history'}).click();
  await page.getByRole('dialog',{name:'Удалить чат?'}).getByRole('button',{name:'Удалить чат'}).click();
  await expect(page).not.toHaveURL(new RegExp(`chat=${oldId}`));
  // A starter sends immediately and hands the emphasis to the dock once.
  await page.emulateMedia({reducedMotion:width===320?'reduce':'no-preference'});
  await page.goto(width===390?'/assistant':'/chief-engineer');
  const workspace=page.locator('.workspace-root');
  const glow=()=>workspace.evaluate(el=>['::before','::after'].map(layer=>Number(getComputedStyle(el,layer).opacity)));
  await expect(input).toBeVisible();
  const before=await glow();
  expect(before[0]).toBeGreaterThan(before[1]);
  await page.evaluate(()=>{
    document.addEventListener('animationstart', event=>{
      if(event.animationName==='workspace-glow-handoff' && event.pseudoElement==='::after'){
        const root=document.documentElement;
        root.dataset.qaGlowStarts=String(Number(root.dataset.qaGlowStarts??0)+1);
      }
    });
  });
  const previousMessages=sent.length;
  const preservedDraft = 'QA unsent draft before clicking a starter';
  const starterLabel = width===390?'Инструкция по ТО':'Разобрать просрочки';
  const starterPrompt = width===390?'Найди ближайшее назначенное мне ТО и покажи утверждённую инструкцию и чек-лист.':'Какие работы просрочены и с чего лучше начать?';
  await input.fill(preservedDraft);
  await page.getByRole('button',{name:starterLabel,exact:true}).click();
  const chat=page.getByRole('region',{name:'Диалог с ИИ'});
  await expect(chat).toBeVisible();
  await expect(chat).toContainText(starterPrompt);
  await expect(input).toHaveValue(preservedDraft);
  expect(sent.slice(previousMessages)).toEqual([expect.objectContaining({content:starterPrompt,attachment_ids:[]})]);
  await expect.poll(async()=>{const [top,bottom]=await glow();return bottom>top;}).toBe(true);
  if(width===320){
    expect(await workspace.evaluate(el=>getComputedStyle(el,'::after').animationName)).toBe('none');
    await expect(page.locator('html')).not.toHaveAttribute('data-qa-glow-starts',/.+/);
  }else{
    await expect(page.locator('html')).toHaveAttribute('data-qa-glow-starts','1');
    await expect.poll(()=>workspace.evaluate(el=>el.getAnimations({subtree:true}).filter(animation=>animation instanceof CSSAnimation&&animation.animationName==='workspace-glow-handoff').length)).toBe(0);
  }
  await expect(chat).not.toHaveAttribute('data-composer-entry','');
  await page.screenshot({path:info.outputPath(`handoff-${width}.png`)});
  await page.goBack();
  if(width!==390)await expect(page.getByRole('heading',{name:'С чего начнём рабочий день?'})).toBeVisible();
  await expect(input).toBeVisible();
  await expect.poll(async()=>{const [top,bottom]=await glow();return top>bottom;}).toBe(true);
  if(width===1440){
    await expect(page.locator('.fr-overview-grid')).toHaveCount(0);
    await expect(page.getByText('Показатели доступных объектов и месячный экспорт',{exact:true})).toHaveCount(0);
    expect(overviewReads).toBe(0);
  }
  await page.goForward();
  await expect(chat).toBeVisible();
  expect(await workspace.evaluate(el=>getComputedStyle(el,'::after').animationName)).toBe('none');
  await page.reload();
  await expect(chat).toBeVisible();
  expect(await workspace.evaluate(el=>getComputedStyle(el,'::after').animationName)).toBe('none');
  const report=info.outputPath('performance.json');writeFileSync(report,JSON.stringify(metrics,null,2));
  await info.attach('performance.json',{path:report,contentType:'application/json'});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);expect(errors).toEqual([]);
});
