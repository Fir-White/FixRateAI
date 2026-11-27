import { Outlet } from "react-router-dom";
import { useRef } from "react";
import { useSession } from "@/shared/session/SessionContext";
import { WorkspaceStateScope } from "@/shared/lib/workspaceState";
import { useWorkspaceView } from "@/shared/lib/useWorkspaceView";
import "./workspace.css";
import { ApiQueryProvider } from "@/shared/lib/ApiQueryProvider";
import { WorkspaceModuleWarmup } from "@/features/navigation/WorkspaceModuleWarmup";
import { DEMO_MODE } from "@/shared/api/request";

/** One persistent background for all protected routes, including executor pages. */
export function WorkspaceLayout() {
  const { profile } = useSession();
  const root = useRef<HTMLDivElement>(null);
  const scope = JSON.stringify([profile?.userId, profile?.siteId ?? profile?.siteName, profile?.role]);
  useWorkspaceView(root, scope);
  return <div ref={root} className="workspace-root"><ApiQueryProvider enabled={!DEMO_MODE} scope={JSON.stringify([profile?.userId, profile?.siteId, profile?.role])}><WorkspaceModuleWarmup/><WorkspaceStateScope key={scope} value={scope}><Outlet /></WorkspaceStateScope></ApiQueryProvider></div>;
}
