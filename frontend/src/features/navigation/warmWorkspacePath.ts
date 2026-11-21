import { preloadPage } from "@/app/pageModules";
import { readQueries } from "@/shared/api/readQueries";
import type { ApiQueryCache } from "@/shared/lib/apiQueryCache";
import { todayAt } from "@/shared/lib/format";
import type { Role } from "@/shared/types/domain";

/** Called only for links the current role can see; cache belongs to its site/session. */
export function warmWorkspacePath(cache: ApiQueryCache | null, path: string, timezone: string, role?: Role) {
  void preloadPage(path)?.catch(() => { /* Navigation exposes the load error. */ });
  if (!cache) return;
  const calendarMonth = () => {
    const [year, month] = todayAt(timezone).split("-").map(Number);
    return readQueries.calendarMonth(year, month);
  };
  const query = path === "/equipment" ? (role === "executor" ? readQueries.equipment : readQueries.registry)
    : path === "/tasks" || path === "/executor" ? readQueries.tasks
    : path === "/calendar" ? calendarMonth()
    : path === "/quality" ? readQueries.quality
    : ["/engineer","/chief-engineer","/dispatcher","/director"].includes(path) ? readQueries.tasks
    : path === "/comparisons" ? readQueries.comparisons
    : path === "/settings/equipment" ? readQueries.serviceIndex
    : path === "/settings/workforce" ? readQueries.workforce
    : path === "/reports" ? readQueries.overview : null;
  if (query) void cache.load<unknown>(query.key, () => query.load(cache)).catch(() => {});
}
