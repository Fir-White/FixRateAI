import { test, expect } from "@playwright/test";
import { createHash } from "node:crypto";

test.beforeEach(async ({ page }) => {
  test.skip(!process.env.FIXRATE_BASE_URL, "Requires the running local application");
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "С возвращением" })).toBeVisible();
});

test("responsive login composition and original logo", async ({ page }, testInfo) => {
  for (const [width, height] of [[1920, 1080], [1440, 900], [1366, 768], [1024, 768], [768, 1024], [390, 844], [375, 812]]) {
    await page.setViewportSize({ width, height });
    const size = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }));
    expect(size.document).toBeLessThanOrEqual(size.viewport);
    const submit = page.getByRole("button", { name: "Войти", exact: true });
    await expect(submit).toBeInViewport();
    const controls = await page.locator("#login-email, #login-password, .auth-submit").evaluateAll(elements => elements.map(element => Math.round(element.getBoundingClientRect().height)));
    expect(controls).toEqual([52, 52, 52]);
    await expect(page.locator(".auth-art__frame, .auth-divider, .auth-support")).toHaveCount(0);
    if (width > 820) {
      const logo = page.locator(".auth-aurora__logo-motion img");
      await expect(logo).toBeVisible();
      expect(await logo.getAttribute("src")).toContain("fixrate-mark");
      const box = (await logo.boundingBox())!;
      expect(Math.abs(box.width - box.height)).toBeLessThan(1);
      expect(box.width).toBeLessThanOrEqual(380);
    } else await expect(page.locator(".auth-aurora")).toBeHidden();
    await page.screenshot({ path: testInfo.outputPath(`aurora-${width}x${height}.png`), fullPage: true });
  }
});

test("smooth scene motion, reduced motion and touch fallback", async ({ page, browser }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  const scene = page.locator(".auth-aurora");
  const sceneBox = (await scene.boundingBox())!;
  await page.mouse.move(sceneBox.x + sceneBox.width * 0.8, sceneBox.height * 0.7);
  await expect.poll(() => scene.evaluate(element => Number((element as HTMLElement).style.getPropertyValue("--aurora-x")))).toBeGreaterThan(0.3);
  const transform = await page.locator(".auth-aurora__logo-motion").evaluate(element => new DOMMatrixReadOnly(getComputedStyle(element).transform).m41);
  expect(transform).toBeGreaterThan(0);
  expect(transform).toBeLessThan(9);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect.poll(() => scene.getAttribute("style")).toBe("");
  await expect(page.locator(".auth-aurora__logo-motion")).toHaveCSS("transform", "none");
  await page.mouse.move(1300, 650);
  await expect(scene).toHaveAttribute("style", "");
  await page.getByLabel("Email", { exact: true }).fill("test@example.test");
  await expect(page.getByLabel("Email", { exact: true })).toHaveValue("test@example.test");
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await expect.poll(() => scene.evaluate(element => (element as HTMLElement).style.getPropertyValue("--aurora-breath"))).not.toBe("");

  const touch = await browser.newContext({ hasTouch: true, isMobile: true, viewport: { width: 390, height: 844 } });
  const touchPage = await touch.newPage();
  await touchPage.goto(`${process.env.FIXRATE_BASE_URL}/login`);
  await expect(touchPage.getByRole("heading", { name: "С возвращением" })).toBeVisible();
  await expect(touchPage.locator(".auth-aurora")).toBeHidden();
  expect(await touchPage.locator(".auth-aurora").getAttribute("style")).toBeNull();
  // A shorter viewport models the space left by an on-screen keyboard.
  await touchPage.setViewportSize({ width: 390, height: 460 });
  await touchPage.getByLabel("Пароль", { exact: true }).focus();
  await touchPage.getByRole("button", { name: "Войти", exact: true }).scrollIntoViewIfNeeded();
  await expect(touchPage.getByRole("button", { name: "Войти", exact: true })).toBeInViewport();
  await touch.close();
});

test("retains object selection when the server requires a site ID", async ({ page }) => {
  await page.route("**/api/v1/auth/login", route => route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ detail: "Укажите site_id: у пользователя несколько объектов" }) }), { times: 1 });
  await page.getByLabel("Email", { exact: true }).fill("fixrate-demo-dispatcher@example.test");
  await page.getByLabel("Пароль", { exact: true }).fill(process.env.FIXRATE_TEST_PASSWORD!);
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  const site = page.getByLabel("ID объекта", { exact: true });
  await expect(site).toBeVisible();
  await expect(site).toHaveAttribute("required");
  const hex = createHash("md5").update("fixrate-demo-site").digest("hex");
  await site.fill(`${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`);
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(page).toHaveURL(/\/dispatcher$/);
});

test("keyboard access, errors, pending state, password visibility and login return route", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  const email = page.getByLabel("Email", { exact: true });
  const password = page.getByLabel("Пароль", { exact: true });
  await page.keyboard.press("Tab");
  await expect(email).toBeFocused();
  await expect(email).toHaveCSS("outline-style", "solid");
  await page.keyboard.press("Tab");
  await expect(password).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Показать пароль" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(password).toHaveAttribute("type", "text");
  await page.keyboard.press("Enter");
  await expect(password).toHaveAttribute("type", "password");
  await page.keyboard.press("Tab");
  await expect(page.locator(".auth-site summary")).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Войти", exact: true })).toBeFocused();

  await email.fill("fixrate-demo-dispatcher@example.test");
  await password.fill("incorrect-password");
  await password.press("Enter");
  await expect(page.getByRole("alert")).toContainText("Неверный email или пароль");

  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/v1/auth/login", async route => {
    await held;
    await route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Проверка состояния ожидания" }) });
  });
  await password.press("Enter");
  await expect(page.getByRole("form", { name: "Вход в систему" })).toHaveAttribute("aria-busy", "true");
  await expect(page.getByRole("button", { name: "Входим…" })).toBeDisabled();
  await expect(email).toBeDisabled();
  await expect(password).toBeDisabled();
  release();
  await expect(page.getByRole("alert")).toContainText("Проверка состояния ожидания");
  await expect(password).toBeEnabled();
  await page.unroute("**/api/v1/auth/login");

  await page.getByRole("button", { name: /Обратитесь к администратору/ }).click();
  await expect(page.getByRole("dialog", { name: "Помощь со входом" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Обратитесь к администратору/ })).toBeFocused();
  await page.getByRole("link", { name: "Регистрация", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Регистрация сотрудника" })).toBeVisible();

  await page.goto("/equipment?source=login#list");
  await expect(page).toHaveURL(/\/login$/);
  await email.fill("fixrate-demo-dispatcher@example.test");
  await password.fill(process.env.FIXRATE_TEST_PASSWORD!);
  await password.press("Enter");
  await expect(page).toHaveURL(new URL("/equipment?source=login#list", process.env.FIXRATE_BASE_URL!).href);
  await expect(page.getByRole("heading", { name: "Оборудование", exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});
