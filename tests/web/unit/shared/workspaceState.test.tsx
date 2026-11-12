import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { isBoolean, useWorkspaceState, WorkspaceStateScope, workspaceKey } from "@/shared/lib/workspaceState";

function Control() {
  const [expanded, setExpanded] = useWorkspaceState("sidebar.expanded", false, isBoolean);
  return <button onClick={() => setExpanded(value => !value)}>{expanded ? "expanded" : "collapsed"}</button>;
}
const viewFor = (scope: string) => <WorkspaceStateScope value={scope}><Control /></WorkspaceStateScope>;
afterEach(() => vi.restoreAllMocks());

describe("workspace preferences", () => {
  it("restores a preference across remounts", () => {
    const view = render(viewFor("a"));
    fireEvent.click(screen.getByRole("button"));
    expect(localStorage.getItem(workspaceKey("a", "sidebar.expanded"))).toBe("true");
    view.unmount();
    render(viewFor("a"));
    expect(screen.getByRole("button")).toHaveTextContent("expanded");
  });
  it("keeps user scopes independent without copying the previous user's value", () => {
    const view = render(viewFor("a"));
    fireEvent.click(screen.getByRole("button"));
    view.rerender(viewFor("b"));
    expect(screen.getByRole("button")).toHaveTextContent("collapsed");
    expect(localStorage.getItem(workspaceKey("b", "sidebar.expanded"))).toBe("false");
    view.rerender(viewFor("a"));
    expect(screen.getByRole("button")).toHaveTextContent("expanded");
  });
  it.each(['{"wrong":true}', 'invalid JSON'])("ignores invalid stored data: %s", value => {
    localStorage.setItem(workspaceKey("a", "sidebar.expanded"), value);
    render(viewFor("a"));
    expect(screen.getByRole("button")).toHaveTextContent("collapsed");
  });
  it("remains usable when browser storage is unavailable", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new DOMException("blocked", "SecurityError"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new DOMException("full", "QuotaExceededError"); });
    render(viewFor("a"));
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByRole("button")).toHaveTextContent("expanded");
  });
});
