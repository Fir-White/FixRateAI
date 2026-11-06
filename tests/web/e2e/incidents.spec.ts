import { test, expect, type Page } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";

async function signIn(page: Page,email:string) {
  await page.goto("/login");await page.getByLabel("Email",{exact:true}).fill(email);
  await page.getByLabel("Пароль",{exact:true}).fill(process.env.FIXRATE_TEST_PASSWORD!);
  await page.getByRole("button",{name:"Войти",exact:true}).click();await expect(page).not.toHaveURL(/\/login$/);
}

test("equipment incident accepts a dropped original, persists it, and remains read-only for the director",async({browser})=>{
  test.skip(!process.env.FIXRATE_BASE_URL,"Use the disposable QA API");
  const context=await browser.newContext({baseURL:process.env.FIXRATE_BASE_URL});const page=await context.newPage();
  const errors:string[]=[];page.on("pageerror",error=>errors.push(error.message));
  await signIn(page,"fixrate-demo-1@example.test");
  const equipment=await(await page.request.get("/api/v1/maintenance/ui/equipment")).json();
  const id=equipment[0].id;await page.goto(`/equipment/${id}`);
  const panel=page.locator("details.fr-disclosure").filter({has:page.locator("summary").filter({hasText:"Дефекты и обращения по оборудованию"})});
  await panel.locator("summary").click();
  const description=`QA incident ${Date.now()}`;
  await page.getByLabel("Что обнаружено",{exact:false}).fill(description);
  const bytes=await fs.readFile(path.resolve(test.info().project.testDir,"../../../data/demo/demo-photo.png"));
  const transfer=await page.evaluateHandle(base64=>{const data=new DataTransfer();data.items.add(new File([Uint8Array.from(atob(base64),char=>char.charCodeAt(0))],"incident-test.png",{type:"image/png"}));return data;},bytes.toString("base64"));
  await panel.locator(".fr-file-target").dispatchEvent("drop",{dataTransfer:transfer});await transfer.dispose();
  await expect(panel.getByText("incident-test.png",{exact:true})).toBeVisible();
  const saved=page.waitForResponse(reply=>reply.url().endsWith("/incidents")&&reply.request().method()==="POST");
  await panel.getByRole("button",{name:"Создать обращение",exact:true}).click();
  const response=await saved;expect(response.status()).toBe(201);
  const record=await response.json();expect(record.equipmentId).toBe(id);expect(record.description).toBe(description);expect(record.attachmentUrl).toBeTruthy();
  const original=await page.request.get(record.attachmentUrl);expect(original.status()).toBe(200);
  expect(createHash("sha256").update(await original.body()).digest("hex")).toBe(createHash("sha256").update(bytes).digest("hex"));
  await expect(panel.getByText(description,{exact:true})).toBeVisible();
  await expect(page.getByLabel("Что обнаружено",{exact:false})).toHaveValue("");
  await page.reload();if(!await panel.evaluate(element=>(element as HTMLDetailsElement).open))await panel.locator("summary").click();await expect(panel.getByText(description,{exact:true})).toBeVisible();
  const directorContext=await browser.newContext({baseURL:process.env.FIXRATE_BASE_URL});const director=await directorContext.newPage();director.on("pageerror",error=>errors.push(error.message));
  await signIn(director,"fixrate-demo-executive@example.test");await director.goto(`/equipment/${id}`);
  const readOnly=director.locator("details.fr-disclosure").filter({has:director.locator("summary").filter({hasText:"Дефекты и обращения по оборудованию"})});await readOnly.locator("summary").click();
  await expect(readOnly.getByText(description,{exact:true})).toBeVisible();
  await expect(readOnly.getByRole("button",{name:"Создать обращение",exact:true})).toHaveCount(0);await expect(readOnly.locator("textarea,input[type=file]")).toHaveCount(0);
  expect(errors).toEqual([]);await context.close();await directorContext.close();
});
