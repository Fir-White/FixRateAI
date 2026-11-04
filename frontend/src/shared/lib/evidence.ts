import type { EvidencePhoto } from "@/shared/types/domain";
export interface EvidencePair {
  key: string;
  checklistItemId: string;
  viewKey: string;
  before: EvidencePhoto[];
  after: EvidencePhoto[];
}
/** Pair only by a real checklist item AND camera view; preserve every attachment. */
export function pairEvidence(photos: EvidencePhoto[]): { pairs: EvidencePair[]; other: EvidencePhoto[] } {
  const grouped = new Map<string, EvidencePair>();
  const other: EvidencePhoto[] = [];
  for (const photo of photos) {
    if (photo.phase !== "before" && photo.phase !== "after") { other.push(photo); continue; }
    const key = JSON.stringify([photo.checklistItemId, photo.viewKey]);
    let pair = grouped.get(key);
    if (!pair) { pair = { key, checklistItemId: photo.checklistItemId, viewKey: photo.viewKey, before: [], after: [] }; grouped.set(key, pair); }
    pair[photo.phase].push(photo);
  }
  return { pairs: [...grouped.values()], other };
}
