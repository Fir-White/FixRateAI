import {
  createContext,
  useEffect,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { Role, SessionProfile } from "@/shared/types/domain";

import { request, DEMO_MODE, ApiError } from "@/shared/api/request";
import { invalidateApiQueries } from "@/shared/lib/apiQueryCache";
import { clearAiKey } from "@/shared/lib/aiCredentials";

const STORAGE_KEY = "fixrate.demo.role";
const SESSION_EVENT_KEY = "fixrate.session.changed.v1";

function notifyOtherTabs() {
  try { window.localStorage.setItem(SESSION_EVENT_KEY, `${Date.now()}:${Math.random()}`); } catch { /* The next focus check still synchronizes the session. */ }
}

function sameSession(a: SessionProfile | null, b: SessionProfile | null) {
  return a?.userId === b?.userId && a?.role === b?.role && a?.siteId === b?.siteId;
}

const DEMO_PROFILES: Record<Role, SessionProfile> = {
  director:{userId:"demo-director",name:"Руководитель",email:"director@example.test",role:"director",siteName:"Демонстрационный объект",timezone:"Asia/Yekaterinburg"},
  chief_engineer:{userId:"demo-chief",name:"Главный инженер",email:"chief@example.test",role:"chief_engineer",siteName:"Демонстрационный объект",timezone:"Asia/Yekaterinburg"},
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
  logout: () => Promise<void>;
  switchRole: (role: Role) => void;
  loading: boolean;
  updateEmail: (email: string, currentPassword: string) => Promise<void>;
  signIn: (email: string, password: string, siteId?: string) => Promise<SessionProfile>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

function isRole(value: string | null): value is Role {
  return (
    value === "director" || value === "chief_engineer" || value === "admin" ||
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
  const profileRef = useRef<SessionProfile | null>(profile);
  const authVersion = useRef(0);
  profileRef.current = profile;
  useEffect(() => {
    if (DEMO_MODE) return;
    let active = true;
    const synchronize = async (initial = false) => {
      const version = ++authVersion.current;
      try {
        const result = await request<{profile: SessionProfile}>("/api/v1/auth/session", {cache: "no-store"});
        if (!active || version !== authVersion.current) return;
        if (!initial && !sameSession(profileRef.current, result.profile)) {
          clearAiKey();
          invalidateApiQueries();
          window.location.replace("/");
          return;
        }
        profileRef.current = result.profile;
        setProfile(result.profile);
      } catch (error) {
        if (!active || version !== authVersion.current) return;
        if (initial) { if (error instanceof ApiError && error.status === 401) clearAiKey(); profileRef.current = null; setProfile(null); }
        else if (error instanceof ApiError && error.status === 401 && profileRef.current) {
          clearAiKey();
          profileRef.current = null;
          setProfile(null);
          window.location.replace("/login");
        }
      } finally {
        if (active && version === authVersion.current) setLoading(false);
      }
    };
    const storage = (event: StorageEvent) => { if (event.key === SESSION_EVENT_KEY) void synchronize(); };
    const focus = () => { if (!document.hidden) void synchronize(); };
    const visibility = () => { if (!document.hidden) void synchronize(); };
    void synchronize(true);
    window.addEventListener("storage", storage);
    window.addEventListener("focus", focus);
    document.addEventListener("visibilitychange", visibility);
    return () => { active = false; authVersion.current++; window.removeEventListener("storage", storage); window.removeEventListener("focus", focus); document.removeEventListener("visibilitychange", visibility); };
  }, []);
  const value = useMemo<SessionContextValue>(() => {
    const login = (nextRole: Role) => {
      if (!DEMO_MODE) return;
      if (nextRole !== role) clearAiKey();
      window.localStorage.setItem(STORAGE_KEY, nextRole);
      setRole(nextRole);
    };
    const logout = async () => {
      if (DEMO_MODE) { clearAiKey(); window.localStorage.removeItem(STORAGE_KEY); setRole(null); }
      else { await request("/api/v1/auth/logout", {method: "POST"}); clearAiKey(); authVersion.current++; profileRef.current = null; setProfile(null); notifyOtherTabs(); }
    };
    return {
      profile: DEMO_MODE ? (role ? DEMO_PROFILES[role] : null) : profile,
      loading, login, logout, switchRole: login,
      updateEmail: async (email: string, currentPassword: string) => {
        if (DEMO_MODE) throw new Error("Изменение профиля недоступно в этом режиме");
        const updated = await request<SessionProfile>("/api/v1/maintenance/users/me/email", {method: "PATCH", body: JSON.stringify({email, current_password: currentPassword})});
        profileRef.current = updated; setProfile(updated); notifyOtherTabs();
      },
      signIn: async (email, password, siteId) => {
        const result = await request<{profile: SessionProfile}>("/api/v1/auth/login", {
          method: "POST", body: JSON.stringify({email, password, ...(siteId ? {site_id: siteId} : {})}),
        });
        clearAiKey(); authVersion.current++; profileRef.current = result.profile; setProfile(result.profile); notifyOtherTabs();
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
