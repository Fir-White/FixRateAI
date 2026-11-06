import { useId, useRef } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { IconButton } from "@/shared/ui/Button";
import { Icon } from "@/shared/ui/Icon";
import { useDialogFocus } from "@/shared/lib/useDialogFocus";
import { useScrollBoundary } from "@/shared/lib/useScrollBoundary";
import { useContentTheme } from "./ContentTheme";

export function Modal({
  open,
  title,
  description,
  onClose,
  children,
  footer,
  tone = "default",
  size = "default",
  instant = false,
  className = "",
}: {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  tone?: "default" | "danger";
  size?: "default" | "wide";
  instant?: boolean;
  className?: string;
}) {
  const titleId = useId();
  const contentTheme = useContentTheme();
  const descriptionId = useId();
  const dialogRef = useDialogFocus<HTMLDivElement>(open, onClose);
  const scrollRef = useRef<HTMLDivElement>(null);
  useScrollBoundary(scrollRef, open);

  if (!open) {
    return null;
  }

  return createPortal(
    <div
      ref={scrollRef}
      className={`${contentTheme ? "fr-content-v2" : ""} fixed inset-0 z-[80] flex items-end justify-center bg-black/75 p-0 ${instant ? "" : "backdrop-blur-sm"} sm:items-center sm:p-6`}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        style={instant ? { animation: "none" } : undefined}
        className={`fr-modal ${className} ${size === "wide" ? "fr-modal--wide" : ""} scroll-boundary max-h-[92dvh] w-full overflow-y-auto rounded-t-2xl border bg-surface shadow-2xl shadow-black/60 sm:max-w-lg sm:rounded-2xl ${
          tone === "danger" ? "border-rose-400/30" : "border-line-strong"
        }`}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div>
            <h2 id={titleId} className="text-base font-semibold text-ink">
              {title}
            </h2>
            {description ? (
              <p
                id={descriptionId}
                className="mt-1.5 text-sm leading-6 text-muted"
              >
                {description}
              </p>
            ) : null}
          </div>
          <IconButton label="Закрыть окно" variant="ghost" onClick={onClose}>
            <Icon name="close" size={18} />
          </IconButton>
        </div>
        <div className="px-5 py-5">{children}</div>
        {footer ? (
          <div className="flex flex-col-reverse gap-2 border-t border-line bg-white/[0.02] px-5 py-4 sm:flex-row sm:justify-end">
            {footer}
          </div>
        ) : null}
      </div>
    </div>,
    document.querySelector(".workspace-root") ?? document.body,
  );
}
