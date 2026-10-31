import { Navigate } from "react-router-dom";
import { useSession } from "@/shared/session/SessionContext";
import { homePathForRole } from "@/shared/lib/roles";

export function HomeRedirect() {
  const { profile } = useSession();

  if (!profile) {
    return <Navigate to="/login" replace />;
  }

  return <Navigate to={homePathForRole(profile.role)} replace />;
}
