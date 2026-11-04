import type { ReactNode } from "react";
import { Card } from "@/shared/ui/Card";
import { Icon } from "@/shared/ui/Icon";

export function LoadingState({
  label = "Загрузка данных",
}: {
  label?: string;
}) {
  return (
    <Card className="p-6" role="status" aria-live="polite" aria-label={label} data-workspace-loading="true">
      <span className="sr-only">{label}</span>
      <div aria-hidden="true" className="space-y-4">
        <div className="flex items-center gap-3">
          <span className="skeleton h-9 w-9 rounded-xl" />
          <span className="skeleton h-3 w-40 rounded-full" />
        </div>
        <span className="skeleton block h-3 w-full rounded-full" />
        <span className="skeleton block h-3 w-4/5 rounded-full" />
        <span className="skeleton block h-3 w-2/3 rounded-full" />
      </div>
    </Card>
  );
}

export function ErrorState({
  title = "Не удалось загрузить данные",
  description,
  action,
}: {
  title?: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <Card className="border-rose-400/25 bg-rose-400/[0.045] p-8" role="alert">
      <div className="mx-auto max-w-md text-center">
        <span className="mx-auto flex h-10 w-10 items-center justify-center rounded-xl border border-rose-400/30 bg-rose-400/10 text-rose-200">
          <Icon name="alert" size={18} />
        </span>
        <p className="mt-4 text-sm font-semibold text-rose-100">{title}</p>
        <p className="mt-2 text-sm leading-6 text-rose-200/75">
          {description}
        </p>
        {action ? <div className="mt-5">{action}</div> : null}
      </div>
    </Card>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <Card className="border-dashed p-8">
      <div className="mx-auto max-w-md text-center">
        <span className="mx-auto flex h-10 w-10 items-center justify-center rounded-xl border border-line-strong bg-white/[0.03] text-muted">
          <Icon name="search" size={18} />
        </span>
        <p className="mt-4 text-sm font-semibold text-ink">{title}</p>
        <p className="mt-2 text-sm leading-6 text-muted">{description}</p>
        {action ? <div className="mt-5">{action}</div> : null}
      </div>
    </Card>
  );
}
