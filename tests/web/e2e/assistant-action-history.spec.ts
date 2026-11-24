import { expect, test } from "@playwright/test";

const chat = "11111111-1111-4111-8111-111111111111";
const time = "2026-11-21T07:00:00Z";
const conversation = {
  conversation_id: chat, title: "Распределение заданий по объекту", agent: "assistant",
  created_at: time, updated_at: time,
};

for (const [width, height] of [[1728, 900], [1440, 900], [1280, 800], [768, 1024], [390, 844], [360, 800]]) {
  test(`action history retains the dialog at ${width}×${height}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height });
    await page.emulateMedia({ reducedMotion: "reduce" });
    const cpuRate = process.env.FIXRATE_QA_CPU4 === "1" ? 4 : 1;
    if (cpuRate === 4) {
      const cdp = await page.context().newCDPSession(page);
      await cdp.send("Emulation.setCPUThrottlingRate", { rate: cpuRate });
    }
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    let failHistory = true;
    await page.route("**/api/**", async route => {
      const { pathname, searchParams } = new URL(route.request().url());
      if (pathname.endsWith("/auth/session")) return route.fulfill({ json: { profile: {
        userId: "qa-user", name: "Мария Волкова", siteId: "qa-site", siteName: "Учебный объект",
        role: width < 768 ? "executor" : "chief_engineer", timezone: "Asia/Yekaterinburg",
      } } });
      if (pathname.endsWith("/assistant/capabilities")) return route.fulfill({ json: {
        available: true, model_ref: "QA", prompt_version: "QA", agents: [],
        tools: { assistant: [], planner: [], photo: [] },
      } });
      if (pathname.endsWith("/assistant/conversations")) return route.fulfill({ json: { items: [conversation], total: 1 } });
      if (pathname.endsWith(`/assistant/conversations/${chat}`)) return route.fulfill({ json: {
        conversation, turns: [], actions: [], attachments: [], total: 0,
      } });
      if (pathname.endsWith("/assistant/actions")) {
        if (failHistory) return route.fulfill({ status: 503, json: { detail: "История временно недоступна" } });
        const offset = Number(searchParams.get("offset"));
        return route.fulfill({ json: {
          items: offset ? [] : Array.from({ length: 25 }, (_, index) => ({
            action_id: `action-${index}`, conversation_id: chat, conversation_title: conversation.title,
            title: ["Назначить исполнителя", "Обновить сведения о задании", "Утвердить план"][index % 3],
            target_id: "22222222-2222-4222-8222-222222222222", created_at: time,
            confirmed_at: index === 0 ? time : null, finished_at: index === 0 ? time : null,
            status: index === 0 ? "succeeded" : index === 2 ? "failed" : "proposed",
            verification: index === 0 ? "confirmed" : null, failure_code: index === 2 ? 422 : null,
          })), total: 26, offset, limit: 25, actor: "Мария Волкова",
        } });
      }
      return route.fulfill({ json: [] });
    });
    await page.goto(`/assistant?chat=${chat}`);
    const input = page.getByLabel("Сообщение помощнику");
    await input.evaluate(element => {
      element.addEventListener("input", () => {
        performance.mark("qa-input");
        requestAnimationFrame(() => performance.measure("qa-input-frame", "qa-input"));
      }, { once: true });
    });
    await input.fill("Сверить смены перед назначением");
    const nav = page.getByRole("navigation", { name: "Разделы помощника" });
    const actions = nav.getByRole("link", { name: "История действий" });
    await actions.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("alert")).toContainText("История временно недоступна");
    failHistory = false;
    await page.getByRole("button", { name: "Повторить", exact: true }).click();
    await expect(actions).toHaveAttribute("aria-current", "page");
    const rows = page.getByRole("list", { name: "Действия помощника" }).getByRole("listitem");
    await expect(rows).toHaveCount(25);
    await expect(rows.first()).toContainText("Результат проверен");
    await expect(rows.nth(1)).toContainText("Ожидает подтверждения");
    await expect(rows.nth(2)).toContainText("Сервер отклонил параметры действия");
    await expect(input).toBeHidden();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await page.screenshot({ path: info.outputPath(`actions-${width}.png`) });
    const frames = page.evaluate(() => new Promise<number[]>(resolve => {
      const values: number[] = [];
      function frame(previous: number) {
        requestAnimationFrame(now => {
          values.push(now - previous);
          if (values.length < 45) frame(now);
          else resolve(values);
        });
      }
      requestAnimationFrame(frame);
    }));
    await page.mouse.wheel(0, 500);
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
    const intervals = (await frames).sort((left, right) => left - right);
    await page.goBack();
    await expect(input).toHaveValue("Сверить смены перед назначением");
    const navigationStarted = performance.now();
    await page.goForward();
    await expect(rows).toHaveCount(25);
    const navigationMs = performance.now() - navigationStarted;
    const inputMs = await page.evaluate(() => performance.getEntriesByName("qa-input-frame")[0]?.duration ?? null);
    await info.attach("interaction-metrics", { contentType: "application/json", body: JSON.stringify({
      width, height, cpuRate, inputMs, navigationMs, scrollFrameP95Ms: intervals[Math.ceil(intervals.length * .95) - 1],
    }) });
    await page.reload();
    await expect(rows.first()).toContainText("Назначить исполнителя");
    await rows.first().getByRole("link").click();
    await expect(page).toHaveURL(new RegExp(`chat=${chat}$`));
    await expect(input).toBeVisible();
    expect(errors).toEqual([]);
  });
}
