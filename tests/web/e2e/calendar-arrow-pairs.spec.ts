import { expect, test } from "@playwright/test";

const member = {
  user_id: "arrow-worker", full_name: "Учебный исполнитель", email: "arrow-worker@example.test",
  role: "executor", is_active: true, qualifications: [], shifts: [], exceptions: [],
};

for (const width of [1440, 390]) {
  for (const [path, group] of [
    ["/calendar", ".fr-calendar-period"],
    ["/settings/workforce?staff=arrow-worker", ".fr-shift-period-controls"],
    ["/my-shifts", ".fr-shift-period-controls"],
  ] as const) {
    test(`calendar arrows mirror each other: ${path}, ${width}px`, async ({page}) => {
      test.skip(!process.env.FIXRATE_BASE_URL, "Requires a production SPA build");
      await page.setViewportSize({width, height:900});
      await page.emulateMedia({reducedMotion:"reduce"});
      await page.clock.setFixedTime(new Date("2026-12-15T10:00:00Z"));
      const personal = path === "/my-shifts";
      const profile = {
        userId: personal ? member.user_id : "arrow-chief", role: personal ? "executor" : "chief_engineer",
        siteId: "arrow-site", name: "Учебный аккаунт", siteName: "Учебный объект", timezone: "UTC",
      };
      await page.route("**/api/**", route => {
        const pathname = new URL(route.request().url()).pathname;
        if (pathname.endsWith("/auth/session")) return route.fulfill({json:{profile}});
        if (pathname.endsWith("/management/workforce")) return route.fulfill({json:{staff:[member],skills:[],applications:[],crews:[],timezone:"UTC"}});
        if (pathname.includes("/management/staff/")) return route.fulfill({json:{intervals:[],diagnostics:[],timezone:"UTC"}});
        return route.fulfill({json:[]});
      });
      await page.goto(path);
      const previous = page.locator(group).getByRole("button", {name:/Предыдущ/});
      const next = page.locator(group).getByRole("button", {name:/Следующ/});
      await expect(previous).toBeVisible();
      await expect(next).toBeVisible();
      const paths = (button: typeof previous) => button.locator("svg path").evaluateAll(nodes => nodes.map(node => node.getAttribute("d")));
      expect(await paths(next)).toEqual(await paths(previous));
      await expect(previous.locator("svg")).toHaveCSS("rotate", "none");
      await expect(next.locator("svg")).toHaveCSS("rotate", "180deg");
      const period = page.locator(path === "/calendar" ? `${group} h2` : ".fr-shift-header :is(h2,h3)");
      const original = (await period.textContent())!;
      await next.click();
      await expect(period).not.toHaveText(original);
      await previous.click();
      await expect(period).toHaveText(original);
    });
  }
}
