import { test, expect } from "@playwright/test";
import { createHash } from "node:crypto";

function demoId(key:string) {
  const h=createHash("md5").update(`fixrate-demo-${key}`).digest("hex");
  return `${h.slice(0,8)}-${h.slice(8,12)}-${h.slice(12,16)}-${h.slice(16,20)}-${h.slice(20)}`;
}

test("calendar → two forecasts → single task → confirmed crew → persisted reload",async ({page}) => {
  test.skip(!process.env.FIXRATE_BASE_URL,"Use scripts/verify.py --browser");
  const errors:string[]=[];
  page.on("pageerror",error=>errors.push(error.message));
  await page.goto("/login");
  await page.getByLabel("Email",{exact:true}).fill("fixrate-demo-dispatcher@example.test");
  await page.getByLabel("Пароль",{exact:true}).fill(process.env.FIXRATE_TEST_PASSWORD!);
  await page.getByRole("button",{name:"Войти",exact:true}).click();
  await expect(page).not.toHaveURL(/\/login$/);
  await page.goto("/calendar");
  const loaded=page.waitForResponse(r=>r.url().includes("/ui/calendar/preview?"));
  await page.getByRole("button",{name:"Рассчитать график",exact:true}).click();
  let preview=await (await loaded).json();
  if (!preview.items.some((item:{operationCode:string})=>item.operationCode==="DEMO-PIPELINE")) {
    const next=page.waitForResponse(r=>r.url().includes("/ui/calendar/preview?"));
    await page.getByRole("button",{name:"Следующий месяц"}).click();
    preview=await (await next).json();
  }
  expect(preview.items.some((item:{operationCode:string})=>item.operationCode==="DEMO-PIPELINE")).toBe(true);
  const saved=page.waitForResponse(r=>r.url().endsWith("/calendar/generate"));
  await page.getByRole("button",{name:"Создать задания по расчёту",exact:true}).click();
  const reply=await saved;
  expect(reply.status()).toBe(200);
  const run=await reply.json();
  const row=run.items.find((item:{operationTitle:string})=>item.operationTitle==="DEMO — сквозное планирование");
  expect(row.created).toBe(true);
  expect(row.comparison.algorithmic.status).toBe("ok");
  const workflow=page.getByRole("region",{name:"Создание заданий из календаря"});
  await expect(workflow.getByText("Создан черновик задания",{exact:true})).toBeVisible();
  await workflow.getByRole("button",{name:"Подобрать и назначить",exact:true}).click();
  const crew=page.getByRole("region",{name:"Подбор бригады",exact:true});
  await crew.getByRole("button",{name:"Найти бригаду",exact:true}).click();
  await crew.getByRole("button",{name:"Подтвердить назначение",exact:true}).click();
  await expect(workflow.getByText("Бригада назначена",{exact:true})).toBeVisible();
  await workflow.getByRole("link",{name:"Открыть задание",exact:true}).click();
  await expect(page).toHaveURL(new RegExp(`/tasks/${row.taskId}$`));
  await page.reload();
  await expect(page.getByText("Назначено",{exact:true})).toBeVisible();
  await expect(page.getByText("DEMO — работник планирования 1",{exact:true})).toBeVisible();
  const persisted=await page.request.get(`/api/v1/maintenance/ui/tasks/${row.taskId}`);
  expect((await persisted.json()).task.assignees).toHaveLength(2);
  await page.goto(`/comparisons/${row.comparison.runId}`);
  await expect(page.getByText(row.comparison.snapshotHash,{exact:true})).toBeVisible();
  await expect(page.getByText("Решение оркестратора",{exact:true})).toBeVisible();
  expect(errors).toEqual([]);
});
