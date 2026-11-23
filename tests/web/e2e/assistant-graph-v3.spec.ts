import { expect, test } from '@playwright/test';

for (const width of [1440, 390]) {
  test(`LangGraph assistant saves a real scoped answer at ${width}px`, async ({ page, context }) => {
    const password = process.env.FIXRATE_TEST_PASSWORD;
    test.skip(!password || process.env.FIXRATE_ASSISTANT_AGENT_VERSION !== 'v3',
      'Requires the disposable v3 API and its demo accounts');
    const desktop = width > 500;
    const email = desktop ? 'fixrate-demo-chief_engineer@example.test' : 'fixrate-demo-1@example.test';
    const login = await context.request.post('/api/v1/auth/login', { data: { email, password } });
    expect(login.ok()).toBeTruthy();
    let question = 'Какие у меня сегодня задания?';
    let equipmentId: string | undefined;
    if (desktop) {
      const response = await context.request.get('/api/v1/assistant/workspace/equipment');
      const equipment = (await response.json()).items.find(
        (row: { asset_code: string }) => /^\p{L}[\p{L}\d]*(?:[-_][\p{L}\d]+)+$/u.test(row.asset_code));
      expect(equipment).toBeTruthy();
      question = `Найди ${equipment.asset_code}`;
      equipmentId = equipment.equipment_id;
    }
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/assistant');
    const input = page.getByLabel('Сообщение помощнику');
    await input.fill(question);
    await page.getByRole('button', { name: 'Отправить', exact: true }).click();
    await expect(page).toHaveURL(/chat=/);
    const chat = new URL(page.url()).searchParams.get('chat');
    expect(chat).toBeTruthy();
    await expect.poll(async () => {
      const response = await context.request.get(`/api/v1/assistant/conversations/${chat}`);
      return (await response.json()).turns[0]?.workflow?.outcome;
    }, { timeout: 20_000 }).toBe('completed');
    const response = await context.request.get(`/api/v1/assistant/conversations/${chat}`);
    const saved = (await response.json()).turns[0];
    expect(saved.execution_engine).toBe('v3');
    expect(saved.workflow.metrics.llm_calls).toBe(0);
    if (equipmentId) expect(saved.answer).toContain(equipmentId);
    await page.reload();
    await expect(page.getByRole('region', { name: 'Сообщения' })).toContainText(question);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  });
}
