import { useEffect } from "react";
import { DEMO_MODE } from "@/shared/api/request";
import { readQueries } from "@/shared/api/readQueries";
import { useApiQueryCache } from "@/shared/lib/ApiQueryProvider";
import { canOpenSection } from "@/shared/lib/roles";
import { useSession } from "@/shared/session/SessionContext";
import { todayAt } from "@/shared/lib/format";

/** Warm only small, authorized workspace lists; never task editors or files. */
export function WorkspaceDataWarmup() {
  const cache = useApiQueryCache();
  const { profile } = useSession();
  useEffect(() => {
    if (!cache || !profile || DEMO_MODE) return;
    const queries: { key: string; load: () => Promise<unknown> }[] = [readQueries.equipment];
    if (canOpenSection(profile.role, "tasks") || canOpenSection(profile.role, "executor")) queries.push(readQueries.tasks);
    if (canOpenSection(profile.role, "calendar")) {
      const [year, month] = todayAt(profile.timezone).split("-").map(Number);
      queries.push(readQueries.calendarMonth(year, month));
    }
    if (canOpenSection(profile.role, "quality")) queries.push(readQueries.quality);
    if (canOpenSection(profile.role, "comparisons")) queries.push(readQueries.comparisons);
    if (canOpenSection(profile.role, "service_settings")) queries.push(readQueries.serviceIndex);
    if (canOpenSection(profile.role, "workforce_settings")) queries.push(readQueries.workforce);
    if (canOpenSection(profile.role, "reports")) queries.push(readQueries.overview);
    let active = true;
    const run = async () => {
      while (active && queries.length) {
        const query = queries.shift()!;
        try { await cache.load(query.key, query.load); } catch { /* Opening the page presents its own retry/error state. */ }
      }
    };
    // Start after the active page mounts, with at most two list loaders.
    const timer = window.setTimeout(() => { void run(); void run(); }, 0);
    return () => { active = false; window.clearTimeout(timer); };
  }, [cache, profile?.userId, profile?.siteId, profile?.role]);
  return null;
}
