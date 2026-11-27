import { test, expect } from '@playwright/test';
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { pickCalendar } from './calendar-input';

const API='/api/v1/maintenance', BASE=`${API}/planning/order-table`;
const demo=(key:string)=>{
  const hex=createHash('md5').update(`fixrate-demo-${key}`).digest('hex');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
};
const taskId=demo('assignment-order'), bindingId=demo('assignment-binding');
function shift(day:string, amount:number){
  const stamp=new Date(`${day}T00:00:00Z`);stamp.setUTCDate(stamp.getUTCDate()+amount);
  return stamp.toISOString().slice(0,10);
}

for(const width of [1440,390]) test(`isolated worksheet writes after confirmation and downloads XLSX at ${width}px`,async({page,context}, info)=>{
  test.skip(process.env.FIXRATE_ORDER_TABLE_E2E!=='1','Requires the isolated confirmed-regulation fixture');
  await page.setViewportSize({width,height:900});
  await page.emulateMedia({reducedMotion:'reduce'});
  const errors:string[]=[];
  page.on('pageerror',error=>errors.push(error.message));
  const login=await context.request.post('/api/v1/auth/login',{data:{email:'fixrate-demo-chief_engineer@example.test',password:process.env.FIXRATE_TEST_PASSWORD}});
  expect(login.status()).toBe(200);
  const headers={'X-CSRF-Token':(await login.json()).csrfToken};
  const read=async(id=taskId)=>(await (await context.request.get(`${API}/ui/tasks/${id}`)).json()).task;
  const initial=await read(), day=initial.mandatoryDueDate as string;
  await page.goto(`/planning?mode=orders&order_month=${day.slice(0,7)}`);
  const table=page.getByRole('region',{name:'Таблица нарядов ТО',exact:true});
  const row=table.getByRole('row').filter({has:page.getByRole('link',{name:initial.title,exact:true})}).first();
  await expect(row).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  const scroller=table.getByRole('region',{name:'Прокручиваемые строки таблицы'});
  const search=table.getByLabel('Поиск по нарядам');
  const measurements:{cpu:number;inputMs:number[];scrollFrameMs:number[];warmTabMs:number}[]=[];
  const cdp=await context.newCDPSession(page);
  const plans=page.getByRole('button',{name:'Планы из Excel',exact:true});
  const worksheet=page.getByRole('button',{name:'Таблица нарядов ТО',exact:true});
  await plans.click();
  await worksheet.click();
  await expect(row).toBeVisible();
  for(const cpu of [1,4]){
    await cdp.send('Emulation.setCPUThrottlingRate',{rate:cpu});
    const trace=await search.evaluate(input=>new Promise<number[]>(resolve=>{
      const samples:number[]=[];
      const run=()=>{
        const started=performance.now();
        const element=input as HTMLInputElement;
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(element,`Манометр ${samples.length}`);
        element.dispatchEvent(new Event('input',{bubbles:true}));
        requestAnimationFrame(()=>{samples.push(performance.now()-started);if(samples.length<12)run();else resolve(samples);});
      };
      run();
    }));
    await plans.click();
    const beforeTab=performance.now();
    await worksheet.click();
    await expect(row).toBeVisible();
    const warmTabMs=performance.now()-beforeTab;
    await scroller.locator('thead').hover();
    const framePromise=page.evaluate(()=>new Promise<number[]>(resolve=>{
      let prior=performance.now();
      const samples:number[]=[];
      const frame=(now:number)=>{samples.push(now-prior);prior=now;if(samples.length<18)requestAnimationFrame(frame);else resolve(samples.slice(1));};
      requestAnimationFrame(frame);
    }));
    const overflow=await scroller.evaluate(element=>element.scrollWidth>element.clientWidth);
    if(overflow) {
      await page.mouse.wheel(460,0);
      await expect.poll(()=>scroller.evaluate(element=>element.scrollLeft)).toBeGreaterThan(0);
      await page.mouse.wheel(-460,0);
    }else{
      const beforeScroll=await page.evaluate(()=>scrollY);
      await page.mouse.wheel(0,220);
      await expect.poll(()=>page.evaluate(()=>scrollY)).toBeGreaterThan(beforeScroll);
    }
    measurements.push({cpu,inputMs:trace,scrollFrameMs:await framePromise,warmTabMs});
  }
  await cdp.send('Emulation.setCPUThrottlingRate',{rate:1});
  await cdp.detach();
  await search.fill('');
  await writeFile(info.outputPath(`worksheet-performance-${width}.json`),JSON.stringify({width,height:900,measurements},null,2));
  if(width===1440){
    await row.getByLabel(/Примечание/).fill('TEST: отметка из таблицы ТО');
    await pickCalendar(page,row.getByRole('button',{name:/Плановое начало/}),day+'T09:00');
  }
  await table.getByRole('button',{name:'Добавить строку',exact:true}).click();
  const editor=table.getByRole('group',{name:'Строка 1',exact:true});
  const binding=editor.getByLabel('Регламент и оборудование');
  await expect(binding.locator(`option[value="${bindingId}"]`)).toHaveCount(1);
  await binding.selectOption(bindingId);
  const newDay=shift(day,width===1440?1:2);
  await pickCalendar(page,editor.getByRole('button',{name:'Плановое начало',exact:true}),newDay+'T09:00');
  await pickCalendar(page,editor.getByRole('button',{name:'Обязательный срок',exact:true}),newDay);
  await table.getByLabel('Основание изменения').fill('TEST: проверяем предпросмотр');
  await page.getByRole('button',{name:'Планы из Excel',exact:true}).click();
  await page.getByRole('button',{name:'Таблица нарядов ТО',exact:true}).click();
  await expect(table.getByLabel('Основание изменения')).toHaveValue('TEST: проверяем предпросмотр');
  await expect(binding).toHaveValue(bindingId);
  await page.goBack();
  await expect(page).not.toHaveURL(/mode=orders/);
  await page.goForward();
  await expect(binding).toHaveValue(bindingId);
  const checked=page.waitForResponse(response=>response.url().endsWith(`${BASE}/preview`));
  await table.getByRole('button',{name:'Проверить изменения',exact:true}).click();
  const preview=await (await checked).json();
  const newId=preview.items.find((item:{action:string})=>item.action==='create').task_id;
  expect((await context.request.get(`${API}/ui/tasks/${newId}`)).status()).toBe(404);
  expect((await read()).revision).toBe(initial.revision);
  const modal=page.getByRole('dialog',{name:'Предпросмотр изменений'});
  const confirm=modal.getByRole('button',{name:'Применить изменения',exact:true});
  await expect(confirm).toBeDisabled();
  await modal.getByRole('checkbox').check();
  await page.screenshot({path:info.outputPath(`worksheet-preview-${width}.png`),animations:'disabled'});
  await confirm.click();
  await expect(table.getByText('Изменения сохранены.')).toBeVisible();
  const created=await read(newId);
  expect(created.state).toBe('draft');
  expect(created.mandatoryDueDate).toBe(newDay);
  expect(created.assignees).toEqual([]);
  if(width===1440){
    const changed=await read();
    expect(changed.planningNote).toBe('TEST: отметка из таблицы ТО');
    const chosen=await context.request.post(`${API}/tasks/${taskId}/assignment-preview`,{headers,data:{
      expected_revision:changed.revision,start_local:day+'T09:00',end_local:day+'T11:00'}});
    const assigned=await context.request.post(`${API}/tasks/${taskId}/assign`,{headers,data:{...(await chosen.json()).command,reason:'TEST: бригада назначена'}});
    expect(assigned.status()).toBe(200);
    const previous=(await assigned.json()).task;
    await page.reload();
    await pickCalendar(page,row.getByRole('button',{name:/Плановое начало/}),day+'T13:00');
    await table.getByLabel('Основание изменения').fill('TEST: перенести ту же бригаду');
    await row.getByRole('button',{name:'Проверить перенос',exact:true}).click();
    const separate=page.getByRole('dialog',{name:'Отдельное подтверждение переноса'});
    await expect(separate.getByText(/Бригада:/)).toBeVisible();
    expect((await read()).revision).toBe(previous.revision);
    await separate.getByRole('checkbox').check();
    await page.screenshot({path:info.outputPath('worksheet-assigned-confirmation.png'),animations:'disabled'});
    await separate.getByRole('button',{name:'Подтвердить перенос',exact:true}).click();
    await expect(table.getByText('Изменения сохранены.')).toBeVisible();
    const next=await read();
    expect(next.scheduledStart.slice(0,16)).toBe(day+'T13:00');
    expect(next.assignees).toEqual(previous.assignees);
  }
  const xlsx=page.waitForEvent('download');
  await table.getByRole('link',{name:'Скачать сохранённое XLSX',exact:true}).click();
  const downloaded=await xlsx;
  expect((await readFile((await downloaded.path())!)).subarray(0,2).toString()).toBe('PK');
  expect(errors).toEqual([]);
});
