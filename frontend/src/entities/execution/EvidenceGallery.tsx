import type { EvidencePhoto } from "@/shared/types/domain";
import { formatDateTime } from "@/shared/lib/format";
import { Badge } from "@/shared/ui/Badge";
import { Card } from "@/shared/ui/Card";
import { Icon } from "@/shared/ui/Icon";

const PHASE_LABELS = {
  before: "До",
  after: "После",
} as const;

export function EvidenceGallery({
  photos,
  emptyText = "Фотографии к этой попытке отсутствуют",
}: {
  photos: EvidencePhoto[];
  emptyText?: string;
}) {
  if (!photos.length) {
    return (
      <div className="rounded-xl border border-dashed border-line-strong p-6 text-center text-sm text-muted">
        {emptyText}
      </div>
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {photos.map((photo) => (
        <Card key={photo.id} className="overflow-hidden">
          <div className="flex h-32 items-center justify-center photo-placeholder text-muted">
            <Icon name="camera" size={30} />
          </div>
          <div className="p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={photo.phase === "after" ? "success" : "info"}>
                {PHASE_LABELS[photo.phase]}
              </Badge>
              {photo.status === "rejected" ? (
                <Badge tone="danger">Отклонено</Badge>
              ) : null}
            </div>
            <p className="mt-2 text-sm font-semibold text-ink">
              {photo.label}
            </p>
            <p className="mt-1 font-mono text-[11px] text-muted">
              {photo.viewKey}
            </p>
            <p className="mt-1 text-xs text-muted">
              {formatDateTime(photo.capturedAt)}
            </p>
          </div>
        </Card>
      ))}
    </div>
  );
}
