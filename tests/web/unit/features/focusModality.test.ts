import { expect, it } from "vitest";
import { installFocusModality } from "@/shared/ui/focusModality";

it("uses Tab for focus indicators and clears them after pointer interaction or window blur", () => {
  const cleanup = installFocusModality();
  try {
    const mode = () => document.documentElement.dataset.focusMode;
    expect(mode()).toBe("pointer");
    document.dispatchEvent(new KeyboardEvent("keydown", {key:"Tab", bubbles:true}));
    expect(mode()).toBe("keyboard");
    window.dispatchEvent(new Event("blur"));
    expect(mode()).toBe("pointer");
    document.dispatchEvent(new KeyboardEvent("keydown", {key:"Tab", shiftKey:true, bubbles:true}));
    expect(mode()).toBe("keyboard");
    document.dispatchEvent(new Event("pointerdown", {bubbles:true}));
    expect(mode()).toBe("pointer");
    document.dispatchEvent(new KeyboardEvent("keydown", {key:"Tab", altKey:true, bubbles:true}));
    expect(mode()).toBe("pointer");
  } finally { cleanup(); }
});
