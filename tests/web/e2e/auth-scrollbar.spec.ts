import { createHash } from "node:crypto";
import { test, expect } from "@playwright/test";

// Headless Chrome hides scrollbars by default; test real, space-taking bars.
test.use({ launchOptions: { ignoreDefaultArgs: ["--hide-scrollbars"], args: ["--disable-features=OverlayScrollbar,OverlayScrollbars"] } });

for (const width of [1440, 390]) {
  test(`auth scrollbar appears only for overflow without moving the artwork at ${width}px`, async ({ page, context }, testInfo) => {
    test.skip(!process.env.FIXRATE_BASE_URL, "Requires the running local application");
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await context.route("**/api/**", route => route.fulfill({ status: 401, json: { detail: "Нет сессии" } }));
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "Вход в систему" })).toBeVisible();
    const scene = page.locator(".auth-aurora");
    const canvas = scene.locator("canvas");
    await expect(scene).toHaveAttribute("data-motion", "paused");
    const original = await canvas.elementHandle();
    const geometry = async () => {
      const data = await canvas.evaluate(element => {
        const bounds = element.getBoundingClientRect();
        const canvas = element as HTMLCanvasElement;
        return { left: bounds.left, top: bounds.top, width: bounds.width, height: bounds.height,
          rasterWidth: canvas.width, rasterHeight: canvas.height, pixels: canvas.toDataURL() };
      });
      return { ...data, pixels: createHash("sha256").update(data.pixels).digest("hex") };
    };
    const documentState = () => page.evaluate(() => ({
      width: innerWidth, clientWidth: document.documentElement.clientWidth,
      height: document.documentElement.clientHeight, scrollHeight: document.documentElement.scrollHeight,
      gutter: getComputedStyle(document.documentElement).scrollbarGutter,
      scrollbar: getComputedStyle(document.documentElement).scrollbarWidth,
    }));
    await expect.poll(async () => (await documentState()).scrollHeight).toBe(900);
    const login = await documentState();
    expect(login.gutter).toBe("auto");
    expect(login.clientWidth).toBe(width);
    const before = await geometry();
    if (width > 820) expect(before.left + before.width).toBe(width);
    await page.screenshot({ path: testInfo.outputPath("login-without-gutter.png") });

    // Exercise the actual native scrollbar transition without remounting the scene.
    await page.locator(".auth-panel").evaluate(panel => {
      const spacer = document.createElement("div");
      spacer.id = "scrollbar-test-spacer";
      spacer.style.cssText = "height:1200px;flex-shrink:0";
      panel.append(spacer);
    });
    await expect.poll(async () => (await documentState()).scrollHeight).toBeGreaterThan(900);
    expect((await documentState()).scrollbar).not.toBe("none");
    expect((await documentState()).clientWidth).toBeLessThan(width);
    expect(await geometry()).toEqual(before);
    await page.mouse.move(200, 600);
    await page.mouse.wheel(0, 400);
    await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(0);
    expect(await geometry()).toEqual(before);
    await page.evaluate(() => { document.getElementById("scrollbar-test-spacer")?.remove(); window.scrollTo(0, 0); });
    await expect.poll(async () => (await documentState()).scrollHeight).toBe(900);
    expect(await geometry()).toEqual(before);

    await page.getByRole("link", { name: "Регистрация", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Регистрация", exact: true })).toBeVisible();
    await expect.poll(async () => (await documentState()).scrollHeight).toBeGreaterThan(900);
    expect(await canvas.evaluate((element, previous) => element === previous, original)).toBe(true);
    expect(await geometry()).toEqual(before);
    expect((await documentState()).scrollbar).not.toBe("none");
    await page.screenshot({ path: testInfo.outputPath("registration-with-scrollbar.png") });
    await page.evaluate(() => window.scrollTo(100, 0));
    expect(await page.evaluate(() => scrollX)).toBe(0);
    await page.locator(".auth-submit").scrollIntoViewIfNeeded();
    await expect(page.locator(".auth-submit")).toBeInViewport();
  });
}
