import { useEffect } from "react";
import { DEMO_MODE } from "@/shared/api/request";
import { readQueries } from "@/shared/api/readQueries";
import { useApiQueryCache } from "@/shared/lib/ApiQueryProvider";
import { canOpenSection } from "@/shared/lib/roles";
import { useSession } from "@/shared/session/SessionContext";
import { todayAt } from "@/shared/lib/format";
import type { ApiQueryCache } from "@/shared/lib/apiQueryCache";
import { preloadPage } from "@/app/pageModules";
import { NAVIGATION_ITEMS } from "@/layouts/navigation";

/** Warm only small, authorized workspace lists; never task editors or files. */
export function WorkspaceDataWarmup() {
  const cache = useApiQueryCache();
  const { profile } = useSession();
  useEffect(() => {
    if (!cache || !profile || DEMO_MODE) return;
    const queries: { key: string; load: (cache?: ApiQueryCache | null) => Promise<unknown> }[] = [readQueries.equipment];
    if (profile.role !== "executor") queries.push(readQueries.registry);
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
    const paths = [...NAVIGATION_ITEMS.filter(item => item.roles.includes(profile.role)).map(item => item.to), "/profile"];
    let moduleTimer: number | undefined;
    let moduleIdle: number | undefined;
    const scheduleModule = () => {
      if (!active || !paths.length) return;
      const next = () => {
        if (!active) return;
        // Let the visible page finish first. Import one authorized module at a time.
        if (document.hidden || document.querySelector(".ops-main [data-workspace-loading]")) {
          moduleTimer = window.setTimeout(scheduleModule, 200); return;
        }
        const path = paths.shift()!;
        void Promise.resolve(preloadPage(path)).catch(() => {}).finally(() => {
          if (active) moduleTimer = window.setTimeout(scheduleModule, 100);
        });
      };
      moduleIdle = window.requestIdleCallback?.(next, { timeout: 2000 });
      if (moduleIdle === undefined) moduleTimer = window.setTimeout(next, 100);
    };
    moduleTimer = window.setTimeout(scheduleModule, 300);
    const run = async () => {
      while (active && queries.length) {
        const query = queries.shift()!;
        try { await cache.load(query.key, () => query.load(cache)); } catch { /* Opening the page presents its own retry/error state. */ }
        await new Promise(resolve => window.setTimeout(resolve, 100));
      }
    };
    // Start after the active page mounts, with at most two list loaders.
    const start = () => { void run(); void run(); };
    const idle = window.requestIdleCallback?.(start, { timeout: 1500 });
    const timer = idle === undefined ? window.setTimeout(start, 300) : undefined;
    return () => {
      active = false;
      if (idle !== undefined) window.cancelIdleCallback(idle);
      if (moduleIdle !== undefined) window.cancelIdleCallback(moduleIdle);
      window.clearTimeout(timer); window.clearTimeout(moduleTimer);
    };
  }, [cache, profile?.userId, profile?.siteId, profile?.role]);
  return null;
}
