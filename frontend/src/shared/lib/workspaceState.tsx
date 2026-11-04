import { createContext, useContext, useEffect, useState, type Dispatch, type SetStateAction } from "react";

export const WorkspaceStateScope = createContext<string | null>(null);
export const workspaceKey = (scope: string, name: string) => `fixrate.workspace.v1:${scope}:${name}`;

export function readWorkspaceValue<T>(key: string, fallback: T, valid: (value: unknown) => value is T, session = false): T {
  try {
    const raw = (session ? window.sessionStorage : window.localStorage).getItem(key);
    const value: unknown = raw === null ? null : JSON.parse(raw);
    return valid(value) ? value : fallback;
  } catch { return fallback; }
}

export function writeWorkspaceValue(key: string, value: unknown, session = false) {
  try { (session ? window.sessionStorage : window.localStorage).setItem(key, JSON.stringify(value)); } catch { /* Storage can be disabled or full. */ }
}

/** Persist UI preferences only; callers explicitly validate each stored value. */
export function useWorkspaceState<T>(name: string, initial: T | (() => T), valid: (value: unknown) => value is T): [T, Dispatch<SetStateAction<T>>] {
  const scope = useContext(WorkspaceStateScope);
  const key = scope ? workspaceKey(scope, name) : null;
  const load = () => {
    const fallback = typeof initial === "function" ? (initial as () => T)() : initial;
    return key ? readWorkspaceValue(key, fallback, valid) : fallback;
  };
  const [entry, setEntry] = useState(() => ({ key, value: load() }));
  let value = entry.value;
  if (entry.key !== key) {
    value = load();
    setEntry({ key, value });
  }
  useEffect(() => { if (key && entry.key === key) writeWorkspaceValue(key, entry.value); }, [key, entry]);
  const setValue: Dispatch<SetStateAction<T>> = update => setEntry(current => {
    const previous = current.key === key ? current.value : load();
    return { key, value: typeof update === "function" ? (update as (value: T) => T)(previous) : update };
  });
  return [value, setValue];
}

export const isBoolean = (value: unknown): value is boolean => typeof value === "boolean";
export const isShortString = (value: unknown): value is string => typeof value === "string" && value.length <= 320;
