export function BrandMark({
  size = 44,
  className = "",
}: {
  size?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      aria-hidden="true"
      className={className}
    >
      <g
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M22 8h-8a6 6 0 0 0-6 6v8" />
        <path d="M42 8h8a6 6 0 0 1 6 6v8" />
        <path d="M22 56h-8a6 6 0 0 1-6-6v-8" />
        <path d="M42 56h8a6 6 0 0 0 6-6v-8" />
        <path d="m25 43 17-17" />
        <path d="m23 45 2-2" strokeWidth="5" />
        <path d="M40 26h4v4" />
        <path d="M39 47 26 34" />
        <path d="M29 23c-3.3 0-6 2.7-6 6 0 1.7.7 3.2 1.8 4.3l4.2-4.2 2.7 2.7-4.2 4.2A6 6 0 0 0 35 29c0-3.3-2.7-6-6-6Z" />
      </g>
    </svg>
  );
}

export function BrandLockup({
  subtitle = "ТО / ППР",
  size = "md",
}: {
  subtitle?: string;
  size?: "sm" | "md" | "lg";
}) {
  const markSize = size === "lg" ? 56 : size === "sm" ? 34 : 42;
  const titleSize =
    size === "lg" ? "text-2xl" : size === "sm" ? "text-sm" : "text-base";

  return (
    <span className="flex items-center gap-3">
      <BrandMark size={markSize} className="shrink-0 text-ink" />
      <span className="min-w-0">
        <span
          className={`block font-semibold tracking-[-0.03em] text-ink ${titleSize}`}
        >
          FixRate AI
        </span>
        <span className="mt-0.5 block text-[10px] font-semibold tracking-[0.18em] text-muted uppercase">
          {subtitle}
        </span>
      </span>
    </span>
  );
}
