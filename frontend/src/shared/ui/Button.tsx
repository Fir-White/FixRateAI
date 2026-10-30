import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md";

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary:
    "border-transparent bg-emerald-700 text-white shadow-sm hover:bg-emerald-800 focus-visible:outline-emerald-700",
  secondary:
    "border-slate-300 bg-white text-slate-800 shadow-sm hover:bg-slate-50 focus-visible:outline-slate-500",
  ghost:
    "border-transparent bg-transparent text-slate-700 hover:bg-slate-100 focus-visible:outline-slate-500",
  danger:
    "border-transparent bg-rose-700 text-white shadow-sm hover:bg-rose-800 focus-visible:outline-rose-700",
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: "h-9 px-3 text-sm",
  md: "h-11 px-5 text-sm",
};

export function buttonClassName(
  variant: ButtonVariant = "primary",
  size: ButtonSize = "md",
  className = "",
): string {
  return `inline-flex items-center justify-center gap-2 rounded-xl border font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`;
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
