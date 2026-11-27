import { test, expect, type Locator, type Page } from "@playwright/test";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const id = (name: string) => createHash("md5").update(`fixrate-demo-${name}`).digest("hex")
  .replace(/^(.{8})(.{4})(.{4})(.{4})(.{12})$/, "$1-$2-$3-$4-$5");
const task = id("runtime-order");
const assignmentTask = id("assignment-order");
const api = "/api/v1/maintenance";
const roles = {
  chief_engineer: "fixrate-demo-chief_engineer@example.test",
  engineer: "fixrate-demo-engineer@example.test",
  executor: "fixrate-demo-1@example.test",
};
type Role = keyof typeof roles;

async function signIn(page: Page, role: Role) {
  await page.goto("/login");
  await page.getByLabel("Email", {exact: true}).fill(roles[role]);
  await page.getByLabel("Пароль", {exact: true}).fill(process.env.FIXRATE_TEST_PASSWORD!);
  await page.getByRole("button", {name: "Войти", exact: true}).click();
  await expect(page).not.toHaveURL(/\/login$/);
  const {profile} = await (await page.request.get("/api/v1/auth/session")).json();
  expect(profile.role).toBe(role);
  expect(profile.permissionProfile).toBe("mvp");
  return profile.permissions as string[];
}

test("documentation gallery: chief engineer, executor and real MVP role parity", async ({browser}, info) => {
  test.skip(process.env.FIXRATE_DOCUMENTATION_CAPTURE !== "1", "Run scripts/verify_web.py --documentation on disposable PostgreSQL");
  test.setTimeout(420_000);
  const baseURL = new URL(process.env.FIXRATE_BASE_URL!);
  expect(["127.0.0.1", "localhost"]).toContain(baseURL.hostname);
  const output = path.join(process.env.FIXRATE_E2E_OUTPUT!, "documentation-gallery");
  await mkdir(output, {recursive: true});
  const manifest: {file: string; role: Role; title: string; route: string; sha256: string; viewport: string}[] = [];
  const omissions: string[] = [];
  const problems: string[] = [];
  const desktop = {width: 1440, height: 1000};
  const mobile = {width: 390, height: 844};
  const pageFor = async (viewport = desktop, video = false) => {
    const context = await browser.newContext({baseURL: baseURL.href, viewport, reducedMotion: "reduce",
      ...(viewport === mobile ? {isMobile: true, hasTouch: true} : {}),
      ...(video ? {recordVideo: {dir: path.join(output, "video"), size: {width: 1152, height: 800}}} : {})});
    const page = await context.newPage();
    page.on("pageerror", error => problems.push(error.message));
    return page;
  };
  const writeManifest = () => writeFile(path.join(output, "manifest.json"), JSON.stringify({
    fixture: "seed-demo; disposable PostgreSQL", source: process.env.FIXRATE_TEST_SOURCE || "local worktree",
    cloud: false, images: manifest, omissions,
  }, null, 2)+"\n");
  const capture = async (page: Page, role: Role, name: string, title: string, ready: Locator) => {
    await expect(ready).toBeVisible();
    await expect(page.locator("[data-workspace-loading]")).toHaveCount(0);
    await page.evaluate(async () => {
      await document.fonts.ready;
      await Promise.all([...document.images].filter(image => {
        const rect = image.getBoundingClientRect();
        return rect.height > 0 && rect.bottom > 0 && rect.top < innerHeight;
      }).map(image => image.decode()));
    });
    const size = page.viewportSize()!;
    const dir = size.width === mobile.width ? "mobile" : role;
    await mkdir(path.join(output, dir), {recursive: true});
    const file = `${dir}/${name}.jpg`;
    const bytes = await page.screenshot({path: path.join(output, file), type: "jpeg", quality: 89, animations: "disabled"});
    const url = new URL(page.url());
    manifest.push({file, role, title, route: url.pathname + (url.pathname === "/assistant" ? "" : url.search), viewport: `${size.width}×${size.height}`,
      sha256: createHash("sha256").update(bytes).digest("hex")});
    await writeManifest();
  };
  const record = process.env.FIXRATE_DOCS_VIDEO === "1";
  const chief = await pageFor(desktop, record);
  const executor = await pageFor(desktop, record);
  const engineer = await pageFor();
  const chiefPermissions = await signIn(chief, "chief_engineer");
  expect(await signIn(engineer, "engineer")).toEqual(chiefPermissions);
  await signIn(executor, "executor");

  for (const page of [chief, engineer]) {
    await expect(page.getByRole("heading", {name: "С чего начнём рабочий день?"})).toBeVisible();
    await page.goto("/planning?mode=orders");
    await expect(page.getByRole("table")).toBeVisible();
    expect((await page.request.get(`${api}/users`)).status()).toBe(403);
    expect((await page.request.get(`${api}/management/enrollment`)).status()).toBe(403);
  }
  expect((await executor.request.get(`${api}/planning/order-table?month=2026-11`)).status()).toBe(403);
  await executor.goto("/planning");
  await expect(executor.getByRole("heading", {name: "Раздел недоступен"})).toBeVisible();
  await executor.goto("/executor");
  const assignedLink = executor.locator(`a[href="/executor/tasks/${task}"]`).first();
  await capture(executor, "executor", "assigned", "Назначенные работы и обязательные сроки", assignedLink);
  await executor.goto("/executor/tasks");
  await capture(executor, "executor", "queue", "Очередь собственных заданий", executor.getByRole("link", {name: "Открыть задание"}));
  await executor.goto("/calendar");
  await expect(executor.getByRole("button", {name: "Рассчитать график", exact: true})).toHaveCount(0);
  await capture(executor, "executor", "calendar", "Календарь исполнителя без команд планирования",
    executor.getByRole("heading", {name: "График ТО и ППР", exact: true}));
  await executor.goto("/executor");

  await chief.goto("/chief-engineer");
  await capture(chief, "chief_engineer", "workday", "Рабочий день главного инженера",
    chief.getByRole("heading", {name: "С чего начнём рабочий день?"}));
  await chief.goto("/equipment");
  await capture(chief, "chief_engineer", "equipment", "Реестр оборудования",
    chief.getByRole("table").first());
  await chief.goto(`/equipment/${id("assignment-equipment")}`);
  await capture(chief, "chief_engineer", "equipment-card", "Паспорт и обслуживание учебного узла",
    chief.getByRole("heading", {name: /учебный узел планирования/}).first());
  await chief.goto(`/settings/equipment?equipment=${id("assignment-equipment")}`);
  await capture(chief, "chief_engineer", "service-settings", "Настройка обслуживания и действующие регламенты",
    chief.getByText(/Регламенты оборудования · /));
  await chief.goto("/tasks");
  await capture(chief, "chief_engineer", "work-orders", "Реестр нарядов и назначений",
    chief.getByRole("heading", {name: "Наряды и назначения"}));
  await chief.goto("/calendar");
  await capture(chief, "chief_engineer", "calendar", "Нормативный график ТО",
    chief.getByRole("heading", {name: "График ТО и ППР"}));
  await chief.goto("/planning?mode=orders");
  await capture(chief, "chief_engineer", "planning", "Оперативная таблица планирования",
    chief.getByRole("table"));
  await chief.goto("/planning");
  await chief.getByRole("button", {name: "Загрузить Excel с регламентами", exact: true}).click();
  await chief.getByLabel("Excel каталога СВиК").setInputFiles(process.env.FIXRATE_DOCS_CATALOG!);
  await chief.getByRole("button", {name: "Проверить каталог", exact: true}).click();
  const catalogPreview = chief.getByRole("region", {name: "Предпросмотр каталога СВиК"});
  await capture(chief, "chief_engineer", "catalog-preview", "Предпросмотр учебного XLSX до сохранения", catalogPreview);
  await catalogPreview.getByRole("button", {name: "Сохранить каталог-черновик", exact: true}).click();
  await expect(chief).toHaveURL(/catalog=[0-9a-f-]{36}/);
  await chief.reload();
  await capture(chief, "chief_engineer", "catalog-draft", "Сохранённый каталог с исходными операциями",
    chief.getByRole("table", {name: "Операции каталога СВиК"}));
  await chief.goto("/reports");
  await capture(chief, "chief_engineer", "analytics", "Аналитика объекта",
    chief.getByRole("heading", {name: "Отчёты", exact: true}));
  await chief.goto(`/tasks/${assignmentTask}`);
  const forecast = chief.waitForResponse(response => response.url().endsWith(`/tasks/${assignmentTask}/forecast`));
  await chief.getByRole("button", {name: "Сравнить прогнозы", exact: true}).click();
  const compared = await forecast;
  expect(compared.status()).toBe(200);
  expect((await compared.json()).run.algorithmic.status).toBe("ok");
  await expect(chief).toHaveURL(/\/comparisons\/[0-9a-f-]{36}$/);
  await capture(chief, "chief_engineer", "forecast", "Сравнение на одном снимке; результат локального расчёта",
    chief.locator(".forecast-methods"));
  await chief.goto("/settings/workforce");
  await capture(chief, "chief_engineer", "workforce", "Команда, смены и бригады",
    chief.getByRole("heading", {name: "Команда и смены", exact: true}));

  for (const [page, role] of [[chief, "chief_engineer"], [engineer, "engineer"]] as const) {
    await page.goto(`/tasks/${assignmentTask}`);
    await page.getByRole("button", {name:"Подобрать бригаду", exact:true}).click();
    const panel = page.getByRole("region", {name:"Подбор бригады", exact:true});
    const read = page.waitForResponse(response => response.url().endsWith(`/tasks/${assignmentTask}/assignment-preview`));
    await panel.getByRole("button", {name:"Найти бригаду", exact:true}).click();
    const prepared = await (await read).json();
    expect(prepared.status).toBe("ok");
    expect(prepared.selectedWorkers).toHaveLength(2);
    if (role === "chief_engineer") {
      await panel.getByText("Полный состав найден", {exact:true}).scrollIntoViewIfNeeded();
      await capture(page, role, "crew-preview", "Подбор бригады и загрузка до записи",
        panel.getByRole("button", {name:"Подтвердить назначение", exact:true}));
    } else {
      const save = page.waitForResponse(response => response.url().endsWith(`/tasks/${assignmentTask}/assign`));
      await panel.getByRole("button",{name:"Подтвердить назначение",exact:true}).click();
      expect((await save).status()).toBe(200);
    }
  }
  await assignedLink.click();
  await capture(executor, "executor", "work-order", "Карточка наряда перед выполнением",
    executor.getByRole("button", {name:"Приступить к работе"}));
  await executor.getByRole("button", {name:"Приступить к работе"}).click();
  await executor.getByRole("checkbox", {name:/Поверхность очищена/}).check();
  await capture(executor, "executor", "checklist", "Обязательный чек-лист",
    executor.getByRole("checkbox", {name:/Поверхность очищена/}));
  await executor.getByRole("button", {name:"Итоговый отчёт", exact:true}).click();
  await executor.getByLabel("Что выполнено и какие замечания остались").fill("Учебный узел очищен. Результат готов к ручной проверке.");
  await executor.getByRole("button", {name:"Добавить фотографии", exact:true}).click();
  const photo = path.resolve(info.project.testDir, "../../../data/demo/demo-photo.png");
  await readFile(photo);
  for (const phase of ["до", "после"]) {
    const uploaded = executor.waitForResponse(response => response.url().endsWith("/photos") && response.request().method() === "POST");
    await executor.getByLabel(new RegExp(`^Фото ${phase}: `)).setInputFiles(photo);
    expect((await uploaded).status()).toBe(200);
    await expect(executor.locator(".evidence-photo img")).toHaveCount(phase === "до" ? 1 : 2);
  }
  await executor.locator(".evidence-photo").first().scrollIntoViewIfNeeded();
  await capture(executor, "executor", "photos", "Прикреплённые учебные снимки до и после",
    executor.locator(".evidence-photo img").first());
  await executor.getByRole("button", {name:"Итоговый отчёт", exact:true}).click();
  await executor.getByRole("button", {name:"Сдать работу", exact:true}).click();
  const submission = executor.getByRole("dialog", {name:"Передать отчёт инженеру?"});
  await capture(executor, "executor", "submit-review", "Отдельное подтверждение сдачи отчёта", submission);
  const submitted = executor.waitForResponse(response => response.url().endsWith("/submit") && response.request().method() === "POST");
  await submission.getByRole("button", {name:"Подтвердить сдачу"}).click();
  expect((await submitted).status()).toBe(200);
  await executor.goto("/executor/reports");
  await capture(executor, "executor", "reports", "Сохранённые отчёты исполнителя",
    executor.locator(`a[href="/executor/tasks/${task}"]`).first());
  await executor.goto("/my-shifts");
  await capture(executor, "executor", "shifts", "Смены и исключения; пустой период",
    executor.getByText("На этот период смен нет", {exact: true}));

  await chief.goto("/quality");
  await capture(chief, "chief_engineer", "review-inbox", "Очередь инженерной проверки",
    chief.locator(`a[href="/quality/${task}"]`).first());
  for (const page of [chief, engineer]) {
    await page.goto(`/quality/${task}`);
    await expect(page.locator(".evidence-photo img")).toHaveCount(2);
    await expect(page.getByRole("button", {name:"Принять работу", exact:true})).toBeVisible();
  }
  const analysis = chief.getByRole("heading", {name:"Анализ фотографий", exact:true});
  await analysis.scrollIntoViewIfNeeded();
  await capture(chief, "chief_engineer", "photo-review", "Фотографии и предварительная оценка; без облачного ключа", analysis);
  const mobileExecutor = await pageFor(mobile);
  await signIn(mobileExecutor, "executor");
  await mobileExecutor.goto(`/executor/tasks/${task}`);
  await capture(mobileExecutor, "executor", "work-order", "Мобильная карточка отправленного наряда",
    mobileExecutor.getByText("На проверке", {exact:true}).first());
  const mobileChief = await pageFor(mobile);
  await signIn(mobileChief, "chief_engineer");
  await mobileChief.goto("/chief-engineer");
  await capture(mobileChief, "chief_engineer", "workday", "Рабочий день на мобильном экране",
    mobileChief.getByRole("heading", {name:"С чего начнём рабочий день?"}));
  await chief.getByLabel(/Причина решения/).fill("Учебная проверка инженером: материалы и чек-лист просмотрены.");
  await chief.getByRole("button", {name:"Принять работу", exact:true}).click();
  await capture(chief, "chief_engineer", "acceptance", "Приёмка требует решения человека",
    chief.getByRole("button", {name:"Подтвердить приёмку"}));
  const accepted = chief.waitForResponse(response => response.url().endsWith("/review") && response.request().method() === "POST");
  await chief.getByRole("button", {name:"Подтвердить приёмку"}).click();
  expect((await (await accepted).json()).task.state).toBe("accepted");

  if (process.env.FIXRATE_DOCS_LOCAL_AI === "1") {
    for (const [page, role] of [[chief, "chief_engineer"], [executor, "executor"]] as const) {
      try {
        const assets = await (await page.request.get("/api/v1/assistant/workspace/equipment")).json();
        const asset = assets.items.find((candidate:{name:string}) => candidate.name.startsWith("DEMO"))
          ?? assets.items[0];
        expect(asset?.asset_code).toBeTruthy();
        await page.goto("/assistant");
        await page.getByLabel("Сообщение помощнику").fill(`Как называется оборудование с кодом ${asset.asset_code}?`);
        await page.getByRole("button", {name:"Отправить", exact:true}).click({timeout:12_000});
        await expect(page).toHaveURL(/chat=/, {timeout:10_000});
        const chat = new URL(page.url()).searchParams.get("chat");
        const read = async () => (await (await page.request.get(`/api/v1/assistant/conversations/${chat}`)).json());
        await expect.poll(async () => ["completed","failed"].includes((await read()).turns.at(-1)?.status),
          {timeout:95_000}).toBe(true);
        const view = await read();
        const turn = view.turns.at(-1);
        expect(turn.status).toBe("completed");
        expect(turn.execution_engine).toBe("v4");
        expect(turn.model_ref).toContain("ollama:");
        expect(turn.answer.toLowerCase()).toContain(asset.name.toLowerCase());
        expect(turn.trace.some((step:{tool:string;status:string}) =>
          ["find_equipment","read_equipment"].includes(step.tool) && step.status === "completed")).toBe(true);
        expect(view.actions).toEqual([]);
        const messages = page.getByRole("region",{name:"Сообщения"});
        await expect(messages).toContainText(asset.name,{ignoreCase:true});
        await capture(page, role, "assistant", "Ответ v4 по данным объекта, проверенный через API (локальная Ollama)", messages);
      } catch {
        omissions.push(`${role}: локальный ответ не подтвердил все условия; изображение не снято`);
      }
    }
  } else omissions.push("Чат v4: локальная модель не включена в этом прогоне");
  await writeManifest();
  expect(problems).toEqual([]);
  for (const [page, role] of [[chief, "chief_engineer"], [executor, "executor"]] as const) {
    if (record) {
      const video = page.video()!;
      await page.context().close();
      await video.saveAs(path.join(output, "video", `${role}.webm`));
      await video.delete();
    }
  }
});
