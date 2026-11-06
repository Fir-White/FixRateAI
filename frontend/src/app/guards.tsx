import { Navigate, Outlet } from "react-router-dom";
import type { ReactNode } from "react";
import { useSession } from "@/shared/session/SessionContext";
import { AccessDeniedPage } from "@/pages/AccessDeniedPage";
import type { Role } from "@/shared/types/domain";

export function RequireSession() {
  const { profile, loading } = useSession();

  if (loading) return <p role="status">Загрузка сессии…</p>;

  if (!profile) {
    return <Navigate to="/login" replace />;
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
