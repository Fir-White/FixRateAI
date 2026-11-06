import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AppRouter } from "@/app/router";
import { SessionProvider } from "@/shared/session/SessionContext";
import type { Role } from "@/shared/types/domain";

// Expected permissions come from the screen specification, independently of router guards.
const roles: Role[] = ["director", "chief_engineer", "admin", "dispatcher", "engineer", "executor"];
const access: Record<string, Role[]> = {
  director:["director"], "chief-engineer":["chief_engineer"], engineer:["engineer"], admin:["admin"],
  dispatcher: ["director", "chief_engineer", "admin", "dispatcher","engineer"], equipment: roles,
  calendar: ["director", "chief_engineer", "dispatcher", "engineer", "executor"], tasks: ["director", "chief_engineer", "dispatcher", "engineer"],
  comparisons: ["director", "chief_engineer", "dispatcher", "engineer"], reports: ["director", "chief_engineer", "dispatcher", "engineer"], quality: ["chief_engineer", "engineer"], executor: ["executor"],
  settings: ["chief_engineer","admin","dispatcher","engineer"], "my-shifts": ["executor"], profile: roles,
};
const routes = [
  ["/profile", "Мой профиль"],
  ["/director", "Панель диспетчера"],
  ["/chief-engineer", "Панель диспетчера"],
  ["/engineer", "Контроль качества и приёмка"],
  ["/admin", "Панель диспетчера"],
  ["/dispatcher", "Панель диспетчера"],
  ["/equipment", "Оборудование"],
  ["/equipment/e1000000-0000-4000-8000-000000000001", "Тепловой пункт №1"],
  ["/calendar", "График ТО и ППР"],
  ["/tasks", "Наряды и назначения"],
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
        const section = new URL(href, "http://localhost").pathname.split("/")[1];
        if (section && section !== "login") expect(access[section], href).toContain(role);
      }
      if (allowed && role === "executor" && path === "/calendar") {
        expect(screen.queryByRole("button", {name: "Рассчитать график"})).not.toBeInTheDocument();
      }
    },
  );
});


const businessMenus: [Role, string[]][] = [
  ["director", ["/director", "/calendar", "/equipment", "/tasks", "/comparisons", "/reports"]],
  ["chief_engineer", ["/chief-engineer", "/quality", "/calendar", "/equipment", "/tasks", "/comparisons", "/reports", "/settings/equipment", "/settings/workforce"]],
  ["engineer", ["/dispatcher", "/engineer", "/calendar", "/equipment", "/tasks", "/comparisons", "/reports", "/settings/equipment", "/settings/workforce"]],
  ["executor", ["/executor", "/calendar", "/equipment", "/my-shifts"]],
];

describe("required business navigation, independently of direct route access", () => {
  it.each(businessMenus)("%s sees the complete permitted menu", async (role, paths) => {
    window.localStorage.setItem("fixrate.demo.role", role);
    render(<SessionProvider><MemoryRouter initialEntries={[role === "executor" ? "/executor" : "/dispatcher"]}><AppRouter /></MemoryRouter></SessionProvider>);
    const menu = await screen.findByRole("navigation", {name: "Основная навигация"});
    const actual = within(menu).getAllByRole("link").map(link => link.getAttribute("href"));
    expect(actual.sort()).toEqual([...paths].sort());
  });
});
