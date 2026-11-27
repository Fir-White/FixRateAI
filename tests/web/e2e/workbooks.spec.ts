import { execFileSync } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { test, expect } from '@playwright/test';

const python = process.env.FIXRATE_XLSX_PYTHON;
const privateBooks: string[] = JSON.parse(process.env.FIXRATE_OFFICE_PRIVATE_BOOKS ?? '[]');
const pythonEnv = {...process.env, PYTHONPATH: resolve('../backend')};
const sha256 = (data: Buffer) => createHash('sha256').update(data).digest('hex');
const build = `
from app.catalog_excel import NS, read_workbook, write_workbook
from base64 import b64encode
from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED
output = BytesIO()
with ZipFile(BytesIO(write_workbook({'Inputs': [['marker', 8]], 'Totals': [['result', 16]]}))) as source:
    with ZipFile(output, 'w', ZIP_DEFLATED) as target:
        for name in source.namelist():
            data = source.read(name)
            if name.startswith('xl/worksheets/'):
                sheet = ET.fromstring(data)
                cell = next(c for c in sheet.iter(f'{{{NS}}}c') if c.attrib['r'] == 'B1')
                cell.clear()
                cell.set('r', 'B1')
                is_formula = name.endswith('sheet2.xml')
                if is_formula:
                    ET.SubElement(cell, f'{{{NS}}}f').text = 'Inputs!B1*2'
                ET.SubElement(cell, f'{{{NS}}}v').text = '16' if is_formula else '8'
                data = ET.tostring(sheet, encoding='utf-8')
            target.writestr(name, data)
assert read_workbook(output.getvalue(), provenance=True)['Totals'][0][1]['B']['formula_text'] == 'Inputs!B1*2'
print(b64encode(output.getvalue()).decode('ascii'))
`;
const inspect = `
from app.catalog_excel import read_workbook
import json, sys
files = read_workbook(sys.stdin.buffer.read(), provenance=True)
first = dict(files['Inputs'])
second = dict(files['Totals'])[1]
print(json.dumps([first[1]['B']['value'], second['B']['formula_text'], second['B']['value'],
                  [first[row][col]['value'] for row in (2,3) for col in ('B','C')]]))
`;

