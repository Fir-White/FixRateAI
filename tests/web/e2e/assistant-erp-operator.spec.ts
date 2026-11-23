import { expect, test } from '@playwright/test';

for (const width of [1440, 390]) {
  test(`ERP operator opens a saved scoped chat at ${width}px`, async ({ page, context }) => {
    const password = process.env.FIXRATE_TEST_PASSWORD;
    test.skip(!password || process.env.FIXRATE_ASSISTANT_V3_PIPELINE !== 'erp_operator',
      'Requires a disposable ERP operator API and a local model');
    const email = width > 500 ? 'fixrate-demo-chief_engineer@example.test' : 'fixrate-demo-1@example.test';
    const login = await context.request.post('/api/v1/auth/login', { data: { email, password } });
    expect(login.ok()).toBeTruthy();
    const registry = await context.request.get('/api/v1/assistant/workspace/equipment');
    expect(registry.ok()).toBeTruthy();
    const asset = (await registry.json()).items[0];
    expect(asset?.asset_code).toBeTruthy();
    const question = `Найди оборудование с точным кодом ${asset.asset_code}.`;

    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/assistant');
    await page.getByLabel('Сообщение помощнику').fill(question);
    await page.getByRole('button', { name: 'Отправить', exact: true }).click();
    await expect(page).toHaveURL(/chat=/);
    const chatUrl = page.url();
    const chat = new URL(chatUrl).searchParams.get('chat');
    const readChat = async () => (await context.request.get(`/api/v1/assistant/conversations/${chat}`)).json();
    await expect.poll(async () => (await readChat()).turns[0]?.status, { timeout: 45_000 }).toBe('completed');
    const stored = await readChat();
    expect(stored.turns[0].workflow.outcome).toBe('completed');
    expect(stored.turns[0].workflow.metrics.llm_calls).toBeGreaterThan(0);
    expect(stored.turns[0].answer).toContain(asset.equipment_id);
    expect(stored.actions).toEqual([]);

    await page.reload();
    await expect(page.getByRole('region', { name: 'Сообщения' })).toContainText(question);
    await expect(page).toHaveURL(chatUrl);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  });
}
