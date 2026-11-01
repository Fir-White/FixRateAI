import { createRequire } from 'node:module';
import { writeFile } from 'node:fs/promises';
import { cpus, platform, release, totalmem } from 'node:os';

const require = createRequire(new URL('../../../../frontend/package.json', import.meta.url));
const { chromium } = require('@playwright/test');
const label = process.argv[2] || 'review';
if (!/^[a-z0-9_-]+$/i.test(label)) throw new Error('Label must contain only letters, digits, underscores or hyphens');
const base = process.env.FIXRATE_BASE_URL || 'http://127.0.0.1:5174';
const categories = 'devtools.timeline,disabled-by-default-devtools.timeline,cc,blink';
const durationMs = 8000;
const wanted = ['Paint', 'RasterTask', 'FireAnimationFrame', 'Layout', 'UpdateLayoutTree', 'FunctionCall', 'PrePaint', 'Layerize', 'CompositeLayers', 'DrawFrame', 'BeginMainThreadFrame', 'EventDispatch', 'RunTask', 'MinorGC', 'MajorGC'];

function summarize(events) {
  const names = new Map();
  for (const event of events) if (event.ph === 'M' && event.name === 'thread_name') names.set(`${event.pid}:${event.tid}`, event.args?.name || '');
  const groups = new Map();
  const aggregate = new Map(wanted.map(name => [name, []]));
  for (const event of events) {
    if (event.ph !== 'X' || !Number.isFinite(event.dur) || event.dur <= 0) continue;
    const thread = names.get(`${event.pid}:${event.tid}`) || `tid:${event.tid}`;
    const key = `${thread}\u0000${event.name}`;
    const group = groups.get(key) || { thread, name: event.name, durations: [] };
    group.durations.push(event.dur / 1000);
    groups.set(key, group);
    if (aggregate.has(event.name)) aggregate.get(event.name).push(event.dur / 1000);
  }
  function stats(values) {
    values.sort((a, b) => a - b);
    return { count: values.length, totalMs: values.reduce((a, b) => a + b, 0), p95Ms: values.length ? values[Math.floor((values.length - 1) * .95)] : null, maxMs: values.length ? values.at(-1) : null };
  }
  const top = [...groups.values()].map(({ thread, name, durations }) => ({ thread, name, ...stats(durations) })).sort((a, b) => b.totalMs - a.totalMs).slice(0, 40);
  const selected = Object.fromEntries([...aggregate.entries()].map(([name, durations]) => [name, stats(durations)]));
  const threads = Object.fromEntries([...names.entries()]);
  return { traceEventCount: events.length, completeEventCount: [...groups.values()].reduce((sum, group) => sum + group.durations.length, 0), selected, top, threads };
}

async function readTrace(cdp, stream) {
  let traceText = '';
  for (;;) {
    const chunk = await cdp.send('IO.read', { handle: stream, size: 1024 * 1024 });
    traceText += chunk.base64Encoded ? Buffer.from(chunk.data, 'base64').toString('utf8') : chunk.data;
    if (chunk.eof) break;
  }
  await cdp.send('IO.close', { handle: stream });
  const parsed = JSON.parse(traceText);
  return summarize(parsed.traceEvents || parsed);
}

const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--disable-background-timer-throttling', '--disable-renderer-backgrounding'] });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
await context.route('**/*', route => new URL(route.request().url()).pathname.startsWith('/api/')
  ? route.fulfill({ status: 401, json: { detail: 'Not authenticated' } }) : route.continue());
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const cdp = await context.newCDPSession(page);
try {
  await page.goto(new URL('/login', base).href);
  await page.locator('.auth-form').waitFor();
  await page.locator('.auth-aurora[data-motion="running"]').waitFor();
  await cdp.send('Performance.enable');
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 });
  await page.waitForTimeout(1200);
  const environment = await page.evaluate(() => ({ userAgent: navigator.userAgent, hardwareConcurrency: navigator.hardwareConcurrency, deviceMemoryGiB: navigator.deviceMemory ?? null, devicePixelRatio, viewport: { width: innerWidth, height: innerHeight }, scene: (() => { const r = document.querySelector('.auth-aurora').getBoundingClientRect(); return { width: r.width, height: r.height }; })() }));
  const results = [];
  for (const state of ['active', 'paused']) {
    if (state === 'paused') {
      await page.locator('.auth-footer button').click();
      await page.getByRole('checkbox', { name: 'ÐÐ½Ð¸Ð¼Ð°Ñ†Ð¸Ñ Ñ„Ð¾Ð½Ð°' }).uncheck();
      await page.keyboard.press('Escape');
      await page.locator('.auth-aurora[data-motion="paused"]').waitFor();
      await page.waitForTimeout(1000);
    }
    const before = (await cdp.send('Performance.getMetrics')).metrics;
    await cdp.send('Tracing.start', { categories, transferMode: 'ReturnAsStream', options: 'record-as-much-as-possible' });
    const started = performance.now();
    await page.waitForTimeout(durationMs);
    const elapsedMs = performance.now() - started;
    const complete = new Promise(resolve => cdp.once('Tracing.tracingComplete', resolve));
    await cdp.send('Tracing.end');
    const { stream } = await complete;
    if (!stream) throw new Error('Tracing.tracingComplete did not provide a stream');
    const after = (await cdp.send('Performance.getMetrics')).metrics;
    const delta = Object.fromEntries(['TaskDuration', 'ScriptDuration', 'LayoutDuration', 'RecalcStyleDuration', 'LayoutCount', 'RecalcStyleCount', 'JSHeapUsedSize', 'JSHeapTotalSize'].map(name => [name, (after.find(item => item.name === name)?.value || 0) - (before.find(item => item.name === name)?.value || 0)]));
    const trace = await readTrace(cdp, stream);
    results.push({ state, elapsedMs, cpuThrottlingRate: 4, cdpDelta: delta, trace });
    process.stdout.write(`${state}: ${JSON.stringify({ elapsedMs, cdpDelta: delta, selected: trace.selected })}\n`);
  }
  const report = { label, generatedAtUtc: new Date().toISOString(), baseUrl: base, browser: browser.version(), headless: true, platform: platform(), platformRelease: release(), cpuModel: cpus()[0]?.model || null, hostCpuCount: cpus().length, totalMemoryBytes: totalmem(), categories, durationMs, environment, eventDurationNote: 'Trace X event durations are inclusive and may overlap; totals across event names/threads are not additive.', results, errors };
  await writeFile(new URL(`./${label}-trace.json`, import.meta.url), JSON.stringify(report, null, 2));
  if (errors.length) throw new Error(`Page errors: ${errors.join('; ')}`);
} finally {
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: 1 }).catch(() => {});
  await browser.close();
}
