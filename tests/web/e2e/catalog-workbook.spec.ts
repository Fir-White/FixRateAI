import { execFileSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { delimiter, resolve } from 'node:path';
import { expect, test } from '@playwright/test';

const python = process.env.FIXRATE_XLSX_PYTHON;
const password = process.env.FIXRATE_TEST_PASSWORD;
const build = `
from base64 import b64encode
from io import BytesIO
import sys
from zipfile import ZipFile
from tests.fixtures.catalog_source import catalog_book
output = BytesIO(catalog_book(2))
with ZipFile(output, 'a') as package:
    package.comment = sys.argv[1].encode('ascii')
print(b64encode(output.getvalue()).decode('ascii'))
`;

for (const width of [1440,390]) {
  test(`Excel открывается в высоком редакторе под строкой каталога при ${width}px`,async({page,context})=>{
    test.skip(!process.env.FIXRATE_OFFICE_E2E||!python||!password,'Нужен изолированный локальный ONLYOFFICE');
    const origin = 'http://127.0.0.1:18086';
    expect(new URL(process.env.FIXRATE_BASE_URL!).origin).toBe(origin);
    test.setTimeout(110_000);
    await page.setViewportSize({width,height:900});
    const marker = randomUUID().slice(0,8), filename = `catalog-direct-${marker}.xlsx`;
    const data = Buffer.from(execFileSync(python!,['-c',build,marker],{
      env:{...process.env,PYTHONPATH:[resolve('../backend'),resolve('..')].join(delimiter)},encoding:'utf8',
    }).trim(),'base64');
    const button = (name:string)=>page.getByRole('button',{name,exact:true});
    await page.goto('/login');
    await page.getByLabel('Email',{exact:true}).fill('fixrate-demo-chief_engineer@example.test');
    await page.getByLabel('Пароль',{exact:true}).fill(password!);
    await button('Войти').click();
    await expect(page).not.toHaveURL(/\/login$/);
    await page.goto('/planning');
    await button('Загрузить Excel с регламентами').click();
    await page.getByLabel('Excel каталога СВиК').setInputFiles({name:filename,
      mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:data});
    await button('Проверить каталог').click();
    await button('Сохранить каталог-черновик').click();
    await expect(page).toHaveURL(/catalog=/);
    await button('← Все файлы и планы').click();

    const file = page.getByRole('button',{name:new RegExp(filename)});
    const row = page.getByRole('listitem').filter({has:file});
    await expect(row.getByRole('button',{name:'Регламент и план',exact:true})).toBeVisible();
    let editorWrites=0;
    page.on('request',req=>{
      if(req.method()==='POST'&&/\/workbooks\/(?:from-catalog\/|[^/]+\/editor-sessions$)/.test(new URL(req.url()).pathname)) editorWrites++;
    });
    await file.focus();
    const warm=page.locator('iframe[title="Локальный редактор Excel"]');
    await expect(warm).toHaveCount(1);
    await expect(warm).not.toBeVisible();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    expect(editorWrites).toBe(0);
    const initialFrame=await warm.elementHandle();
    const start=performance.now();
    await file.click();
    const dialog=page.getByRole('region',{name:new RegExp(`Редактор Excel: ${filename}`)});
    await dialog.waitFor();
    const shellMs=Math.round(performance.now()-start);
    const dimensions=(await dialog.boundingBox())!;
    expect(dimensions.height).toBeGreaterThanOrEqual(960);
    expect(dimensions.width).toBeLessThanOrEqual(width);
    const rowBox=(await row.boundingBox())!;
    expect(dimensions.y).toBeGreaterThan(rowBox.y);
    expect(dimensions.y+dimensions.height).toBeLessThanOrEqual(rowBox.y+rowBox.height+1);
    const save=dialog.getByRole('button',{name:'Сохранить новую версию',exact:true});
    await expect(save).toBeEnabled({timeout:50_000});
    const readyMs=Math.round(performance.now()-start);
    const frameHeight=(await warm.boundingBox())!.height;
    expect(frameHeight).toBeGreaterThan(650);
    expect(await warm.evaluate((node,initial)=>node===initial,initialFrame)).toBe(true);
    expect(editorWrites).toBe(2);
    expect(new URL(page.url()).searchParams.has('catalog')).toBe(false);
    await expect(dialog.getByRole('heading',{name:`${filename} · версия 1`})).toBeVisible();
    await dialog.getByRole('button',{name:'Закрыть редактор',exact:true}).click();
    await expect(file).toBeFocused();
    await expect(warm).not.toBeVisible();
    const reopened=performance.now();
    await file.click();
    await expect(save).toBeEnabled({timeout:50_000});
    const reopenMs=Math.round(performance.now()-reopened);
    expect(await warm.evaluate((node,initial)=>node===initial,initialFrame)).toBe(true);
    expect(editorWrites).toBe(2);
    const scrollBefore=await page.evaluate(()=>window.scrollY);
    await page.mouse.move(4,450);
    await page.mouse.wheel(0,240);
    await expect.poll(()=>page.evaluate(()=>window.scrollY)).toBeGreaterThan(scrollBefore);
    console.log(JSON.stringify({viewport:width,dialogWidth:Math.round(dimensions.width),dialogHeight:Math.round(dimensions.height),frameHeight:Math.round(frameHeight),shellMs,readyMs,reopenMs}));
    if(width===390){
      await dialog.getByRole('button',{name:'Закрыть редактор',exact:true}).click();
      await expect(file).toBeFocused();
      const versions=await page.request.get('/api/v1/maintenance/workbooks');
      expect(versions.ok()).toBe(true);
      const book=(await versions.json()).items.find((item:{filename:string})=>item.filename===filename);
      expect(book?.version).toBe(1);
      const csrf=(await context.cookies()).find(cookie=>cookie.name==='fixrate_csrf')?.value;
      expect(csrf).toBeTruthy();
      const nextData=Buffer.from(execFileSync(python!,['-c',build,`${marker}-updated`],{
        env:{...process.env,PYTHONPATH:[resolve('../backend'),resolve('..')].join(delimiter)},encoding:'utf8',
      }).trim(),'base64');
      const changed=await page.request.post(`/api/v1/maintenance/workbooks/${book.book_id}/versions/from-file`,{
        headers:{'X-CSRF-Token':csrf!},multipart:{file:{name:filename,mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:nextData},
          expected_version:'1',idempotency_key:randomUUID()},
      });
      expect(changed.status()).toBe(201);
      expect((await changed.json()).version).toBe(2);
      await file.click();
      await expect(dialog.getByRole('heading',{name:`${filename} · версия 2`})).toBeVisible({timeout:15_000});
      await expect(save).toBeEnabled({timeout:50_000});
      expect(await initialFrame!.evaluate(node=>node.isConnected)).toBe(false);
      await dialog.getByRole('button',{name:'Закрыть редактор',exact:true}).click();
      await expect(file).toBeFocused();
      await page.route(`**/workbooks/${book.book_id}/editor-sessions/*`,route=>route.fulfill({
        status:403,json:{detail:'Доступ к редактору отозван'},
      }),{times:1});
      await file.click();
      await expect(dialog.getByRole('alert')).toHaveText('Доступ к редактору отозван');
      await expect(warm).toHaveCount(0);
      await dialog.getByRole('button',{name:'Закрыть редактор',exact:true}).click();
      await row.getByRole('button',{name:'Регламент и план',exact:true}).click();
      await expect(page).toHaveURL(/catalog=/);
      await expect(dialog).toHaveCount(0);
      return;
    }

    await context.grantPermissions(['clipboard-read','clipboard-write'],{origin});
    const sheet=dialog.frameLocator('iframe[title="Локальный редактор Excel"]').frameLocator('iframe');
    const box=sheet.locator('#ce-cell-name input, input#ce-cell-name').first();
    await box.fill('AM1');
    await box.press('Enter');
    await page.evaluate(()=>navigator.clipboard.writeText('37'));
    await page.keyboard.press('Control+v');
    await expect(save).toBeEnabled();
    await save.click();
    await expect(page.getByText('Версия 2 сохранена. Оригинал не изменился.',{exact:false})).toBeVisible({timeout:50_000});
    await expect(page).toHaveURL(/mode=workbooks.*version=2/);
    await page.goBack();
    await file.click();
    await expect(dialog.getByRole('heading',{name:`${filename} · версия 2`})).toBeVisible({timeout:15_000});
    await expect(save).toBeEnabled({timeout:50_000});
  });
}
