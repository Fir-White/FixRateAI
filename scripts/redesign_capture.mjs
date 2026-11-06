import { chromium } from '../frontend/node_modules/playwright-core/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const base = process.env.FIXRATE_CAPTURE_URL || 'http://127.0.0.1:8000';
const phase = process.env.FIXRATE_CAPTURE_PHASE || 'before';
const output = path.join(root, 'reports/redesign-v2', phase);
await fs.mkdir(output, { recursive: true });
const accounts = await fs.readFile('D:/FixRate AI/FixRate_AI/var/compose-local/accounts.txt', 'utf8');
const password = accounts.match(/^Password:\s*(.+)$/m)?.[1]?.trim();
if (!password) throw new Error('Local credentials unavailable');
const manifest = process.env.FIXRATE_CAPTURE_ROLES ? JSON.parse(await fs.readFile(path.join(output,'manifest.json'),'utf8')) : [];
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const sourceCommit = process.env.FIXRATE_CAPTURE_SHA || '422eacf94aadf0fc75e29ef8b1ee110abce78bd2';
async function capture(page, role, state, width, tiles = false) {
  const height = width === 1440 ? 900 : 844;
  const total = await page.evaluate(() => document.documentElement.scrollHeight);
  const positions = tiles ? [...new Set([0, ...Array.from({length: Math.ceil(total / (height - 100))}, (_, i) => Math.min(i*(height-100),Math.max(0,total-height)))])] : [0];
  for (const y of positions) {
    await page.evaluate(y => window.scrollTo(0,y), y);
    await page.waitForTimeout(80);
    const actual = await page.evaluate(() => window.scrollY);
    const name = `${role}-${state}-${width}-y${actual}.png`;
    await page.screenshot({ path: path.join(output,name), animations:'disabled' });
    const url = new URL(page.url());
    manifest.push({role,route:url.pathname+url.search,state,viewport:{width,height},sourceCommit,fixture:'Existing local presentation database; read-only navigation',capture:'live React authenticated',y:actual,totalHeight:total,file:name,status:'passed',review:'PARTIAL: pending individual image review'});
  }
  await page.evaluate(() => window.scrollTo(0,0));
}
try {
  for (const role of process.env.FIXRATE_CAPTURE_ROLES?.split(',') || ['executor','engineer','chief_engineer','director']) {
    const email = accounts.match(new RegExp(`^${role}:\\s*(\\S+)`, 'm'))?.[1];
    if (!email) throw new Error(`Missing account: ${role}`);
    const context = await browser.newContext({ viewport: {width:1440,height:900}, reducedMotion:'reduce' });
    const page = await context.newPage();
    const errors=[];
    page.on('pageerror', error=>errors.push(error.message));
    await page.goto(`${base}/login`);
    await page.getByLabel('Email',{exact:true}).fill(email);
    await page.getByLabel('Пароль',{exact:true}).fill(password);
    await page.getByRole('button',{name:'Войти',exact:true}).click();
    await page.waitForURL(url=>!url.pathname.endsWith('/login'));
    await page.waitForTimeout(1000);
    await capture(page,role,'home',1440,true);
    const names = await page.getByRole('button').allTextContents();
    const labels = await page.locator('button[aria-label]').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('aria-label')));
    await fs.writeFile(path.join(output,`${role}-controls.json`),JSON.stringify({names,labels},null,2));
    const toggle = page.getByRole('button',{name:/Свернуть меню|Свернуть боковую|Свернуть навигацию|Свернуть панель/}).first();
    if(await toggle.count()) { await toggle.click();await capture(page,role,'sidebar-collapsed',1440); }
    const notification=page.getByRole('button',{name:/Уведомления/}).first();
    if(await notification.count()) { await notification.click();await capture(page,role,'notifications',1440);await page.keyboard.press('Escape'); }
    await page.goto(`${base}/profile`);await page.waitForTimeout(500);await capture(page,role,'profile',1440,true);
    const route=role==='executor'?'/executor/tasks/e856be90-077a-5b50-ae78-885a40b80ae1':role==='engineer'?'/quality/e856be90-077a-5b50-ae78-885a40b80ae1':role==='chief_engineer'?'/settings/equipment':'/director';
    await page.goto(base+route);await page.waitForTimeout(1000);
    if(role==='chief_engineer') {
      await page.getByRole('combobox',{name:'Оборудование для настройки'}).selectOption({index:1});
      await page.getByRole('button',{name:'Настроить',exact:true}).first().waitFor();
      await page.getByRole('button',{name:'Настроить',exact:true}).first().click();
      await page.getByRole('heading',{name:'Изменить обслуживание',exact:true}).waitFor();
    }
    await capture(page,role,'anchor',1440,true);
    await page.setViewportSize({width:390,height:844});await page.waitForTimeout(300);await capture(page,role,'anchor',390,true);
    if(role!=='executor') {await page.goto(base+'/tasks');await page.waitForTimeout(700);await capture(page,role,'tasks',390,true);}
    await page.goto(base+'/profile');await page.waitForTimeout(500);await capture(page,role,'profile',390,true);
    await fs.writeFile(path.join(output,`${role}-errors.json`),JSON.stringify(errors,null,2));
    await context.close();
    console.log(`Captured ${role}; runtime errors: ${errors.length}`);
  }
} finally {
  await fs.writeFile(path.join(output,'manifest.json'),JSON.stringify([...new Map(manifest.map(item=>[item.file,item])).values()],null,2));
  await browser.close();
}
