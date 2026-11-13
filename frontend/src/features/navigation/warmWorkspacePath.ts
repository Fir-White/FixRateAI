import { preloadPage } from "@/app/pageModules";
import { readQueries } from "@/shared/api/readQueries";
import type { ApiQueryCache } from "@/shared/lib/apiQueryCache";
import { todayAt } from "@/shared/lib/format";

/** Called only for links the current role can see; cache belongs to its site/session. */
export function warmWorkspacePath(cache: ApiQueryCache | null, path: string, timezone: string) {
  void preloadPage(path)?.catch(() => { /* Navigation exposes the load error. */ });
  if (!cache) return;
  const [year, month] = todayAt(timezone).split("-").map(Number);
  const query = path === "/equipment" ? readQueries.registry
    : path === "/tasks" || path === "/executor" ? readQueries.tasks
    : path === "/calendar" ? readQueries.calendarMonth(year, month)
    : path === "/quality" || path === "/engineer" ? readQueries.quality
    : path === "/comparisons" ? readQueries.comparisons
    : path === "/settings/equipment" ? readQueries.serviceIndex
    : path === "/settings/workforce" ? readQueries.workforce
    : path === "/reports" ? readQueries.overview : null;
  if (query) void cache.load<unknown>(query.key, () => query.load(cache)).catch(() => {});
}
