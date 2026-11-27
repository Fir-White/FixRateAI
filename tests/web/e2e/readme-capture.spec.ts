import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { expect, test, type Locator, type Page } from "@playwright/test";

const maintenance = "/api/v1/maintenance";
const assistant = "/api/v1/assistant";
const demoId = (name: string) => createHash("md5").update(`fixrate-demo-${name}`).digest("hex")
  .replace(/^(.{8})(.{4})(.{4})(.{4})(.{12})$/, "$1-$2-$3-$4-$5");
const task = demoId("runtime-order");
const other = demoId("assignment-order");
const size = {width:1440,height:1000};

test("README product walkthrough from assignment to acceptance and assistant", async ({browser}) => {
  test.skip(process.env.FIXRATE_README_CAPTURE !== "1", "Run verify_web.py --readme on a disposable database");
  test.setTimeout(420_000);
  const baseURL = new URL(process.env.FIXRATE_BASE_URL!);
  expect(baseURL.hostname).toBe("127.0.0.1");
  const dir = process.env.FIXRATE_README_FIXTURE!;
  const output = path.join(process.env.FIXRATE_E2E_OUTPUT!,"readme-gallery");
  await mkdir(output,{recursive:true});
  const fixture = JSON.parse(await readFile(path.join(dir,"fixture.json"),"utf8")) as {
    assetCode: string; assetName: string;
  };
  const images: {file:string; route:string; sha256:string}[] = [];
  const signIn = async (email:string, role:string) => {
    const context = await browser.newContext({baseURL:baseURL.href,viewport:size,reducedMotion:"reduce"});
    const r = await context.request.post("/api/v1/auth/login",{data:{email,password:process.env.FIXRATE_TEST_PASSWORD}});
    expect(r.status()).toBe(200);
    const {profile,csrfToken} = await r.json();
    expect(profile.role).toBe(role);
    return {context,page:await context.newPage(),headers:{"X-CSRF-Token":csrfToken}};
  };
  const chief = await signIn("fixrate-demo-chief_engineer@example.test","chief_engineer");
  const executor = await signIn("fixrate-demo-1@example.test","executor");
  const shot = async (page:Page,file:string,ready:Locator) => {
    await expect(ready).toBeVisible();
    await expect(page.locator("body")).not.toContainText(/\bDEMO\b|демонстрацион|деморежим|@example\.test/i);
    await page.evaluate(async () => {
      await document.fonts.ready;
      await Promise.all([...document.images].filter(img => {
        const rect=img.getBoundingClientRect();
        return rect.height>0 && rect.top<innerHeight && rect.bottom>0;
      }).map(img=>img.decode()));
    });
    const bytes=await page.screenshot({path:path.join(output,file),type:"jpeg",quality:87,animations:"disabled"});
    images.push({file,route:new URL(page.url()).pathname,sha256:createHash("sha256").update(bytes).digest("hex")});
  };

  const worker=executor.page;
  await worker.goto("/executor");
  await worker.locator(`a[href="/executor/tasks/${task}"]`).first().click();
  const start=worker.getByRole("button",{name:"Приступить к работе",exact:true});
  await shot(worker,"01-naryad.jpg",start);
  await start.click();
  await worker.getByRole("checkbox",{name:/Поверхность очищена/}).check();
  await worker.getByRole("button",{name:"Итоговый отчёт",exact:true}).click();
  await worker.getByLabel("Что выполнено и какие замечания остались").fill("Поверхность очищена. Крепёж и защитная решётка без видимых повреждений.");
  await worker.getByRole("button",{name:"Добавить фотографии",exact:true}).click();
  for(const [phase,name] of [["до","before"],["после","after"]]){
    const upload=worker.waitForResponse(r=>r.url().endsWith("/photos")&&r.request().method()==="POST");
    await worker.getByLabel(new RegExp(`^Фото ${phase}: `)).setInputFiles(path.join(dir,`${name}.jpg`));
    expect((await upload).status()).toBe(200);
  }
  const photos=worker.locator(".evidence-photo img");
  await expect(photos).toHaveCount(2);
  await photos.first().evaluate(element=>element.scrollIntoView({block:"center"}));
  await shot(worker,"02-fotootchet.jpg",photos.first());
  await worker.getByRole("button",{name:"Итоговый отчёт",exact:true}).click();
  await worker.getByRole("button",{name:"Сдать работу",exact:true}).click();
  const submit=worker.waitForResponse(r=>r.url().endsWith("/submit")&&r.request().method()==="POST");
  await worker.getByRole("button",{name:"Подтвердить сдачу"}).click();
  expect((await submit).status()).toBe(200);

  const page=chief.page;
  await page.goto("/quality");
  await page.locator(`a[href="/quality/${task}"]`).first().click();
  await expect(page.locator(".evidence-photo img")).toHaveCount(2);
  await page.getByLabel(/Причина решения/).fill("Фотографии и отметка чек-листа проверены. Замечаний к отчёту нет.");
  await page.locator("#review-evidence").evaluate(element=>element.scrollIntoView({block:"center"}));
  await shot(page,"03-priemka.jpg",page.getByRole("button",{name:"Принять работу",exact:true}));
  await page.getByRole("button",{name:"Принять работу",exact:true}).click();
  await expect(page.getByRole("button",{name:"Подтвердить приёмку"})).toBeVisible();
  const acceptance=page.waitForResponse(r=>r.url().endsWith("/review")&&r.request().method()==="POST");
  await page.getByRole("button",{name:"Подтвердить приёмку"}).click();
  const accepted=await acceptance;
  expect(accepted.status()).toBe(200);
  expect((await accepted.json()).task.state).toBe("accepted");

  await page.goto("/assistant");
  await page.getByLabel("Сообщение помощнику").fill(`Как называется оборудование с кодом ${fixture.assetCode}?`);
  await page.getByRole("button",{name:"Отправить",exact:true}).click({timeout:12_000});
  await expect(page).toHaveURL(/chat=/,{timeout:12_000});
  const chat=new URL(page.url()).searchParams.get("chat");
  const readChat=async()=> (await (await chief.context.request.get(`${assistant}/conversations/${chat}`)).json());
  await expect.poll(async()=> (await readChat()).turns.at(-1)?.status,{timeout:120_000}).toMatch(/^(completed|failed)$/);
  const answer=await readChat();
  const turn=answer.turns.at(-1);
  expect(turn.status,turn.error_code).toBe("completed");
  expect(turn.execution_engine).toBe("v4");
  expect(turn.model_ref).toContain("ollama:");
  expect(turn.answer.toLowerCase()).toContain(fixture.assetName.toLowerCase());
  expect(turn.trace.some((step:{tool:string;status:string})=>["find_equipment","read_equipment"].includes(step.tool)
    && step.status==="completed")).toBe(true);
  expect(answer.actions).toEqual([]);
  const messages=page.getByRole("region",{name:"Сообщения"});
  await expect(messages).toContainText(fixture.assetName,{ignoreCase:true});
  await shot(page,"04-agent.jpg",messages);

  const taskUrl=`${maintenance}/ui/tasks/${other}`;
  const initial=(await (await chief.context.request.get(taskUrl)).json()).task;
  const slot=(await (await chief.context.request.get(`${taskUrl}/assignment-context`)).json());
  expect(slot.status).toBe("ready");
  const previewResponse=await chief.context.request.post(`${maintenance}/tasks/${other}/assignment-preview`,{
    headers:chief.headers,data:{expected_revision:slot.expectedRevision,start_local:slot.defaultStartLocal,end_local:slot.defaultEndLocal},
  });
  expect(previewResponse.ok()).toBe(true);
  const preview=await previewResponse.json();
  expect(preview.status).toBe("ok");
  const thread=await chief.context.request.post(`${assistant}/conversations`,{
    headers:chief.headers,data:{agent:"assistant",title:"Назначение бригады"},
  });
  expect(thread.status()).toBe(201);
  const {conversation_id}=await thread.json();
  expect(conversation_id).not.toBe(chat);
  const response=await chief.context.request.post(`${assistant}/mcp`,{
    headers:{...chief.headers,Accept:"application/json, text/event-stream","MCP-Protocol-Version":"2025-06-18"},
    data:{jsonrpc:"2.0",id:1,method:"tools/call",params:{name:"task_assign",arguments:{
      conversation_id,path:{task_id:other},body:{...preview.command,reason:"Плановый осмотр вентиляционной установки"},
    }}},
  });
  expect(response.ok()).toBe(true);
  const proposed=(await response.json()).result;
  expect(proposed.isError).toBe(false);
  expect(JSON.parse(proposed.content[0].text).status).toBe("proposed");
  await page.goto(`/assistant?chat=${conversation_id}`);
  const card=page.getByRole("region",{name:"Предложение: Назначить бригаду и время"});
  const confirm=card.getByRole("button",{name:"Подтвердить и выполнить",exact:true});
  await expect(confirm).toBeDisabled();
  await confirm.scrollIntoViewIfNeeded();
  await shot(page,"05-podtverzhdenie.jpg",confirm);
  const final=(await (await chief.context.request.get(taskUrl)).json()).task;
  expect(final.revision).toBe(initial.revision);
  expect(final.assignees).toEqual(initial.assignees);
  await writeFile(path.join(output,"manifest.json"),JSON.stringify({
    data:"synthetic", build:"production", browser:"Chrome via Playwright", viewport:size,
    checks:["assignment","checklist and two photos","manual acceptance","live v4 / Ollama read","MCP proposal; unchanged order"],images,
  },null,2)+"\n");
  await chief.context.close();
  await executor.context.close();
});
