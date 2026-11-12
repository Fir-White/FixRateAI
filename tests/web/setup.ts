import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

if (typeof window !== "undefined") {
  const createStorage = () => {
    let store: Record<string, string> = {};
    return {
      getItem: (key: string) => store[key] ?? null,
      setItem: (key: string, value: string) => { store[key] = String(value); },
      removeItem: (key: string) => { delete store[key]; },
      clear: () => { store = {}; },
      key: (i: number) => Object.keys(store)[i] ?? null,
      get length() { return Object.keys(store).length; },
    };
  };
  try {
    if (!window.localStorage || typeof window.localStorage.setItem !== "function") {
      Object.defineProperty(window, "localStorage", { value: createStorage(), configurable: true, writable: true });
    }
    if (!window.sessionStorage || typeof window.sessionStorage.setItem !== "function") {
      Object.defineProperty(window, "sessionStorage", { value: createStorage(), configurable: true, writable: true });
    }
  } catch {
    // ignore
  }
}

afterEach(() => {
  cleanup();
  window.localStorage?.clear();
  window.sessionStorage?.clear();
});
