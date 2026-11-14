import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import path from 'node:path';

test.describe('assistant real API with explicitly scripted TEST model',()=>{
  test.skip(!process.env.FIXRATE_ASSISTANT_QA,'Requires isolated assistant QA stand');
  for(const width of [1440,390,320])test(`human approval and saved conversation at ${width}px`,async({page,context},info)=>{
    const cases=JSON.parse(readFileSync(path.resolve('reports/assistant-qa-cases.json'),'utf8'));
    const fixture=cases[String(width)];const base=process.env.FIXRATE_BASE_URL!;
    const auth=await context.request.post(base+'/api/v1/auth/login',{data:{email:fixture.email,password:'Test-Requirements-2026!'}});expect(auth.ok()).toBeTruthy();
    const csrf=(await auth.json()).csrfToken;await page.setViewportSize({width,height:900});
    const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto('/assistant');
    const input=page.getByLabel('Сообщение помощнику');await input.fill(`TEST ONLY create equipment AIQA-${width}`);
    await page.getByRole('button',{name:'Отправить',exact:true}).click();
    await expect(page).toHaveURL(/chat=/);const saved=page.url();
    const proposal=page.getByRole('region',{name:'Предложение: Добавить оборудование'});
    await expect(proposal).toBeVisible();await expect(proposal).toContainText(`AIQA-${width}`);
    const listing=async()=>{const response=await context.request.get(base+'/api/v1/maintenance/equipment');return (await response.json()).items.filter((item:{asset_code:string})=>item.asset_code===`AIQA-${width}`);};
    expect(await listing()).toHaveLength(0);
    await page.reload();await expect(proposal).toBeVisible();
    await expect(proposal.getByRole('button',{name:'Подтвердить и выполнить'})).toBeDisabled();
    await proposal.getByRole('checkbox').check();await proposal.getByRole('button',{name:'Подтвердить и выполнить'}).click();
    await expect(proposal.getByRole('status')).toHaveText('Выполнено');
    expect(await listing()).toHaveLength(1);
    await expect(proposal.getByRole('button',{name:'Подтвердить и выполнить'})).toHaveCount(0);
    await input.fill('TEST ONLY retained composer');
    await page.getByRole('button',{name:/Новый чат/}).first().click();
    await page.goBack();await expect(page).toHaveURL(saved);await expect(input).toHaveValue('TEST ONLY retained composer');
    await input.fill('TEST ONLY fail');await page.getByRole('button',{name:'Отправить',exact:true}).click();
    await expect(page.getByText('Код: AITUNNEL_UNAVAILABLE')).toBeVisible();
    expect(await listing()).toHaveLength(1);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:info.outputPath(`assistant-${width}.png`),fullPage:true});expect(errors).toEqual([]);
    await context.request.post(base+'/api/v1/auth/logout',{data:{},headers:{'X-CSRF-Token':csrf}});
  });
});
