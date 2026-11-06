import type { ChecklistItem, EvidencePhoto } from "@/shared/types/domain";
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

/** The report snapshot requires one same-view before/after pair per photoRequired item. */
export function photoRequirementProgress(checklist: ChecklistItem[], photos: EvidencePhoto[]) {
  const { pairs } = pairEvidence(photos);
  const items = checklist.filter(item => item.photoRequired).map(item => {
    const coverage = pairs.filter(pair => pair.checklistItemId === item.id)
      .reduce((best, pair) => Math.max(best, Number(pair.before.length > 0) + Number(pair.after.length > 0)), 0);
    return { item, coverage, complete: coverage === 2 };
  });
  return { items, minimum: items.length * 2, covered: items.reduce((sum, item) => sum + item.coverage, 0), ready: items.every(item => item.complete) };
}
