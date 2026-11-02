import { test, expect, type BrowserContext, type Page } from "@playwright/test";

async function sessionFixture(context: BrowserContext) {
  let profile: { userId: string; name: string; email: string; role: string; siteName: string; timezone: string } | null = null;
  let rejectLogout = true;
  const logoutHeaders: string[] = [];
  await context.addCookies([{ name: "fixrate_csrf", value: "workspace-qa", url: process.env.FIXRATE_BASE_URL! }]);
  await context.route("**/*", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== new URL(process.env.FIXRATE_BASE_URL!).origin) return route.abort();
    if (!url.pathname.startsWith("/api/")) return route.continue();
    if (url.pathname === "/api/v1/auth/login") {
      const email = request.postDataJSON().email as string;
      const engineer = email.startsWith("engineer");
      profile = { userId: email, name: engineer ? "Инженер QA" : "Диспетчер QA", email, role: engineer ? "engineer" : "dispatcher", siteName: "Объект QA", timezone: "UTC" };
      return route.fulfill({ json: { profile } });
    }
    if (url.pathname === "/api/v1/auth/session") return route.fulfill(profile ? { json: { profile } } : { status: 401, json: { detail: "Нет сессии" } });
    if (url.pathname === "/api/v1/auth/logout") {
      expect(request.method()).toBe("POST");
      logoutHeaders.push((await request.allHeaders())["x-csrf-token"]);
      if (rejectLogout) { rejectLogout = false; return route.fulfill({ status: 503, json: { detail: "Сервис временно недоступен" } }); }
      profile = null;
      return route.fulfill({ status: 204 });
    }
    return route.fulfill({ json: [] });
  });
  return logoutHeaders;
}

async function signIn(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Пароль", { exact: true }).fill("local-workspace-password");
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(page).not.toHaveURL(/\/login$/);
}

test("account preserves session after failed logout and clears the previous user after successful logout", async ({ page, context }) => {
  test.skip(!process.env.FIXRATE_BASE_URL, "Requires the running local application");
  const headers = await sessionFixture(context);
  await page.setViewportSize({ width: 1440, height: 900 });
  await signIn(page, "dispatcher@workspace.test");
  const canvas = await page.locator(".workspace-aurora canvas").elementHandle();
  await page.getByRole("link", { name: "Оборудование", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Оборудование", exact: true })).toBeVisible();
  expect(await page.locator(".workspace-aurora canvas").evaluate((element, original) => element === original, canvas)).toBe(true);
  await page.locator(".workspace-account-trigger").click();
  await page.getByRole("button", { name: "Мой профиль", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Мой профиль" })).toContainText("dispatcher@workspace.test");
  await page.keyboard.press("Escape");
  await expect(page.locator(".workspace-account-trigger")).toBeFocused();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Выйти из аккаунта", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText("Сервис временно недоступен");
  await expect(page.locator(".workspace-account-trigger")).toContainText("Диспетчер QA");
  await expect(page.getByRole("button", { name: "Выйти из аккаунта", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Выйти из аккаунта", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.locator(".workspace-root")).toHaveCount(0);
  await page.goto("/equipment");
  await expect(page).toHaveURL(/\/login$/);
  await signIn(page, "engineer@workspace.test");
  await expect(page.locator(".workspace-account-trigger")).toContainText("Инженер QA");
  await page.locator(".workspace-account-trigger").click();
  await page.getByRole("button", { name: "Мой профиль", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Мой профиль" })).toContainText("engineer@workspace.test");
  await expect(page.locator("body")).not.toContainText("dispatcher@workspace.test");
  expect(headers).toEqual(["workspace-qa", "workspace-qa"]);
});

test("one mobile sidebar contains the account and preserves the reduced-motion background", async ({ page, context }) => {
  test.skip(!process.env.FIXRATE_BASE_URL, "Requires the running local application");
  await sessionFixture(context);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await signIn(page, "dispatcher@workspace.test");
  await expect(page.locator(".workspace-aurora canvas")).toHaveAttribute("data-state", "paused");
  await expect(page.locator(".ops-sidebar, .ops-sidebar-nav, .workspace-aurora canvas")).toHaveCount(3);
  await page.getByRole("button", { name: "Открыть меню", exact: true }).click();
  await page.locator(".workspace-account-trigger").click();
  await expect(page.getByRole("dialog", { name: "Меню аккаунта", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Мобильная навигация" })).toBeVisible();
  await page.getByRole("link", { name: "Оборудование", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".ops-stage")).not.toHaveAttribute("inert");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});
