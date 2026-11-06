import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Input } from "@/shared/ui/Form";

beforeEach(()=>{vi.stubGlobal("URL",class extends URL {static createObjectURL=vi.fn(()=>"blob:photo");static revokeObjectURL=vi.fn();});});
afterEach(()=>{vi.unstubAllGlobals();});

it("keeps a real accessible file input, shows the selected original, and clears the consumer selection",async()=>{
  const changed=vi.fn();const user=userEvent.setup();
  const {unmount}=render(<Input type="file" aria-label="Фото дефекта" accept="image/png" onChange={event=>changed(event.target.files?.[0]??null)}/>);
  const file=new File(["bytes"],"defect.png",{type:"image/png"});
  await user.upload(screen.getByLabelText("Фото дефекта"),file);
  expect(changed).toHaveBeenLastCalledWith(file);
  expect(screen.getByText("defect.png")).toBeInTheDocument();
  expect(screen.getByAltText("Выбранное изображение")).toHaveAttribute("src","blob:photo");
  await user.click(screen.getByRole("button",{name:"Убрать выбранный файл"}));
  expect(changed).toHaveBeenLastCalledWith(null);
  expect(screen.queryByText("defect.png")).not.toBeInTheDocument();
  unmount();expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:photo");
});

it("shows an error for an unsupported file and preserves disabled fieldset behavior",()=>{
  const {rerender}=render(<Input type="file" aria-label="Скан" accept="image/png"/>);
  fireEvent.change(screen.getByLabelText("Скан"),{target:{files:[new File(["text"],"notes.txt",{type:"text/plain"})]}});
  expect(screen.getByRole("alert")).toHaveTextContent("не подходит");
  rerender(<fieldset disabled><Input type="file" aria-label="Скан" accept="image/png"/></fieldset>);
  expect(screen.getByLabelText("Скан")).toBeDisabled();
});
