import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Input } from "@/shared/ui/Form";
import { ContentTheme } from "@/shared/ui/ContentTheme";
import { calendarValueIssue } from "@/shared/ui/DateTimeField";
import { sectionErrors, revealField } from "@/features/settings/SectionForm";

it("uses the same custom calendar for date/month/time/datetime without native calendar controls", () => {
  const {container}=render(<ContentTheme>{["date","month","time","datetime-local"].map(type=><Input key={type} aria-label={type} type={type}/>)}</ContentTheme>);
  for(const type of ["date","month","time","datetime-local"])expect(screen.getByRole("button",{name:type})).toHaveAttribute("aria-haspopup","dialog");
  expect(container.querySelector('input[type="date"],input[type="month"],input[type="time"],input[type="datetime-local"]')).toBeNull();
});

it("emits the original date-only value and preserves native form data and validation", async () => {
  const changed=vi.fn();
  function Form(){const [value,setValue]=useState("");return <ContentTheme><form aria-label="Регламент"><Input name="valid_from" aria-label="Действует с" type="date" required min="2026-11-05" max="2026-11-08" value={value} onChange={event=>{changed(event.target.value);setValue(event.target.value);}}/></form></ContentTheme>;}
  render(<Form/>);const user=userEvent.setup();const form=screen.getByRole("form") as HTMLFormElement;
  expect(form.checkValidity()).toBe(false);
  await user.click(screen.getByRole("button",{name:"Действует с"}));
  fireEvent.change(screen.getByLabelText("Дата",{exact:true}),{target:{value:"04112026"}});
  expect(screen.getByRole("button",{name:"Применить"})).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Дата",{exact:true}),{target:{value:"05112026"}});
  await user.click(screen.getByRole("button",{name:"Применить"}));
  expect(changed).toHaveBeenCalledExactlyOnceWith("2026-11-05");
  expect(new FormData(form).get("valid_from")).toBe("2026-11-05");
  expect(form.checkValidity()).toBe(true);
});

it("retains seconds and local time without converting through UTC", async () => {
  const changed=vi.fn();render(<ContentTheme><Input aria-label="Смена" type="time" value="22:15:30" onChange={event=>changed(event.target.value)}/></ContentTheme>);
  fireEvent.click(screen.getByRole("button",{name:"Смена"}));
  expect(screen.getByLabelText("Секунды")).toHaveValue("30");
  fireEvent.change(screen.getByLabelText("Часы"),{target:{value:"23"}});
  fireEvent.click(screen.getByRole("button",{name:"Применить"}));
  expect(changed).toHaveBeenCalledExactlyOnceWith("23:15:30");
});

it("keeps disabled ancestry and makes invalid hidden-section calendar fields reachable", () => {
  const {container}=render(<ContentTheme><form><fieldset disabled><Input aria-label="Закрытая дата" type="date" required/></fieldset><details><summary>Период</summary><Input aria-label="Дата регламента" type="date" required/></details></form></ContentTheme>);
  expect(screen.getByRole("button",{name:"Закрытая дата"})).toBeDisabled();
  const errors=sectionErrors(container.querySelector("form")!);
  expect(errors).toHaveLength(1);expect(errors[0].label).toBe("Дата регламента");
  revealField(errors[0].field);
  expect(container.querySelector("details")).toHaveAttribute("open");
  expect(screen.getByRole("button",{name:"Дата регламента"})).toHaveFocus();
});

it("validates calendar impossibilities and mixed precision bounds without shifting the day", () => {
  expect(calendarValueIssue("date","2026-02-29")).not.toBe("");
  expect(calendarValueIssue("date","2024-02-29")).toBe("");
  expect(calendarValueIssue("datetime-local","2026-11-05T00:00","2026-11-05T00:00:00")).toBe("");
  expect(calendarValueIssue("time","00:00","00:00:00","23:59:00")).toBe("");
});

it("keeps a wrapping label stable when the displayed date changes", async () => {
  render(<ContentTheme><label>Месяц экспорта<Input type="month" value="2026-11" onChange={()=>{}}/></label></ContentTheme>);
  expect(screen.getByRole("button",{name:"Месяц экспорта"})).toHaveTextContent("ноябрь 2026");
});
