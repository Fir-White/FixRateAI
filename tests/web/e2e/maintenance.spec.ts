import { test, expect, type Page } from "@playwright/test";
import { createHash } from "node:crypto";
import path from "node:path";
import fs from 'node:fs/promises';

function demoId(key: string) {
  const hex = createHash("md5").update(`fixrate-demo-${key}`).digest("hex");
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}
async function signIn(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email", {exact: true}).fill(email);
  await page.getByLabel("Пароль", {exact: true}).fill(process.env.FIXRATE_TEST_PASSWORD!);
  await page.getByRole("button", {name: "Войти", exact: true}).click();
  await expect(page).not.toHaveURL(/\/login$/);
}
async function checkpoint(page:Page,state:string){
  const output=process.env.FIXRATE_E2E_OUTPUT;
  if(!output)return;
  const geometry=await page.evaluate(()=>({width:innerWidth,height:innerHeight,y:scrollY}));
  const file=`${state}-${geometry.width}-y${geometry.y}.png`;
  await page.screenshot({path:path.join(output,file),animations:'disabled'});
  await fs.appendFile(path.join(output,'checkpoints.jsonl'),JSON.stringify({state,file,route:new URL(page.url()).pathname,...geometry,source:process.env.FIXRATE_TEST_SOURCE,fixture:'isolated runtime-order',capture:'live viewport',status:'passed'})+'\n');
}
test("real SPA → API → PostgreSQL → photos → ML guardrails → engineer acceptance", async ({browser,viewport,isMobile,hasTouch}) => {
  test.skip(!process.env.FIXRATE_BASE_URL, "Use scripts/verify.py --browser to create a disposable database");
  const errors: string[] = [];
  const contextOptions={viewport:viewport??undefined,isMobile,hasTouch,baseURL:process.env.FIXRATE_BASE_URL};
  const executorContext = await browser.newContext(contextOptions);
  const executor = await executorContext.newPage();
  executor.on("pageerror", error => errors.push(error.message));
  await signIn(executor, "fixrate-demo-1@example.test");
  const configuredViewport=test.info().project.use.viewport;
  if(configuredViewport)expect(await executor.evaluate(()=>innerWidth)).toBe(configuredViewport.width);
  await executor.locator(`a[href="/executor/tasks/${demoId("runtime-order")}"]`).first().click();
  await executor.getByRole("button", {name: "Приступить к работе"}).click();
  await executor.getByRole("checkbox", {name: /Поверхность очищена/}).check();
  await checkpoint(executor,'executor-active');
  await executor.getByLabel("Что выполнено и какие замечания остались").fill("Проверка полного процесса в браузере");
  // Upload must preserve the currently edited checklist and narrative without a manual save.
  const photo = path.resolve(test.info().project.testDir, "../../../data/demo/demo-photo.png");
  for (const phase of ["before", "after"]) {
    await executor.getByRole("combobox", {name: /Этап/}).selectOption(phase);
    await executor.getByLabel("Файл фото").setInputFiles(photo);
    const reply = executor.waitForResponse(r => r.url().endsWith("/photos") && r.request().method() === "POST");
    await executor.getByRole("button", {name: "Загрузить фото"}).click();
    expect((await reply).status()).toBe(200);
    await expect(executor.locator(".evidence-photo img")).toHaveCount(phase === "before" ? 1 : 2);
    await expect(executor.getByLabel("Что выполнено и какие замечания остались")).toHaveValue("Проверка полного процесса в браузере");
    await expect(executor.getByRole("checkbox", {name: /Поверхность очищена/})).toBeChecked();
  }
  await expect(executor.locator(".evidence-photo img")).toHaveCount(2);
  await executor.locator('.evidence-photo').first().scrollIntoViewIfNeeded();
  await checkpoint(executor,'executor-uploaded');
  const submit = executor.waitForResponse(r => r.url().endsWith("/submit"));
  await executor.getByLabel("Что выполнено и какие замечания остались").fill("Последние изменения перед сдачей");
  await executor.getByRole("button", {name: "Сдать работу"}).click();
  await executor.getByRole("dialog", {name: "Передать отчёт инженеру?"}).getByRole("button", {name: "Подтвердить сдачу"}).click();
  expect((await submit).status()).toBe(200);
  await expect(executor.getByRole("button", {name: "Сдать работу"})).toHaveCount(0);
  const engineerContext = await browser.newContext(contextOptions);
  const engineer = await engineerContext.newPage();
  engineer.on("pageerror", error => errors.push(error.message));
  await signIn(engineer, "fixrate-demo-engineer@example.test");
  if(configuredViewport)expect(await engineer.evaluate(()=>innerWidth)).toBe(configuredViewport.width);
  await engineer.goto(`/quality/${demoId("runtime-order")}`);
  await expect(engineer.locator(".evidence-photo img")).toHaveCount(2);
  await expect(engineer.getByText("Последние изменения перед сдачей", {exact: true})).toBeVisible();
  await checkpoint(engineer,'engineer-submitted');
  // No engineer POST or comparability confirmation: submission queues the analysis.
  await expect.poll(async()=> (await (await engineer.request.get(`/api/v1/maintenance/ui/tasks/${demoId("runtime-order")}`)).json()).photoAnalysisStatus,{timeout:30000}).toBe("ready");
  const automaticallyReviewed=await (await engineer.request.get(`/api/v1/maintenance/ui/tasks/${demoId("runtime-order")}`)).json();
  expect(automaticallyReviewed.review.status).toBe("uncertain");
  expect(automaticallyReviewed.review.id).toBeTruthy();
  await expect(engineer.getByRole("checkbox", {name: /Подтверждаю, что фото/})).toHaveCount(0);
  await expect(engineer.getByText("Разбор фотоотчёта",{exact:true})).toBeVisible();
  await engineer.getByLabel(/Причина решения/).fill("Одинаковые учебные фото проверены; это синтетический E2E сценарий.");
  await engineer.getByRole("button", {name: "Вернуть на доработку", exact: true}).click();
  const reject = engineer.waitForResponse(r => r.url().endsWith("/review") && r.request().method() === "POST");
  await engineer.getByRole("dialog").getByRole("button", {name: "Вернуть на доработку", exact: true}).click();
  const rejected = await reject;
  expect(rejected.status()).toBe(200);
  const firstAttempt = (await rejected.json()).execution.id;
  await executor.reload();
  await executor.getByRole("button", {name: "Начать новую попытку"}).click();
  await expect(executor.getByRole("heading", {name: "Чек-лист"})).toBeVisible();
  await expect(executor.getByText("Попытка №2", {exact: true})).toBeVisible();
  await executor.getByRole("checkbox", {name: /Поверхность очищена/}).check();
  for (const phase of ["before", "after"]) {
    await executor.getByRole("combobox", {name: /Этап/}).selectOption(phase);
    await executor.getByLabel("Файл фото").setInputFiles(photo);
    const uploaded = executor.waitForResponse(r => r.url().endsWith("/photos") && r.request().method() === "POST");
    await executor.getByRole("button", {name: "Загрузить фото"}).click();
    expect((await uploaded).status()).toBe(200);
    await expect(executor.locator(".evidence-photo img")).toHaveCount(phase === "before" ? 1 : 2);
  }
  const resubmit = executor.waitForResponse(r => r.url().endsWith("/submit"));
  await executor.getByRole("button", {name: "Сдать работу"}).click();
  await executor.getByRole("dialog", {name: "Передать отчёт инженеру?"}).getByRole("button", {name: "Подтвердить сдачу"}).click();
  const submittedAgain = await resubmit;
  expect(submittedAgain.status()).toBe(200);
  expect((await submittedAgain.json()).execution.id).not.toBe(firstAttempt);
  await engineer.reload();
  await expect(engineer.getByText("Попытка №2", {exact: true})).toBeVisible();
  await engineer.getByLabel(/Причина решения/).fill("Повторная попытка проверена инженером.");
  await engineer.getByRole("button", {name: "Принять работу", exact: true}).click();
  const accept = engineer.waitForResponse(r => r.url().endsWith("/review") && r.request().method() === "POST");
  await engineer.getByRole("button", {name: "Подтвердить приёмку"}).click();
  const accepted = await accept;
  expect(accepted.status()).toBe(200);
  expect((await accepted.json()).task.state).toBe("accepted");
  await engineer.goto(`/tasks/${demoId("runtime-order")}`);
  await engineer.getByRole("button", {name: "Сравнить прогнозы", exact: true}).click();
  await expect(engineer).toHaveURL(/\/comparisons\//);
  const forecastDetails=engineer.locator('summary').filter({hasText:'Метод, версия и диагностика'});
  await expect(forecastDetails.first()).toBeVisible();
  for(const details of await forecastDetails.all())await details.click();
  await expect(engineer.getByText("rf-days-v1", {exact: true})).toBeVisible();
  await expect(engineer.getByText("RULE_INPUT_REQUIRED", {exact: false}).first()).toBeVisible();
  if (process.env.FIXRATE_E2E_OUTPUT) await engineer.screenshot({path: path.join(process.env.FIXRATE_E2E_OUTPUT, "comparison.png"), fullPage: true});
  const directorContext=await browser.newContext(contextOptions);
  const director=await directorContext.newPage();
  director.on('pageerror',error=>errors.push(error.message));
  await signIn(director,'fixrate-demo-executive@example.test');
  if(configuredViewport)expect(await director.evaluate(()=>innerWidth)).toBe(configuredViewport.width);
  await director.goto(`/tasks/${demoId('runtime-order')}`);
  await expect(director.getByRole('heading',{name:'Решение инженера',exact:true})).toBeVisible();
  await expect(director.getByText('Повторная попытка проверена инженером.',{exact:true})).toBeVisible();
  for(const name of ['Подобрать бригаду','Принять работу','Вернуть на доработку','Сдать работу','Отменить задание']){
    await expect(director.getByRole('button',{name,exact:true})).toHaveCount(0);
  }
  await director.locator('summary').filter({hasText:'История попыток и доказательств'}).click();
  await expect(director.getByRole('heading',{name:/Попытка 1 ·/})).toBeVisible();
  await expect(director.getByRole('heading',{name:/Попытка 2 ·/})).toBeVisible();
  await expect(director.getByRole('heading',{name:/Попытка 2 ·/})).not.toContainText(/\d{4}-\d{2}-\d{2}T\d{2}:/);
  await expect(director.getByRole('link',{name:'Фото до · Спереди',exact:true}).first()).toBeVisible();
  await director.getByRole('heading',{name:/Попытка 2 ·/}).scrollIntoViewIfNeeded();
  await checkpoint(director,'director-history');
  const original=director.getByRole('link',{name:/Фото до ·/}).first();
  const popupPromise=director.waitForEvent('popup');
  await original.click();
  const popup=await popupPromise;
  await popup.waitForLoadState();
  expect(new URL(popup.url()).pathname).toMatch(/^\/api\/v1\/maintenance\/photos\//);
  const originalResponse=await director.request.get(popup.url());
  expect(originalResponse.status()).toBe(200);
  expect(originalResponse.headers()['content-type']).toMatch(/^image\//);
  await popup.close();
  await directorContext.close();
  expect(errors).toEqual([]);
  await executorContext.close();
  await engineerContext.close();
});
