import {test, expect} from '@playwright/test';

// Production SPA with local API fixtures. No LLM, credentials or domain writes.
for (const facts of [false,true]) for (const width of [1440, 390]) for (const reducedMotion of ['no-preference', 'reduce'] as const) {
  test(`native saved details remain readable at ${width}px, ${reducedMotion}, facts=${facts}`, async ({page, context}, info) => {
    const origin = new URL(String(info.project.use.baseURL)).origin;
    await page.setViewportSize({width, height: 900});
    await page.emulateMedia({reducedMotion});
    const now = '2026-11-16T09:00:00Z';
    const id = '11111111-1111-4111-8111-111111111111';
    const conversation = {conversation_id: id, title: 'QA длинная история', agent: 'assistant', created_at: now, updated_at: now};
    const answer = Array.from({length: 35}, (_, index) => [
      `- QA оборудование ${index}: исходная запись; обслуживание ещё не подтверждено.`,
      '  - Факт: исходные данные сохранены; исполнение и приёмка требуют отдельной проверки.',
      '  - Норма: 0; единица не указана; длительность и состав бригады не подтверждены.',
      `  - Последнее поле записи ${index}: фактическое значение должно остаться доступным.`,
    ].join('\n')).join('\n');
    const turns = Array.from({length: 21}, (_, index) => ({turn_id: `turn-${index}`, content: `QA вопрос ${index}`,
      answer:'QA_FIND_'+index+'\n'+answer, workflow: {answer_format:facts?'facts':undefined,outcome:'completed',goals:[{id:'qa-facts',title:'QA saved facts',status:'completed'}]}, status: 'completed', trace: [], error_code: null, created_at: now, finished_at: now, model_ref: 'API-FIXTURE-NO-LLM'}));
    const errors: string[] = [], writes: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await context.route('**/*', async route => {
      const request = route.request(), url = new URL(request.url());
      if (url.origin !== origin) return route.abort('blockedbyclient');
      if (!url.pathname.startsWith('/api/')) return route.continue();
      if (request.method() !== 'GET') {writes.push(request.method() + ' ' + url.pathname); return route.fulfill({status: 405});}
      if (url.pathname === '/api/v1/auth/session') return route.fulfill({json: {profile: {userId: 'QA-only', siteId: 'QA-site',
        name: 'QA', role: width === 390 ? 'executor' : 'chief_engineer', siteName: 'QA fixtures', timezone: 'UTC'}}});
      if (url.pathname.endsWith('/assistant/capabilities')) return route.fulfill({json: {available: true, model_ref: 'FIXTURE',
        prompt_version: 'QA', agents: [], tools: {assistant: [], planner: [], photo: []}}});
      if (url.pathname.endsWith('/assistant/conversations')) return route.fulfill({json: {items: [conversation], total: 1}});
      if (url.pathname.endsWith('/assistant/conversations/' + id)) return route.fulfill({json: {conversation, turns, total: 21,
        actions: [], attachments: [], pending_attachments: []}});
      if (url.pathname.includes('/registry')) return route.fulfill({json: {items: [], systems: []}});
      return route.fulfill({json: []}); // Empty bounded workspace warm-up lists.
    });
    await page.goto('/assistant?chat=' + id);
    const region = page.getByRole('region', {name: 'Сообщения'}), articles = region.locator('article');
    await expect(articles).toHaveCount(21);
    await expect(articles.last().locator('.assistant-answer')).toContainText('Последнее поле записи 34');
    await expect.poll(() => region.evaluate(el => el.scrollHeight - el.scrollTop - el.clientHeight)).toBeLessThan(3);
    expect(await region.locator('.assistant-answer').count()).toBe(1);
    expect(await region.locator('.assistant-saved-plain').count()).toBe(20);
    const nativeKey = async (key: string) => {
      const ended = region.evaluate(el => new Promise<void>(resolve => el.addEventListener('scrollend', () => resolve(), {once: true})));
      await page.keyboard.press(key);
      await ended;
    };
    await region.focus();
    await nativeKey('Home');
    await expect(articles.first().locator('.assistant-saved-plain')).toContainText('Последнее поле записи 34');
    const first=articles.first(),details=first.locator('.assistant-saved-answer'),summary=details.locator('summary');
    const source=first.locator('.assistant-saved-plain');
    await source.dispatchEvent('beforematch');
    await expect(details).toHaveAttribute('open','');
    await expect(source).toContainText('QA_FIND_0');
    await expect(first.locator('.assistant-answer')).toHaveCount(0);
    await summary.focus();await page.keyboard.press('Enter');
    await expect(details).not.toHaveAttribute('open','');
    await page.keyboard.press('Enter');
    await expect(first.locator('.assistant-answer')).toContainText('QA_FIND_0');
    await expect(summary).toBeFocused();
    const before = await region.evaluate(el => el.scrollTop);
    await nativeKey('PageDown');
    expect(await region.evaluate(el => el.scrollTop)).toBeGreaterThan(before);
    await nativeKey('End');
    await expect.poll(() => region.evaluate(el => el.scrollHeight - el.scrollTop - el.clientHeight)).toBeLessThan(3);
    const input = page.getByLabel('Сообщение помощнику');
    await input.fill('Черновик сохранён при переходе');
    await page.getByRole('group', {name: 'Управление чатом'}).getByRole('button', {name: 'Новый чат'}).click();
    await page.goBack();
    await expect(input).toHaveValue('Черновик сохранён при переходе');
    await expect(articles.last().locator('.assistant-answer')).toContainText('Последнее поле записи 34');
    await page.reload();
    await expect(articles).toHaveCount(21);
    await expect(articles.last().locator('.assistant-answer')).toContainText('Последнее поле записи 34');
    await expect.poll(() => region.evaluate(el => el.scrollHeight - el.scrollTop - el.clientHeight)).toBeLessThan(3);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    expect(writes).toEqual([]);
    expect(errors).toEqual([]);
  });
}
