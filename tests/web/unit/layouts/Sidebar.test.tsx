import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Sidebar } from "@/layouts/Sidebar";
import { NAVIGATION_ITEMS } from "@/layouts/navigation";

const items = NAVIGATION_ITEMS.filter(item => item.roles.includes("dispatcher"));
const timezone = "UTC";

function RouteProbe() {
  const location = useLocation();
  return <output data-testid="route">{JSON.stringify(location)}</output>;
}

describe("mobile workspace navigation", () => {
  it("returns from a detail page and preserves an active section's search and hash", () => {
    const onClose = vi.fn();
    const menu = <Sidebar items={items} open onClose={onClose} timezone={timezone}/>;
    const view = render(<MemoryRouter initialEntries={["/tasks/task-id"]}>{menu}<RouteProbe/></MemoryRouter>);
    fireEvent.click(screen.getByRole("link",{name:"Задания"}));
    expect(JSON.parse(screen.getByTestId("route").textContent!).pathname).toBe("/tasks");
    view.unmount();
    render(<MemoryRouter initialEntries={["/tasks/?view=attention#saved"]}>{menu}<RouteProbe/></MemoryRouter>);
    const initial = screen.getByTestId("route").textContent;
    fireEvent.click(screen.getByRole("link",{name:"Задания"}));
    expect(screen.getByTestId("route").textContent).toBe(initial);
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("preserves modified clicks without closing the navigation", () => {
    const onClose = vi.fn();
    render(<MemoryRouter initialEntries={["/tasks"]}><Sidebar items={items} open onClose={onClose} timezone={timezone}/></MemoryRouter>);
    let prevented: boolean | undefined;
    document.addEventListener("click", event => {prevented=event.defaultPrevented;event.preventDefault();},{once:true});
    fireEvent.click(screen.getByRole("link",{name:"Задания"}),{ctrlKey:true});
    expect(prevented).toBe(false);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("retains one dialog, preserves the active link and restores native scrolling", () => {
    const onClose = vi.fn();
    const menu = (open:boolean)=><MemoryRouter initialEntries={["/tasks"]}><Sidebar items={items} open={open} onClose={onClose} timezone={timezone}/></MemoryRouter>;
    const view = render(menu(false));
    const aside = view.container.querySelector("aside")!;
    expect(aside).toHaveAttribute("inert");
    view.rerender(menu(true));
    const dialog = screen.getByRole("dialog",{name:"Мобильная навигация"});
    expect(dialog).toBe(aside);
    expect(document.body.style.overflow).toBe("hidden");
    const navigation = within(dialog).getByRole("navigation");
    expect(within(navigation).getAllByRole("link")).toHaveLength(items.length);
    expect(within(navigation).getByRole("link",{name:"Задания"})).toHaveAttribute("aria-current","page");
    fireEvent.keyDown(document,{key:"Escape"});
    expect(onClose).toHaveBeenCalledOnce();
    view.rerender(menu(false));
    expect(document.body.style.overflow).toBe("");
    expect(view.container.querySelector("aside")).toBe(aside);
  });
});
