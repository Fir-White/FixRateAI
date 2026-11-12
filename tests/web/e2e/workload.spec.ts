import { test, expect } from "@playwright/test";

for (const width of [1365, 390, 320]) {
  test(`workload read-only calculation and capacity control at ${width}px`, async ({page}) => {
    test.skip(!process.env.FIXRATE_BASE_URL, "Use an isolated API/PostgreSQL instance");
    await page.setViewportSize({width, height: 900});
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto("/login");
    await page.getByLabel("Email", {exact: true}).fill("fixrate-demo-chief_engineer@example.test");
    await page.getByLabel("Пароль", {exact: true}).fill(process.env.FIXRATE_TEST_PASSWORD!);
    await page.getByRole("button", {name: "Войти", exact: true}).click();
    await expect(page).not.toHaveURL(/\/login$/);
    await page.goto("/calendar");
    const loaded = page.waitForResponse(response => response.url().includes("/planning/workload?"));
    await page.getByRole("button", {name: "Нагрузка и персонал", exact: true}).click();
    const initial = await loaded;
    expect(initial.status()).toBe(200);
    const data = await initial.json();
    expect(Number(data.capacity_hours_per_24h)).toBe(24);
    expect(data.policy_status).toBe("provisional");
    const panel = page.getByRole("region", {name: "Нагрузка и персонал", exact: true});
    await expect(panel.getByLabel("Полезные часы за 24 часа присутствия")).toHaveValue("24");
    await expect(panel.getByRole("status")).toHaveCount(0);
    expect(await panel.locator(".fr-workload-day").count()).toBe(data.days.length);
    const changed = page.waitForResponse(response => response.url().includes("capacity_hours_per_24h=12"));
    await panel.getByLabel("Полезные часы за 24 часа присутствия").fill("12");
    // Keyboard submission remains available on narrow screens.
    await panel.getByLabel("Полезные часы за 24 часа присутствия").press("Enter");
    const next = await changed;
    expect(next.status()).toBe(200);
    expect(Number((await next.json()).capacity_hours_per_24h)).toBe(12);
    await expect(panel.getByRole("status")).toHaveCount(0);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    expect(overflow).toBe(false);
    await page.screenshot({path: test.info().outputPath(`workload-${width}.png`), animations: "disabled"});
    expect(errors).toEqual([]);
  });
}
