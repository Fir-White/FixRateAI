import { test, expect } from "@playwright/test";
import { createHash } from "node:crypto";
import path from "node:path";

function demoId(key: string) {
  const hex = createHash("md5").update(`fixrate-demo-${key}`).digest("hex");
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}

test("dispatcher selects a complete crew from real availability and load without saving an assignment", async ({page}) => {
  test.skip(!process.env.FIXRATE_BASE_URL, "Use scripts/verify.py --browser for an isolated database");
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/login");
  await page.getByLabel("Email", {exact: true}).fill("fixrate-demo-dispatcher@example.test");
  await page.getByLabel("Пароль", {exact: true}).fill(process.env.FIXRATE_TEST_PASSWORD!);
  await page.getByRole("button", {name: "Войти", exact: true}).click();
  await expect(page).not.toHaveURL(/\/login$/);
  const task = demoId("assignment-order");
  await page.goto(`/tasks/${task}`);
  await page.getByRole("button", {name: "Подобрать бригаду", exact: true}).click();
  const panel = page.getByRole("region", {name: "Подбор бригады", exact: true});
  await expect(panel.getByText(/Нужно 2 чел. на 60 мин./)).toBeVisible();
  const search = panel.getByRole("button", {name: "Найти бригаду", exact: true});
  async function find() {
    const response = page.waitForResponse(reply => reply.url().endsWith(`/tasks/${task}/assignment-preview`) && reply.request().method() === "POST");
    await search.click();
    const reply = await response;
    expect(reply.status()).toBe(200);
    return reply.json();
  }
  const result = await find();
  expect(result.status).toBe("ok");
  expect(result.selectedWorkers.map((worker: {executorId: string}) => worker.executorId).sort()).toEqual([1,2].map(i => demoId(`assignment-worker-${i}`)).sort());
  expect(result.workers.find((worker: {executorId: string}) => worker.executorId === demoId("assignment-worker-3")).loadMinutes).toBe(60);
  await expect(panel.getByText("Полный состав найден", {exact: true})).toBeVisible();
  await expect(panel.getByText("Плановая загрузка: 120 чел.-мин.", {exact: true})).toBeVisible();
  await panel.getByLabel("Состав", {exact: true}).selectOption(demoId("assignment-crew"));
  const named = await find();
  expect(named.status).toBe("ok");
  expect(named.crewId).toBe(demoId("assignment-crew"));
  await expect(panel.getByText("Полный состав найден", {exact: true})).toBeVisible();
  if (process.env.FIXRATE_E2E_OUTPUT) {
    await page.evaluate(async () => {
      window.scrollTo(0, 0);
      await document.fonts.ready;
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    });
    await page.screenshot({path: path.join(process.env.FIXRATE_E2E_OUTPUT, "assignment-preview.png"), fullPage: true, animations: "disabled"});
  }
  const start = await panel.getByLabel("Начало окна поиска", {exact: true}).inputValue();
  await panel.getByLabel("Конец окна поиска", {exact: true}).fill(`${start.slice(0, 10)}T09:30`);
  const short = await find();
  expect(short.status).toBe("unavailable");
  expect(short.selectedWorkers).toEqual([]);
  expect(short.command).toBeNull();
  await expect(panel.getByText("Бригада не подобрана", {exact: true})).toBeVisible();
  await expect(panel.getByText("Полный состав найден", {exact: true})).toHaveCount(0);
  const unchanged = await page.request.get(`/api/v1/maintenance/ui/tasks/${task}`);
  expect(unchanged.status()).toBe(200);
  const bundle = await unchanged.json();
  expect(bundle.task.state).toBe("draft");
  expect(bundle.task.assignees).toEqual([]);
  expect(errors).toEqual([]);
});

test("dispatcher confirms a proposal and sees persisted crew and interval after reload", async ({page}) => {
  test.skip(!process.env.FIXRATE_BASE_URL, "Use scripts/verify.py --browser for an isolated database");
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/login");
  await page.getByLabel("Email", {exact: true}).fill("fixrate-demo-dispatcher@example.test");
  await page.getByLabel("Пароль", {exact: true}).fill(process.env.FIXRATE_TEST_PASSWORD!);
  await page.getByRole("button", {name: "Войти", exact: true}).click();
  await expect(page).not.toHaveURL(/\/login$/);
  const task = demoId("assignment-order");
  await page.goto(`/tasks/${task}`);
  await page.getByRole("button", {name: "Подобрать бригаду", exact: true}).click();
  const panel = page.getByRole("region", {name: "Подбор бригады", exact: true});
  const preview = page.waitForResponse(response => response.url().endsWith(`/tasks/${task}/assignment-preview`));
  await panel.getByRole("button", {name: "Найти бригаду", exact: true}).click();
  const proposal = await (await preview).json();
  const save = page.waitForResponse(response => response.url().endsWith(`/tasks/${task}/assign`));
  await panel.getByRole("button", {name: "Подтвердить назначение", exact: true}).click();
  const reply = await save;
  expect(reply.status()).toBe(200);
  const saved = await reply.json();
  expect(saved.task.state).toBe("assigned");
  expect(saved.task.revision).toBe(proposal.command.expected_revision + 1);
  expect(saved.assignments).toHaveLength(2);
  await expect(page.getByText("Бригада назначена", {exact: true})).toBeVisible();
  await expect(page.getByRole("region", {name: "Подбор бригады", exact: true})).toHaveCount(0);
  await expect(page.getByText("DEMO — работник планирования 1", {exact: true})).toBeVisible();
  await expect(page.getByText("DEMO — работник планирования 2", {exact: true})).toBeVisible();
  await page.reload();
  await expect(page.getByText("DEMO — работник планирования 1", {exact: true})).toBeVisible();
  const persisted = await page.request.get(`/api/v1/maintenance/ui/tasks/${task}`);
  const bundle = await persisted.json();
  expect(bundle.task).toEqual(saved.task);
  expect(new Date(bundle.task.scheduledEnd).getTime()).toBe(new Date(proposal.command.end_at).getTime());
  expect(errors).toEqual([]);
});
