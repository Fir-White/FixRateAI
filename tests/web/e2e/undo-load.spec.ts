import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';

for(const width of [1440,390,320])test(`own undo, exact load, retained form and linked history at ${width}px`,async({page,context},info)=>{
  test.skip(!process.env.FIXRATE_UNDO_LOAD_E2E,'Requires disposable undo/load TEST database');
  expect(process.env.FIXRATE_BASE_URL).toBe('http://127.0.0.1:8885');
  const fixture=JSON.parse(await readFile('reports/gateway-qa-cases.json','utf8'))[String(width)];
  const login=await context.request.post('/api/v1/auth/login',{data:{email:fixture.email,password:'Test-Requirements-2026!'}});expect(login.ok()).toBe(true);const auth=await login.json();
  const prefix='/api/v1/maintenance',headers={'X-CSRF-Token':auth.csrfToken},errors:string[]=[],writes:string[]=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST'&&/publication-proposals|\/assignments/.test(r.url()))writes.push(r.url());});
  const post=async(path:string,data:unknown)=>{const r=await context.request.post(prefix+path,{data,headers});expect(r.ok(),await r.text()).toBe(true);return r.json();};
  try{
    const equipment=await post('/equipment',{system_id:fixture.system,equipment_type_id:fixture.type,asset_code:`TEST-UNDO-${width}-${Date.now()}`,name:`TEST undo pump ${width}`,commissioned_on:'2026-01-01'});
    const rule=await post(`/equipment/${equipment.equipment_id}/service-configurations`,{code:`TEST-UNDO-${width}`,title:`TEST undo inspection ${width}`,instructions:'TEST ONLY procedure',maintenance_type:'ТО2',pattern:{frequency:'dates',anchor_date:'2027-01-10',dates:['2027-01-10'],weekend_policy:'none'},valid_from:'2027-01-01',crew_size:1,norm_value:'2',norm_unit:'person_hour',duration_minutes:120,qualification_ids:[],checklist:[{text:'TEST ONLY inspect pump'}],allowed_lead_days:9,enabled:true,methodology_ref:'TEST ONLY approved methodology'});
    const input={kind:'portfolio',requirements:{starts_on:'2027-01-01',ends_on:'2027-01-31',include_regulations:true,binding_ids:[rule.binding_id]},policy:{format_version:2,capacity_status:'confirmed',capacity_hours_per_24h:'24',capacity_confirmed:true,capacity_ref:'TEST ONLY capacity',access_status:'confirmed',access_mode:'unrestricted',access_ref:'TEST ONLY access'}};
    const preview=await post('/portfolio-plans/preview',input);expect(preview.can_save).toBe(true);
    let record=await post('/portfolio-plans',{input,preview_sha256:preview.input_sha256,idempotency_key:crypto.randomUUID(),title:`TEST undo plan ${width}`,reason:'TEST ONLY initial draft'});
    const r=await context.request.get(prefix+`/draft-plans/${record.draft_id}/occurrences/${preview.items[0].occurrence_id}/segments`),segments=await r.json();expect(r.ok()).toBe(true);
    const w=await context.request.get(prefix+'/draft-plans/choices/workers'),workers=await w.json();expect(w.ok()).toBe(true);
    record=await post(`/draft-plans/${record.draft_id}/placements`,{expected_revision:1,segment_id:segments.items[0].segment_id,start_local:'2027-01-10T09:00',end_local:'2027-01-10T11:00',worker_ids:[workers.items[0].id],locked:true,reason:'TEST ONLY own locked placement'});
    await page.setViewportSize({width,height:900});await page.goto(`/planning?mode=requirements&portfolio=${record.draft_id}&portfolio_revision=2&portfolio_view=load`);
    const saved=page.getByRole('region',{name:'Сохранённая версия плана'}),load=page.getByRole('region',{name:'Нагрузка выбранной версии плана'}),steps=saved.getByRole('navigation',{name:'Этапы работы с планом'});
    await expect(load).toContainText('Альтернативные планы не суммируются');await expect(load.getByRole('list',{name:'Подневная нагрузка'}).getByRole('listitem')).toHaveCount(25);
    await expect(load.getByText('Распределено по датам',{exact:true}).locator('..')).toContainText('2 чел.-ч');
    await load.getByRole('button',{name:/2027-01 · размещено/}).click();await expect(page).toHaveURL(/portfolio_month=2027-01/);
    await page.reload();await expect(load.getByText('Распределено по датам',{exact:true}).locator('..')).toContainText('2 чел.-ч');
    await saved.getByRole('button',{name:'Отменить последнее своё изменение',exact:true}).click();
    const undo=page.getByRole('region',{name:'Отмена собственного изменения'}),reason=undo.getByLabel('Причина отмены изменения');
    await reason.fill('TEST ONLY incorrect placement; restore initial scope');
    await steps.getByRole('button',{name:'Состав работ',exact:true}).click();await steps.getByRole('button',{name:'Нагрузка',exact:true}).click();
    await expect(reason).toHaveValue('TEST ONLY incorrect placement; restore initial scope');
    await saved.getByRole('button',{name:'Отменить последнее своё изменение',exact:true}).click();await saved.getByRole('button',{name:'Отменить последнее своё изменение',exact:true}).click();
    await expect(reason).toHaveValue('TEST ONLY incorrect placement; restore initial scope');
    await undo.getByRole('checkbox',{name:'Подтверждаю восстановление предыдущего состояния новой версией'}).check();
    await expect(undo.getByRole('button',{name:'Отменить изменение новой версией'})).toBeDisabled();
    await undo.getByRole('checkbox',{name:'Разрешаю отменить изменённые закрепления сегментов'}).check();await undo.getByRole('button',{name:'Отменить изменение новой версией'}).click();
    await expect(page).toHaveURL(/portfolio_revision=3/);await expect(saved).toContainText('Восстановлено содержимое версии 1');
    await expect(load.getByText('Осталось распределить',{exact:true}).locator('..')).toContainText('2 чел.-ч');
    await expect(load.getByText('Распределено по датам',{exact:true}).locator('..')).toContainText('0 чел.-ч');
    await saved.getByRole('button',{name:'История версий плана'}).click();await saved.getByRole('button',{name:/Версия 2 ·/}).click();
    await expect(saved).toContainText('Открыта версия для просмотра');await expect(saved.getByRole('button',{name:'Отменить последнее своё изменение',exact:true})).toHaveCount(0);
    await expect(load.getByText('Распределено по датам',{exact:true}).locator('..')).toContainText('2 чел.-ч');
    await page.goBack();await expect(page).toHaveURL(/portfolio_revision=3/);await expect(load.getByText('Осталось распределить',{exact:true}).locator('..')).toContainText('2 чел.-ч');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:info.outputPath(`undo-load-${width}.png`)});
    expect(errors).toEqual([]);expect(writes).toEqual([]);
  }finally{await context.request.post('/api/v1/auth/logout',{data:{},headers});}
});
