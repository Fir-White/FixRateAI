import { expect, test, type Page } from "@playwright/test";

const password = "local-test-password";
const setupToken = "fixture-setup-token";
const profile = {
  userId: "access-qa",
  name: "QA",
  email: "qa@example.test",
  role: "executor",
  siteName: "QA",
  timezone: "UTC",
};

async function expectCenteredSplash(page: Page, code: "403" | "404") {
  await expect(page.locator(".access-error-code")).toHaveText(code);
  const measurements = await page.locator(".access-error-page").evaluate(main => {
    const viewport = main.getBoundingClientRect();
    const center = (selector: string) => {
      const rect = main.querySelector(selector)!.getBoundingClientRect();
      return rect.left + rect.width / 2;
    };
    const content = main.querySelector(".access-error-content")!.getBoundingClientRect();
    return {
      axis: viewport.width / 2,
      centers: [".auth-brand", ".access-error-code", "h1", ".access-error-description", "a"].map(center),
      paddingDelta: Math.abs(content.top - (viewport.bottom - content.bottom)),
      overflow: document.documentElement.scrollWidth > viewport.width,
    };
  });
  for (const center of measurements.centers) expect(Math.abs(center - measurements.axis)).toBeLessThan(1);
  expect(measurements.paddingDelta).toBeLessThan(1);
  expect(measurements.overflow).toBe(false);
}

test.beforeEach(() => test.skip(!process.env.FIXRATE_BASE_URL, "Requires a production preview"));

for (const size of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  test(`error splashes show the right return action at ${size.width}px`, async ({ page }, info) => {
    await page.setViewportSize(size);
    await page.emulateMedia({ reducedMotion: "reduce" });
    let role: string | null = null;
    await page.route("**/api/**", route => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/auth/session")) {
        return role ? route.fulfill({ json: { profile: { ...profile, role } } }) : route.fulfill({ status: 401, json: {} });
      }
      return route.fulfill({ json: [] });
    });

    await page.goto("/unknown-fixrate-page");
    await expect(page.getByRole("heading", { name: "Страница не найдена" })).toBeFocused();
    await expectCenteredSplash(page, "404");
    await page.screenshot({ path: info.outputPath("404.png") });
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Войти" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/login$/);
    await page.goBack();
    await expectCenteredSplash(page, "404");
    await page.goForward();
    await expect(page).toHaveURL(/\/login$/);

    role = "executor";
    await page.goto("/quality");
    await expect(page.getByRole("heading", { name: "Раздел недоступен" })).toBeFocused();
    await expectCenteredSplash(page, "403");
    await expect(page.getByRole("navigation")).toHaveCount(0);
    await page.screenshot({ path: info.outputPath("403.png") });
    await page.getByRole("link", { name: "К моим заданиям" }).click();
    await expect(page).toHaveURL(/\/executor$/);
    await page.goBack();
    await expectCenteredSplash(page, "403");
    await page.reload();
    await expectCenteredSplash(page, "403");

    await page.goto("/unknown-fixrate-page");
    await expect(page.getByRole("link", { name: "На главную" })).toHaveAttribute("href", "/executor");

    role = "engineer";
    await page.goto("/executor/tasks/fixture-task");
    await expectCenteredSplash(page, "403");
    await expect(page.getByRole("link", { name: "Вернуться в рабочий раздел" })).toHaveAttribute("href", "/engineer");
  });

  test(`access forms share the shell and scroll to their actions at ${size.width}px`, async ({ page }, info) => {
    await page.setViewportSize(size);
    await page.emulateMedia({ reducedMotion: "reduce" });
    let setupAttempts = 0;
    await page.route("**/api/**", async route => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      if (path.endsWith("/auth/register")) {
        expect(request.postDataJSON()).toMatchObject({ company_code: "fixture-company-code" });
        return route.fulfill({ json: { message: "Учётная запись создана. Администратор компании должен выдать роль и доступ к объекту." } });
      }
      if (path === "/api/setup") {
        if (request.method() === "GET") return route.fulfill({ json: { required: true } });
        expect(request.headers()["x-fixrate-setup-token"]).toBe(setupToken);
        expect(request.postDataJSON()).not.toHaveProperty("token");
        ++setupAttempts;
        return setupAttempts === 1
          ? route.fulfill({ status: 403, json: { detail: "Проверьте установочный код" } })
          : route.fulfill({ json: {} });
      }
      return route.fulfill({ status: 401, json: {} });
    });

    const geometry = () => page.locator(".auth-panel").evaluate(panel => {
      const rect = (selector: string) => document.querySelector(selector)!.getBoundingClientRect();
      const bounds = rect(".auth-panel");
      const brand = rect(".auth-brand");
      const backdrop = rect(".auth-aurora");
      const control = rect(".auth-input, .auth-success");
      return {
        anchor: [brand.left, brand.top + window.scrollY, brand.width, brand.height],
        scene: [backdrop.left, backdrop.top, backdrop.width, backdrop.height],
        gutters: [control.left - bounds.left, bounds.right - control.right],
        overflow: document.documentElement.scrollWidth > innerWidth,
        panelWidth: panel.clientWidth,
      };
    });

    await page.goto("/login");
    await expect(page.getByLabel("Email", { exact: true })).toBeVisible();
    const login = await geometry();
    expect(login.overflow).toBe(false);
    await page.screenshot({ path: info.outputPath("login.png") });
    await page.getByRole("link", { name: "Регистрация" }).click();
    await expect(page.getByRole("heading", { name: "Регистрация" })).toBeFocused();
    expect(await geometry()).toEqual(login);
    await page.screenshot({ path: info.outputPath("registration.png"), fullPage: true });
    await page.getByLabel("Имя и фамилия").fill("Тестовый сотрудник");
    await page.getByLabel("Email", { exact: true }).fill("new.qa@example.test");
    await page.getByLabel("Пароль", { exact: true }).fill(password);
    await page.getByLabel("Подтвердите пароль", { exact: true }).fill(password);
    await page.getByLabel("Код компании", { exact: true }).fill("fixture-company-code");
    await page.getByRole("button", { name: "Зарегистрироваться" }).click();
    await expect(page.getByRole("status")).toContainText("Учётная запись создана");
    expect(await geometry()).toEqual(login);
    await page.screenshot({ path: info.outputPath("registration-complete.png") });

    await page.goto("/setup");
    const setup = page.getByRole("form", { name: "Создание первого администратора" });
    await expect(setup.locator("input")).toHaveCount(6);
    expect(await geometry()).toEqual(login);
    await page.screenshot({ path: info.outputPath("setup.png"), fullPage: true });
    await page.getByLabel("Одноразовый установочный код").fill(setupToken);
    await page.getByLabel("Организация").fill("QA");
    await page.getByLabel("Первое здание").fill("QA");
    await page.getByLabel("Имя администратора").fill("QA");
    await page.getByLabel("Email", { exact: true }).fill("admin.qa@example.test");
    await page.getByLabel("Пароль", { exact: true }).fill(password);
    const create = page.getByRole("button", { name: "Создать администратора" });
    await create.click();
    await expect(page.getByRole("alert")).toHaveText("Проверьте установочный код");
    await expect(page.getByLabel("Организация")).toHaveValue("QA");
    await create.click();
    await expect(page.getByRole("status")).toContainText("Администратор создан");
    await page.getByRole("link", { name: "Перейти ко входу" }).click();
    await expect(page).toHaveURL(/\/login$/);
  });
}