for (const width of [1440,390]) {
  test(`ONLYOFFICE сохраняет отдельную XLSX-версию и формулу при ширине ${width}`,async ({page,context})=>{
    test.skip(!process.env.FIXRATE_TEST_PASSWORD||!python||!process.env.FIXRATE_OFFICE_E2E,'Нужен изолированный локальный ONLYOFFICE');
    test.setTimeout(95_000);
    await page.setViewportSize({width,height:900});
    const original=Buffer.from(execFileSync(python!,['-c',build.replace("'marker'",`'${randomUUID()}'`)],{env:pythonEnv,encoding:'utf8'}).trim(),'base64');
    await page.goto('/login');
    await page.getByLabel('Email',{exact:true}).fill('fixrate-demo-chief_engineer@example.test');
    await page.getByLabel('Пароль',{exact:true}).fill(process.env.FIXRATE_TEST_PASSWORD!);
    await page.getByRole('button',{name:'Войти',exact:true}).click();
    await expect(page).not.toHaveURL(/\/login$/);
    await page.goto('/planning?mode=workbooks');
    await page.getByLabel('Исходный XLSX',{exact:true}).setInputFiles({name:'synthetic-formula.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:original});
    const uploaded=page.waitForResponse(response=>response.request().method()==='POST'&&response.url().endsWith('/workbooks'));
    await page.getByRole('button',{name:'Загрузить книгу',exact:true}).click();
    const uploadResult=await uploaded;
    expect(uploadResult.status(),uploadResult.ok()?'':await uploadResult.text()).toBe(201);
    await expect(page).toHaveURL(/version=1/);
    const initial=page.url(), download=await page.getByRole('link',{name:'Скачать XLSX',exact:true}).getAttribute('href');
    const responses:string[]=[];
    page.on('response',response=>{
      const {pathname}=new URL(response.url());
      if(response.status()>=400&&pathname.startsWith('/api/')) responses.push(`${response.status()} ${pathname}`);
    });
    await page.getByRole('button',{name:'Редактировать книгу',exact:true}).click();
    const dialog=page.getByRole('dialog');
    const save=dialog.getByRole('button',{name:'Сохранить новую версию',exact:true});
    await expect(save).toBeEnabled({timeout:50_000});
    expect(await page.locator('script[src*="/api/documents/api.js"]').count()).toBe(0);
    const iframe=dialog.frameLocator('iframe[title="Локальный редактор Excel"]').frameLocator('iframe');
    const box=iframe.locator('#ce-cell-name input, input#ce-cell-name').first();
    await context.grantPermissions(['clipboard-read','clipboard-write'],{origin:new URL(page.url()).origin});
    await box.fill('B1');
    await box.press('Enter');
    await page.evaluate(()=>navigator.clipboard.writeText('12'));
    await page.keyboard.press('Control+v');
    await box.fill('B2');
    await box.press('Enter');
    await page.evaluate(()=>navigator.clipboard.writeText('31\t32\n41\t42'));
    await page.keyboard.press('Control+v');
    if (width===390) {
      await expect(iframe.locator('#status-math-box')).toBeHidden();
    }
    await iframe.locator('#statusbar_bottom [tabtitle="Totals"]').click({timeout:8000});
    await box.fill('B1');
    await box.press('Enter');
    await page.keyboard.press('Control+c');
    await expect.poll(async()=> (await page.evaluate(()=>navigator.clipboard.readText())).trim(),{timeout:5000}).toBe('24');
    await expect(save).toBeEnabled({timeout:20000});
    await save.click();
    await expect(page.getByText('Версия 2 сохранена. Оригинал не изменился.',{exact:true}),responses.join('\n')).toBeVisible({timeout:50000});
    const revised=await page.getByRole('link',{name:'Скачать XLSX',exact:true}).getAttribute('href');
    const downloaded=await page.request.get(revised!);
    const values=execFileSync(python!,['-c',inspect],{env:pythonEnv,input:await downloaded.body()}).toString();
    expect(JSON.parse(values)).toEqual(['12','Inputs!B1*2','24',['31','32','41','42']]);
    expect(await (await page.request.get(download!)).body()).toEqual(original);
    await page.reload();
    await expect(page.getByText('Версия 2',{exact:true}).first()).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL(initial);
    await expect(page.getByText('Версия 1 · оригинал',{exact:true}).first()).toBeVisible();
    await page.goForward();
    await expect(page).toHaveURL(/version=2/);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  });
}

test('ONLYOFFICE открывает обе переданные книги без внешних подключений',async({page})=>{
  test.skip(!process.env.FIXRATE_OFFICE_E2E||!process.env.FIXRATE_TEST_PASSWORD||privateBooks.length!==2,'Нужны два файла на изолированном стенде');
  const target=new URL(process.env.FIXRATE_BASE_URL!);
  expect(target.hostname).toBe('127.0.0.1');
  expect(target.port).toBe('18086');
  test.setTimeout(120000);
  await page.goto('/login');
  await page.getByLabel('Email',{exact:true}).fill('fixrate-demo-chief_engineer@example.test');
  await page.getByLabel('Пароль',{exact:true}).fill(process.env.FIXRATE_TEST_PASSWORD!);
  await page.getByRole('button',{name:'Войти',exact:true}).click();
  await expect(page).not.toHaveURL(/\/login$/);
  for (const [index,filename] of privateBooks.entries()) {
    const original=await readFile(filename);
    await page.goto('/planning?mode=workbooks');
    await page.getByLabel('Исходный XLSX',{exact:true}).setInputFiles({name:`input-compatible-${index+1}.xlsx`,mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:original});
    await page.getByRole('button',{name:'Загрузить книгу',exact:true}).click();
    await expect(page).toHaveURL(/version=1/);
    const download=await page.getByRole('link',{name:'Скачать XLSX',exact:true}).getAttribute('href');
    expect(sha256(await (await page.request.get(download!)).body())).toBe(sha256(original));
    await page.getByRole('button',{name:'Редактировать книгу',exact:true}).click();
    const editor=page.getByRole('dialog');
    await expect(editor.getByRole('button',{name:'Сохранить новую версию'})).toBeEnabled({timeout:45_000});
    await expect(editor.getByText(/Подключения к внешним данным отключены/)).toBeVisible();
    await editor.getByRole('button',{name:'Закрыть редактор'}).click();
  }
});
