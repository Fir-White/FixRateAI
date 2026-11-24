import { expect, test } from '@playwright/test';
import { resolve } from 'node:path';

for (const { role, width } of [{ role: 'engineer', width: 1440 }, { role: 'executor', width: 390 }]) {
  test(`v4: ${role} sees grounded chat through the built app at ${width}px`, async ({ page, context }) => {
    test.skip(process.env.FIXRATE_TOOL_AGENT_BROWSER !== '1', 'Requires disposable v4 HTTP server and real Ollama');
    test.setTimeout(210_000);
    const email = role === 'engineer' ? 'fixrate-demo-engineer@example.test' : 'fixrate-demo-1@example.test';
    const login = await context.request.post('/api/v1/auth/login', { data: { email, password: process.env.FIXRATE_TEST_PASSWORD } });
    expect(login.ok()).toBeTruthy();
    expect((await login.json()).profile.role).toBe(role);
    const assets = await context.request.get('/api/v1/assistant/workspace/equipment');
    expect(assets.ok()).toBeTruthy();
    const asset = (await assets.json()).items[0];
    expect(asset?.asset_code).toBeTruthy();

    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/assistant');
    const composer = page.getByLabel('Сообщение помощнику');
    const send = () => page.getByRole('button', { name: 'Отправить', exact: true }).click();
    const question = `Как называется оборудование с кодом ${asset.asset_code}?`;
    await composer.fill(question);
    await send();
    await expect(page).toHaveURL(/chat=/);
    const chatUrl = page.url();
    const id = new URL(chatUrl).searchParams.get('chat');
    const read = async () => (await context.request.get(`/api/v1/assistant/conversations/${id}`)).json();
    await expect.poll(async () => (await read()).turns.at(-1)?.status, { timeout: 90_000 }).toBe('completed');
    const view = await read();
    expect(view.turns[0].execution_engine).toBe('v4');
    expect(view.turns[0].prompt_version).toBe('fixrate-tool-calling-v4');
    expect(view.turns[0].model_ref).toContain('ollama:');
    expect(view.turns[0].answer.toLowerCase()).toContain(asset.name.toLowerCase());
    expect(view.turns[0].workflow).toBeNull();
    expect(view.actions).toEqual([]);
    await expect(page.getByRole('region', { name: 'Сообщения' })).toContainText(asset.name, { ignoreCase: true });

    await page.reload();
    await expect(page.getByRole('region', { name: 'Сообщения' })).toContainText(question);
    await expect(page).toHaveURL(chatUrl);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();

    if (role === 'executor') {
      const owned = await context.request.get('/api/v1/maintenance/ui/tasks');
      const task = (await owned.json())[0];
      expect(task?.id).toBeTruthy();
      await page.goto(`/executor/tasks/${task.id}`);
      const [taskChat] = await Promise.all([
        page.waitForEvent('popup'), page.getByRole('link', { name: 'Спросить ИИ по наряду' }).click(),
      ]);
      await expect(taskChat).toHaveURL(/task=/);
      await taskChat.locator('input[type=file]').setInputFiles(resolve('..', 'data', 'demo', 'demo-photo.png'));
      await expect(taskChat).toHaveURL(/chat=/);
      await taskChat.getByLabel('Сообщение помощнику').fill('Посмотри снимок. Что на нём можно оценить?');
      await taskChat.getByRole('button', { name: 'Отправить', exact: true }).click();
      const scopedId = new URL(taskChat.url()).searchParams.get('chat');
      await expect.poll(async () => {
        const res = (await context.request.get(`/api/v1/assistant/conversations/${scopedId}`));
        const state = await res.json();
        const next = state.turns?.[0];
        return state.conversation?.subject_task_id === task.id && next?.status === 'completed'
          && next.trace.some((step: { source?: string }) => step.source === 'chat_subject')
          && next.trace.some((step: { images?: number }) => step.images === 1);
      }, { timeout: 90_000 }).toBe(true);
      await expect(taskChat.getByRole('link', { name: 'demo-photo.png' })).toBeVisible();
    }
  });
}

test('v4: a crew follow-up renders one actionable confirmation card', async ({ page, context }) => {
  const task = process.env.FIXRATE_TEST_ASSIGNMENT_ORDER;
  test.skip(process.env.FIXRATE_TOOL_AGENT_BROWSER !== '1' || !task, 'Requires disposable v4 assignment fixture');
  test.setTimeout(210_000);
  const login = await context.request.post('/api/v1/auth/login', {
    data: { email: 'fixrate-demo-engineer@example.test', password: process.env.FIXRATE_TEST_PASSWORD },
  });
  expect(login.ok()).toBeTruthy();
  await page.goto('/assistant');
  const composer = page.getByLabel('Сообщение помощнику');
  const read = async () => {
    const id = new URL(page.url()).searchParams.get('chat');
    return (await context.request.get(`/api/v1/assistant/conversations/${id}`)).json();
  };
  const taskState = async () => {
    const response = await context.request.get(`/api/v1/maintenance/ui/tasks/${task}`);
    expect(response.ok()).toBeTruthy();
    return (await response.json()).task.state;
  };
  const send = async (message: string, expectedTurns: number) => {
    await composer.fill(message);
    await page.getByRole('button', { name: 'Отправить', exact: true }).click();
    await expect(page).toHaveURL(/chat=/);
    await expect.poll(async () => {
      const view = await read();
      return [view.turns?.length, view.turns?.at(-1)?.status];
    }, { timeout: 60_000 }).toEqual([expectedTurns, 'completed']);
    return read();
  };
  const suggested = await send('Кого можно отправить на наряд «DEMO — подбор бригады»? Пока только проверь состав.', 1);
  expect(suggested.actions).toEqual([]);
  expect(suggested.turns[0].trace).toEqual(expect.arrayContaining([expect.objectContaining({ tool: 'check_assignment', status: 'completed' })]));
  expect((await send('Давай первого назначай', 2)).actions).toEqual([]);
  const prepared = await send('Обоих тогда', 3);
  expect(prepared.actions).toHaveLength(1);
  const [card] = prepared.actions;
  expect(card.status).toBe('proposed');
  expect(card.arguments.path.task_id).toBe(task);
  expect(card.arguments.body.executor_ids).toHaveLength(2);
  const confirmation = page.getByRole('button', { name: 'Подтвердить и выполнить' });
  await expect(confirmation).toBeVisible();
  const acknowledged = await send('Подтверждаю', 4);
  expect(acknowledged.actions.map((action: { action_id: string }) => action.action_id)).toEqual([card.action_id]);
  expect(await taskState()).toBe('draft');
  await expect(confirmation).toHaveCount(1);
  await page.getByRole('checkbox', { name: 'Я проверил параметры и подтверждаю это изменение' }).check();
  await confirmation.click();
  await expect.poll(async () => (await read()).actions[0]?.status).toBe('succeeded');
  expect(await taskState()).toBe('assigned');
});
