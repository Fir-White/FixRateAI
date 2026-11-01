import { test, expect } from "@playwright/test";
import path from "node:path";

test("calendar preview reads persisted rules, explains missing inputs and switches months", async ({page}) => {
  test.skip(!process.env.FIXRATE_BASE_URL, "Use scripts/verify.py --browser for an isolated database");
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/login");
  await page.getByLabel("Email", {exact: true}).fill("fixrate-demo-dispatcher@example.test");
  await page.getByLabel("Пароль", {exact: true}).fill(process.env.FIXRATE_TEST_PASSWORD!);
  await page.getByRole("button", {name: "Войти", exact: true}).click();
  await expect(page).not.toHaveURL(/\/login$/);
  await page.goto("/calendar");
  const calculate = page.getByRole("button", {name: "Рассчитать график", exact: true});
  await expect(calculate).toBeEnabled();
  const requested = page.waitForResponse(reply => reply.url().includes("/ui/calendar/preview?"));
  await calculate.click();
  const reply = await requested;
  expect(reply.status()).toBe(200);
  const preview = await reply.json();
  expect(preview.items.every((item: {dataOrigin: string}) => item.dataOrigin === "synthetic_demo")).toBe(true);
  expect(preview.diagnostics.some((item: {code: string}) => item.code === "RULE_UNCONFIRMED")).toBe(true);
  await expect(page.getByRole("heading", {name: "Результат по оборудованию и операциям"})).toBeVisible();
  await expect(page.getByText("Нужны данные", {exact: true}).first()).toBeVisible();
  await expect(page.getByText("Регламент или его редакция не утверждены.", {exact: false}).first()).toBeVisible();
  if (process.env.FIXRATE_E2E_OUTPUT) {
    await page.screenshot({path: path.join(process.env.FIXRATE_E2E_OUTPUT, "calendar-preview.png"), fullPage: true});
  }
  const nextRequest = page.waitForResponse(response => response.url().includes("/ui/calendar/preview?"));
  await page.getByRole("button", {name: "Следующий месяц"}).click();
  const next = await (await nextRequest).json();
  expect(next.month).toBe(preview.month === 12 ? 1 : preview.month + 1);
  expect(next.year).toBe(preview.month === 12 ? preview.year + 1 : preview.year);
  await page.getByRole("button", {name: "Сохранённый график", exact: true}).click();
  await expect(page.getByRole("heading", {name: "Результат по оборудованию и операциям"})).toHaveCount(0);
  expect(errors).toEqual([]);
});
