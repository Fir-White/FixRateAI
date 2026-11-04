import type { ButtonHTMLAttributes, ReactNode } from "react";

export function FilterChip({
  active = false,
  children,
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  active?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      className={`ui-filter-chip rounded-lg border px-3 py-2 text-xs font-semibold whitespace-nowrap transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
        active
          ? "border-accent/20 bg-accent/10 text-accent"
          : "border-transparent text-ink-soft hover:border-line-strong hover:bg-white/[0.045] hover:text-ink"
      } ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
