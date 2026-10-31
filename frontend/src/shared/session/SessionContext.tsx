import {
  createContext,
  useEffect,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Role, SessionProfile } from "@/shared/types/domain";

import { request, DEMO_MODE } from "@/shared/api/request";

const STORAGE_KEY = "fixrate.demo.role";

const DEMO_PROFILES: Record<Role, SessionProfile> = {
  admin: {
    userId: "u1000000-0000-4000-8000-000000000010",
    name: "Орлова М.С.",
    email: "qa_admin@example.test",
    role: "admin",
    siteName: "Демонстрационный объект",
    timezone: "Asia/Yekaterinburg",
  },
  dispatcher: {
    userId: "u1000000-0000-4000-8000-000000000011",
    name: "Волков А.Н.",
    email: "qa_dispatcher@example.test",
    role: "dispatcher",
    siteName: "Демонстрационный объект",
    timezone: "Asia/Yekaterinburg",
  },
  engineer: {
    userId: "u1000000-0000-4000-8000-000000000012",
    name: "Смирнова А.П.",
    email: "qa_engineer@example.test",
    role: "engineer",
    siteName: "Демонстрационный объект",
    timezone: "Asia/Yekaterinburg",
  },
  executor: {
    userId: "u1000000-0000-4000-8000-000000000001",
    name: "Иванов И.И.",
    email: "qa_executor_1@example.test",
    role: "executor",
    siteName: "Демонстрационный объект",
    timezone: "Asia/Yekaterinburg",
  },
};

interface SessionContextValue {
  profile: SessionProfile | null;
  login: (role: Role) => void;
  logout: () => void;
  switchRole: (role: Role) => void;
  loading: boolean;
  signIn: (email: string, password: string, siteId?: string) => Promise<SessionProfile>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

function isRole(value: string | null): value is Role {
  return (
    value === "admin" ||
    value === "dispatcher" ||
    value === "engineer" ||
    value === "executor"
  );
}

function readStoredRole(): Role | null {
  if (typeof window === "undefined") {
    return null;
  }
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return isRole(stored) ? stored : null;
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [role, setRole] = useState<Role | null>(() => DEMO_MODE ? readStoredRole() : null);
  const [profile, setProfile] = useState<SessionProfile | null>(null);
  const [loading, setLoading] = useState(!DEMO_MODE);
  useEffect(() => {
    if (DEMO_MODE) return;
    let active = true;
    request<{profile: SessionProfile}>("/api/v1/auth/session")
      .then(result => { if (active) setProfile(result.profile); })
      .catch(() => { if (active) setProfile(null); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  const value = useMemo<SessionContextValue>(() => {
    const login = (nextRole: Role) => {
      if (!DEMO_MODE) return;
      window.localStorage.setItem(STORAGE_KEY, nextRole);
      setRole(nextRole);
    };
    const logout = () => {
      if (DEMO_MODE) { window.localStorage.removeItem(STORAGE_KEY); setRole(null); }
      else { void request("/api/v1/auth/logout", {method: "POST"}).then(() => setProfile(null)); }
    };
    return {
      profile: DEMO_MODE ? (role ? DEMO_PROFILES[role] : null) : profile,
      loading, login, logout, switchRole: login,
      signIn: async (email, password, siteId) => {
        const result = await request<{profile: SessionProfile}>("/api/v1/auth/login", {
          method: "POST", body: JSON.stringify({email, password, ...(siteId ? {site_id: siteId} : {})}),
        });
        setProfile(result.profile);
        return result.profile;
      },
    };
  }, [role, profile, loading]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error("useSession must be used inside SessionProvider");
  }
  return context;
}
