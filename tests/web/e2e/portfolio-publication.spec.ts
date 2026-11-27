import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';

for(const width of [1440,390,320])test(`real regulation approval and publication at ${width}px`,async({page,context},info)=>{
  test.skip(!process.env.FIXRATE_GATEWAY_E2E,'Requires disposable gateway TEST database');
  expect(process.env.FIXRATE_BASE_URL).toBe('http://127.0.0.1:8885');
  const fixture=JSON.parse(await readFile('reports/gateway-qa-cases.json','utf8'))[String(width)];
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  const login=await context.request.post('/api/v1/auth/login',{data:{email:fixture.email,password:'Test-Requirements-2026!'}});expect(login.ok()).toBe(true);const auth=await login.json();
  const prefix='/api/v1/maintenance',headers={'X-CSRF-Token':auth.csrfToken};
  const post=async(path:string,data:unknown)=>{const response=await context.request.post(prefix+path,{data,headers});expect(response.ok(),await response.text()).toBe(true);return response.json();};
  try{
    // Only disposable TEST records are created. Each viewport has its own binding.
    const equipment=await post('/equipment',{system_id:fixture.system,equipment_type_id:fixture.type,asset_code:`TEST-GATEWAY-${width}-${Date.now()}`,name:`TEST gateway pump ${width}`,commissioned_on:'2026-01-01'});
    const configured=await post(`/equipment/${equipment.equipment_id}/service-configurations`,{code:`TEST-PUBLISH-${width}`,title:`TEST pump inspection ${width}`,instructions:'TEST ONLY approved inspection procedure',maintenance_type:'ТО2',pattern:{frequency:'dates',anchor_date:'2027-01-10',dates:['2027-01-10'],weekend_policy:'none'},valid_from:'2027-01-01',crew_size:1,norm_value:'2',norm_unit:'person_hour',duration_minutes:120,qualification_ids:[],checklist:[{text:'TEST ONLY confirm pump inspection',answer_kind:'boolean',required:true}],allowed_lead_days:0,enabled:true,methodology_ref:'TEST ONLY approved source methodology'});
    const input={kind:'portfolio',requirements:{starts_on:'2027-01-01',ends_on:'2027-01-31',include_regulations:true,binding_ids:[configured.binding_id]},policy:{format_version:2,capacity_status:'confirmed',capacity_hours_per_24h:'24',capacity_confirmed:true,capacity_ref:'TEST ONLY synthetic capacity',access_status:'confirmed',access_mode:'unrestricted',access_ref:'TEST ONLY approved synthetic access'}};
    const preview=await post('/portfolio-plans/preview',input);expect(preview.can_save).toBe(true);
    let record=await post('/portfolio-plans',{input,preview_sha256:preview.input_sha256,idempotency_key:crypto.randomUUID(),title:`TEST gateway plan ${width}`,reason:'TEST ONLY reviewed binding scope'});
    const root=preview.items[0];const segmentResponse=await context.request.get(prefix+`/draft-plans/${record.draft_id}/occurrences/${root.occurrence_id}/segments`);expect(segmentResponse.ok()).toBe(true);const segments=await segmentResponse.json();
    const workersResponse=await context.request.get(prefix+'/draft-plans/choices/workers');expect(workersResponse.ok()).toBe(true);const people=await workersResponse.json();expect(people.total).toBeGreaterThanOrEqual(2);
    record=await post(`/draft-plans/${record.draft_id}/placements`,{expected_revision:1,segment_id:segments.items[0].segment_id,start_local:'2027-01-10T09:00',end_local:'2027-01-10T11:00',worker_ids:[people.items[0].id],reason:'TEST ONLY explicit approved candidate'});
    await page.setViewportSize({width,height:900});
    await page.goto(`/planning?mode=requirements&portfolio=${record.draft_id}&portfolio_revision=${record.revision}&portfolio_view=publish`);
    const panel=page.getByRole('region',{name:'Утверждение и публикация плана'});
    await panel.getByRole('button',{name:'Подготовить предложение к публикации'}).click();
    await panel.getByRole('button',{name:new RegExp(`TEST-PUBLISH-${width} · TEST pump inspection ${width}`)}).click();
    await expect(panel).toContainText('TEST ONLY approved inspection procedure');
    await expect(panel).toContainText('TEST ONLY confirm pump inspection');
    await panel.getByLabel('Меры безопасности для регламента').fill('TEST ONLY apply approved isolation procedure');
    await panel.getByLabel('Примечание инженера для регламента').fill('TEST ONLY verify the pump identification first');
    await panel.getByLabel('Состав и границы публикации').fill('TEST ONLY one pump, confirmed original date and real regulation');
    await panel.getByLabel('Основание предложения').fill('TEST ONLY reviewed placement and source');
    await panel.getByRole('button',{name:'Сохранить предложение на утверждение'}).click();
    const proposal=panel.getByRole('region',{name:'Предложение публикации'});
    await expect(proposal.getByRole('status',{name:'Состояние предложения'})).toContainText('Ожидает утверждения');
    await expect(proposal).toContainText('Регламентных работ: 1');
    await proposal.getByRole('button',{name:'Проверить инструкцию и чек-лист'}).click();
    await expect(proposal.getByRole('region',{name:'Утверждаемая инструкция'})).toContainText('TEST ONLY verify the pump identification first');
    await proposal.getByLabel('Основание решения главного инженера').fill('TEST ONLY reviewed exact scope and resources');
    await proposal.getByRole('checkbox',{name:'Проверены выбранный состав, ограничения, инструкции, чек-листы и назначения'}).check();
    await proposal.getByRole('button',{name:'Утвердить предложение',exact:true}).click();
    await expect(proposal.getByRole('status',{name:'Состояние предложения'})).toContainText('Утверждено');
    await expect(proposal.getByRole('button',{name:'Опубликовать утверждённый план'})).toBeDisabled();
    await proposal.getByRole('checkbox',{name:'Создать утверждённые задания и назначения в рабочем календаре и уведомить исполнителей'}).check();
    await proposal.getByRole('button',{name:'Опубликовать утверждённый план'}).click();
    await expect(proposal.getByRole('status',{name:'Состояние предложения'})).toContainText('Опубликовано');
    await expect(proposal.getByRole('link',{name:'Открыть календарь'})).toBeVisible();
    const calendar=await context.request.get(prefix+'/ui/calendar?year=2027&month=1');expect(calendar.ok()).toBe(true);
    const items=await calendar.json();const tasks=items.filter((x:{operationCode:string})=>x.operationCode===`TEST-PUBLISH-${width}`);expect(tasks).toHaveLength(1);expect(tasks[0].equipmentId).toBe(equipment.equipment_id);
    const ledger=await post('/planning-requirements/preview',input.requirements);expect(ledger.items[0].state).toBe('existing');
    await page.reload();await panel.getByRole('button',{name:/версия 2 · Опубликовано/}).click();
    await expect(proposal.getByRole('status',{name:'Состояние предложения'})).toContainText('Опубликовано');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:info.outputPath(`gateway-${width}.png`)});expect(errors).toEqual([]);
  }finally{await context.request.post('/api/v1/auth/logout',{data:{},headers});}
});
