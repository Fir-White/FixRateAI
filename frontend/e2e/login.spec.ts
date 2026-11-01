import { test, expect, type BrowserContext } from "@playwright/test";
import { createHash } from "node:crypto";

const PASSWORD = "local-test-password";
async function mockLocalApi(context: BrowserContext) {
  await context.route("**/*", route => {
    const url = new URL(route.request().url());
    if (url.origin !== new URL(process.env.FIXRATE_BASE_URL!).origin) return route.abort();
    if (!url.pathname.startsWith("/api/")) return route.continue();
    if (url.pathname === "/api/v1/auth/login" && route.request().postDataJSON()?.password === PASSWORD) {
      return route.fulfill({ json: { profile: { userId: "local-qa", name: "QA", email: "qa@example.test", role: "dispatcher", siteName: "QA", timezone: "UTC" } } });
    }
    return route.fulfill({ status: 401, json: { detail: "Неверный email или пароль" } });
  });
}

test.beforeEach(async ({ page, context }) => {
  test.skip(!process.env.FIXRATE_BASE_URL, "Requires the running local application");
  await mockLocalApi(context);
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "С возвращением" })).toBeVisible();
  await expect(page.getByLabel("Email", { exact: true })).toBeVisible();
});

test("responsive login composition and original logo", async ({ page }, testInfo) => {
  for (const [width, height] of [[1920, 1080], [1440, 900], [1366, 768], [1200, 900], [1199, 900], [1440, 700], [1024, 768], [768, 1024], [390, 844], [375, 812]]) {
    await page.setViewportSize({ width, height });
    const size = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }));
    expect(size.document).toBeLessThanOrEqual(size.viewport);
    const submit = page.getByRole("button", { name: "Войти", exact: true });
    await expect(submit).toBeInViewport();
    const controls = await page.locator("#login-email, #login-password, .auth-submit").evaluateAll(elements => elements.map(element => Math.round(element.getBoundingClientRect().height)));
    expect(controls).toEqual([52, 52, 52]);
    await expect(page.locator(".auth-art__frame, .auth-divider, .auth-support")).toHaveCount(0);
    if (width > 820) {
      const logo = page.locator(".auth-aurora__logo img");
      await expect(logo).toBeVisible();
      expect(await logo.getAttribute("src")).toContain("fixrate-mark");
      const box = (await logo.boundingBox())!;
      expect(Math.abs(box.width - box.height)).toBeLessThan(1);
      expect(box.width).toBeLessThanOrEqual(380);
    } else {
      await expect(page.locator(".auth-aurora__brand")).toBeHidden();
      await expect(page.locator(".auth-ribbons").first()).toBeVisible();
    }
    await expect(page.locator("[data-aurora-ribbon]")).toHaveCount(3);
    await expect(page.locator(".auth-orb, .auth-motion-toggle")).toHaveCount(0);
    await expect(page.locator(".auth-particle")).toHaveCount(10);
    for (const particle of await page.locator(".auth-particle").all()) {
      if (width <= 1199 || height <= 700) await expect(particle).toBeHidden();
      else await expect(particle).toBeVisible();
    }
    await page.screenshot({ path: testInfo.outputPath(`aurora-${width}x${height}.png`), fullPage: true });
  }
});

test("independent light motion, static logo, pause continuity, reduced motion and touch fallback", async ({ page, browser }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  const lights = () => page.locator(".auth-light-motion, .auth-particle").evaluateAll(elements => elements.map(element => ({ transform: getComputedStyle(element).transform, time: element.getAnimations()[0]?.currentTime })));
  const setAnimation = async (enabled: boolean) => {
    await page.getByRole("button", { name: /Обратитесь к администратору/ }).click();
    const checkbox = page.getByRole("checkbox", { name: "Анимация фона" });
    await checkbox.focus();
    await page.keyboard.press("Space");
    if (enabled) await expect(checkbox).toBeChecked();
    else await expect(checkbox).not.toBeChecked();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("button", { name: /Обратитесь к администратору/ })).toBeFocused();
  };
  const logos = () => page.locator(".auth-brand img, .auth-aurora__logo img").evaluateAll(elements => elements.map(element => ({ box: element.getBoundingClientRect().toJSON(), transform: getComputedStyle(element).transform, opacity: getComputedStyle(element).opacity })));
  const originalLogo = await logos();
  const start = await lights();
  await page.waitForTimeout(2200);
  expect((await lights()).every((light, index) => light.transform !== start[index].transform)).toBe(true);
  await page.mouse.move(1300, 650);
  expect(await logos()).toEqual(originalLogo);
  await expect(page.locator(".auth-aurora button")).toHaveCount(0);
  await setAnimation(false);
  await page.waitForTimeout(100);
  const paused = await lights();
  await page.evaluate(() => { Object.defineProperty(document, "hidden", { configurable: true, value: true }); document.dispatchEvent(new Event("visibilitychange")); });
  await page.evaluate(() => { Reflect.deleteProperty(document, "hidden"); document.dispatchEvent(new Event("visibilitychange")); });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.setViewportSize({ width: 1199, height: 700 });
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.locator(".auth-aurora")).toHaveAttribute("data-motion", "paused");
  await page.waitForTimeout(2200);
  expect(await lights()).toEqual(paused);
  await setAnimation(true);
  const resumed = await lights();
  resumed.forEach((light, index) => expect(Math.abs(Number(light.time) - Number(paused[index].time))).toBeLessThan(200));
  expect(await logos()).toEqual(originalLogo);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.getByRole("button", { name: /Обратитесь к администратору/ }).click();
  await expect(page.getByRole("checkbox", { name: "Анимация фона" })).toBeDisabled();
  await expect(page.getByRole("checkbox", { name: "Анимация фона" })).not.toBeChecked();
  await expect(page.getByText("Анимация отключена системной настройкой уменьшения движения.")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.waitForTimeout(100);
  const reduced = await lights();
  await page.waitForTimeout(2200);
  expect(await lights()).toEqual(reduced);
  await page.getByLabel("Email", { exact: true }).fill("test@example.test");
  await expect(page.getByLabel("Email", { exact: true })).toHaveValue("test@example.test");
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await expect(page.locator(".auth-aurora")).toHaveAttribute("data-motion", "running");

  const touch = await browser.newContext({ hasTouch: true, isMobile: true, viewport: { width: 390, height: 844 } });
  await mockLocalApi(touch);
  const touchPage = await touch.newPage();
  await touchPage.goto(`${process.env.FIXRATE_BASE_URL}/login`);
  await expect(touchPage.getByRole("heading", { name: "С возвращением" })).toBeVisible();
  await expect(touchPage.locator(".auth-aurora__brand")).toBeHidden();
  await expect(touchPage.locator(".auth-ribbons").first()).toBeVisible();
  await expect(touchPage.locator(".auth-aurora")).toHaveAttribute("data-motion", "paused");
  // A shorter viewport models the space left by an on-screen keyboard.
  await touchPage.setViewportSize({ width: 390, height: 460 });
  await touchPage.getByLabel("Пароль", { exact: true }).focus();
  await touchPage.getByRole("button", { name: "Войти", exact: true }).scrollIntoViewIfNeeded();
  await expect(touchPage.getByRole("button", { name: "Войти", exact: true })).toBeInViewport();
  await touch.close();
});

