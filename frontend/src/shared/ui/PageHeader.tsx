import type { ReactNode } from "react";

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="ops-page-header">
      <div className="min-w-0 max-w-3xl">
        <h1 className="fr-page-title">
          {title}
        </h1>
        {description ? (
          <p className="fr-page-description">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex flex-wrap items-center gap-2">{actions}</div>
      ) : null}
    </header>
  );
}
