import { Outlet } from "react-router-dom";
import { useRef } from "react";
import { useSession } from "@/shared/session/SessionContext";
import { WorkspaceStateScope } from "@/shared/lib/workspaceState";
import { useWorkspaceView } from "@/shared/lib/useWorkspaceView";
import { WorkspaceAuroraBackground } from "./WorkspaceAuroraBackground";
import "./workspace.css";

/** One persistent background for all protected routes, including executor pages. */
export function WorkspaceLayout() {
  const { profile } = useSession();
  const root = useRef<HTMLDivElement>(null);
  const scope = JSON.stringify([profile?.userId, profile?.siteName, profile?.role]);
  useWorkspaceView(root, scope);
  return <div ref={root} className="workspace-root"><WorkspaceAuroraBackground /><WorkspaceStateScope key={scope} value={scope}><Outlet /></WorkspaceStateScope></div>;
}
