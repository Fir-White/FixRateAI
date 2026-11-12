import { useRef } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useWorkspaceView } from "@/shared/lib/useWorkspaceView";
import { workspaceKey } from "@/shared/lib/workspaceState";

const key = workspaceKey("test", "view:/equipment");
function Content({ loading }: { loading: boolean }) {
  const root = useRef<HTMLDivElement>(null);
  useWorkspaceView(root, "test");
  return <div ref={root} data-testid="root">{loading ? <div data-workspace-loading /> : <><div data-testid="table" data-scroll-key="table" /><details><summary>Section</summary>Contents</details></>}</div>;
}
const page = (loading: boolean) => <MemoryRouter initialEntries={["/equipment"]}><Content loading={loading} /></MemoryRouter>;
const saved = { page: { x: 0, y: 450 }, scrolls: { table: { x: 160, y: 0 } }, details: { "0:Section": true } };
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("workspace view restoration", () => {
  it("waits for asynchronous content and restores table scroll and expanded sections", async () => {
    sessionStorage.setItem(key, JSON.stringify(saved));
    const scroll = vi.fn(); vi.stubGlobal("scrollTo", scroll);
    const view = render(page(true));
    expect(JSON.parse(sessionStorage.getItem(key)!)).toEqual(saved);
    view.rerender(page(false));
    await waitFor(() => expect(screen.getByTestId("table").scrollLeft).toBe(160));
    expect(view.container.querySelector("details")).toHaveAttribute("open");
    expect(scroll).toHaveBeenLastCalledWith({ left: 0, top: 450, behavior: "instant" });
  });
  it("does not jump back after the user starts scrolling during loading", async () => {
    sessionStorage.setItem(key, JSON.stringify(saved));
    const scroll = vi.fn(); vi.stubGlobal("scrollTo", scroll);
    const view = render(page(true)); scroll.mockClear();
    fireEvent.wheel(screen.getByTestId("root"), { deltaY: 100 });
    view.rerender(page(false));
    await waitFor(() => expect(screen.getByTestId("table")).toBeInTheDocument());
    expect(scroll).not.toHaveBeenCalled();
    expect(screen.getByTestId("table").scrollLeft).toBe(0);
  });
  it("flushes the current position on pagehide without waiting for the debounce", () => {
    vi.stubGlobal("scrollY", 210);
    const view = render(page(false));
    const table = screen.getByTestId("table"); table.scrollLeft = 140;
    fireEvent.scroll(table);
    fireEvent(window, new Event("pagehide"));
    expect(JSON.parse(sessionStorage.getItem(key)!)).toMatchObject({ page: { y: 210 }, scrolls: { table: { x: 140 } } });
    view.unmount();
  });
});
