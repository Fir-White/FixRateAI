import type { ButtonHTMLAttributes, ReactNode } from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary:
    "border-transparent bg-accent text-accent-ink hover:bg-accent-strong active:bg-accent",
  secondary:
    "border-line-strong bg-white/[0.035] text-ink hover:border-muted/60 hover:bg-white/[0.07]",
  ghost:
    "border-transparent bg-transparent text-ink-soft hover:bg-white/[0.06] hover:text-ink",
  danger:
    "border-rose-400/30 bg-rose-400/10 text-rose-200 hover:bg-rose-400/20",
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: "h-9 px-3 text-xs",
  md: "h-11 px-4 text-sm",
};

export function buttonClassName(
  variant: ButtonVariant = "primary",
  size: ButtonSize = "md",
  className = "",
): string {
  return `motion-button inline-flex items-center justify-center gap-2 rounded-lg border font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-40 ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`;
}

export function Button({
  children,
  variant = "primary",
  size = "md",
  className = "",
  type = "button",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
}) {
  return (
    <button
      type={type}
      className={buttonClassName(variant, size, className)}
      {...props}
    >
      {children}
    </button>
  );
}

export function IconButton({
  label,
  children,
  variant = "secondary",
  className = "",
  type = "button",
  ...props
}: Omit<ButtonHTMLAttributes<HTMLButtonElement>, "aria-label"> & {
  label: string;
  children: ReactNode;
  variant?: ButtonVariant;
}) {
  return (
    <button
      type={type}
      aria-label={label}
      title={label}
      className={buttonClassName(variant, "sm", `w-9 px-0 ${className}`)}
      {...props}
    >
      {children}
    </button>
  );
}
