/** Native disabled fieldsets and inert subtrees cannot dispatch a completing click. */
export function isAuthGestureEnabled(element: Element | null): element is Element {
  return !!element && !element.matches(":disabled") && !element.closest("[inert]");
}
