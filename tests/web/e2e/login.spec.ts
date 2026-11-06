import { chromium, test, expect, type BrowserContext } from "@playwright/test";
import { createHash } from "node:crypto";

const PASSWORD = "local-test-password";
async function mockLocalApi(context: BrowserContext) {
  let signedIn = false;
  const profile = { userId: "local-qa", name: "QA", email: "qa@example.test", role: "dispatcher", siteName: "QA", timezone: "UTC" };
  await context.route("**/*", route => {
    const url = new URL(route.request().url());
    if (url.origin !== new URL(process.env.FIXRATE_BASE_URL!).origin) return route.abort();
    if (!url.pathname.startsWith("/api/")) return route.continue();
    if (url.pathname === "/api/v1/auth/login" && route.request().postDataJSON()?.password === PASSWORD) {
      signedIn = true;
      return route.fulfill({ json: { profile } });
    }
    if (signedIn && url.pathname === "/api/v1/auth/session") return route.fulfill({ json: {profile} });
    if (signedIn && route.request().method() === "GET" && url.pathname.startsWith("/api/v1/maintenance/")) return route.fulfill({json: []});
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

test("responsive open light scene and original small auth brand", async ({ page }, testInfo) => {
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
    await expect(page.locator(".auth-aurora img, .auth-aurora__brand, .auth-aurora__logo, .auth-aurora__scrim, .auth-aurora__vignette")).toHaveCount(0);
    await expect(page.locator(".auth-brand__mark")).toBeVisible();
    expect(await page.locator(".auth-brand__mark").getAttribute("src")).toContain("fixrate-mark");
    await page.screenshot({path:testInfo.outputPath(`aurora-${width}x${height}.png`),fullPage:true});
  }
});

test("independent curves, tiny particles, automatic pauses, reduced motion and static small brand", async ({page,browser},testInfo)=>{
  await page.setViewportSize({width:1440,height:900});
  const pixels=()=>page.locator(".auth-aurora canvas").evaluateAll(elements=>elements.map(element=>{
    const canvas=element as HTMLCanvasElement, data=canvas.getContext("2d")!.getImageData(0,0,canvas.width,canvas.height).data;
    let hash=2166136261,maxAlpha=0;
    for(let i=3;i<data.length;i+=4){ maxAlpha=Math.max(maxAlpha,data[i]); hash=Math.imul(hash^data[i],16777619); }
    return {hash,maxAlpha};
  }));
  const paths=()=>page.locator("[data-aurora-ribbon]").evaluateAll(elements=>elements.map(element=>element.getAttribute("d")));
  const snapshot=async()=>({paths:await paths(),pixels:await pixels()});
  const logos=()=>page.locator(".auth-brand img").evaluateAll(elements=>elements.map(element=>({box:element.getBoundingClientRect().toJSON(),transform:getComputedStyle(element).transform,opacity:getComputedStyle(element).opacity})));
  const original=await logos(), initial=await snapshot();
  expect(initial.pixels[0].maxAlpha).toBeGreaterThan(0);
  expect(initial.pixels[0].maxAlpha).toBeLessThan(92);
  await page.waitForTimeout(900);
  const moved=await snapshot(); expect(moved.paths[0]).not.toBe(initial.paths[0]);expect(moved.paths[1]).not.toBe(initial.paths[1]);expect(moved.paths[2]).toBe(initial.paths[2]);
  expect(moved.pixels[0].hash).not.toBe(initial.pixels[0].hash);
  await page.mouse.move(1300,650); expect(await logos()).toEqual(original);
  await page.screenshot({path:testInfo.outputPath("original-curves-moving.png")});
  await page.evaluate(()=>{Object.defineProperty(document,"hidden",{configurable:true,value:true});document.dispatchEvent(new Event("visibilitychange"));});
  await expect(page.locator(".auth-aurora")).toHaveAttribute("data-motion","paused");
  await page.setViewportSize({width:1199,height:700}); await page.setViewportSize({width:1440,height:900});
  // ResizeObserver redraw is asynchronous even while animation is paused.
  // Wait for the restored desktop canvas before comparing its frozen frames.
  await expect.poll(async () => (await pixels())[0]?.maxAlpha ?? 0).toBeGreaterThan(0);
  const paused=await snapshot(); await page.waitForTimeout(500); expect(await snapshot()).toEqual(paused);
  await page.evaluate(()=>{Reflect.deleteProperty(document,"hidden");document.dispatchEvent(new Event("visibilitychange"));});
  await expect(page.locator(".auth-aurora")).toHaveAttribute("data-motion","running");
  await page.waitForTimeout(300); expect(await snapshot()).not.toEqual(paused); expect(await logos()).toEqual(original);
  const password=page.getByLabel("Пароль",{exact:true});
  await password.focus();await password.press("Space");await expect(password).toHaveValue(" ");
  await expect(page.locator(".auth-aurora")).toHaveAttribute("data-motion","running");
  const beforeSpace=await paths();await page.waitForTimeout(300);expect(await paths()).not.toEqual(beforeSpace);
  await password.fill("");
  await page.emulateMedia({reducedMotion:"reduce"}); await expect(page.locator(".auth-aurora")).toHaveAttribute("data-motion","paused");
  const reduced=await snapshot(); await page.waitForTimeout(500); expect(await snapshot()).toEqual(reduced);
  await expect(page.getByRole("checkbox")).toHaveCount(0);await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.emulateMedia({reducedMotion:"no-preference"}); await expect(page.locator(".auth-aurora")).toHaveAttribute("data-motion","running");
  const touch=await browser.newContext({hasTouch:true,isMobile:true,viewport:{width:390,height:844}}); await mockLocalApi(touch);
  const touchPage=await touch.newPage(); await touchPage.goto(`${process.env.FIXRATE_BASE_URL}/login`);
  await expect(touchPage.getByLabel("Email",{exact:true})).toBeVisible(); await expect(touchPage.locator(".auth-aurora")).toHaveAttribute("data-motion","running");
  await expect(touchPage.locator(".auth-aurora")).toHaveAttribute("data-profile","mobile");
  await expect(touchPage.locator(".auth-aurora")).toHaveAttribute("data-renderer","canvas");
  await expect(touchPage.locator("svg.auth-ribbons")).toBeHidden();
  const touchPixels=()=>touchPage.locator(".auth-aurora canvas").evaluate(element=>{
    const canvas=element as HTMLCanvasElement,data=canvas.getContext("2d")!.getImageData(0,0,canvas.width,canvas.height).data;
    let hash=2166136261;for(let i=3;i<data.length;i+=64)hash=Math.imul(hash^data[i],16777619);return hash;
  });
  const mobileStart=await touchPixels();await touchPage.waitForTimeout(500);expect(await touchPixels()).not.toBe(mobileStart);
  await touchPage.emulateMedia({reducedMotion:"reduce"});await expect(touchPage.locator(".auth-aurora")).toHaveAttribute("data-motion","paused");
  const mobileReduced=await touchPixels();await touchPage.waitForTimeout(300);expect(await touchPixels()).toBe(mobileReduced);
  await touch.close();
});

test("retains object selection when the server requires a site ID", async ({ page }) => {
  await page.setViewportSize({width:1366,height:768});
  const logo=page.locator(".auth-brand__mark");
  await expect(logo).toBeVisible();
  const logoPlacement=()=>logo.evaluate(element=>{const box=element.getBoundingClientRect();return{x:box.x+scrollX,y:box.y+scrollY,width:box.width,height:box.height,transform:getComputedStyle(element).transform};});
  const originalLogo=await logoPlacement();
  await expect(page.locator("details, summary, #login-site")).toHaveCount(0);
  await page.route("**/api/v1/auth/login", route => route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ detail: "Укажите site_id: у пользователя несколько объектов" }) }), { times: 1 });
  await page.getByLabel("Email", { exact: true }).fill("fixrate-demo-dispatcher@example.test");
  await page.getByLabel("Пароль", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  const site = page.getByLabel("ID объекта", { exact: true });
  await expect(site).toBeVisible();
  await expect(site).toHaveAttribute("required");
  expect(await logoPlacement()).toEqual(originalLogo);
  await page.getByLabel("Email",{exact:true}).fill("");
  await page.getByLabel("Пароль",{exact:true}).fill("");
  await page.getByRole("button",{name:"Войти",exact:true}).click();
  await expect(page.getByRole("alert")).toHaveCount(3);
  expect(await logoPlacement()).toEqual(originalLogo);
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
  await expect(email).toHaveCSS("outline-style", "none");
  await expect(email).toHaveCSS("box-shadow", "none");
  await expect(email).toHaveCSS("border-width", "2px");
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

  await expect(page.locator(".auth-footer")).toHaveText("Не получается войти?Обратитесь к администратору вашего объекта для восстановления доступа.");
  await expect(page.locator(".auth-footer a, .auth-footer button, .auth-footer input")).toHaveCount(0);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("link", { name: "Регистрация", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Регистрация" })).toBeVisible();

  await page.goto("/equipment?source=login#list");
  await expect(page).toHaveURL(/\/login$/);
  await email.fill("fixrate-demo-dispatcher@example.test");
  await password.fill(PASSWORD);
  await password.press("Enter");
  await expect(page).toHaveURL(new URL("/dispatcher", process.env.FIXRATE_BASE_URL!).href);
  await expect(page.getByRole("heading", { name: "Панель диспетчера", exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test("auth links activate on the first physical click or touch while an empty field loses focus", async ({ browser }) => {
  for (const mobile of [false,true]) {
    const context=await browser.newContext({viewport:mobile ? {width:390,height:844} : {width:1366,height:768},hasTouch:mobile,isMobile:mobile});
    await mockLocalApi(context);
    const page=await context.newPage();
    try {
      await page.goto(`${process.env.FIXRATE_BASE_URL}/login`);
      for (const [field,label,destination] of [["Пароль","Регистрация","/register"],["Подтвердите пароль","Перейти ко входу","/login"]]) {
        const link=page.getByRole("link",{name:label,exact:true});
        await link.scrollIntoViewIfNeeded();
        await page.getByLabel(field,{exact:true}).focus();
        const box=await link.boundingBox();
        expect(box).not.toBeNull();
        const x=box!.x+box!.width/2,y=box!.y+box!.height/2;
        if(mobile) await page.touchscreen.tap(x,y);
        else { await page.mouse.move(x,y);await page.mouse.down();await page.mouse.up(); }
        await expect(page).toHaveURL(new URL(destination,process.env.FIXRATE_BASE_URL!).href,{timeout:2000});
      }
      await page.getByLabel("Пароль",{exact:true}).focus();
      const submit=await page.getByRole("button",{name:"Войти",exact:true}).boundingBox();
      expect(submit).not.toBeNull();
      const x=submit!.x+submit!.width/2,y=submit!.y+submit!.height/2;
      if(mobile) await page.touchscreen.tap(x,y);
      else { await page.mouse.move(x,y);await page.mouse.down();await page.mouse.up(); }
      await expect(page.getByRole("alert")).toHaveCount(2);
      await expect(page.getByLabel("Email",{exact:true})).toBeFocused();
      await page.goto(`${process.env.FIXRATE_BASE_URL}/login`);
      await page.getByLabel("Пароль",{exact:true}).focus();
      await page.getByLabel("Email",{exact:true}).focus();
      await expect(page.getByLabel("Пароль",{exact:true})).toHaveAttribute("aria-invalid","true");
      await expect(page.getByRole("alert")).toHaveText("Введите пароль");
    } finally { await context.close(); }
  }
});

for (const target of ["submit", "password visibility"]) {
  test(`a second physical press on disabled pending ${target} cannot hide a server error`, async ({ page }) => {
    let posts=0,release!:()=>void;
    const held=new Promise<void>(resolve=>{release=resolve;});
    await page.route("**/api/v1/auth/login",async route=>{
      posts++;
      if(posts===1) await held;
      await route.fulfill({status:401,json:{detail:"Неверный email или пароль"}});
    });
    await page.getByLabel("Email",{exact:true}).fill("test@example.test");
    await page.getByLabel("Пароль",{exact:true}).fill("incorrect-password");
    const submit=page.locator(".auth-submit");
    const first=await submit.boundingBox();
    await page.mouse.click(first!.x+first!.width/2,first!.y+first!.height/2);
    await expect(submit).toBeDisabled();
    const disabled=target==="submit" ? submit : page.getByRole("button",{name:"Показать пароль"});
    await expect(disabled).toBeDisabled();
    const second=await disabled.boundingBox();
    await page.mouse.click(second!.x+second!.width/2,second!.y+second!.height/2);
    release();
    const alert=page.locator("#login-error");
    await expect(alert).toHaveText("Неверный email или пароль");
    await expect.poll(()=>alert.evaluate(element=>element.parentElement!.getBoundingClientRect().height)).toBeGreaterThan(20);
    await expect.poll(()=>page.locator(".auth-panel").evaluate(element=>element.getAnimations({subtree:true}).filter(animation=>animation.id==="motion-feedback-layout" && animation.playState==="paused").length)).toBe(0);
    expect(posts).toBe(1);
    await expect(submit).toBeEnabled();
    const retry=await submit.boundingBox();
    await page.mouse.click(retry!.x+retry!.width/2,retry!.y+retry!.height/2);
    await expect.poll(()=>posts).toBe(2);
    await expect(alert).toHaveText("Неверный email или пароль");
    await expect(submit).toBeEnabled();
  });
}

test("mobile reload reveals the brand and the bounded moving background covers long forms and changing viewports",async({browser})=>{
  for(const [width,height]of [[360,800],[390,844],[412,915],[430,932]]){
    const context=await browser.newContext({viewport:{width,height},hasTouch:true,isMobile:true,deviceScaleFactor:3});
    await mockLocalApi(context);const page=await context.newPage();
    try{
      await page.goto(`${process.env.FIXRATE_BASE_URL}/register`);
      await expect(page.locator(".auth-aurora")).toHaveAttribute("data-renderer","canvas");
      await page.evaluate(()=>scrollTo(0,80));expect(await page.evaluate(()=>scrollY)).toBeGreaterThan(0);
      await page.reload();await expect(page.getByLabel("Имя и фамилия")).toBeVisible();
      await expect.poll(()=>page.evaluate(()=>scrollY)).toBe(0);
      expect(await page.locator(".auth-brand").evaluate(e=>e.getBoundingClientRect().top)).toBeGreaterThanOrEqual(28);
      await page.getByRole("button",{name:"Зарегистрироваться",exact:true}).tap();await expect(page.getByRole("alert")).toHaveCount(5);
      await page.evaluate(()=>scrollTo(0,document.documentElement.scrollHeight));
      const covered=()=>page.locator(".auth-aurora").evaluate(e=>{const b=e.getBoundingClientRect();return b.top===0&&b.bottom>=innerHeight;});
      expect(await covered()).toBe(true);
      await page.setViewportSize({width,height:height-100});expect(await covered()).toBe(true);
      expect(await page.evaluate(()=>scrollY)).toBeGreaterThan(0);
      await page.setViewportSize({width,height:420});
      const confirmation=page.getByLabel("Подтвердите пароль",{exact:true});await confirmation.fill("keyboard-check");await confirmation.scrollIntoViewIfNeeded();
      await expect(confirmation).toBeInViewport();expect(await covered()).toBe(true);
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    }finally{await context.close();}
  }
});

test("phone auth shares its brand anchor and compact heading rhythm while long forms remain scrollable",async({browser})=>{
  const context=await browser.newContext({hasTouch:true,isMobile:true});
  await mockLocalApi(context);
  const page=await context.newPage();
  const placement=()=>page.evaluate(()=>{
    const brand=document.querySelector(".auth-brand")!.getBoundingClientRect();
    const heading=document.querySelector(".auth-heading h1")!.getBoundingClientRect();
    return {brand:brand.top+scrollY,heading:heading.top+scrollY,gap:heading.top-brand.bottom};
  });
  try {
    for(const [width,height] of [[320,568],[375,667],[390,844],[430,932]]){
      await page.setViewportSize({width,height});
      await page.goto(`${process.env.FIXRATE_BASE_URL}/login`);
      await page.getByLabel("Email",{exact:true}).focus();
      const login=await placement();
      expect(login.gap).toBeGreaterThanOrEqual(24);expect(login.gap).toBeLessThanOrEqual(32);
      await page.getByRole("link",{name:"Регистрация",exact:true}).tap();
      await expect(page.getByRole("heading",{name:"Регистрация",exact:true})).toBeFocused();
      await expect(page.locator(".auth-page")).toHaveAttribute("data-transition","idle");
      expect(await placement()).toEqual(login);
      await page.getByRole("button",{name:"Зарегистрироваться",exact:true}).tap();
      await expect(page.getByRole("alert")).toHaveCount(5);
      await expect(page.getByLabel("Имя и фамилия")).toBeFocused();
      if(height<700)expect(await page.evaluate(()=>document.documentElement.scrollHeight>innerHeight)).toBe(true);
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
      await page.setViewportSize({width,height:Math.min(height,420)});
      const confirmation=page.getByLabel("Подтвердите пароль",{exact:true});
      await confirmation.fill("short");await confirmation.scrollIntoViewIfNeeded();
      await expect(confirmation).toBeInViewport();await expect(confirmation).toHaveValue("short");
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    }
  } finally {await context.close();}
});

test("scrolled phone auth navigation places the focused new heading in view, including Back and Forward",async({browser})=>{
  const context=await browser.newContext({viewport:{width:320,height:568},hasTouch:true,isMobile:true});
  await mockLocalApi(context);
  const page=await context.newPage();
  const visibleHeading=async(name:string)=>{
    const heading=page.getByRole("heading",{name,exact:true});
    await expect(heading).toBeFocused();
    await expect(page.locator(".auth-page")).toHaveAttribute("data-transition","idle");
    await expect.poll(()=>heading.evaluate(element=>{
      const box=element.getBoundingClientRect();
      return box.top>=0 && box.bottom<=window.innerHeight;
    })).toBe(true);
  };
  try {
    await page.goto(`${process.env.FIXRATE_BASE_URL}/login`);
    await expect(page.getByRole("heading",{name:"Вход в систему",exact:true})).toBeVisible();
    await page.getByLabel("Email",{exact:true}).focus();
    for(const [label,heading] of [["Регистрация","Регистрация"],["Перейти ко входу","Вход в систему"]]){
      await page.evaluate(()=>window.scrollTo({top:document.documentElement.scrollHeight,behavior:"instant"}));
      const link=page.getByRole("link",{name:label,exact:true});
      await link.scrollIntoViewIfNeeded();
      expect(await page.evaluate(()=>window.scrollY)).toBeGreaterThan(0);
      const box=await link.boundingBox();
      await page.touchscreen.tap(box!.x+box!.width/2,box!.y+box!.height/2);
      await visibleHeading(heading);
      expect(await page.evaluate(()=>window.scrollY)).toBe(0);
    }
    await page.goBack();await visibleHeading("Регистрация");
    await page.goForward();await visibleHeading("Вход в систему");
  } finally {await context.close();}
});

test("confirmed phone login from a scrolled form reveals and focuses its safe app destination",async({browser})=>{
  const context=await browser.newContext({viewport:{width:320,height:568},hasTouch:true,isMobile:true});
  await mockLocalApi(context);
  const page=await context.newPage();
  await page.route("**/api/v1/maintenance/ui/**",route=>route.fulfill({json:[]}));
  try {
    await page.goto(`${process.env.FIXRATE_BASE_URL}/equipment?source=short-auth#overview`);
    await expect(page).toHaveURL(/\/login$/);
    await page.getByLabel("Email",{exact:true}).fill("test@example.test");
    await page.getByLabel("Пароль",{exact:true}).fill(PASSWORD);
    await page.evaluate(()=>window.scrollTo({top:document.documentElement.scrollHeight,behavior:"instant"}));
    expect(await page.evaluate(()=>window.scrollY)).toBeGreaterThan(0);
    const box=await page.locator(".auth-submit").boundingBox();
    await page.touchscreen.tap(box!.x+box!.width/2,box!.y+box!.height/2);
    await expect(page).toHaveURL(new URL("/dispatcher",process.env.FIXRATE_BASE_URL!).href);
    await expect(page.locator("#main-content")).toBeFocused();
    expect(await page.evaluate(()=>window.scrollY)).toBe(0);
    const heading=page.getByRole("heading",{name:"Панель диспетчера",exact:true});
    await expect(heading).toBeVisible();
    await expect.poll(()=>heading.evaluate(element=>{const box=element.getBoundingClientRect();return box.top>=0&&box.bottom<=window.innerHeight;})).toBe(true);
  } finally {await context.close();}
});

test("classic root scrollbar preserves auth geometry across route overflow and errors",async()=>{
  const browser=await chromium.launch({channel:"chrome",headless:true,ignoreDefaultArgs:["--hide-scrollbars"],args:["--disable-features=OverlayScrollbar,OverlayScrollbars"]});
  const context=await browser.newContext({viewport:{width:1366,height:768}});
  await mockLocalApi(context);
  const page=await context.newPage();
  const measurements:unknown[]=[];
  const geometry=async()=>{
    const value=await page.evaluate(()=>{
      const x=(selector:string)=>{const box=document.querySelector(selector)!.getBoundingClientRect();return{x:box.x,width:box.width};};
      return{clientWidth:document.documentElement.clientWidth,layout:{rootWidth:document.documentElement.getBoundingClientRect().width,panel:x(".auth-panel"),scene:x(".auth-aurora"),brand:x(".auth-brand")}};
    });
    measurements.push(value);
    expect(value.clientWidth).toBeGreaterThanOrEqual(value.layout.rootWidth);
    expect(value.clientWidth).toBeLessThanOrEqual(1366);
    return value.layout;
  };
  try{
    await page.goto(`${process.env.FIXRATE_BASE_URL}/login`);
    // Prove this browser uses a real layout gutter rather than overlay scrollbars.
    await page.evaluate(()=>{const probe=document.createElement("div");probe.id="classic-scrollbar-probe";probe.style.height="2000px";document.body.append(probe);});
    expect(await page.evaluate(()=>window.innerWidth-document.documentElement.clientWidth)).toBeGreaterThan(0);
    await page.evaluate(()=>document.getElementById("classic-scrollbar-probe")!.remove());
    const short=await geometry();
    expect(short.rootWidth).toBeLessThan(1366);
    await page.getByRole("link",{name:"Регистрация",exact:true}).click();
    await expect(page.getByRole("heading",{name:"Регистрация",exact:true})).toBeFocused();
    await expect(page.locator(".auth-page")).toHaveAttribute("data-transition","idle");
    expect(await page.evaluate(()=>document.documentElement.scrollHeight>document.documentElement.clientHeight)).toBe(true);
    expect(await geometry()).toEqual(short);
    await expect(page.locator(".auth-footer")).toHaveText("Нужна помощь с регистрацией?Обратитесь к администратору вашего объекта.");
    await expect(page.locator(".auth-footer a, .auth-footer button, .auth-footer input")).toHaveCount(0);
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(await page.evaluate(()=>document.body.style.overflow)).toBe("");
    await page.getByRole("link",{name:"Перейти ко входу",exact:true}).click();
    await expect(page.getByRole("heading",{name:"Вход в систему",exact:true})).toBeFocused();
    await expect(page.locator(".auth-page")).toHaveAttribute("data-transition","idle");
    await page.route("**/api/v1/auth/login",route=>route.fulfill({status:409,json:{detail:"Укажите site_id: у пользователя несколько объектов"}}),{times:1});
    await page.getByLabel("Email",{exact:true}).fill("test@example.test");
    await page.getByLabel("Пароль",{exact:true}).fill("test-password");
    await page.getByRole("button",{name:"Войти",exact:true}).click();
    await expect(page.getByLabel("ID объекта",{exact:true})).toBeVisible();
    await page.getByLabel("Email",{exact:true}).fill("");await page.getByLabel("Пароль",{exact:true}).fill("");
    await page.getByRole("button",{name:"Войти",exact:true}).click();
    await expect(page.getByRole("alert")).toHaveCount(3);
    expect(await geometry()).toEqual(short);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth)).toBe(true);
    await test.info().attach("classic-root-scrollbar-measurements",{body:JSON.stringify(measurements,null,2),contentType:"application/json"});
  } finally{await browser.close();}
});

test("editorial hero stays secondary, reveals once across auth navigation and respects mobile and reduced motion",async({page})=>{
  await page.setViewportSize({width:1440,height:900});
  const hero=page.locator(".auth-hero-copy");
  const heading=page.getByRole("heading",{level:2,name:"Интеллектуальная система прогнозирования ТО и ППР."});
  await expect(heading).toBeVisible();
  await expect(page.getByRole("heading",{level:1,name:"Вход в систему"})).toBeVisible();
  await expect(hero).toContainText("Планирование обслуживания, анализ состояния оборудования и контроль выполнения работ в единой системе.");
  await expect(hero.locator("a,button,input,[tabindex]")).toHaveCount(0);
  expect(await hero.evaluate(element=>element.closest('[aria-hidden="true"]')===null)).toBe(true);
  const form=await page.locator(".auth-panel").boundingBox(),copy=await heading.boundingBox();
  expect(copy!.x).toBeGreaterThan(form!.x+form!.width);
  await expect.poll(()=>hero.evaluate(element=>element.getAnimations({subtree:true}).length)).toBe(0);
  await expect(heading).toHaveCSS("opacity","1");await expect(heading).toHaveCSS("transform","none");
  const original=await hero.elementHandle();
  await page.getByRole("link",{name:"Регистрация",exact:true}).click();
  await expect(page.getByRole("heading",{level:1,name:"Регистрация"})).toBeFocused();
  expect(await hero.evaluate((element,previous)=>element===previous,original)).toBe(true);
  expect(await hero.evaluate(element=>element.getAnimations({subtree:true}).length)).toBe(0);
  await page.emulateMedia({reducedMotion:"reduce"});await page.reload();
  await expect(heading).toBeVisible();await expect(heading).toHaveCSS("opacity","1");await expect(heading).toHaveCSS("transform","none");
  expect(await hero.evaluate(element=>element.getAnimations({subtree:true}).length)).toBe(0);
  for(const [width,height] of [[768,1024],[390,844],[844,390]]){
    await page.setViewportSize({width,height});
    await expect(hero).toBeHidden();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  }
});
