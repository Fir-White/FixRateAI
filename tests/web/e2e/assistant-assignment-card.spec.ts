import {createHash} from 'node:crypto';
import {expect,test} from '@playwright/test';
import type {ChatAction} from '../../../frontend/src/shared/api/assistant';

const hex=createHash('md5').update('fixrate-demo-assignment-order').digest('hex');
const taskId=`${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
const maintenance='/api/v1/maintenance';
const assistant='/api/v1/assistant';

for(const width of [1920,390])test(`состав, время и подтверждение в карточке назначения при ${width}px`,async({page,context},info)=>{
  test.skip(!process.env.FIXRATE_TEST_PASSWORD||!process.env.FIXRATE_ASSISTANT_LAYOUT_E2E,'Нужен изолированный стенд');
  expect(new URL(process.env.FIXRATE_BASE_URL!).origin).toBe('http://127.0.0.1:18086');
  await page.setViewportSize({width,height:900});
  await page.emulateMedia({reducedMotion:'reduce'});
  const session=await context.request.post('/api/v1/auth/login',{data:{email:'fixrate-demo-chief_engineer@example.test',password:process.env.FIXRATE_TEST_PASSWORD}});
  expect(session.ok()).toBe(true);
  const headers={'X-CSRF-Token':(await session.json()).csrfToken};
  const path={task_id:taskId};
  const taskUrl=`${maintenance}/ui/tasks/${taskId}`;
  const assignmentContext=await context.request.get(`${taskUrl}/assignment-context`);
  expect(assignmentContext.ok()).toBe(true);
  const slot=await assignmentContext.json();
  expect(slot.status).toBe('ready');
  const initialTask=(await (await context.request.get(taskUrl)).json()).task;
  const previewResponse=await context.request.post(`${maintenance}/tasks/${taskId}/assignment-preview`,{
    headers,data:{expected_revision:slot.expectedRevision,start_local:slot.defaultStartLocal,end_local:slot.defaultEndLocal},
  });
  expect(previewResponse.ok()).toBe(true);
  const preview=await previewResponse.json();
  expect(preview.status).toBe('ok');
  const {expected_revision,executor_ids,start_at,end_at}=preview.command;
  const reason='Учебная проверка карточки без назначения';
  const created=await context.request.post(`${assistant}/conversations`,{headers,data:{agent:'assistant'}});
  expect(created.ok()).toBe(true);
  const {conversation_id}=await created.json();
  try{
    const proposed=await context.request.post(`${assistant}/mcp`,{
      headers:{...headers,Accept:'application/json, text/event-stream','MCP-Protocol-Version':'2025-06-18'},
      data:{jsonrpc:'2.0',id:1,method:'tools/call',params:{name:'task_assign',arguments:{conversation_id,path,body:{expected_revision,executor_ids,start_at,end_at,reason}}}},
    });
    expect(proposed.ok()).toBe(true);
    const prepared=(await proposed.json()).result;
    expect(prepared.isError).toBe(false);
    const action=JSON.parse(prepared.content[0].text) as ChatAction;
    expect(action.status).toBe('proposed');
    const names=new Map<string,string>(preview.selectedWorkers.map(({executorId,name}:{executorId:string;name:string})=>[executorId,name]));
    await page.goto(`/assistant?chat=${conversation_id}`);
    const card=page.getByRole('region',{name:'Предложение: Назначить бригаду и время'});
    await expect(card).toBeVisible();
    await expect(card.getByRole('list',{name:'Исполнители'}).getByRole('listitem')).toHaveText(executor_ids.map((id:string)=>names.get(id)!));
    await expect(card.getByText(initialTask.title,{exact:true})).toBeVisible();
    await expect(card.getByText('Время объекта',{exact:true})).toBeVisible();
    await expect(card.getByText(`Основание: ${reason}`,{exact:true})).toBeVisible();
    await expect(card.getByRole('link',{name:'Открыть задание'})).toHaveAttribute('href',`/tasks/${taskId}`);
    const technical=card.getByText('Технические детали',{exact:true});
    expect((await card.boundingBox())!.width).toBeLessThanOrEqual(832);
    await expect(technical.locator('svg')).toHaveCount(0);
    const raw=card.locator('pre').first();
    await expect(raw).toBeHidden();
    const confirm=card.getByRole('button',{name:'Подтвердить и выполнить'});
    await expect(confirm).toBeDisabled();
    await card.screenshot({path:info.outputPath(`assignment-card-${width}.png`)});
    await technical.press('Enter');
    await expect(raw).toBeVisible();
    await expect(raw).toContainText(executor_ids[0]);
    const transcript=page.locator('.assistant-transcript');
    if(width===390){
      await transcript.evaluate(element=>{element.scrollTop=0;});
      const bounds=(await transcript.boundingBox())!;
      await page.mouse.move(bounds.x+bounds.width/2,bounds.y+bounds.height/2);
      await page.mouse.wheel(0,220);
      await expect.poll(()=>transcript.evaluate(element=>element.scrollTop)).toBeGreaterThan(0);
    }
    await technical.press('Enter');
    await expect(raw).toBeHidden();
    await page.reload();
    await expect(card.getByRole('list',{name:'Исполнители'})).toBeVisible();
    await card.getByRole('checkbox').check();
    await expect(confirm).toBeEnabled();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await card.getByRole('button',{name:'Отклонить'}).click();
    await expect(card.getByRole('status')).toHaveText('Отклонено');
    await expect(confirm).toHaveCount(0);
    const finalTask=(await (await context.request.get(taskUrl)).json()).task;
    expect(finalTask.revision).toBe(initialTask.revision);
    expect(finalTask.assignees).toEqual(initialTask.assignees);
  }finally{
    expect((await context.request.delete(`${assistant}/conversations/${conversation_id}`,{headers})).ok()).toBe(true);
  }
});
