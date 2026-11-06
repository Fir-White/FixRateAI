import { test, expect } from "@playwright/test";

test("executor reads real shifts, changes weeks, and uses the shared calendar without native pickers", async ({page}) => {
  test.skip(!process.env.FIXRATE_BASE_URL,"Use an isolated QA API");
  test.setTimeout(90000);
  const errors: string[]=[];page.on("pageerror",error=>errors.push(error.message));
  await page.goto("/login");
  await page.getByLabel("Email",{exact:true}).fill("fixrate-assignment-2@example.test");
  await page.getByLabel("Пароль",{exact:true}).fill(process.env.FIXRATE_TEST_PASSWORD!);
  await page.getByRole("button",{name:"Войти",exact:true}).click();
  await expect(page).not.toHaveURL(/\/login$/);
  const calendar=page.waitForResponse(reply=>reply.url().includes("/management/staff/")&&reply.url().includes("/calendar?"));
  await page.goto("/my-shifts");
  const response=await calendar;expect(response.status()).toBe(200);
  let data=await response.json();
  if (!data.intervals.length) {
    const upcoming=page.waitForResponse(reply=>reply.url().includes("/management/staff/")&&reply.url().includes("/calendar?"));
    await page.getByRole("button",{name:"????????? ??????",exact:true}).click();
    const reply=await upcoming;expect(reply.status()).toBe(200);data=await reply.json();
  }
  await expect(page.locator(".fr-shift-row")).toHaveCount(data.intervals.length);
  expect(data.intervals.length).toBeGreaterThan(0);
  await page.getByRole("button",{name:"Выбрать даты",exact:true}).click();
  const trigger=page.getByLabel("Календарь сотрудника: с",{exact:true});
  const start=await trigger.getAttribute("data-value");
  await trigger.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("grid")).toBeVisible();
  await page.keyboard.press("Escape");await expect(trigger).toBeFocused();
  expect(await page.locator('input[type="date"],input[type="month"],input[type="time"],input[type="datetime-local"]').count()).toBe(0);
  const next=page.waitForResponse(reply=>reply.url().includes("/management/staff/")&&reply.url().includes("/calendar?"));
  await page.getByRole("button",{name:"Следующий период смен",exact:true}).click();
  const nextResponse=await next;expect(nextResponse.status()).toBe(200);
  const nextStart=new URL(nextResponse.url()).searchParams.get("start");
  expect(Date.parse(nextStart!)-Date.parse(start!)).toBe(7*86400000);
  expect(errors).toEqual([]);
});
