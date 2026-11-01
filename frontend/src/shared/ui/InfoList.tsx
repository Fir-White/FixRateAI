import type { ReactNode } from "react";

export function InfoList({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <dl className={className}>{children}</dl>;
}

export function InfoItem({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: ReactNode;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="text-[10px] font-semibold tracking-[0.14em] text-muted uppercase">
        {label}
      </dt>
      <dd
        className={`mt-1.5 text-sm font-semibold text-ink ${mono ? "font-mono" : ""}`}
      >
        {value}
      </dd>
    </div>
  );
}
