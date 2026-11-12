export const AUTH_ENTRY_STATE = { fixrateAuthEntry: true } as const;

export function isAuthEntryNavigation(state: unknown, navigationType: string): boolean {
  return navigationType !== "POP" && !!state && typeof state === "object" && "fixrateAuthEntry" in state && state.fixrateAuthEntry === true;
}
