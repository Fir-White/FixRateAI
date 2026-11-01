import { test, expect, type Page } from "@playwright/test";
import { createHash } from "node:crypto";
import path from "node:path";

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
test("real SPA → API → PostgreSQL → photos → ML guardrails → engineer acceptance", async ({browser}) => {
  test.skip(!process.env.FIXRATE_BASE_URL, "Use scripts/verify.py --browser to create a disposable database");
  const errors: string[] = [];
  const executorContext = await browser.newContext();
  const executor = await executorContext.newPage();
  executor.on("pageerror", error => errors.push(error.message));
  await signIn(executor, "fixrate-demo-1@example.test");
  await executor.getByRole("link", {name: "DEMO — чистка учебного узла", exact: true}).click();
  await executor.getByRole("button", {name: "Приступить к работе"}).click();
  await executor.getByRole("checkbox", {name: /Поверхность очищена/}).check();
  await executor.getByLabel("Комментарий исполнителя").fill("Проверка полного процесса в браузере");
  // Upload must preserve the currently edited checklist and narrative without a manual save.
  const photo = path.resolve("../database/demo/demo-photo.png");
  for (const phase of ["before", "after"]) {
    await executor.getByRole("combobox", {name: /Этап/}).selectOption(phase);
    await executor.getByLabel("Файл фото").setInputFiles(photo);
    const reply = executor.waitForResponse(r => r.url().endsWith("/photos") && r.request().method() === "POST");
    await executor.getByRole("button", {name: "Загрузить фото"}).click();
    expect((await reply).status()).toBe(200);
    await expect(executor.locator("img")).toHaveCount(phase === "before" ? 1 : 2);
    await expect(executor.getByLabel("Комментарий исполнителя")).toHaveValue("Проверка полного процесса в браузере");
    await expect(executor.getByRole("checkbox", {name: /Поверхность очищена/})).toBeChecked();
  }
  await expect(executor.locator("img")).toHaveCount(2);
  const submit = executor.waitForResponse(r => r.url().endsWith("/submit"));
  await executor.getByLabel("Комментарий исполнителя").fill("Последние изменения перед сдачей");
  await executor.getByRole("button", {name: "Сдать работу"}).click();
  expect((await submit).status()).toBe(200);
  await expect(executor.getByRole("button", {name: "Сдать работу"})).toHaveCount(0);
  const engineerContext = await browser.newContext();
  const engineer = await engineerContext.newPage();
  engineer.on("pageerror", error => errors.push(error.message));
  await signIn(engineer, "fixrate-demo-engineer@example.test");
  await engineer.goto(`/quality/${demoId("runtime-order")}`);
  await expect(engineer.locator("img")).toHaveCount(2);
  await expect(engineer.getByText("Последние изменения перед сдачей", {exact: true})).toBeVisible();
  const review = engineer.waitForResponse(r => r.url().endsWith("/photo-review"));
  await engineer.getByRole("button", {name: "Анализировать фото"}).click();
  const result = await review;
  expect(result.status()).toBe(200);
  expect((await result.json()).status).toBe("uncertain");
  await engineer.getByLabel(/Причина решения/).fill("Одинаковые учебные фото проверены; это синтетический E2E сценарий.");
  await engineer.getByRole("button", {name: "Вернуть на доработку", exact: true}).click();
  const reject = engineer.waitForResponse(r => r.url().endsWith("/review") && r.request().method() === "POST");
  await engineer.getByRole("dialog").getByRole("button", {name: "Вернуть на доработку", exact: true}).click();
  const rejected = await reject;
  expect(rejected.status()).toBe(200);
  const firstAttempt = (await rejected.json()).execution.id;
  await executor.reload();
  await executor.getByRole("button", {name: "Начать новую попытку"}).click();
  await expect(executor.getByRole("heading", {name: "Чек-лист · Попытка №2"})).toBeVisible();
  await executor.getByRole("checkbox", {name: /Поверхность очищена/}).check();
  for (const phase of ["before", "after"]) {
    await executor.getByRole("combobox", {name: /Этап/}).selectOption(phase);
    await executor.getByLabel("Файл фото").setInputFiles(photo);
    const uploaded = executor.waitForResponse(r => r.url().endsWith("/photos") && r.request().method() === "POST");
    await executor.getByRole("button", {name: "Загрузить фото"}).click();
    expect((await uploaded).status()).toBe(200);
    await expect(executor.locator("img")).toHaveCount(phase === "before" ? 1 : 2);
  }
  const resubmit = executor.waitForResponse(r => r.url().endsWith("/submit"));
  await executor.getByRole("button", {name: "Сдать работу"}).click();
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
  await expect(engineer.getByText("rf-days-v1", {exact: true})).toBeVisible();
  await expect(engineer.getByText("RULE_INPUT_REQUIRED", {exact: false}).first()).toBeVisible();
  if (process.env.FIXRATE_E2E_OUTPUT) await engineer.screenshot({path: path.join(process.env.FIXRATE_E2E_OUTPUT, "comparison.png"), fullPage: true});
  expect(errors).toEqual([]);
  await executorContext.close();
  await engineerContext.close();
});
