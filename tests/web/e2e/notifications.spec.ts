import { test, expect } from '@playwright/test';

for(const width of [1440,390]){
  test(`notification portal stays ready, scrolls natively and acknowledges writes at ${width}px`,async({page,context},testInfo)=>{
    test.skip(!process.env.FIXRATE_BASE_URL,'Requires the built application');
    await page.setViewportSize({width,height:900});
    let loggedIn=false,reads=0;
    const items=Array.from({length:100},(_,index)=>({id:String(index+1),message:`Фотоотчёт ожидает приёмки ${index+1}`,taskId:null,createdAt:'2026-11-12T06:11:00Z',readAt:index<9?null:'2026-11-12T10:00:00Z'}));
    const profile={userId:'notifications-qa',siteId:'notifications-site',name:'Инженер QA',email:'notifications@example.test',role:'engineer',siteName:'Объект QA',timezone:'Asia/Yekaterinburg'};
    await context.route('**/api/**',async route=>{
      const path=new URL(route.request().url()).pathname;
      if(path==='/api/v1/auth/login'){loggedIn=true;return route.fulfill({json:{profile}});}
      if(path==='/api/v1/auth/session')return route.fulfill(loggedIn?{json:{profile}}:{status:401,json:{detail:'Нет сессии'}});
      if(path==='/api/v1/maintenance/notifications')return route.fulfill({json:items});
      if(path==='/api/v1/maintenance/notifications/1/read'){
        reads++;await new Promise(resolve=>setTimeout(resolve,500));items[0].readAt='2026-11-13T06:00:00Z';return route.fulfill({json:{read:true}});
      }
      return route.fulfill({json:[]});
    });
    await page.goto('/login');await page.getByLabel('Email',{exact:true}).fill(profile.email);await page.getByLabel('Пароль',{exact:true}).fill('notification-qa-password');await page.getByRole('button',{name:'Войти',exact:true}).click();
    const trigger=page.getByRole('button',{name:'Уведомления, непрочитанных: 9'}),panel=page.locator('.inbox-panel');
    await expect(trigger).toBeVisible();
    await expect(panel).toHaveCount(1);
    await expect(panel).toHaveAttribute('hidden');
    // Regression: Tailwind's !important [hidden] rule previously discarded the layout.
    await expect(panel).toHaveCSS('display','flex');await expect(panel).toHaveCSS('visibility','hidden');
    expect(await panel.evaluate(element=>element.closest('.ops-topbar'))).toBeNull();
    const original=await panel.locator('.inbox-item').first().elementHandle();
    await page.locator('.workspace-root').evaluate(root=>{const spacer=document.createElement('div');spacer.style.height='2500px';root.append(spacer);});
    for(let index=0;index<3;index++){
      await trigger.click();await expect(page.getByRole('dialog',{name:'Уведомления',exact:true})).toBeVisible();
      await expect(panel.getByRole('button',{name:'Закрыть уведомления',exact:true})).toBeFocused();
      expect(await panel.locator('.inbox-item').first().evaluate((element,previous)=>element===previous,original)).toBe(true);
      const box=await panel.boundingBox();expect(box!.x).toBeGreaterThanOrEqual(0);expect(box!.x+box!.width).toBeLessThanOrEqual(width);expect(box!.y+box!.height).toBeLessThanOrEqual(900);
      await page.keyboard.press('Escape');await expect(panel).toHaveAttribute('hidden');await expect(trigger).toBeFocused();
    }
    await trigger.click();
    const list=panel.locator('.inbox-list');await list.hover();await page.mouse.wheel(0,450);
    await expect.poll(()=>list.evaluate(element=>element.scrollTop)).toBeGreaterThan(0);
    expect(await page.evaluate(()=>scrollY)).toBe(0);
    await list.evaluate(element=>{element.scrollTop=element.scrollHeight;});await page.mouse.wheel(0,500);await page.waitForTimeout(150);expect(await page.evaluate(()=>scrollY)).toBe(0);
    await panel.locator('.inbox-header').hover();await page.mouse.wheel(0,400);await page.waitForTimeout(150);expect(await page.evaluate(()=>scrollY)).toBe(0);
    await list.evaluate(element=>{element.scrollTop=0;});
    await panel.locator('.inbox-item').filter({hasText:'Фотоотчёт ожидает приёмки 1'}).first().getByRole('button',{name:'Отметить прочитанным',exact:true}).click();
    await expect(page.getByRole('button',{name:'Уведомления, непрочитанных: 8'})).toBeVisible();
    await expect(panel).toHaveAttribute('data-state','open');
    await expect.poll(()=>reads).toBe(1);
    await expect(panel.locator('button:disabled')).toHaveCount(0);
    await page.screenshot({path:testInfo.outputPath('notifications.png')});
    await page.mouse.click(8,850);await expect(panel).toHaveAttribute('hidden');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  });
}
