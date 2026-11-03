import { Navigate, useLocation, useNavigationType } from "react-router-dom";
import { useSession } from "@/shared/session/SessionContext";
import { homePathForRole } from "@/shared/lib/roles";
import { AUTH_ENTRY_STATE, isAuthEntryNavigation } from "@/shared/motion/authEntry";

export function HomeRedirect() {
  const { profile } = useSession();
  const location = useLocation();
  const navigationType = useNavigationType();

  if (!profile) {
    return <Navigate to="/login" replace />;
  }

  return <Navigate to={homePathForRole(profile.role)} replace state={isAuthEntryNavigation(location.state, navigationType) ? AUTH_ENTRY_STATE : undefined} />;
}
