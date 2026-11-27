import { test, expect } from '@playwright/test';

test('opens the registry data request without waiting for the route JavaScript', async ({page}) => {
  test.skip(!process.env.FIXRATE_BASE_URL, 'Requires a production SPA build');
  const profile = {userId:'cold-chief',siteId:'cold-site',role:'chief_engineer',name:'Инженер QA',email:'cold@example.test',siteName:'Объект QA',timezone:'UTC'};
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/v1/auth/session') return route.fulfill({json:{profile}});
    if (path === '/api/v1/maintenance/registry') return route.fulfill({json:{site_id:profile.siteId,systems:[],items:[]}});
    return route.fulfill({json:[]});
  });
  let release!: () => void;
  const pending = new Promise<void>(resolve => {release=resolve;});
  let reads=0;
  page.on('request', request => {
    if (new URL(request.url()).pathname==='/api/v1/maintenance/registry') reads++;
  });
  await page.route('**/assets/EquipmentPage-*.js', async route => {
    await pending;
    await route.continue();
  });
  try {
    const script=page.waitForRequest('**/assets/EquipmentPage-*.js',{timeout:10_000});
    await page.goto('/equipment',{waitUntil:'commit'});
    await script;
    await expect.poll(()=>reads,{timeout:2500}).toBe(1);
    const workspace=page.locator('.workspace-root');
    await expect.poll(()=>workspace.evaluate(el=>getComputedStyle(el,'::after').visibility)).toBe('hidden');
  } finally {release();}
  await expect(page.getByRole('textbox',{name:'Поиск по реестру'})).toBeVisible();
  expect(await page.locator('.workspace-root').evaluate(el=>getComputedStyle(el,'::after').visibility)).toBe('visible');
  expect(reads).toBe(1);
});

for (const width of [1440, 390]) {
  test(`large registry bounds DOM, searches all records and reuses scoped reads at ${width}px`, async ({page, context}) => {
    test.skip(!process.env.FIXRATE_BASE_URL, 'Requires a production SPA build');
    await page.setViewportSize({width, height:900});
    await page.clock.setFixedTime(new Date('2026-11-13T12:00:00Z'));
    const errors:string[]=[];page.on('pageerror', error=>errors.push(error.message));
    const profile={userId:'performance-chief',siteId:'performance-site',role:'chief_engineer',name:'Инженер QA',email:'perf@example.test',siteName:'Объект QA',timezone:'UTC'};
    let registryReads=0;
    await context.route('**/api/**', async route=>{
      const path=new URL(route.request().url()).pathname;
      if(path==='/api/v1/auth/session')return route.fulfill({json:{profile}});
      if(path==='/api/v1/auth/sites')return route.fulfill({json:[{site_id:profile.siteId,name:profile.siteName,timezone:'UTC',role:profile.role}]});
      if(path==='/api/v1/maintenance/registry'){
        registryReads++;
        return route.fulfill({json:{site_id:profile.siteId,site_name:profile.siteName,timezone:'UTC',systems:[{id:'electric',name:'Электрика',code:'EL',system_group:'electricity',revision:1,is_active:true}],items:Array.from({length:1000},(_,index)=>({equipment_id:`equipment-${index}`,site_id:profile.siteId,system_id:'electric',asset_code:`EL-${index}`,name:`Насос ${String(index).padStart(4,'0')}`,status:'active',revision:1,services:[],components:[],properties:{}}))}});
      }
      return route.fulfill({json:[]});
    });
    await page.goto('/equipment');
    const rows=page.locator('.registry-table tbody tr');
    await expect(rows).toHaveCount(25);
    await expect(page.getByRole('navigation',{name:'Страницы оборудования'})).toContainText('1–25 из 1000');
    const workspace=page.locator('.workspace-root');
    const glow = await workspace.evaluate(el => ['::before', '::after'].map(pseudo => getComputedStyle(el, pseudo).opacity));
    expect(glow.every(opacity => Number(opacity) > 0 && Number(opacity) < .5)).toBe(true);
    await expect(workspace.locator('canvas')).toHaveCount(0);
    await page.getByRole('button',{name:'Следующая страница оборудования'}).click();
    await expect(rows.first()).toContainText('Насос 0025');
    await page.getByRole('textbox',{name:'Поиск по реестру'}).fill('Насос 0999');
    await expect(rows).toHaveCount(1);await expect(rows).toContainText('EL-999');
    await page.getByRole('textbox',{name:'Поиск по реестру'}).fill('');
    await expect(rows).toHaveCount(25);await expect(rows.first()).toContainText('Насос 0000');
    await page.mouse.move(width-30,400);await page.mouse.wheel(0,500);
    await expect.poll(()=>page.evaluate(()=>window.scrollY)).toBeGreaterThan(0);
    const navigate=async(name:string)=>{
      if(width<1024)await page.getByRole('button',{name:'Открыть меню',exact:true}).click();
      await page.getByRole('link',{name,exact:true}).click();
    };
    await navigate('Задания');await expect(page.locator('.ops-main h1')).toHaveText('Наряды и назначения');
    await navigate('Оборудование');await expect(rows).toHaveCount(25);
    expect(registryReads).toBe(1);
    expect(errors).toEqual([]);
  });
}
