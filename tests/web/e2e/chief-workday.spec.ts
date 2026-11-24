import { expect, test, type Page, type Route } from '@playwright/test';
import type { MaintenanceTask } from '../../../frontend/src/shared/types/domain';

const profile = {
  userId: 'workday-qa', siteId: 'workday-site', role: 'chief_engineer', name: 'Главный инженер QA',
  email: 'workday@example.test', siteName: 'Объект QA', timezone: 'Asia/Yekaterinburg',
};
const now = '2026-11-21T12:00:00Z';
const model = 'qwen3.5:4b-q4_K_M';
const selection = { provider: 'ollama', model };
const preference = { selection, revision: 3, available: true, is_default: true };
const capabilities = { available: true, model_ref: model, prompt_version: 'qa', agents: [],
  tools: { assistant: [], planner: [], photo: [] }, model_preference: preference };
const conversation = { conversation_id: 'workday-qa-conversation', title: 'Рабочий день QA',
  agent: 'assistant', created_at: now, updated_at: now };
const tasksPath = '/api/v1/maintenance/ui/tasks';

function task(id: string, options: Partial<MaintenanceTask> = {}): MaintenanceTask {
  return {
    id, code: id, title: `Проверка ${id}`, equipmentId: null,
    equipmentName: 'Циркуляционный насос контура отопления', operationCode: 'CHECK', maintenanceType: null,
    state: 'draft', isOverdue: false, deadlineBreached: false, mandatoryDueDate: '2026-11-22',
    scheduledStart: '2026-11-22T00:05:00+05:00', scheduledEnd: null, crewSize: 1,
    assignees: [], activeExecutionId: null, revision: 1, dataOrigin: 'synthetic_demo', summary: '',
    ...options,
  };
}

async function openWorkday(page: Page, respond: (route: Route, path: string) => Promise<void> | void) {
  await page.clock.setFixedTime(new Date(now));
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/v1/auth/session') return route.fulfill({ json: { profile } });
    if (path.endsWith('/assistant/capabilities')) return route.fulfill({ json: capabilities });
    await respond(route, path);
  });
  await page.goto('/chief-engineer');
}

test.beforeEach(() => test.skip(!process.env.FIXRATE_BASE_URL, 'Requires the production SPA'));

test('chief timeline uses the planned start, site timezone and actual task links', async ({ page }) => {
  const first = task('planned-a', { title: 'Проверить давление', isOverdue: true });
  const sameTime = task('planned-b', { title: 'Снять показания', scheduledStart: '2026-11-21T19:05:00Z',
    state: 'assigned', assignees: [{ executorId: 'qa', name: 'Мария Соколова', qualifications: [] }] });
  const longName = 'Очень длинное наименование оборудования '.repeat(12).trim();
  const secondDay = task('planned-c', { title: 'Проверить вентиль', state: 'in_progress', equipmentName: longName,
    scheduledStart: '2026-11-23T11:00:00+05:00' });
  const items = [secondDay, sameTime, first, task('later', { scheduledStart: '2026-11-24T09:00:00+05:00' }),
    task('deadline-only', { scheduledStart: null }), task('closed', { state: 'accepted' })];

  await page.setViewportSize({ width: 360, height: 800 });
  await openWorkday(page, (route, path) => {
    if (path === tasksPath) return route.fulfill({ json: items });
    if (path === `${tasksPath}/${first.id}`) return route.fulfill({ json: {
      task: first, execution: null, review: null, decision: null, allowedActions: [],
    } });
    return route.fulfill({ json: [] });
  });
  const timeline = page.getByRole('region', { name: 'Ближайшие задания' });
  await expect(timeline.getByRole('listitem')).toHaveCount(3);
  await expect(timeline.locator('time strong')).toHaveText(['00:05', '00:05', '11:00']);
  await expect(timeline.locator('time span')).toHaveText(['22 ноября', '22 ноября', '23 ноября']);
  await expect(timeline.locator('time').first()).toHaveAttribute('datetime', first.scheduledStart!);
  const firstStop = timeline.getByRole('listitem').first();
  for (const label of ['Черновик', 'Просрочено', 'Без исполнителя']) {
    await expect(firstStop.getByText(label, { exact: true })).toBeVisible();
  }
  await expect(timeline.getByText('Мария Соколова')).toBeVisible();
  await expect(timeline.getByText(longName)).toBeVisible();
  await expect(timeline).not.toContainText('deadline-only');
  await expect(timeline).not.toContainText('planned-a');
  await expect(timeline.getByRole('link', { name: 'Открыть график' })).toHaveAttribute('href', '/calendar?date=2026-11-22');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360);
  await expect(page.getByRole('link', { name: '5 незавершённых работ' })).toHaveAttribute('href', '/tasks?status=open');
  await expect(page.getByRole('link', { name: '1 Просрочено' })).toHaveAttribute('href', '/tasks?status=overdue');
  await expect(page.getByRole('link', { name: '3 Без исполнителя' })).toHaveAttribute('href', '/tasks?status=unassigned');
  await timeline.getByRole('link', { name: first.title }).click();
  await expect(page).toHaveURL(/\/tasks\/planned-a$/);
  await expect(page.getByRole('heading', { name: first.title })).toBeVisible();
  await page.goBack();
  await expect(timeline.getByRole('listitem')).toHaveCount(3);
  await page.goForward();
  await expect(page).toHaveURL(/\/tasks\/planned-a$/);
});

