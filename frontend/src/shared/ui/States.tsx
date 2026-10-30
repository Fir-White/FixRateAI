import type { ReactNode } from "react";
import { Card } from "@/shared/ui/Card";

export function LoadingState({ label = "Загрузка данных" }: { label?: string }) {
  return (
    <Card className="p-8">
      <div className="mx-auto flex max-w-sm flex-col items-center gap-3 text-center">
        <span className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-700" />
        <p className="text-sm font-medium text-slate-500">{label}</p>
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
    <Card className="border-rose-200 bg-rose-50/40 p-8">
      <div className="mx-auto max-w-md text-center">
        <p className="text-sm font-bold text-rose-800">{title}</p>
        <p className="mt-2 text-sm leading-6 text-rose-700">{description}</p>
        {action ? <div className="mt-4">{action}</div> : null}
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
        <p className="text-sm font-bold text-slate-800">{title}</p>
        <p className="mt-2 text-sm leading-6 text-slate-500">{description}</p>
        {action ? <div className="mt-4">{action}</div> : null}
      </div>
    </Card>
  );
}
