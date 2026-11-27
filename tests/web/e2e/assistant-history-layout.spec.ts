import {expect,test} from '@playwright/test';

for(const width of [1920,390]) {
  test(`шапка остаётся на месте между рабочим днём и чатом при ширине ${width}`,async({page})=>{
    test.skip(!process.env.FIXRATE_TEST_PASSWORD||!process.env.FIXRATE_ASSISTANT_LAYOUT_E2E,'Нужен изолированный стенд');
    expect(new URL(process.env.FIXRATE_BASE_URL!).origin).toBe('http://127.0.0.1:18086');
    await page.setViewportSize({width,height:950});
    await page.emulateMedia({reducedMotion:'reduce'});
    await page.goto('/login');
    await page.getByLabel('Email',{exact:true}).fill('fixrate-demo-chief_engineer@example.test');
    await page.getByLabel('Пароль',{exact:true}).fill(process.env.FIXRATE_TEST_PASSWORD!);
    await page.getByRole('button',{name:'Войти',exact:true}).click();
    await expect(page.getByRole('heading',{name:/С чего начнём рабочий день/})).toBeVisible();
    await page.evaluate(()=>document.fonts.ready);
    const assistant=page.locator('.e3-assistant-trigger');
    const logo=page.locator('.e3-brand');
    const targets=[logo,assistant,page.locator('.e3-profile-trigger'),page.locator('.e3-topbar .inbox-trigger')];
    if(width===1920)targets.push(page.getByRole('navigation',{name:'Основная навигация'}));
    const boxes=()=>Promise.all(targets.map(target=>target.boundingBox()));
    const baseline=await boxes();
    expect(baseline.every(box=>box!==null)).toBe(true);
    const positions=baseline.map(box=>({x:Math.round(box!.x),y:Math.round(box!.y),width:Math.round(box!.width),height:Math.round(box!.height)}));
    const label=await assistant.getAttribute('aria-label');
    await assistant.click();
    await expect(page).toHaveURL(/\/assistant$/);
    await expect(page.getByRole('group',{name:'Управление чатом'})).toBeVisible();
    const compare=async()=>{
      const current=await boxes();
      expect(current.map(box=>({x:Math.round(box!.x),y:Math.round(box!.y),width:Math.round(box!.width),height:Math.round(box!.height)}))).toEqual(positions);
      await assistant.hover();
      await expect(assistant).toHaveAttribute('aria-label',label!);
      await expect(assistant.locator('.topbar-hint')).toBeVisible();
      await expect(assistant.locator('.topbar-hint')).toHaveText(label!);
    };
    await page.reload();
    await expect(page.getByRole('group',{name:'Управление чатом'})).toBeVisible();
    await page.evaluate(()=>document.fonts.ready);
    await compare();
    await page.goBack();
    await expect(page.getByRole('heading',{name:/С чего начнём рабочий день/})).toBeVisible();
    await compare();
    await page.goForward();
    await expect(page.getByRole('group',{name:'Управление чатом'})).toBeVisible();
    await compare();
  });
  test(`история и кнопка нового чата при ширине ${width}`,async({page})=>{
    test.skip(!process.env.FIXRATE_TEST_PASSWORD||!process.env.FIXRATE_ASSISTANT_LAYOUT_E2E,'Нужен изолированный стенд');
    expect(new URL(process.env.FIXRATE_BASE_URL!).origin).toBe('http://127.0.0.1:18086');
    await page.setViewportSize({width,height:900});
    await page.emulateMedia({reducedMotion:'reduce'});
    await page.goto('/login');
    await page.getByLabel('Email',{exact:true}).fill('fixrate-demo-chief_engineer@example.test');
    await page.getByLabel('Пароль',{exact:true}).fill(process.env.FIXRATE_TEST_PASSWORD!);
    await page.getByRole('button',{name:'Войти',exact:true}).click();
    await expect(page).not.toHaveURL(/\/login$/);
    await page.goto('/assistant');
    const toolbar=page.getByRole('group',{name:'Управление чатом'});
    const add=toolbar.getByRole('button',{name:'Новый чат'});
    await expect(add).toBeVisible();
    await expect(toolbar).toHaveCSS('background-color','rgba(0, 0, 0, 0)');
    await expect(add.locator('svg path').first()).toHaveAttribute('d',/Z$/);
    const greeting=await page.getByRole('heading',{name:'С чего начнём?',exact:true}).boundingBox();
    const tools=await toolbar.boundingBox();
    expect(greeting).not.toBeNull();
    expect(tools).not.toBeNull();
    if(width===1920){
      expect(greeting!.x).toBeGreaterThan(width/2);
      expect(greeting!.y).toBeLessThan(tools!.y+tools!.height);
    }else expect(greeting!.y).toBeGreaterThanOrEqual(tools!.y+tools!.height);
    const toggle=toolbar.getByRole('button',{name:/историю чатов/});
    if(await toggle.getAttribute('aria-expanded')==='false') await toggle.click();
    if(width===1920){
      const rail=await page.getByRole('complementary',{name:'История диалогов'}).boundingBox();
      expect(rail!.x).toBeLessThanOrEqual(32);
    } else {
      await expect(page.getByRole('dialog',{name:'История диалогов'})).toBeVisible();
      await page.keyboard.press('Escape');
      await expect(toggle).toBeFocused();
    }
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  });
}
