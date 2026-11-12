import { test, expect } from "@playwright/test";
import { createHash } from "node:crypto";

function demoId(key: string) {
  const hex = createHash("md5").update(`fixrate-demo-${key}`).digest("hex");
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}

const roles = ["director","chief_engineer","admin", "dispatcher", "engineer", "executor"];
const allowed: Record<string, string[]> = {
  director:["director"], "chief-engineer":["chief_engineer"], engineer:["engineer"], admin:["admin"], profile:roles,
  dispatcher: ["director","chief_engineer","engineer","admin", "dispatcher"], equipment: roles,
  calendar: ["director","chief_engineer","dispatcher", "engineer", "executor"], tasks: ["director","chief_engineer","dispatcher", "engineer"],
  comparisons: ["director","chief_engineer","dispatcher", "engineer"], reports: ["director","chief_engineer","dispatcher", "engineer"], quality: ["chief_engineer","engineer"], executor: ["executor"],
  settings: ["chief_engineer","admin","dispatcher","engineer"], "my-shifts": ["executor"],
};

for (const role of roles) {
  test(`real ${role} session: screens, navigation and logout`, async ({page}) => {
    test.skip(!process.env.FIXRATE_BASE_URL, "Run scripts/verify.py --browser");
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    const destination = `/equipment/${demoId("equipment-2")}?tab=passport#details`;
    await page.goto(destination);
    await expect(page).toHaveURL(/\/login$/);
    const account = role === "executor" ? "1" : role === "director" ? "executive" : role;
    const homes:Record<string,string>={director:"/director",chief_engineer:"/chief-engineer",engineer:"/engineer",executor:"/executor",admin:"/admin",dispatcher:"/dispatcher"};
    await page.getByLabel("Email", {exact: true}).fill(`fixrate-demo-${account}@example.test`);
    await page.getByLabel("Пароль", {exact: true}).fill(process.env.FIXRATE_TEST_PASSWORD!);
    await page.getByRole("button", {name: "Войти", exact: true}).click();
    await expect(page).toHaveURL(new URL(homes[role], process.env.FIXRATE_BASE_URL!).href);
    const businessMenus:Record<string,string[]>={
      director:["/director","/calendar","/equipment","/tasks","/comparisons","/reports"],
      chief_engineer:["/chief-engineer","/quality","/calendar","/equipment","/tasks","/comparisons","/reports","/settings/equipment","/settings/workforce"],
      engineer:["/dispatcher","/engineer","/calendar","/equipment","/tasks","/comparisons","/reports","/settings/equipment","/settings/workforce"],
      executor:["/executor","/calendar","/equipment","/my-shifts"],
    };
    if(businessMenus[role])expect(await page.getByRole("navigation",{name:"Основная навигация"}).getByRole("link").evaluateAll(links=>links.map(link=>link.getAttribute("href")))).toEqual(businessMenus[role]);
    const routes = ["/director","/chief-engineer","/engineer","/admin","/profile","/dispatcher", "/equipment", `/equipment/${demoId("equipment-2")}`, "/calendar", "/tasks",
      `/tasks/${demoId("runtime-order")}`, "/comparisons", "/reports", "/quality", `/quality/${demoId("runtime-order")}`,
      "/executor", `/executor/tasks/${demoId("runtime-order")}`,"/settings/equipment","/settings/workforce","/my-shifts"];
    for (const route of routes) {
      await page.goto(route);
      const permitted = allowed[route.split("/")[1]].includes(role);
      if (!permitted) {
        await expect(page.getByRole("heading", {name: "Раздел недоступен для текущей роли"})).toBeVisible();
        continue;
      }
      await expect(page.locator("h1")).toBeVisible();
      await expect(page.locator("[data-workspace-loading]")).toHaveCount(0);
      await expect(page.getByRole("alert")).toHaveCount(0);
      const hrefs = await page.locator("a[href]").evaluateAll(links => links.map(link => link.getAttribute("href")!));
      for (const href of hrefs.filter(href => href.startsWith("/"))) {
        if(href.startsWith("/api/v1/maintenance/export.xlsx?")){
          const exported=await page.request.get(href);expect(exported.status()).toBe(200);
          expect(exported.headers()["content-type"]).toContain("spreadsheetml.sheet");
          expect((await exported.body()).subarray(0,2).toString()).toBe("PK");continue;
        }
        if (href.startsWith("/api/")) {
          expect(href).toMatch(/^\/api\/v1\/maintenance\/photos\/[0-9a-f-]+$/);
          const photo = await page.request.get(href);
          expect(photo.status()).toBe(200);
          expect(photo.headers()["content-type"]).toMatch(/^image\//);
          expect(photo.headers()["cache-control"]).toBe("private, no-store");
          continue;
        }
        const section = new URL(href, process.env.FIXRATE_BASE_URL!).pathname.split("/")[1];
        if (section && section !== "login") expect(allowed[section], `${role}: ${route} → ${href}`).toContain(role);
      }
      if (role === "executor" && route === "/calendar") {
        const event = page.getByRole("button", {name: /DEMO — чистка учебного узла/}).first();
        if (!(await event.count())) {
          // The seed schedules tomorrow, which can fall in the next local month.
          await page.getByRole("button", {name: "Следующий месяц"}).click();
          await expect(page.locator("[data-workspace-loading]")).toHaveCount(0);
        }
        await event.click();
        await page.getByRole("dialog").getByRole("link", {name: "Открыть наряд"}).click();
        await expect(page).toHaveURL(new RegExp(`/executor/tasks/${demoId("runtime-order")}$`));
        await expect(page.getByRole("heading", {name: "DEMO — чистка учебного узла"})).toBeVisible();
      }
    }
    await page.goto("/profile");
    await page.getByRole("button", {name: "Выйти из аккаунта", exact: true}).click();
    await expect(page).toHaveURL(/\/login$/);
    await page.reload();
    await expect(page.getByRole("heading", {name: "Вход в систему"})).toBeVisible();
    const session = await page.request.get("/api/v1/auth/session");
    expect(session.status()).toBe(401);
    expect(errors).toEqual([]);
  });
}
