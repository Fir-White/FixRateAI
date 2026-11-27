import { useState } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ContentTheme } from "@/shared/ui/ContentTheme";
import { FormField, Select } from "@/shared/ui/Form";

it("opens a custom listbox popover instead of the native OS select menu on mousedown", () => {
  const changed = vi.fn();
  function Example() {
    const [val, setVal] = useState("to1");
    return (
      <ContentTheme>
        <FormField label="Вид ТО">
          <Select value={val} onChange={(e) => { changed(e.target.value); setVal(e.target.value); }}>
            <option value="to1">ТО1 · Ежемесячное</option>
            <option value="to2">ТО2 · Квартальное</option>
            <option value="to3" disabled>ТО3 · Годовое</option>
          </Select>
        </FormField>
      </ContentTheme>
    );
  }
  render(<Example />);
  const select = screen.getByRole("combobox", { name: "Вид ТО" });
  const downEvent = new MouseEvent("mousedown", { bubbles: true, cancelable: true, button: 0 });
  fireEvent(select, downEvent);
  expect(downEvent.defaultPrevented).toBe(true);
  const listbox = screen.getByRole("listbox");
  expect(listbox).toBeInTheDocument();
  expect(within(listbox).getByRole("option", { name: "ТО3 · Годовое" })).toBeDisabled();

  fireEvent.click(within(listbox).getByRole("option", { name: "ТО2 · Квартальное" }));
  expect(changed).toHaveBeenCalledExactlyOnceWith("to2");
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(select).toHaveValue("to2");
});

it("supports keyboard navigation and programmatic selectOptions", async () => {
  const user = userEvent.setup();
  const changed = vi.fn();
  function Example() {
    const [val, setVal] = useState("a");
    return (
      <ContentTheme>
        <Select aria-label="Статус" value={val} onChange={(e) => { changed(e.target.value); setVal(e.target.value); }}>
          <option value="a">Активно</option>
          <option value="b">В ремонте</option>
        </Select>
      </ContentTheme>
    );
  }
  render(<Example />);
  const select = screen.getByRole("combobox", { name: "Статус" });
  fireEvent.keyDown(select, { key: "Enter" });
  expect(screen.getByRole("listbox")).toBeInTheDocument();
  fireEvent.keyDown(select, { key: "ArrowDown" });
  fireEvent.keyDown(select, { key: "Enter" });
  expect(changed).toHaveBeenCalledWith("b");
  expect(screen.queryByRole("listbox")).toBeNull();

  await user.selectOptions(select, "a");
  expect(changed).toHaveBeenCalledWith("a");
});
