import { execFileSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { resolve } from 'node:path';
import { expect, test } from '@playwright/test';

const mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
const note = 'Уточнено из исходной книги при браузерной приёмке';
const build = `
from base64 import b64encode
from app.catalog_excel import write_workbook
print(b64encode(write_workbook({'Сводка': [['Учебный файл', 'MARKER']], 'Изменения нарядов': [[]]})).decode('ascii'))
`;
const readChanges = `
import json, sys
from app.catalog_excel import read_workbook
rows = dict(read_workbook(sys.stdin.buffer.read(), datetime_cells=True)['Изменения нарядов'])
print(json.dumps([[rows[row][col]['value'] for col in 'ABCD'] for row in (1, 2)]))
`;

test('от правки исходного XLSX до обновления того же выпущенного наряда', async ({page,context})=>{
  const fixture = process.env.FIXRATE_OFFICE_ISSUED_ORDER;
  const python = process.env.FIXRATE_XLSX_PYTHON;
  const password = process.env.FIXRATE_TEST_PASSWORD;
  test.skip(!process.env.FIXRATE_OFFICE_E2E||!fixture||!python||!password,'Нужен опубликованный учебный наряд из fixrate-xlsx-check');
  expect(new URL(process.env.FIXRATE_BASE_URL!).origin).toBe('http://127.0.0.1:18086');
  const {chiefEmail,taskId}: {chiefEmail:string;taskId:string} = JSON.parse(fixture!);
  const taskCode=taskId.slice(0,8);
  const pythonEnv={...process.env,PYTHONPATH:resolve('../backend')};
  const original=Buffer.from(execFileSync(python!,['-c',build.replace('MARKER',randomUUID())],{env:pythonEnv,encoding:'utf8'}).trim(),'base64');

  test.setTimeout(100_000);
  await page.setViewportSize({width:1440,height:900});
  await context.grantPermissions(['clipboard-read','clipboard-write'],{origin:'http://127.0.0.1:18086'});
  await page.goto('/login');
  await page.getByLabel('Email',{exact:true}).fill(chiefEmail);
  await page.getByLabel('Пароль',{exact:true}).fill(password!);
  await page.getByRole('button',{name:'Войти',exact:true}).click();
  await expect(page).not.toHaveURL(/\/login$/);
  const task=async()=>{
    const response=await page.request.get(`/api/v1/maintenance/ui/tasks/${taskId}`);
    expect(response.status()).toBe(200);
    return (await response.json()).task;
  };
  const before=await task();
  expect(before).toMatchObject({id:taskId,state:'assigned',scheduledStart:'2027-01-02T09:00:00+05:00'});
  expect(before.assignees).toHaveLength(1);

  await page.goto('/planning?mode=workbooks');
  await page.getByLabel('Исходный XLSX',{exact:true}).setInputFiles({name:'issued-order-qa.xlsx',mimeType:mime,buffer:original});
  await page.getByRole('button',{name:'Загрузить книгу',exact:true}).click();
  await expect(page).toHaveURL(/version=1/);
  const originalUrl=(await page.getByRole('link',{name:'Скачать XLSX',exact:true}).getAttribute('href'))!;
  await page.getByRole('button',{name:'Редактировать книгу',exact:true}).click();
  const dialog=page.getByRole('dialog');
  const save=dialog.getByRole('button',{name:'Сохранить новую версию',exact:true});
  await expect(save).toBeEnabled({timeout:45000});
  const iframe=dialog.frameLocator('iframe[title="Локальный редактор Excel"]').frameLocator('iframe');
  await iframe.locator('#statusbar_bottom [tabtitle="Изменения нарядов"]').click();
  const box=iframe.locator('#ce-cell-name input, input#ce-cell-name').first();
  const selectCell=async (address:string)=>{
    await box.fill(address);
    await box.press('Enter');
  };
  const tray=dialog.getByRole('button',{name:'Правки наряда',exact:true});
  await tray.click();
  await dialog.getByRole('button',{name:'Скопировать заголовки',exact:true}).click();
  const clipboard=()=>page.evaluate(()=>navigator.clipboard.readText());
  await expect.poll(clipboard).toBe('Наряд\tНачало\tПлан, чел.-ч\tПримечание');
  await tray.click();
  await selectCell('A1');
  await page.keyboard.press('Control+v');

  await tray.click();
  await dialog.getByRole('textbox',{name:'Номер, название работы или оборудование'}).fill(taskCode);
  const search=page.waitForResponse(response=>{
    const url=new URL(response.url());
    return url.pathname.endsWith('/workbooks/issued-orders')&&url.searchParams.get('q')===taskCode;
  });
  await dialog.getByRole('button',{name:'Найти выпущенный наряд',exact:true}).click();
  expect((await search).status()).toBe(200);
  await dialog.getByRole('button',{name:`Скопировать строку наряда ${taskCode}`,exact:true}).click();
  await expect.poll(clipboard).toBe(taskId);
  await tray.click();
  await selectCell('A2');
  await page.keyboard.press('Control+v');
  await selectCell('B2');
  // In the Russian spreadsheet locale a dot can turn 3.5 into a date.
  await page.evaluate(value=>navigator.clipboard.writeText(value),`2027-01-02T10:00\t3,5\t${note}`);
  await page.keyboard.press('Control+v');
  await expect(save).toBeEnabled();
  await save.click();
  await expect(page).toHaveURL(/version=2/,{timeout:45000});

  const revisedUrl=(await page.getByRole('link',{name:'Скачать XLSX',exact:true}).getAttribute('href'))!;
  const revised=await page.request.get(revisedUrl);
  expect(revised.status()).toBe(200);
  const rows=JSON.parse(execFileSync(python!,['-c',readChanges],{env:pythonEnv,input:await revised.body(),encoding:'utf8'}));
  expect(rows).toEqual([
    ['Наряд','Начало','План, чел.-ч','Примечание'],
    [taskId,expect.stringMatching(/^2027-01-02T10:00(?::00)?$/),expect.stringMatching(/^3[.,]5$/),note],
  ]);
  expect(await (await page.request.get(originalUrl)).body()).toEqual(original);
  expect(await task()).toMatchObject({revision:before.revision,scheduledStart:before.scheduledStart});

  await page.getByText('Применить к выпущенному наряду',{exact:true}).click();
  const selected=page.getByRole('combobox',{name:'Наряд из сохранённой книги'});
  await expect(selected).toHaveValue('2');
  await expect(selected.locator('option:checked')).toContainText(taskCode);
  await page.getByRole('textbox',{name:'Основание правки'}).fill('Учебный перенос с сохранением исполнителя');
  await page.getByRole('button',{name:'Проверить изменения наряда'}).click();
  const diff=page.getByRole('region',{name:'Изменения выпущенного наряда'});
  await expect(diff).toContainText('2027-01-02 09:00');
  await expect(diff).toContainText('2027-01-02 10:00');
  await expect(diff).toContainText(note);
  const confirm=diff.getByRole('button',{name:'Подтвердить и применить к наряду'});
  await expect(confirm).toBeDisabled();
  expect(await task()).toMatchObject({revision:before.revision,scheduledStart:before.scheduledStart});

  await diff.getByRole('checkbox',{name:/Подтверждаю перенос/}).check();
  await confirm.click();
  const open=page.getByRole('link',{name:'Открыть этот наряд'});
  await expect(open).toHaveAttribute('href',`/tasks/${taskId}`);
  await open.click();
  await expect(page).toHaveURL(new RegExp(`/tasks/${taskId}$`));
  await expect(page.getByText(note,{exact:true})).toBeVisible();
  await expect(page.getByText('3.5 чел.-ч',{exact:true})).toBeVisible();
  const after=await task();
  expect(after).toMatchObject({
    id:taskId,state:'assigned',revision:before.revision+1,planningNote:note,plannedPersonHours:'3.5',
    scheduledStart:'2027-01-02T10:00:00+05:00',scheduledEnd:'2027-01-02T13:00:00+05:00',
    mandatoryDeadlineAt:before.mandatoryDeadlineAt,normHours:before.normHours,
  });
  expect(after.assignees.map((person:{executorId:string})=>person.executorId))
    .toEqual(before.assignees.map((person:{executorId:string})=>person.executorId));
});
