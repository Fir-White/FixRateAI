import { createContext, useContext, type ReactNode } from "react";
import "./content-theme.css";

// React ownership crosses portals; DOM ancestry must never theme the shell.
const ContentThemeContext = createContext(false);
export const useContentTheme = () => useContext(ContentThemeContext);

export function ContentTheme({ children }: { children: ReactNode }) {
  return <ContentThemeContext.Provider value={true}><div className="fr-content-v2">{children}</div></ContentThemeContext.Provider>;
}

export function ReadOnlyValue({ label, children }: { label: string; children: ReactNode }) {
  return <div className="fr-read-value"><span>{label}</span><div>{children ?? "Нет данных"}</div></div>;
}
