/** Show non-text control focus indicators only after keyboard Tab navigation. */
export function installFocusModality() {
  const root = document.documentElement;
  const pointer = () => { root.dataset.focusMode = "pointer"; };
  const keydown = (event: KeyboardEvent) => {
    if (event.key !== "Tab") return;
    root.dataset.focusMode = event.altKey || event.ctrlKey || event.metaKey ? "pointer" : "keyboard";
  };
  pointer();
  document.addEventListener("pointerdown", pointer, true);
  document.addEventListener("keydown", keydown, true);
  window.addEventListener("blur", pointer);
  return () => {
    document.removeEventListener("pointerdown", pointer, true);
    document.removeEventListener("keydown", keydown, true);
    window.removeEventListener("blur", pointer);
    delete root.dataset.focusMode;
  };
}
