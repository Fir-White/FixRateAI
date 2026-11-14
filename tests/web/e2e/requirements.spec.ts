import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';

for(const width of [1440,390,320]){
  test(`real common requirements, retained inputs and bounded rows at ${width}px`,async({page,context},info)=>{
    test.skip(!process.env.FIXRATE_REQUIREMENTS_E2E,'Requires a disposable requirements QA scenario');
    expect(process.env.FIXRATE_BASE_URL).toBe('http://127.0.0.1:8885');
    const scenario=JSON.parse(await readFile('reports/requirements-qa-scenario.json','utf8'));
    const writes:string[]=[],errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
    page.on('request',request=>{const url=new URL(request.url());if(url.pathname.startsWith('/api/v1/maintenance/')&&!['GET','HEAD'].includes(request.method())&&url.pathname!=='/api/v1/maintenance/planning-requirements/preview')writes.push(url.pathname);});
    const login=await context.request.post('/api/v1/auth/login',{data:{email:'chief@requirements.test',password:'Test-Requirements-2026!'}});expect(login.ok()).toBe(true);
    const auth=await login.json();
    try{
      await page.setViewportSize({width,height:900});
      const path=`/planning?mode=requirements&requirements_catalog=${scenario.catalog}&requirements_start=2027-01-01&requirements_end=2027-12-31`;
      await page.goto(path);
      const panel=page.getByRole('region',{name:'Обязательные работы из регламентов и Excel'});
      await expect(panel.getByRole('heading',{name:'Что нужно обслужить в выбранном периоде'})).toBeVisible();
      await expect(page.getByRole('region',{name:'Состав обязательств',exact:true})).toHaveCount(0);
      await panel.getByLabel('Даты из Excel',{exact:true}).selectOption('source_january');
      await panel.getByRole('button',{name:'Выбрать все подготовленные строки Excel',exact:true}).click();
      await expect(panel).toContainText('Выбрано строк: 1');
      await panel.getByRole('button',{name:'Рассчитать состав обязательств',exact:true}).click();
      const result=page.getByRole('region',{name:'Состав обязательств',exact:true});
      await expect(result.getByRole('list',{name:'Работы общего состава'}).getByRole('listitem')).toHaveCount(2);
      await expect(result.getByText('Известная трудоёмкость',{exact:true}).locator('..')).toContainText(/5(?:\.0+)? чел.-ч/);
      await expect(result).toContainText('вне выбранного состава: 216');
      await expect(result.getByRole('region',{name:'Что нужно уточнить для расчёта'})).toHaveCount(0);
      const search=result.getByLabel('Поиск обязательных работ');
      await search.pressSequentially('TEST approved',{delay:15});
      await expect(result.getByRole('list',{name:'Работы общего состава'}).getByRole('listitem')).toHaveCount(1);
      await expect(search).toBeFocused();
      const card=result.getByRole('article');
      await card.getByText('Источник, сроки и объяснение',{exact:true}).click();
      await expect(card).toContainText('TEST-REG-PUMP');await expect(card).toContainText('15 февр. 2027');
      await search.fill('');
      await expect(result.getByRole('list',{name:'Работы общего состава'}).getByRole('listitem')).toHaveCount(2);
      await result.getByRole('button',{name:/Задание уже создано: 0/}).click();
      await expect(result).toContainText('Работы в этом представлении не найдены');
      await result.getByRole('button',{name:'Все работы',exact:true}).click();
      await expect(result.getByRole('list',{name:'Работы общего состава'}).getByRole('listitem')).toHaveCount(2);
      const views=page.getByRole('navigation',{name:'Представления планирования'});
      await views.getByRole('button',{name:'Планы из Excel',exact:true}).click();
      await expect(page.getByRole('button',{name:/TEST_REQUIREMENTS.xlsx · 217/})).toBeVisible();
      await views.getByRole('button',{name:'Общий состав обязательств',exact:true}).click();
      await expect(panel.getByLabel('Даты из Excel',{exact:true})).toHaveValue('source_january');
      await expect(panel).toContainText('Выбрано строк: 1');
      await expect(result.getByRole('list',{name:'Работы общего состава'}).getByRole('listitem')).toHaveCount(2);
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
      await result.scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath(`requirements-${width}.png`)});
      await page.reload();await expect(panel.getByRole('button',{name:'TEST_REQUIREMENTS.xlsx',exact:true})).toBeVisible();
      expect(writes).toEqual([]);expect(errors).toEqual([]);
    }finally{await context.request.post('/api/v1/auth/logout',{data:{},headers:{'X-CSRF-Token':auth.csrfToken}});}
  });
}
