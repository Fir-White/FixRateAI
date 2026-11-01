import { fireEvent, render } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { useMobileAuthViewport } from "./useMobileAuthViewport";

function Harness({ navigation = "POP" }: { navigation?: "POP" | "PUSH" | "REPLACE" }) {
  useMobileAuthViewport(navigation);
  return <input aria-label="Field" />;
}

it("only resets a fresh mobile auth document, restores policy and leaves later SPA, viewport and history interaction alone", () => {
  const descriptor = Object.getOwnPropertyDescriptor(performance, "getEntriesByType");
  const previousURL = window.location.href, previousPolicy = history.scrollRestoration;
  let mobile = false, type = "reload";
  window.history.replaceState(null, "", "/login");
  Object.defineProperty(performance, "getEntriesByType", { configurable: true, value: () => [{ name: window.location.href, type }] });
  vi.stubGlobal("matchMedia", () => ({ matches: mobile }));
  const scroll = vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  history.scrollRestoration = "auto";
  try {
    let view = render(<Harness />);view.unmount();
    expect(scroll).not.toHaveBeenCalled();
    mobile = true;type = "back_forward";
    view = render(<Harness />);view.unmount();
    expect(scroll).not.toHaveBeenCalled();
    type = "reload";
    view = render(<Harness navigation="PUSH" />);view.unmount();
    expect(scroll).not.toHaveBeenCalled();
    view = render(<Harness />);
    expect(scroll).toHaveBeenCalledTimes(1);expect(history.scrollRestoration).toBe("manual");
    view.rerender(<Harness navigation="PUSH" />);
    fireEvent(window, new Event("resize"));fireEvent.focus(view.getByLabelText("Field"));fireEvent.touchStart(view.getByLabelText("Field"));
    expect(scroll).toHaveBeenCalledTimes(1);expect(history.scrollRestoration).toBe("manual");
    fireEvent(window, new Event("pagehide"));expect(history.scrollRestoration).toBe("auto");
    view.unmount();expect(history.scrollRestoration).toBe("auto");
    view = render(<Harness />);view.unmount();
    expect(scroll).toHaveBeenCalledTimes(1);
  } finally {
    if (descriptor) Object.defineProperty(performance, "getEntriesByType", descriptor);
    else Reflect.deleteProperty(performance, "getEntriesByType");
    history.scrollRestoration = previousPolicy;window.history.replaceState(null, "", previousURL);
    vi.restoreAllMocks();vi.unstubAllGlobals();
  }
});
