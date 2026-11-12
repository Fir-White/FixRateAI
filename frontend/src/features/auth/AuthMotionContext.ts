import { createContext } from "react";

export const AuthMotionContext = createContext<{ leaveAfterSuccess: (navigate: () => void) => Promise<boolean> } | null>(null);
