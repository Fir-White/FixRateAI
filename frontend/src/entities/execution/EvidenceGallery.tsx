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
      <div className="rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
        {emptyText}
      </div>
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {photos.map((photo) => (
        <Card key={photo.id} className="overflow-hidden">
          <div className="flex h-32 items-center justify-center bg-[linear-gradient(135deg,#e2e8f0_25%,#f1f5f9_25%,#f1f5f9_50%,#e2e8f0_50%,#e2e8f0_75%,#f1f5f9_75%)] bg-[length:20px_20px] text-slate-400">
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
            <p className="mt-2 text-sm font-semibold text-slate-900">
              {photo.label}
            </p>
            <p className="mt-1 font-mono text-[11px] text-slate-500">
              {photo.viewKey}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              {formatDateTime(photo.capturedAt)}
            </p>
          </div>
        </Card>
      ))}
    </div>
  );
}
