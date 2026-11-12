import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Sidebar } from "@/layouts/Sidebar";
import { NAVIGATION_ITEMS } from "@/layouts/navigation";

const items = NAVIGATION_ITEMS.filter(item => item.roles.includes("dispatcher"));
function RouteProbe() {
  const location = useLocation();
  return <output data-testid="route">{JSON.stringify(location)}</output>;
}

describe("single sidebar", () => {
  it("toggles the sidebar with the logo without changing the route", () => {
    const toggle = vi.fn();
    render(<MemoryRouter initialEntries={["/tasks/?view=attention#saved"]}><Sidebar items={items} expanded={false} mobile={false} open={false} onClose={vi.fn()} onToggle={toggle} /><RouteProbe /></MemoryRouter>);
    const initial = screen.getByTestId("route").textContent;
    fireEvent.click(screen.getByRole("button", {name:"Развернуть меню"}));
    expect(toggle).toHaveBeenCalledOnce();
    expect(screen.getByTestId("route").textContent).toBe(initial);
    expect(screen.queryByRole("link", {name:/FixRate AI/})).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", {name:"Задания"}));
    expect(screen.getByTestId("route").textContent).toBe(initial);
  });

  it("allows return from a detail page and closes mobile navigation on a repeated section click", () => {
    const close = vi.fn();
    render(<MemoryRouter initialEntries={["/tasks/task-id"]}><Sidebar items={items} expanded={false} mobile open onClose={close} onToggle={vi.fn()} /><RouteProbe /></MemoryRouter>);
    fireEvent.click(screen.getByRole("link", {name:"Задания"}));
    expect(JSON.parse(screen.getByTestId("route").textContent!).pathname).toBe("/tasks");
    const current = screen.getByTestId("route").textContent;
    fireEvent.click(screen.getByRole("link", {name:"Задания"}));
    expect(screen.getByTestId("route").textContent).toBe(current);
    expect(close).toHaveBeenCalledTimes(2);
  });

  it("preserves the browser's modified-click behavior on the current section", () => {
    render(<MemoryRouter initialEntries={["/tasks"]}><Sidebar items={items} expanded={false} mobile={false} open={false} onClose={vi.fn()} onToggle={vi.fn()} /></MemoryRouter>);
    let prevented: boolean | undefined;
    document.addEventListener("click", event => { prevented = event.defaultPrevented; event.preventDefault(); }, {once:true});
    fireEvent.click(screen.getByRole("link", {name:"Задания"}), {ctrlKey:true});
    expect(prevented).toBe(false);
  });

  it("retains one navigation and the same active link nodes while expanding", () => {
    const props = {items, expanded:false, mobile:false, open:false, onClose:vi.fn(), onToggle:vi.fn()};
    const view = render(<MemoryRouter initialEntries={["/tasks"]}><Sidebar {...props} /></MemoryRouter>);
    const sidebar = view.container.querySelector("aside");
    const links = within(screen.getByRole("navigation")).getAllByRole("link");
    expect(links).toHaveLength(items.length);
    expect(within(screen.getByRole("navigation")).getByRole("link", {name:"Задания"})).toHaveAttribute("aria-current", "page");
    view.rerender(<MemoryRouter initialEntries={["/tasks"]}><Sidebar {...props} expanded /></MemoryRouter>);
    expect(view.container.querySelector("aside")).toBe(sidebar);
    expect(screen.getAllByRole("navigation")).toHaveLength(1);
    within(screen.getByRole("navigation")).getAllByRole("link").forEach((link,index) => expect(link).toBe(links[index]));
    expect(within(screen.getByRole("navigation")).getByRole("link", {name:"Задания"})).toHaveAttribute("aria-current", "page");
  });

  it("uses the same sidebar as a mobile dialog, locks scrolling and closes on navigation", () => {
    const close = vi.fn();
    const props = {items, expanded:false, mobile:true, open:false, onClose:close, onToggle:vi.fn()};
    const view = render(<MemoryRouter><Sidebar {...props} /></MemoryRouter>);
    const sidebar = view.container.querySelector("aside")!;
    expect(sidebar).toHaveAttribute("inert");
    expect(sidebar).toHaveAttribute("aria-hidden", "true");
    view.rerender(<MemoryRouter><Sidebar {...props} open /></MemoryRouter>);
    expect(screen.getByRole("dialog", {name:"Мобильная навигация"})).toBe(sidebar);
    expect(document.body.style.overflow).toBe("hidden");
    expect(sidebar).not.toHaveAttribute("inert");
    fireEvent.click(within(sidebar).getByRole("link", {name:"Задания"}));
    expect(close).toHaveBeenCalledOnce();
    view.rerender(<MemoryRouter><Sidebar {...props} /></MemoryRouter>);
    expect(document.body.style.overflow).toBe("");
    expect(view.container.querySelectorAll("aside")).toHaveLength(1);
  });

  it("shows a collapsed tooltip on keyboard focus and dismisses it with Escape", () => {
    render(<MemoryRouter><Sidebar items={items} expanded={false} mobile={false} open={false} onClose={vi.fn()} onToggle={vi.fn()} /></MemoryRouter>);
    const link = screen.getByRole("link", {name:"Оборудование"});
    fireEvent.focus(link);
    expect(screen.getByRole("tooltip")).toHaveTextContent("Оборудование");
    expect(link).toHaveAttribute("aria-describedby", screen.getByRole("tooltip").id);
    fireEvent.keyDown(link, {key:"Escape"});
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("dismisses on window blur without reopening on restored focus, but allows fresh hover and keyboard navigation", () => {
    render(<MemoryRouter><Sidebar items={items} expanded={false} mobile={false} open={false} onClose={vi.fn()} onToggle={vi.fn()} /></MemoryRouter>);
    const link = screen.getByRole("link", {name:"Прогнозы"});
    fireEvent.mouseEnter(link);
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
    fireEvent.blur(window);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    fireEvent.keyDown(document, {key:"Tab", altKey:true});
    fireEvent.focus(window); fireEvent.focus(link);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    fireEvent.mouseEnter(link);
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
    fireEvent.focus(window);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    fireEvent.mouseEnter(link);
    fireEvent.pointerLeave(document.documentElement);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    fireEvent.keyDown(document, {key:"Tab"}); fireEvent.focus(link);
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
  });

  it("dismisses when the tab is hidden and does not restore a stale tooltip", () => {
    render(<MemoryRouter><Sidebar items={items} expanded={false} mobile={false} open={false} onClose={vi.fn()} onToggle={vi.fn()} /></MemoryRouter>);
    const link = screen.getByRole("link", {name:"Прогнозы"});
    fireEvent.focus(link);
    const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(true);
    try {
      fireEvent(document, new Event("visibilitychange"));
      expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
      hidden.mockReturnValue(false);
      fireEvent(document, new Event("visibilitychange")); fireEvent.focus(link);
      expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    } finally { hidden.mockRestore(); }
  });
});
