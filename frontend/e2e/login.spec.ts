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
  await expect(page.getByRole("heading", { name: "Вход в систему" })).toBeVisible();
  await expect(page.getByLabel("Email", { exact: true })).toBeVisible();
});

test("responsive login composition and original logo", async ({ page }, testInfo) => {
  for (const [width, height] of [[1920,1080],[1440,900],[1366,768],[1024,768],[768,1024],[390,844],[375,812]]) {
    await page.setViewportSize({width,height});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await expect(page.locator(".auth-submit")).toBeInViewport();
    await expect(page.locator("svg.auth-ribbons")).toHaveCount(1);
    await expect(page.locator("canvas[data-aurora-particles]")).toHaveCount(1);
    await expect(page.locator(".auth-aurora filter")).toHaveCount(3);
    await expect(page.locator(".auth-aurora svg use")).toHaveCount(8);
    await expect(page.locator(".auth-aurora mask, .auth-particle, details, summary")).toHaveCount(0);
    const raster=await page.locator("canvas[data-aurora-particles]").evaluate(element=>({width:(element as HTMLCanvasElement).width,height:(element as HTMLCanvasElement).height}));
    expect(raster.width).toBeLessThanOrEqual(2400); expect(raster.height).toBeLessThanOrEqual(1800);
    if(width>820){ const logo=page.locator(".auth-aurora__logo img"); await expect(logo).toBeVisible(); expect(await logo.getAttribute("src")).toContain("fixrate-mark"); }
    else await expect(page.locator(".auth-aurora__brand")).toBeHidden();
    await page.screenshot({path:testInfo.outputPath(`aurora-${width}x${height}.png`),fullPage:true});
  }
});

test("original independent curves, tiny particles, pause, reduced motion and static logo", async ({page,browser},testInfo)=>{
  await page.setViewportSize({width:1440,height:900});
  const pixels=()=>page.locator(".auth-aurora canvas").evaluateAll(elements=>elements.map(element=>{
    const canvas=element as HTMLCanvasElement, data=canvas.getContext("2d")!.getImageData(0,0,canvas.width,canvas.height).data;
    let hash=2166136261,maxAlpha=0;
    for(let i=3;i<data.length;i+=4){ maxAlpha=Math.max(maxAlpha,data[i]); hash=Math.imul(hash^data[i],16777619); }
    return {hash,maxAlpha};
  }));
  const paths=()=>page.locator("[data-aurora-ribbon]").evaluateAll(elements=>elements.map(element=>element.getAttribute("d")));
  const snapshot=async()=>({paths:await paths(),pixels:await pixels()});
  const logos=()=>page.locator(".auth-brand img,.auth-aurora__logo img").evaluateAll(elements=>elements.map(element=>({box:element.getBoundingClientRect().toJSON(),transform:getComputedStyle(element).transform,opacity:getComputedStyle(element).opacity})));
  const setAnimation=async()=>{ await page.locator(".auth-footer button").click(); await page.locator(".auth-motion-setting input").press("Space"); await page.keyboard.press("Escape"); };
  const original=await logos(), initial=await snapshot();
  expect(initial.pixels[0].maxAlpha).toBeGreaterThan(0);
  expect(initial.pixels[0].maxAlpha).toBeLessThan(92);
  await page.waitForTimeout(900);
  const moved=await snapshot(); expect(moved.paths[0]).not.toBe(initial.paths[0]);expect(moved.paths[1]).not.toBe(initial.paths[1]);expect(moved.paths[2]).toBe(initial.paths[2]);
  expect(moved.pixels[0].hash).not.toBe(initial.pixels[0].hash);
  await page.mouse.move(1300,650); expect(await logos()).toEqual(original);
  await page.screenshot({path:testInfo.outputPath("original-curves-moving.png")});
  await setAnimation(); await expect(page.locator(".auth-aurora")).toHaveAttribute("data-motion","paused");
  await page.evaluate(()=>{Object.defineProperty(document,"hidden",{configurable:true,value:true});document.dispatchEvent(new Event("visibilitychange"));Reflect.deleteProperty(document,"hidden");document.dispatchEvent(new Event("visibilitychange"));});
  await page.setViewportSize({width:1199,height:700}); await page.setViewportSize({width:1440,height:900});
  const paused=await snapshot(); await page.waitForTimeout(500); expect(await snapshot()).toEqual(paused);
  await setAnimation(); await expect(page.locator(".auth-aurora")).toHaveAttribute("data-motion","running");
  await page.waitForTimeout(300); expect(await snapshot()).not.toEqual(paused); expect(await logos()).toEqual(original);
  await page.emulateMedia({reducedMotion:"reduce"}); await expect(page.locator(".auth-aurora")).toHaveAttribute("data-motion","paused");
  const reduced=await snapshot(); await page.waitForTimeout(500); expect(await snapshot()).toEqual(reduced);
  await page.locator(".auth-footer button").click(); await expect(page.locator(".auth-motion-setting input")).toBeDisabled(); await page.keyboard.press("Escape");
  await page.emulateMedia({reducedMotion:"no-preference"}); await expect(page.locator(".auth-aurora")).toHaveAttribute("data-motion","running");
  const touch=await browser.newContext({hasTouch:true,isMobile:true,viewport:{width:390,height:844}}); await mockLocalApi(touch);
  const touchPage=await touch.newPage(); await touchPage.goto(`${process.env.FIXRATE_BASE_URL}/login`);
  await expect(touchPage.getByLabel("Email",{exact:true})).toBeVisible(); await expect(touchPage.locator(".auth-aurora")).toHaveAttribute("data-motion","paused");
  await touch.close();
});

test("retains object selection when the server requires a site ID", async ({ page }) => {
  await page.setViewportSize({width:1366,height:768});
  const logo=page.locator(".auth-aurora__logo img");
  await expect(logo).toBeVisible();
  const originalLogo=await logo.boundingBox();
  await expect(page.locator("details, summary, #login-site")).toHaveCount(0);
  await page.route("**/api/v1/auth/login", route => route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ detail: "Укажите site_id: у пользователя несколько объектов" }) }), { times: 1 });
  await page.getByLabel("Email", { exact: true }).fill("fixrate-demo-dispatcher@example.test");
  await page.getByLabel("Пароль", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  const site = page.getByLabel("ID объекта", { exact: true });
  await expect(site).toBeVisible();
  await expect(site).toHaveAttribute("required");
  expect(await logo.boundingBox()).toEqual(originalLogo);
  await page.getByLabel("Email",{exact:true}).fill("");
  await page.getByLabel("Пароль",{exact:true}).fill("");
  await page.getByRole("button",{name:"Войти",exact:true}).click();
  await expect(page.getByRole("alert")).toHaveCount(3);
  expect(await logo.boundingBox()).toEqual(originalLogo);
  await page.getByLabel("Email",{exact:true}).fill("fixrate-demo-dispatcher@example.test");
  await page.getByLabel("Пароль",{exact:true}).fill(PASSWORD);
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
  await expect(page.getByRole("heading", { name: "Регистрация" })).toBeVisible();

  await page.goto("/equipment?source=login#list");
  await expect(page).toHaveURL(/\/login$/);
  await email.fill("fixrate-demo-dispatcher@example.test");
  await password.fill(PASSWORD);
  await password.press("Enter");
  await expect(page).toHaveURL(new URL("/equipment?source=login#list", process.env.FIXRATE_BASE_URL!).href);
  await expect(page.getByRole("heading", { name: "Оборудование", exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});
