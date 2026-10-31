import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Role, SessionProfile } from "@/shared/types/domain";

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
  const [role, setRole] = useState<Role | null>(readStoredRole);

  const value = useMemo<SessionContextValue>(() => {
    const login = (nextRole: Role) => {
      window.localStorage.setItem(STORAGE_KEY, nextRole);
      setRole(nextRole);
    };

    const logout = () => {
      window.localStorage.removeItem(STORAGE_KEY);
      setRole(null);
    };

    return {
      profile: role ? DEMO_PROFILES[role] : null,
      login,
      logout,
      switchRole: login,
    };
  }, [role]);

  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  );
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error("useSession must be used inside SessionProvider");
  }
  return context;
}