test('chief retains the composer during loading and retries a timeline error', async ({ page }) => {
  let attempt = 0;
  let finishLoad!: () => void;
  const paused = new Promise<void>(resolve => { finishLoad = resolve; });
  await openWorkday(page, async (route, path) => {
    if (path !== tasksPath) return route.fulfill({ json: [] });
    attempt++;
    if (attempt === 1) {
      await paused;
      return route.fulfill({ status: 503, json: { detail: 'График временно недоступен' } });
    }
    return route.fulfill({ json: [task('single')] });
  });
  const timeline = page.getByRole('region', { name: 'Ближайшие задания' });
  const field = page.getByLabel('Сообщение помощнику');
  await expect(timeline.getByRole('status')).toHaveText('Загружаем график заданий…');
  await field.fill('Черновик не должен пропасть');
  finishLoad();
  await expect(timeline.getByRole('alert')).toContainText('График временно недоступен');
  await timeline.getByRole('button', { name: 'Повторить загрузку' }).click();
  await expect(timeline.getByRole('listitem')).toHaveCount(1);
  await expect(field).toHaveValue('Черновик не должен пропасть');
  expect(attempt).toBe(2);
});

test('chief preserves scroll while a delayed timeline reloads on mobile', async ({ page }) => {
  let delayTasks = false;
  let finishLoad!: () => void;
  const paused = new Promise<void>(resolve => { finishLoad = resolve; });
  await page.setViewportSize({ width: 390, height: 550 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await openWorkday(page, async (route, path) => {
    if (path !== tasksPath) return route.fulfill({ json: [] });
    if (delayTasks) await paused;
    return route.fulfill({ json: [task('a'), task('b'), task('c')] });
  });
  const timeline = page.getByRole('region', { name: 'Ближайшие задания' });
  await expect(timeline.getByRole('listitem')).toHaveCount(3);
  await page.evaluate(() => scrollTo(0, 320));
  await expect.poll(() => page.evaluate(() => scrollY)).toBe(320);
  delayTasks = true;
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(timeline.getByRole('status')).toBeVisible();
  finishLoad();
  await expect(timeline.getByRole('listitem')).toHaveCount(3);
  await expect.poll(() => page.evaluate(() => scrollY)).toBe(320);
});

test('chief composer keeps a long draft after failure and sends a quick action in one click', async ({ page }) => {
  let finishSend!: () => void;
  const paused = new Promise<void>(resolve => { finishSend = resolve; });
  const sent: string[] = [];
  await page.setViewportSize({ width: 390, height: 844 });
  await openWorkday(page, async (route, path) => {
    if (path.endsWith('/assistant/models')) return route.fulfill({ json: { providers: [{
      id: 'ollama', name: 'Локальные модели', status: 'ready', error_code: null, models: [
        { id: model, name: model, description: '', selectable: true },
      ],
    }] } });
    if (path.endsWith('/assistant/conversations')) return route.fulfill({ json: route.request().method() === 'POST'
      ? conversation : { items: [conversation], total: 1 } });
    if (path.endsWith('/messages')) {
      sent.push(route.request().postDataJSON().content);
      if (sent.length === 1) {
        await paused;
        return route.fulfill({ status: 503, json: { detail: 'Модель временно недоступна' } });
      }
      return route.fulfill({ json: { turn_id: 'qa-turn', status: 'completed' } });
    }
    if (path.endsWith(`/conversations/${conversation.conversation_id}`))
      return route.fulfill({ json: { conversation, turns: [], total: 0, actions: [] } });
    return route.fulfill({ json: [] });
  });
  await expect(page.getByText('На сегодня и ближайшие дни нет заданий с запланированным началом.')).toBeVisible();
  const field = page.getByPlaceholder('Что нужно сделать сегодня?');
  await expect(page.getByRole('button', { name: 'Отправить', exact: true })).toBeDisabled();
  const trigger = page.getByRole('button', { name: 'Выбрать модель: Локальная модель' });
  const form = page.getByRole('form', { name: 'Написать помощнику' });
  const height = (await form.boundingBox())!.height;
  await trigger.click();
  await expect(page.getByRole('dialog', { name: 'Используемая модель' }).getByRole('button', { name: new RegExp(model) })).toBeVisible();
  expect((await form.boundingBox())!.height).toBe(height);
  await page.keyboard.press('Escape');
  await expect(trigger).toBeFocused();
  await expect(page.getByRole('link', { name: 'Открыть ИИ-диалоги' })).toHaveAttribute('href', '/assistant');
  await expect(page.getByRole('link', { name: 'Открыть диалоги', exact: true })).toHaveAttribute('href', '/assistant');
  await field.fill('Первая строка');
  await field.press('Shift+Enter');
  await expect(field).toHaveValue('Первая строка\n');
  const draft = 'Длинный запрос на выборку задач. '.repeat(320).trimEnd();
  await field.fill(draft);
  expect(await field.evaluate(el => el.scrollHeight > el.clientHeight)).toBe(true);
  await expect(field).toHaveCSS('max-height', '180px');
  await field.press('Enter');
  await expect(page.getByRole('button', { name: 'Отправка сообщения' })).toBeDisabled();
  finishSend();
  await expect(page.getByRole('alert')).toContainText('Модель временно недоступна');
  expect(sent).toEqual([draft]);
  await expect(field).toHaveValue(draft);
  await page.getByRole('button', { name: 'Проверить загрузку', exact: true }).click();
  await expect(page).toHaveURL(/\/assistant\?chat=workday-qa-conversation$/);
  expect(sent).toEqual([draft, 'Проверь загрузку работников и ближайшие назначения.']);
  await expect(page.getByLabel('Сообщение помощнику')).toHaveValue(draft);
});

for (const count of [0, 12, 'error'] as const) {
  test(`chief notifications expose ${count} in the existing panel`, async ({ page }) => {
    await openWorkday(page, (route, path) => {
      if (path !== '/api/v1/maintenance/notifications') return route.fulfill({ json: [] });
      if (count === 'error') return route.fulfill({ status: 503, json: { detail: 'Сбой' } });
      return route.fulfill({ json: Array.from({ length: count }, (_, index) => ({
        id: String(index + 1), message: 'Просрочено ТО', taskId: null, createdAt: now, readAt: null,
      })) });
    });
    await page.getByRole('button', { name: count === 'error' ? 'Уведомления' : `Уведомления, непрочитанных: ${count}`, exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Уведомления' });
    await expect(dialog).toBeVisible();
    if (count === 'error') await expect(dialog.getByRole('alert')).toContainText('Не удалось загрузить уведомления');
    else await expect(dialog.getByText(count ? 'Непрочитанных: 12' : 'Уведомлений нет', { exact: true })).toBeVisible();
  });
}
