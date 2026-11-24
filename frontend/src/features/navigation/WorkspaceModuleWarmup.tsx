import { useEffect } from "react";
import { DEMO_MODE } from "@/shared/api/request";
import { useSession } from "@/shared/session/SessionContext";
import { preloadPage } from "@/app/pageModules";
import { NAVIGATION_ITEMS } from "@/layouts/navigation";

/** Prepare authorized route code when idle. Link intent warms the actual data. */
export function WorkspaceModuleWarmup() {
  const { profile } = useSession();
  useEffect(() => {
    if (!profile || DEMO_MODE) return;
    let active = true;
    const paths = [...NAVIGATION_ITEMS.filter(item => item.roles.includes(profile.role)).map(item => item.to), "/profile"];
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
          if (active) moduleTimer = window.setTimeout(scheduleModule, 100);
        });
      };
      moduleIdle = window.requestIdleCallback?.(next);
      if (moduleIdle === undefined) moduleTimer = window.setTimeout(next, 100);
    };
    moduleTimer = window.setTimeout(scheduleModule, 300);
    return () => {
      active = false;
      if (moduleIdle !== undefined) window.cancelIdleCallback(moduleIdle);
      window.clearTimeout(moduleTimer);
    };
  }, [profile?.role]);
  return null;
}
