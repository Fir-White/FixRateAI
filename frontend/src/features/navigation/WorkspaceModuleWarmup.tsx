import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { DEMO_MODE } from "@/shared/api/request";
import { useSession } from "@/shared/session/SessionContext";
import { preloadPage } from "@/app/pageModules";
import { NAVIGATION_ITEMS } from "@/layouts/navigation";
import { useApiQueryCache } from "@/shared/lib/ApiQueryProvider";
import { homePathForRole } from "@/shared/lib/roles";
import { warmWorkspacePath } from "./warmWorkspacePath";

/** Prepare the active route and then warm other authorized modules when idle. */
export function WorkspaceModuleWarmup() {
  const { profile } = useSession();
  const cache = useApiQueryCache();
  const { pathname } = useLocation();
  const path = pathname.replace(/\/+$/, "");
  const role = profile?.role;
  const timezone = profile?.timezone;
  const prepared = useRef<typeof cache>(null);
  useEffect(() => {
    if (!cache || prepared.current === cache || !role || !timezone) return;
    prepared.current = cache;
    // Only the initial, role-checked route needs this. Links handle later intent.
    warmWorkspacePath(cache, path || homePathForRole(role), timezone, role);
  }, [cache, path, role, timezone]);
  useEffect(() => {
    if (!role || DEMO_MODE) return;
    const connection = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
    if (connection?.saveData || connection?.effectiveType?.endsWith("2g")) return;
    let active = true;
    const paths = [...NAVIGATION_ITEMS.filter(item => item.roles.includes(role)).map(item => item.to), "/profile"];
    let moduleTimer: number | undefined;
    let moduleIdle: number | undefined;
    const scheduleModule = () => {
      if (!active || !paths.length) return;
      const next = (deadline?: IdleDeadline) => {
        if (!active) return;
        // Let the visible page finish first. Import one authorized module at a time.
        if (document.hidden || document.querySelector(".ops-main [data-workspace-loading]") ||
            (deadline && deadline.timeRemaining() < 4)) {
          moduleTimer = window.setTimeout(scheduleModule, 200); return;
        }
        const path = paths.shift()!;
        void Promise.resolve(preloadPage(path)).catch(() => {}).finally(() => {
          if (active) moduleTimer = window.setTimeout(scheduleModule, 250);
        });
      };
      moduleIdle = window.requestIdleCallback?.(next);
      if (moduleIdle === undefined) moduleTimer = window.setTimeout(next, 100);
    };
    moduleTimer = window.setTimeout(scheduleModule, 1200);
    return () => {
      active = false;
      if (moduleIdle !== undefined) window.cancelIdleCallback(moduleIdle);
      window.clearTimeout(moduleTimer);
    };
  }, [role]);
  return null;
}
