import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AppRouter } from "@/app/router";
import { SessionProvider } from "@/shared/session/SessionContext";
import type { Role } from "@/shared/types/domain";

// Expected permissions come from the screen specification, independently of router guards.
const roles: Role[] = ["admin", "dispatcher", "engineer", "executor"];
const access: Record<string, Role[]> = {
  dispatcher: ["admin", "dispatcher"], equipment: roles,
  calendar: ["dispatcher", "engineer", "executor"], tasks: ["dispatcher", "engineer"],
  comparisons: ["dispatcher", "engineer"], reports: ["dispatcher", "engineer"], quality: ["engineer"], executor: ["executor"],
  settings: ["admin","dispatcher","engineer"], "my-shifts": ["executor"],
};
const routes = [
  ["/dispatcher", "Панель диспетчера"],
  ["/equipment", "Оборудование"],
  ["/equipment/e1000000-0000-4000-8000-000000000001", "Тепловой пункт №1"],
  ["/calendar", "Календарь технического обслуживания"],
  ["/tasks", "Очередь заданий"],
  ["/tasks/b1000000-0000-4000-8000-000000000004", "Очистка учебного узла"],
  ["/comparisons", "Сравнение прогнозов"],
  ["/reports", "Отчёты"],
  ["/comparisons/c1000000-0000-4000-8000-000000000001", "Учебный узел очистки"],
  ["/quality", "Контроль качества и приёмка"],
  ["/quality/b1000000-0000-4000-8000-000000000004", "Очистка учебного узла"],
  ["/executor", "Мои задания"],
  ["/executor/tasks/b1000000-0000-4000-8000-000000000004", "Очистка учебного узла"],
];

describe("role access and links on every screen", () => {
  it.each(roles.flatMap(role => routes.map(([path, heading]) => ({role, path, heading}))))(
    "$role → $path", async ({role, path, heading}) => {
      window.localStorage.setItem("fixrate.demo.role", role);
      render(<SessionProvider><MemoryRouter initialEntries={[path]}><AppRouter /></MemoryRouter></SessionProvider>);
      const allowed = access[path.split("/")[1]].includes(role);
      await screen.findByRole("heading", {name: allowed ? heading : "Раздел недоступен для текущей роли"});
      await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
      for (const link of screen.getAllByRole("link")) {
        const href = link.getAttribute("href") ?? "";
        if (!href.startsWith("/")) continue;
        const section = href.split("/")[1];
        if (section && section !== "login") expect(access[section], href).toContain(role);
      }
      if (allowed && role === "executor" && path === "/calendar") {
        expect(screen.getAllByRole("link").some(link => link.getAttribute("href")?.startsWith("/executor/tasks/"))).toBe(true);
      }
    },
  );
});
