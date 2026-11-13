import { useEffect, useRef } from "react";
import type { RefObject } from "react";

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), summary, [tabindex]:not([tabindex="-1"])';

const dialogStack: HTMLElement[] = [];
let bodyOverflowBeforeDialogs='';

function isAvailable(element:HTMLElement) {
  if(element.hasAttribute('disabled')||element.closest('[hidden],[inert],[aria-hidden="true"]'))return false;
  let parent=element.parentElement;
  while(parent){
    if(parent instanceof HTMLDetailsElement&&!parent.open&&!parent.querySelector(':scope > summary')?.contains(element))return false;
    parent=parent.parentElement;
  }
  return true;
}

export function useDialogFocus<T extends HTMLElement>(
  open: boolean,
  onClose: () => void,
): RefObject<T | null> {
  const containerRef = useRef<T>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) {
      return;
    }

    const previousFocus = document.activeElement as HTMLElement | null;
    if(dialogStack.length===0)bodyOverflowBeforeDialogs=document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const container = containerRef.current;
    if(container)dialogStack.push(container);
    const items = () =>
      Array.from(
        container?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR) ?? [],
      ).filter(isAvailable);

    (container?.querySelector<HTMLElement>("[data-dialog-autofocus]") ?? items()[0])?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if(container&&dialogStack.at(-1)!==container)return;
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }

      if (event.key !== "Tab" || !container) {
        return;
      }

      const focusable = items();
      if (!focusable.length) {
        event.preventDefault();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      if(container){const index=dialogStack.lastIndexOf(container);if(index>=0)dialogStack.splice(index,1);}
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = dialogStack.length?'hidden':bodyOverflowBeforeDialogs;
      previousFocus?.focus();
    };
  }, [open]);

  return containerRef;
}