test("ribbons retain separate static geometry; particles exclude the fully opaque protected brand", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const paths = page.locator("[data-aurora-ribbon]");
  const initial = await paths.evaluateAll(elements => elements.map(element => element.getAttribute("d")));
  await page.screenshot({ path: testInfo.outputPath("flow-idle-start.png") });
  await page.waitForTimeout(2200);
  expect(await paths.evaluateAll(elements => elements.map(element => element.getAttribute("d")))).toEqual(initial);
  const logo = (await page.locator(".auth-aurora__logo img").boundingBox())!;
  for (const particle of await page.locator(".auth-particle").all()) {
    const corridor = await particle.evaluate(element => {
      const box = element.getBoundingClientRect();
      const current = new DOMMatrixReadOnly(getComputedStyle(element).transform);
      return (element.getAnimations()[0].effect as KeyframeEffect).getKeyframes().map(frame => {
        const transform = new DOMMatrixReadOnly(String(frame.transform));
        return { x: box.x - current.m41 + transform.m41, y: box.y - current.m42 + transform.m42, width: box.width, height: box.height };
      });
    });
    for (const box of corridor) expect(box.x + box.width < logo.x - 48 || box.x > logo.x + logo.width + 48 || box.y + box.height < logo.y - 48 || box.y > logo.y + logo.height + 48).toBe(true);
  }
  await expect(page.locator(".auth-aurora__logo img")).toHaveCSS("opacity", "1");
  const ancestors = await page.locator(".auth-aurora__logo img").evaluate(image => {
    const values = [];
    for (let element: Element | null = image; element; element = element.parentElement) {
      const style = getComputedStyle(element);
      values.push({ transform: style.transform, filter: style.filter, opacity: style.opacity, blend: style.mixBlendMode, animations: element.getAnimations().length });
      if (element.classList.contains("auth-page")) break;
    }
    return values;
  });
  ancestors.forEach(value => expect(value).toEqual({ transform: "none", filter: "none", opacity: "1", blend: "normal", animations: 0 }));
  const stack = await page.locator(".auth-aurora").evaluate(scene => [".auth-aurora__vignette", ".auth-aurora__scrim", ".auth-aurora__brand"].map(selector => Number(getComputedStyle(scene.querySelector(selector)!).zIndex)));
  expect(stack).toEqual([2, 3, 4]);
  expect(await page.locator(".auth-aurora__brand").evaluate(element => getComputedStyle(element, "::before").content)).toBe("none");
  await page.screenshot({ path: testInfo.outputPath("flow-idle-moving.png") });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.locator(".auth-aurora")).toHaveAttribute("data-motion", "paused");
  const still = await paths.evaluateAll(elements => elements.map(element => element.getAttribute("d")));
  expect(still.every(path => path && path.includes(" C ") && path.includes(" S "))).toBe(true);
  await expect(page.locator(".auth-ribbons").first()).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("flow-reduced-motion.png") });
  expect(await paths.evaluateAll(elements => elements.map(element => element.getAttribute("d")))).toEqual(still);
});

test("retains object selection when the server requires a site ID", async ({ page }) => {
  await expect(page.locator("details, summary, #login-site")).toHaveCount(0);
  await page.route("**/api/v1/auth/login", route => route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ detail: "Укажите site_id: у пользователя несколько объектов" }) }), { times: 1 });
  await page.getByLabel("Email", { exact: true }).fill("fixrate-demo-dispatcher@example.test");
  await page.getByLabel("Пароль", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  const site = page.getByLabel("ID объекта", { exact: true });
  await expect(site).toBeVisible();
  await expect(site).toHaveAttribute("required");
  const hex = createHash("md5").update("fixrate-demo-site").digest("hex");
  const siteId = `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
  await site.fill(siteId);
  const payload = page.waitForRequest(request => request.url().endsWith("/api/v1/auth/login"));
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  expect((await payload).postDataJSON().site_id).toBe(siteId);
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
  await password.fill(PASSWORD);
  await password.press("Enter");
  await expect(page).toHaveURL(new URL("/equipment?source=login#list", process.env.FIXRATE_BASE_URL!).href);
  await expect(page.getByRole("heading", { name: "Оборудование", exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});
