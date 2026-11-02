import { test, expect, type BrowserContext, type Page } from "@playwright/test";
import type { Equipment, SessionProfile } from "@/shared/types/domain";

async function fixtures(context: BrowserContext) {
  let profile: SessionProfile | null = null;
  let delay = 0;
  const equipment: Equipment = { id: "equipment", siteId: "site", siteName: "QA", equipmentType: "Насос", inventoryCode: "QA-1", name: "Насос QA", location: "Цех", commissionedOn: null, state: "active", revision: 1, dataOrigin: "synthetic_demo", nextDueDate: null, lastServiceAt: null, activeOperation: null };
  await context.route("**/*", async route => {
    const request = route.request(); const path = new URL(request.url()).pathname;
    if (!path.startsWith("/api/")) return route.continue();
    if (path.endsWith("/auth/login")) {
      const email = request.postDataJSON().email as string;
      profile = { userId: email, email, name: "QA", role: "dispatcher", siteName: "QA", timezone: "UTC" };
      return route.fulfill({ json: { profile } });
    }
    if (path.endsWith("/auth/session")) return route.fulfill(profile ? { json: { profile } } : { status: 401, json: { detail: "Нет сессии" } });
    if (path.endsWith("/auth/logout")) { profile = null; return route.fulfill({ status: 204 }); }
    if (path.endsWith("/ui/tasks") && delay) await new Promise(resolve => setTimeout(resolve, delay));
    return route.fulfill({ json: path.endsWith("/ui/equipment") ? [equipment] : [] });
  });
  return (milliseconds: number) => { delay = milliseconds; };
}

async function login(page: Page, email = "qa@workspace.test") {
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Пароль", { exact: true }).fill("workspace-password");
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(page).not.toHaveURL(/\/login$/);
  if (!page.url().endsWith("/dispatcher")) await page.goto("/dispatcher");
  await page.locator(".ops-overview").waitFor();
  await expect(page.locator(".workspace-root [data-workspace-loading]")).toHaveCount(0);
}

test.beforeEach(async () => { test.skip(!process.env.FIXRATE_BASE_URL, "Requires the running local application"); });

test("reload retains sidebar width, page scroll, month and filters without leaking to another account", async ({ page, context }) => {
  await fixtures(context);
  await page.setViewportSize({ width: 1440, height: 500 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await login(page);
  for (const expanded of [true, false]) {
    await page.locator(".ops-sidebar-toggle").click();
    await page.evaluate(() => scrollTo(0, 300));
    await expect.poll(() => page.evaluate(() => scrollY)).toBe(300);
    await page.reload();
    await expect(page.locator(".ops-shell")).toHaveAttribute("data-sidebar-expanded", String(expanded));
    await expect.poll(() => page.evaluate(() => scrollY)).toBe(300);
  }
  await page.goto("/equipment");
  await page.locator("#equipment-search").fill("Насос");
  await page.getByLabel("Состояние", { exact: true }).selectOption("active");
  await page.reload();
  await expect(page.locator("#equipment-search")).toHaveValue("Насос");
  await expect(page.getByLabel("Состояние", { exact: true })).toHaveValue("active");
  await page.goto("/calendar");
  await page.getByRole("button", { name: "Следующий месяц" }).click();
  const month = await page.getByRole("button", { name: "Следующий месяц" }).evaluate(element => element.previousElementSibling!.textContent);
  await page.reload();
  await expect.poll(() => page.getByRole("button", { name: "Следующий месяц" }).evaluate(element => element.previousElementSibling!.textContent)).toBe(month);
  await page.locator(".workspace-account-trigger").click();
  await page.getByRole("button", { name: "Выйти из аккаунта", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await login(page, "other@workspace.test");
  await page.goto("/equipment");
  await expect(page.locator("#equipment-search")).toHaveValue("");
  await expect(page.getByLabel("Состояние", { exact: true })).toHaveValue("all");
});

test("phone reload retains an open menu and horizontal table position", async ({ page, context }) => {
  await fixtures(context);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await login(page);
  await page.goto("/equipment");
  const table = page.getByRole("region", { name: "Реестр оборудования" });
  await table.waitFor(); await table.evaluate(element => { element.scrollLeft = 200; });
  await page.reload();
  await expect.poll(() => table.evaluate(element => element.scrollLeft)).toBe(200);
  await page.getByRole("button", { name: "Открыть меню", exact: true }).click();
  await page.reload();
  await expect(page.getByRole("dialog", { name: "Мобильная навигация" })).toBeVisible();
  await expect(page.locator(".ops-stage")).toHaveAttribute("inert");
  await page.keyboard.press("Escape");
  await expect(page.locator(".ops-stage")).not.toHaveAttribute("inert");
});

test("delayed API restores scroll after loading and manual scrolling cancels restoration", async ({ page, context }) => {
  const delay = await fixtures(context);
  await page.setViewportSize({ width: 1440, height: 500 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await login(page);
  await page.evaluate(() => scrollTo(0, 300));
  delay(1000);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator(".workspace-root [data-workspace-loading]").first().waitFor();
  await expect(page.locator(".workspace-root [data-workspace-loading]")).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => scrollY)).toBe(300);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator(".workspace-root [data-workspace-loading]").first().waitFor();
  await page.mouse.move(900, 300); await page.mouse.wheel(0, -1000);
  await expect(page.locator(".workspace-root [data-workspace-loading]")).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => scrollY)).toBe(0);
});
