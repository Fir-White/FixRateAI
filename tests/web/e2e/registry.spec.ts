import { randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { test, expect, type Page } from '@playwright/test';

async function csrf(page: Page) {return page.evaluate(()=>decodeURIComponent(document.cookie.split('; ').find(s=>s.startsWith('fixrate_csrf='))!.split('=')[1]));}
for(const width of [1440,390]) {
  test(`registry manual entry, part usage, replacement and Excel survive reload at ${width}px`,async({page},testInfo)=>{
    test.skip(!process.env.FIXRATE_TEST_PASSWORD || !process.env.FIXRATE_REGISTRY_E2E, 'Requires the isolated registry test application');
    const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
    await page.setViewportSize({width,height:900});
    await page.goto('/login');
    await page.getByLabel('Email',{exact:true}).fill('fixrate-demo-chief_engineer@example.test');
    await page.getByLabel('Пароль',{exact:true}).fill(process.env.FIXRATE_TEST_PASSWORD!);
    await page.getByRole('button',{name:'Войти',exact:true}).click();
    await expect(page).not.toHaveURL(/\/login$/);
    await page.goto('/equipment');
    await expect(page.getByRole('heading',{name:'Работы + реестр оборудования',exact:true})).toBeVisible();
    await page.getByRole('link',{name:'Добавить оборудование',exact:true}).click();
    const asset='REG-'+randomUUID().slice(0,8), name='Насос '+asset;
    await page.getByLabel('Инвентарный номер',{exact:true}).fill(asset);
    await page.getByLabel('Название оборудования',{exact:true}).fill(name);
    const system=await page.getByLabel('Инженерная система',{exact:true}).inputValue();
    await page.getByRole('button',{name:'Сохранить оборудование',exact:true}).click();
    await expect(page.getByText('Оборудование сохранено',{exact:true})).toBeVisible();
    const equipmentId=new URL(page.url()).searchParams.get('equipment')!;
    const day=new Date().toISOString().slice(0,10);
    const response=await page.request.post(`/api/v1/maintenance/equipment/${equipmentId}/service-configurations`,{headers:{'X-CSRF-Token':await csrf(page)},data:{code:asset+'-TO',title:'Проверка насоса',instructions:'Сверить показатели с паспортом',maintenance_type:'ТО3',pattern:{frequency:'month',interval:3,anchor_date:day,weekend_policy:'none'},valid_from:day,crew_size:2,norm_value:'4',norm_unit:'person_hour',duration_minutes:120,qualification_ids:[],checklist:[{text:'Сверить показатели'}],allowed_lead_days:0,enabled:false}});
    expect(response.status()).toBe(201);
    await page.goto('/equipment');
    await page.getByText('Группы инженерных систем',{exact:true}).click();
    const systems=await page.request.get('/api/v1/maintenance/registry');
    const systemName=(await systems.json()).systems.find((s:{id:string})=>s.id===system).name;
    await page.getByLabel(`Группа системы ${systemName}`,{exact:true}).selectOption('water');
    await page.getByRole('tab',{name:/Вода/}).click();
    const row=page.getByRole('row').filter({hasText:asset});
    await expect(row).toContainText('ТО3');await expect(row).toContainText('4 чел.-ч');
    await row.getByRole('button',{name:'Детали и наработка',exact:true}).click();
    const panel=page.getByRole('region',{name:'Детали и наработка',exact:true});
    await panel.getByRole('button',{name:'Установить деталь',exact:true}).click();
    await panel.getByLabel('Позиция в оборудовании',{exact:true}).fill('bearing-1');
    await panel.getByLabel('Название детали',{exact:true}).fill('Подшипник тестовый');
    await panel.getByLabel('Наработка при установке',{exact:true}).fill('50');
    await panel.getByLabel('Норматив ресурса, если известен',{exact:true}).fill('100');
    await panel.getByLabel('Источник норматива ресурса',{exact:true}).fill('Тестовый паспорт');
    await panel.getByRole('button',{name:'Сохранить деталь',exact:true}).click();
    await expect(panel.getByRole('heading',{name:'Подшипник тестовый',exact:true})).toBeVisible();
    await panel.getByRole('button',{name:'Внести наработку',exact:true}).click();
    await panel.getByLabel('Суммарная наработка',{exact:true}).fill('75');
    await panel.getByLabel('Примечание к показанию',{exact:true}).fill('Ручная сверка журнала');
    await panel.getByRole('button',{name:'Сохранить показание',exact:true}).click();
    await expect(panel.getByText('75 ч',{exact:true})).toBeVisible();
    await page.reload();await page.getByRole('tab',{name:/Вода/}).click();
    await page.getByRole('row').filter({hasText:asset}).getByRole('button',{name:'Детали и наработка',exact:true}).click();
    await expect(panel.getByText('75 ч',{exact:true})).toBeVisible();
    await panel.getByRole('button',{name:'Заменить деталь',exact:true}).click();
    await panel.getByLabel('Причина замены',{exact:true}).fill('Учебная замена');
    await panel.getByLabel('Наработка при установке',{exact:true}).fill('0');
    await panel.getByRole('button',{name:'Сохранить деталь',exact:true}).click();
    await expect(panel.getByRole('heading',{name:'Подшипник тестовый',exact:true})).toHaveCount(2);
    await expect(panel.getByText('75 ч',{exact:true})).toBeVisible();await expect(panel.getByText('0 ч',{exact:true})).toBeVisible();
    const downloadEvent=page.waitForEvent('download');await page.getByRole('button',{name:'Экспорт реестра',exact:true}).click();
    const download=await downloadEvent;expect(download.suggestedFilename()).toBe('fixrate-registry.xlsx');
    const exported=await readFile((await download.path())!);expect(exported.subarray(0,2).toString()).toBe('PK');
    await page.getByText('Импортировать оборудование, работы и детали',{exact:true}).click();
    await page.getByLabel('Excel реестра',{exact:true}).setInputFiles({name:'registry.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:exported});
    await page.getByRole('button',{name:'Проверить файл',exact:true}).click();
    await expect(page.getByRole('button',{name:'Сохранить проверенные изменения',exact:true})).toBeEnabled();
    await page.screenshot({path:testInfo.outputPath('registry.png'),fullPage:true});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  });
}

test('login selects an authorized building by name instead of a raw UUID',async({page,context})=>{
  test.skip(!process.env.FIXRATE_BASE_URL,'Requires the built application');
  const first='10000000-0000-4000-8000-000000000001',second='10000000-0000-4000-8000-000000000002';
  let selected='';
  const profile={userId:'qa-multisite',siteId:second,name:'Техник QA',email:'multisite@example.test',role:'executor',siteName:'Второй корпус',timezone:'UTC'};
  await context.route('**/api/**',route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==='/api/v1/auth/login'){
      const body=route.request().postDataJSON();
      if(!body.site_id)return route.fulfill({status:409,json:{detail:'Укажите site_id: у пользователя несколько объектов'}});
      selected=body.site_id;return route.fulfill({json:{profile}});
    }
    if(path==='/api/v1/auth/sites')return route.fulfill({json:[{site_id:first,name:'Первый корпус'},{site_id:second,name:'Второй корпус'}]});
    if(path==='/api/v1/auth/session')return route.fulfill(selected?{json:{profile}}:{status:401,json:{detail:'Нет сессии'}});
    return route.fulfill({json:[]});
  });
  await page.setViewportSize({width:390,height:900});await page.goto('/login');
  await page.getByLabel('Email',{exact:true}).fill('multisite@example.test');
  await page.getByLabel('Пароль',{exact:true}).fill('test-multisite-password');
  await page.getByRole('button',{name:'Войти',exact:true}).click();
  await page.getByLabel('Здание',{exact:true}).selectOption({label:'Второй корпус'});
  await page.getByRole('button',{name:'Войти',exact:true}).click();
  await expect(page).toHaveURL(/\/executor$/);expect(selected).toBe(second);
});
