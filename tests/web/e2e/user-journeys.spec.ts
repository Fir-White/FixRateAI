import {test,expect} from '@playwright/test';

const homes:Record<string,string>={director:'/director',chief_engineer:'/chief-engineer',engineer:'/engineer',executor:'/executor',dispatcher:'/dispatcher',admin:'/admin'};
for(const [role,home] of Object.entries(homes)){
  test(`${role}: task-based navigation and permitted sections`,async({page,context})=>{
    test.skip(!process.env.FIXRATE_BASE_URL,'Requires the production SPA');
    const profile={role,userId:role,siteId:'journey-site',siteName:'Объект проверки',timezone:'UTC',name:'Проверяющий',email:'qa@example.test'};
    const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
    await context.route('**/api/**',route=>{
      const path=new URL(route.request().url()).pathname;
      if(path==='/api/v1/auth/session')return route.fulfill({json:{profile}});
      if(path==='/api/v1/maintenance/catalog-imports')return route.fulfill({json:{items:[],total:0}});
      return route.fulfill({json:[]});
    });
    await page.goto('/');await expect(page).toHaveURL(new RegExp(home+'$'));
    const menu=page.getByRole('navigation',{name:'Основная навигация'});
    if(role==='executor'){
      await expect(page.getByRole('heading',{name:'Мои задания'})).toBeVisible();
      await expect(menu.getByRole('link')).toHaveCount(4);
      await expect(menu.getByRole('link',{name:'Планирование ТО'})).toHaveCount(0);
      await menu.getByRole('link',{name:'Мой календарь'}).click();
      await expect(page.getByRole('navigation',{name:'Разделы планирования'})).toHaveCount(0);
      await page.goto('/planning');await expect(page.getByRole('heading',{name:'Раздел недоступен'})).toBeVisible();
    }else{
      const shortcuts=page.getByRole('navigation',{name:'Основные задачи'});
      if(role==='admin'||role==='director')await expect(shortcuts).toBeVisible();
      else await expect(shortcuts).toHaveCount(0);
      await menu.getByRole('link',{name:'Планирование ТО'}).click();
      await expect(page.getByRole('heading',{name:'Планирование ТО',exact:true})).toBeVisible();
      const sections=page.getByRole('navigation',{name:'Разделы планирования'});
      await expect(sections.getByRole('link',{name:'Планы из Excel'})).toHaveAttribute('aria-current','page');
      if(role==='admin'){
        await expect(sections.getByRole('link',{name:'Действующий календарь'})).toHaveCount(0);
        await expect(sections.getByRole('link',{name:'AI-прогнозы'})).toHaveCount(0);
      }else{
        await sections.getByRole('link',{name:'Действующий календарь'}).click();
        await expect(menu.getByRole('link',{name:'Планирование ТО'})).toHaveAttribute('aria-current','page');
        await expect(sections.getByRole('link',{name:'Действующий календарь'})).toHaveAttribute('aria-current','page');
      }
    }
    expect(errors).toEqual([]);
  });
}

for(const width of [1440,390,320]){
  test(`isolated saved Excel → plan → stages → reload, without business mutations at ${width}px`,async({page,context},testInfo)=>{
    test.skip(!process.env.FIXRATE_JOURNEY_LIVE,'Requires the prepared manual QA fixture');
    expect(['http://127.0.0.1:8875','http://127.0.0.1:8890']).toContain(process.env.FIXRATE_BASE_URL);
    await page.setViewportSize({width,height:900});
    const errors:string[]=[],writes:string[]=[];page.on('pageerror',error=>errors.push(error.message));
    page.on('request',request=>{const path=new URL(request.url()).pathname;if(path.startsWith('/api/v1/maintenance/')&&!['GET','HEAD'].includes(request.method()))writes.push(path);});
    const login=await context.request.post('/api/v1/auth/login',{data:{email:'chief@test.local',password:'Test-FixRate-2026!'}});expect(login.ok()).toBe(true);
    const auth=await login.json();
    try{
      await page.goto('/');
      const openMenu=page.getByRole('button',{name:'Открыть меню',exact:true});
      if(width<768)await openMenu.click();
      await page.getByRole('navigation',{name:'Основная навигация'}).getByRole('link',{name:'Планирование ТО',exact:true}).click();
      const file=page.getByRole('button',{name:/TEST_HVAC.xlsx · 217 операций/});await expect(file).toBeVisible();
      await expect(page.getByLabel('Excel каталога СВиК')).toHaveCount(0);
      await page.screenshot({path:testInfo.outputPath(`planning-files-${width}.png`)});
      await file.click();await expect(page).toHaveURL(/catalog=/);
      await page.getByRole('button',{name:'Перейти к плану →'}).click();
      await page.getByRole('button',{name:/ТЕСТ — одно ТО за 1–10 января · версия/}).click();
      await expect(page.getByRole('region',{name:'Сохранённая версия плана'})).toBeVisible();
      await expect(page).toHaveURL(/draft=.*revision=/);
      await page.getByRole('button',{name:'Даты и бригады',exact:true}).click();
      await expect(page.getByRole('button',{name:'Рассчитать два варианта'})).toBeVisible();
      await page.getByRole('button',{name:'Утверждение и выпуск',exact:true}).click();
      await page.getByRole('button',{name:'Подготовить предложение к публикации'}).click();
      await page.getByLabel('Основание предложения').fill('Локальный ввод, без сохранения');
      await page.getByRole('button',{name:'Состав работ',exact:true}).click();
      await expect(page.getByLabel('Основание предложения')).not.toBeVisible();
      await page.getByRole('button',{name:'Утверждение и выпуск',exact:true}).click();
      await expect(page.getByLabel('Основание предложения')).toHaveValue('Локальный ввод, без сохранения');
      await page.getByRole('button',{name:'Даты и бригады',exact:true}).click();
      const address=page.url();await page.reload();await expect(page).toHaveURL(address);
      await expect(page.getByRole('button',{name:'Рассчитать два варианта'})).toBeVisible();
      await page.goBack();await expect(page.getByRole('button',{name:'Подготовить предложение к публикации'})).toBeVisible();
      await page.goForward();await expect(page.getByRole('button',{name:'Рассчитать два варианта'})).toBeVisible();
      await page.screenshot({path:testInfo.outputPath(`planning-stages-${width}.png`)});
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
      expect(writes).toEqual([]);expect(errors).toEqual([]);
    }finally{await context.request.post('/api/v1/auth/logout',{headers:{'X-CSRF-Token':auth.csrfToken}});}
  });
}
