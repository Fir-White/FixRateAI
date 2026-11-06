import {chromium} from '../frontend/node_modules/playwright-core/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
const root=path.resolve(import.meta.dirname,'..');
const out=path.join(root,'reports/redesign-v2/accessibility');
await fs.mkdir(out,{recursive:true});
const commonGit=path.resolve(root,execFileSync('git',['rev-parse','--git-common-dir'],{cwd:root,encoding:'utf8'}).trim());
const accounts=await fs.readFile(process.env.FIXRATE_CAPTURE_ACCOUNTS||path.join(path.dirname(commonGit),'var/compose-local/accounts.txt'),'utf8');
const password=accounts.match(/^Password:\s*(.+)$/m)[1].trim();
const base=process.env.FIXRATE_CAPTURE_URL||'http://127.0.0.1:5174';
const source=process.env.FIXRATE_CAPTURE_SHA;
if(!source)throw new Error('Set FIXRATE_CAPTURE_SHA to the tested source revision (with -dirty if applicable)');
const browser=await chromium.launch({channel:'chrome',headless:true});
const results=[];
async function anchor(page,role){
 const routes={executor:'/executor/tasks/e856be90-077a-5b50-ae78-885a40b80ae1',engineer:'/quality/e856be90-077a-5b50-ae78-885a40b80ae1',chief_engineer:'/settings/equipment',director:'/director'};
 await page.goto(base+routes[role]);await page.waitForTimeout(600);
 if(role==='chief_engineer'){
  await page.getByLabel('Оборудование для настройки',{exact:true}).selectOption({index:1});
  await page.getByRole('button',{name:'Настроить',exact:true}).first().click();
  await page.getByRole('heading',{name:'Изменить обслуживание',exact:true}).waitFor();
 }
 // A real wheel event cancels the application's pending saved-scroll restoration.
 await page.mouse.move(250,400);await page.mouse.wheel(0,-100000);await page.waitForTimeout(250);
 await page.evaluate(()=>window.scrollTo(0,0));
}
async function measure(page,role,width,state){
 const geometry=await page.evaluate(()=>({viewport:innerWidth,scrollWidth:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight,contentWidth:document.querySelector('.fr-content-v2')?.getBoundingClientRect().width,
  overflow:[...document.querySelectorAll('.fr-content-v2 *')].filter(el=>{const r=el.getBoundingClientRect();return r.width>0&&r.right>innerWidth+1&&getComputedStyle(el).visibility!=='hidden';}).slice(0,12).map(el=>({tag:el.tagName,class:el.className,text:el.textContent?.slice(0,100),right:el.getBoundingClientRect().right}))}));
 results.push({role,width,state,route:new URL(page.url()).pathname,source,status:geometry.scrollWidth<=width?'passed':'failed',...geometry});
 for(const [part,y] of [['top',0],['middle',Math.round(geometry.height/2)],['bottom',geometry.height]]){
  await page.evaluate(y=>window.scrollTo(0,y),y);await page.waitForTimeout(200);
  const actualY=await page.evaluate(()=>scrollY);
  await page.screenshot({path:path.join(out,`${role}-${width}-${state}-${part}.png`),animations:'disabled'});
  results.push({role,width,state:'capture-position',variant:state,part,actualY,status:part==='top'&&actualY!==0?'failed':'passed'});
 }
}
try{
 for(const role of process.env.FIXRATE_A11Y_ROLES?.split(',')||['executor','engineer','chief_engineer','director']){
  const context=await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'});
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/login');await page.getByLabel('Email',{exact:true}).fill(accounts.match(new RegExp(`^${role}:\\s*(\\S+)`,'m'))[1]);
  await page.getByLabel('Пароль',{exact:true}).fill(password);await page.getByRole('button',{name:'Войти',exact:true}).click();await page.waitForURL(url=>!url.pathname.endsWith('/login'));
  for(const width of process.env.FIXRATE_TEXT_ONLY?[]:(process.env.FIXRATE_A11Y_WIDTHS?.split(',').map(Number)||[1440,1280,768,390,360,320])){
   await page.setViewportSize({width,height:width>768?900:844});await anchor(page,role);await measure(page,role,width,'normal');
  }
  await page.setViewportSize({width:390,height:844});await anchor(page,role);
  await page.evaluate(()=>{
   const values=[...document.querySelectorAll('.fr-content-v2,.fr-content-v2 *')].filter(el=>el instanceof HTMLElement).map(el=>({el,font:parseFloat(getComputedStyle(el).fontSize),line:parseFloat(getComputedStyle(el).lineHeight)}));
   for(const {el,font,line} of values){el.style.fontSize=font*2+'px';if(Number.isFinite(line))el.style.lineHeight=line*2+'px';}
  });
  await measure(page,role,390,'text200');
  await anchor(page,role);
  if(role==='engineer'){
   const jump=page.getByRole('link',{name:'Перейти к основанию решения',exact:true});
   await page.screenshot({path:path.join(out,'engineer-decision-jump-top.png'),animations:'disabled'});
   await jump.click();await page.waitForTimeout(200);
   const target=page.locator('#review-decision');
   const top=await target.evaluate(el=>el.getBoundingClientRect().top);
   await page.screenshot({path:path.join(out,'engineer-decision-jump-target.png'),animations:'disabled'});
   results.push({role,state:'decision-jump',status:top>=60&&top<400?'passed':'failed',top});
  }
  const summary=page.locator('.fr-content-v2 details > summary').first();
  if(await summary.count()){
   await summary.focus();const initial=await summary.evaluate(el=>el.parentElement.open);
   await page.keyboard.press('Enter');const toggled=await summary.evaluate(el=>el.parentElement.open);
   results.push({role,state:'keyboard-details',status:initial!==toggled?'passed':'failed'});
  }
  if(role==='director'){
   await page.goto(base+'/calendar');await page.waitForTimeout(600);
   const trigger=page.locator('.fr-calendar-agenda li button,.fr-calendar-event').first();
   await trigger.focus();const handle=await trigger.elementHandle();await page.keyboard.press('Enter');
   const dialog=page.getByRole('dialog');await dialog.waitFor();
   const focusedInside=await dialog.evaluate(el=>el.contains(document.activeElement));
   const trapped=[];for(let i=0;i<12;i++){await page.keyboard.press('Tab');trapped.push(await dialog.evaluate(el=>el.contains(document.activeElement)));}
   await page.screenshot({path:path.join(out,'director-keyboard-drawer.png'),animations:'disabled'});
   await page.keyboard.press('Escape');await dialog.waitFor({state:'detached'});
   const returned=await page.evaluate(el=>document.activeElement===el,handle);
   results.push({role,state:'keyboard-drawer',status:focusedInside&&trapped.every(Boolean)&&returned?'passed':'failed',focusedInside,trapped,returned});
  }
  results.push({role,state:'runtime',status:errors.length?'failed':'passed',errors});await context.close();console.log(`C14 ${role} complete`);
 }
}finally{await fs.writeFile(path.join(out,process.env.FIXRATE_A11Y_ROLES?'fix-results.json':process.env.FIXRATE_TEXT_ONLY?'text-results.json':'results.json'),JSON.stringify(results,null,2));await browser.close();}
console.log(JSON.stringify(results.filter(r=>r.status==='failed'),null,2));
