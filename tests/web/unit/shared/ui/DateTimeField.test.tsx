import { useState } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ContentTheme } from "@/shared/ui/ContentTheme";
import { DateTimeField } from "@/shared/ui/DateTimeField";

function setup(initial = "2026-11-05T23:55", disabled = false) {
  const changed = vi.fn();
  function Field() {
    const [value, setValue] = useState(initial);
    return <ContentTheme><DateTimeField label="Фактическое начало" value={value} disabled={disabled} onChange={next => { changed(next); setValue(next); }} /></ContentTheme>;
  }
  render(<Field />);
  return { changed, user: userEvent.setup(), trigger: screen.getByRole("button", { name: "Фактическое начало" }) };
}

it("keeps the existing local value when a draft is cancelled and returns focus", async () => {
  const { user, trigger, changed } = setup();
  await user.click(trigger);
  await user.click(screen.getByRole("button", { name: /^6 ноября 2026/ }));
  fireEvent.change(screen.getByLabelText("Часы"), { target: { value: "10" } });
  await user.click(screen.getByRole("button", { name: "Отмена" }));
  expect(changed).not.toHaveBeenCalled();
  expect(trigger).toHaveTextContent("5 ноября 2026");
  expect(trigger).toHaveTextContent("23:55");
  expect(trigger).toHaveFocus();
});

it("applies exactly the chosen local day and midnight time without UTC conversion", async () => {
  const { user, trigger, changed } = setup("2026-02-28T23:55");
  await user.click(trigger);
  await user.click(screen.getByRole("button", { name: "Следующий месяц" }));
  expect(screen.getByRole("button", { name: /^1 марта 2026/ })).toHaveAttribute("tabindex", "0");
  await user.click(screen.getByRole("button", { name: /^1 марта 2026/ }));
  fireEvent.change(screen.getByLabelText("Часы"), { target: { value: "0" } });
  fireEvent.change(screen.getByLabelText("Минуты"), { target: { value: "5" } });
  expect(changed).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Применить" }));
  expect(changed).toHaveBeenCalledExactlyOnceWith("2026-03-01T00:05");
  expect(trigger).toHaveTextContent("00:05");
});

it("validates calendar dates, leap years and time before allowing apply", async () => {
  const { user, trigger, changed } = setup("2024-02-29T12:30");
  await user.click(trigger);
  const date = screen.getByLabelText("Дата", { exact: true });
  fireEvent.change(date, { target: { value: "29022025" } });
  expect(date).toHaveValue("29.02.2025");
  expect(screen.getByRole("button", { name: "Применить" })).toBeDisabled();
  fireEvent.change(date, { target: { value: "29022024" } });
  fireEvent.change(screen.getByLabelText("Часы"), { target: { value: "24" } });
  expect(screen.getByRole("button", { name: "Применить" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Часы"), { target: { value: "23" } });
  fireEvent.change(screen.getByLabelText("Минуты"), { target: { value: "60" } });
  expect(screen.getByRole("button", { name: "Применить" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Минуты"), { target: { value: "59" } });
  await user.click(screen.getByRole("button", { name: "Применить" }));
  expect(changed).toHaveBeenCalledExactlyOnceWith("2024-02-29T23:59");
});

it("requires an explicit time for a previously empty value", async () => {
  const { user, trigger, changed } = setup("");
  await user.click(trigger);
  expect(screen.getByLabelText("Часы")).toHaveValue("");
  expect(screen.getByLabelText("Минуты")).toHaveValue("");
  expect(screen.getByRole("button", { name: "Применить" })).toBeDisabled();
  await user.keyboard("{Escape}");
  expect(changed).not.toHaveBeenCalled();
});

it("moves through a month boundary with the keyboard without committing", async () => {
  const { user, trigger, changed } = setup("2026-11-30T12:30");
  await user.click(trigger);
  screen.getByRole("button", { name: /30 ноября 2026/ }).focus();
  await user.keyboard("{ArrowRight}");
  const next = await screen.findByRole("button", { name: /^1 декабря 2026/ });
  expect(screen.getByLabelText("Дата", { exact: true })).toHaveValue("01.12.2026");
  expect(next).toHaveAttribute("tabindex", "0");
  expect(changed).not.toHaveBeenCalled();
  await user.keyboard("{Escape}");
  expect(trigger).toHaveFocus();
});

it("can clear an existing value and respects disabled capability", async () => {
  const { user, trigger, changed } = setup();
  await user.click(trigger);
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Очистить" }));
  expect(changed).toHaveBeenCalledExactlyOnceWith("");
});

it("does not open a disabled field", async () => {
  const { user, trigger, changed } = setup("2026-11-05T23:55", true);
  await user.click(trigger);
  expect(trigger).toBeDisabled();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(changed).not.toHaveBeenCalled();
});
