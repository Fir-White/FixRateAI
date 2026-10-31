import { Navigate, Outlet, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { useSession } from "@/shared/session/SessionContext";
import { AccessDeniedPage } from "@/pages/AccessDeniedPage";
import type { Role } from "@/shared/types/domain";

export function RequireSession() {
  const { profile, loading } = useSession();
  const location = useLocation();

  if (loading) return <p role="status">Загрузка сессии…</p>;

  if (!profile) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <Outlet />;
}

export function RequireRole({
  roles,
  children,
}: {
  roles: Role[];
  children: ReactNode;
}) {
  const { profile, loading } = useSession();

  if (loading) return <p role="status">Загрузка сессии…</p>;

  if (!profile) {
    return <Navigate to="/login" replace />;
  }

  if (!roles.includes(profile.role)) {
    return <AccessDeniedPage allowedRoles={roles} />;
  }

  return children;
}
