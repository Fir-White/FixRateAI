import type { Locator, Page } from "@playwright/test";

/** Operate the real calendar dialog; never write directly to its validation proxy. */
export async function pickCalendar(page: Page, control: Locator, value: string) {
  await control.click();
  const dialog = page.getByRole("dialog");
  const [date, time] = value.split("T");
  await dialog.getByLabel("Дата", {exact:true}).fill(date.slice(8)+date.slice(5,7)+date.slice(0,4));
  if(time){await dialog.getByLabel("Часы",{exact:true}).fill(time.slice(0,2));await dialog.getByLabel("Минуты",{exact:true}).fill(time.slice(3,5));}
  await dialog.getByRole("button",{name:"Применить",exact:true}).click();
}
