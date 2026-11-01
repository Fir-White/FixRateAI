import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { Checkbox, FieldCaption, FormField, Input, Select, Textarea } from "./Form";

it.each([
  ["input", <Input id="field" />],
  ["select", <Select id="field"><option>Первый</option></Select>],
  ["textarea", <Textarea id="field" />],
])("preserves the %s label and switches the associated hint to an error", (_name, control) => {
  const view = render(<FormField label="Поле" htmlFor="field" hint="Подсказка">{control}</FormField>);
  const input = screen.getByLabelText("Поле");
  expect(input).toHaveAccessibleDescription("Подсказка");
  expect(input).not.toHaveAttribute("aria-invalid");
  const description = input.getAttribute("aria-describedby");

  view.rerender(<FormField label="Поле" htmlFor="field" error="Проверьте значение">{control}</FormField>);
  expect(screen.getByLabelText("Поле")).toBe(input);
  expect(input).toHaveAttribute("aria-describedby", description);
  expect(input).toHaveAttribute("aria-invalid", "true");
  expect(input).toHaveAccessibleDescription("Проверьте значение");
  expect(screen.getByRole("alert")).toHaveTextContent("Проверьте значение");

  view.rerender(<FormField label="Поле" htmlFor="field" hint="Подсказка">{control}</FormField>);
  expect(input).not.toHaveAttribute("aria-invalid");
  expect(screen.queryByRole("alert")).toBeNull();
});

it("keeps wrapping captions clickable and checkbox labels independently operable", async () => {
  const user = userEvent.setup();
  render(<>
    <label><FieldCaption>Расположение</FieldCaption><Input /></label>
    <Checkbox label="Включено" />
  </>);
  const input = screen.getByLabelText("Расположение");
  await user.click(screen.getByText("Расположение"));
  expect(input).toHaveFocus();
  await user.type(input, "Этаж 2");
  expect(input).toHaveValue("Этаж 2");
  await user.click(screen.getByText("Включено"));
  expect(screen.getByRole("checkbox", { name: "Включено" })).toBeChecked();
});
