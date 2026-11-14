import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';

test.describe('unified assistant workspace on isolated TEST data',()=>{
  test.skip(!process.env.FIXRATE_ASSISTANT_QA,'Requires disposable assistant QA stand');
  for(const width of [1440,390,320])test(`blank chat, right history and latest messages at ${width}px`,async({page,context},info)=>{
    const fixture=JSON.parse(readFileSync('reports/assistant-profile-fixture.json','utf8')),base=process.env.FIXRATE_BASE_URL!;
    await page.setViewportSize({width,height:900});await page.emulateMedia({reducedMotion:'reduce'});
    const auth=await context.request.post(base+'/api/v1/auth/login',{data:{email:fixture.email,password:'Test-Requirements-2026!'}});expect(auth.ok()).toBeTruthy();const csrf=(await auth.json()).csrfToken;
    const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto('/assistant');const input=page.getByLabel('Сообщение помощнику');await expect(input).toBeVisible();await expect(input).toHaveValue('');
    await expect(page.getByRole('button',{name:'Фотоанализ',exact:true})).toHaveCount(0);await expect(page.getByRole('button',{name:'Планирование',exact:true})).toHaveCount(0);
    await page.screenshot({path:info.outputPath(`welcome-${width}.png`),fullPage:true});
    const openHistory=async()=>{if(width<1280)await page.getByRole('button',{name:'Открыть историю чатов'}).click();};
    await openHistory();
    if(width>=1280){const rail=await page.getByRole('complementary',{name:'История диалогов'}).boundingBox(),composer=await input.boundingBox();expect(rail!.x).toBeGreaterThan(composer!.x+composer!.width);}
    else{await expect(page.getByRole('dialog',{name:'История диалогов'})).toBeVisible();await page.keyboard.press('Escape');await expect(page.getByRole('button',{name:'Открыть историю чатов'})).toBeFocused();await openHistory();}
    await page.getByRole('button',{name:/TEST ONLY long chat profile/}).click();await expect(page).toHaveURL(new RegExp(`chat=${fixture.thread}`));
    const region=page.getByRole('region',{name:'Сообщения'});await expect(region.locator('article')).toHaveCount(25);
    await expect.poll(()=>region.evaluate(el=>el.scrollHeight-el.clientHeight-el.scrollTop)).toBeLessThan(3);
    await expect(region.locator('time')).toHaveCount(50);await expect(input).toBeInViewport();
    await page.screenshot({path:info.outputPath(`latest-${width}.png`),fullPage:true});
    await region.evaluate(el=>{el.scrollTop=0;});await expect(page.getByRole('button',{name:'К последним сообщениям'})).toBeVisible();
    await input.fill('TEST ONLY unsent draft');expect(await region.evaluate(el=>el.scrollTop)).toBeLessThan(3);
    await page.getByRole('button',{name:/Новый чат/}).first().click();await expect(input).toHaveValue('');await page.goBack();await expect(input).toHaveValue('TEST ONLY unsent draft');
    await expect.poll(()=>region.evaluate(el=>el.scrollHeight-el.clientHeight-el.scrollTop)).toBeLessThan(3);
    await page.reload();await expect(region.locator('article')).toHaveCount(25);await expect.poll(()=>region.evaluate(el=>el.scrollHeight-el.clientHeight-el.scrollTop)).toBeLessThan(3);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);expect(errors).toEqual([]);
    await context.request.post(base+'/api/v1/auth/logout',{data:{},headers:{'X-CSRF-Token':csrf}});
  });
  test('shows real in-flight progress and preserves manual reading position',async({page,context})=>{
    const fixture=JSON.parse(readFileSync('reports/assistant-profile-fixture.json','utf8')),base=process.env.FIXRATE_BASE_URL!;
    await page.setViewportSize({width:390,height:900});
    const auth=await context.request.post(base+'/api/v1/auth/login',{data:{email:fixture.email,password:'Test-Requirements-2026!'}});const csrf=(await auth.json()).csrfToken;
    await page.goto(`/assistant?chat=${fixture.thread}`);const input=page.getByLabel('Сообщение помощнику'),region=page.getByRole('region',{name:'Сообщения'});
    await input.waitFor();const completedBefore=await page.getByText('TEST ONLY progress completed',{exact:true}).count();
    await input.fill('TEST ONLY progress');await input.press('Enter');
    await expect(page.getByRole('status')).toContainText(/Подбираю действия|Сопоставляю данные/);
    await region.evaluate(el=>{el.scrollTop=0;});await expect(page.getByRole('button',{name:'К последним сообщениям'})).toBeVisible();
    await expect(page.getByText('TEST ONLY progress completed',{exact:true})).toHaveCount(completedBefore+1,{timeout:20000});
    expect(await region.evaluate(el=>el.scrollTop)).toBeLessThan(3);
    await page.getByRole('button',{name:'К последним сообщениям'}).click();await expect.poll(()=>region.evaluate(el=>el.scrollHeight-el.clientHeight-el.scrollTop)).toBeLessThan(3);
    await context.request.post(base+'/api/v1/auth/logout',{data:{},headers:{'X-CSRF-Token':csrf}});
  });
});
