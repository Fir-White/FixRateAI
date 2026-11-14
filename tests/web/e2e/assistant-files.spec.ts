import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import path from 'node:path';
test.describe('complete assistant file workflow on isolated TEST stand',()=>{
  test.skip(!process.env.FIXRATE_ASSISTANT_QA,'Requires isolated assistant QA');
  for(const width of [1440,390,320])test(`file preview, confirmed import and download at ${width}px`,async({page,context},info)=>{
    const fixture=JSON.parse(readFileSync('reports/assistant-qa-cases.json','utf8'))[String(width)],base=process.env.FIXRATE_BASE_URL!;
    const auth=await context.request.post(base+'/api/v1/auth/login',{data:{email:fixture.email,password:'Test-Requirements-2026!'}});expect(auth.ok()).toBeTruthy();const csrf=(await auth.json()).csrfToken;
    await page.setViewportSize({width,height:900});const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto('/assistant');
    await page.getByLabel('Прикрепить файл').setInputFiles(path.resolve(`reports/assistant-import-fixtures/${width}.xlsx`));
    await expect(page.getByRole('list',{name:'Вложения диалога'})).toContainText(`${width}.xlsx`);
    let listing=await context.request.get(base+'/api/v1/maintenance/equipment?'+new URLSearchParams({q:'XLS-1'}));expect((await listing.json()).items.filter((item:{asset_code:string})=>item.asset_code==='XLS-1')).toHaveLength(0);
    const input=page.getByLabel('Сообщение помощнику');await input.fill('TEST ONLY import this attached registry');await page.getByRole('button',{name:'Отправить',exact:true}).click();
    const proposal=page.getByRole('region',{name:'Предложение: Применить проверенный импорт реестра'});await expect(proposal).toBeVisible();await expect(proposal).toContainText(`${width}.xlsx`);
    await page.reload();await expect(proposal).toBeVisible();await proposal.getByRole('checkbox').check();await proposal.getByRole('button',{name:'Подтвердить и выполнить'}).click();await expect(proposal.getByRole('status')).toHaveText('Выполнено');
    listing=await context.request.get(base+'/api/v1/maintenance/equipment?'+new URLSearchParams({q:'XLS-1'}));expect((await listing.json()).items.filter((item:{asset_code:string})=>item.asset_code==='XLS-1')).toHaveLength(1);
    await input.fill('TEST ONLY export registry');await page.getByRole('button',{name:'Отправить',exact:true}).click();
    const download=page.getByRole('link',{name:'Выгрузить реестр или шаблон Excel',exact:true});await expect(download).toBeVisible();
    const resource=await context.request.get(base+(await download.getAttribute('href')));expect(resource.ok()).toBeTruthy();expect((await resource.body()).subarray(0,2).toString()).toBe('PK');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);expect(errors).toEqual([]);await page.screenshot({path:info.outputPath(`assistant-files-${width}.png`),fullPage:true});
    await context.request.post(base+'/api/v1/auth/logout',{data:{},headers:{'X-CSRF-Token':csrf}});
  });
});
