import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { pageLoaders } from "@/app/pageModules";
import { AppRouter } from "@/app/router";
import { SessionProvider } from "@/shared/session/SessionContext";
import type { Role } from "@/shared/types/domain";

// This suite verifies role guards and links, independently of the AI provider.
vi.mock("@/shared/api/assistant", () => ({assistantApi: {
  capabilities: async () => ({available:false,model_ref:null,prompt_version:"TEST",agents:[],tools:{assistant:[],planner:[],photo:[]}}),
  list: async () => ({items:[],total:0}),
}}));

// Permission checks exercise rendered routes; bundler transforms are measured by browser tests.
beforeAll(async () => { await Promise.all(Object.values(pageLoaders).map(load => load())); });

// Expected permissions come from the screen specification, independently of router guards.
const roles: Role[] = ["director", "chief_engineer", "admin", "dispatcher", "engineer", "executor"];
const access: Record<string, Role[]> = {
  assistant: roles,
  director:["director"], "chief-engineer":["chief_engineer"], engineer:["engineer"], admin:["admin"],
  planning:["director","chief_engineer","admin","dispatcher","engineer"],
  dispatcher: ["director", "chief_engineer", "admin", "dispatcher","engineer"], equipment: roles,
  calendar: ["director", "chief_engineer", "dispatcher", "engineer", "executor"], tasks: ["director", "chief_engineer", "dispatcher", "engineer"],
  comparisons: ["director", "chief_engineer", "dispatcher", "engineer"], reports: ["director", "chief_engineer", "dispatcher", "engineer"], quality: ["chief_engineer", "engineer"], executor: ["executor"],
  settings: ["chief_engineer","admin","dispatcher","engineer"], "my-shifts": ["executor"], profile: roles,
};
const routes = [
  ["/assistant", "ИИ-помощник"],
  ["/planning", "Планирование ТО"],
  ["/profile", "Мой профиль"],
  ["/director", "Обзор объекта"],
  ["/chief-engineer", "С чего начнём рабочий день?"],
  ["/engineer", "Рабочий день инженера"],
  ["/admin", "Рабочее пространство"],
  ["/dispatcher", "Рабочий день диспетчера"],
  ["/equipment", "Оборудование"],
  ["/equipment/e1000000-0000-4000-8000-000000000001", "Тепловой пункт №1"],
  ["/calendar", "График ТО и ППР"],
  ["/tasks", "Наряды и назначения"],
  ["/tasks/b1000000-0000-4000-8000-000000000004", "Очистка учебного узла"],
  ["/comparisons", "Сравнение прогнозов"],
  ["/reports", "Отчёты"],
  ["/comparisons/c1000000-0000-4000-8000-000000000001", "Учебный узел очистки"],
  ["/quality", "Приёмка работ"],
  ["/quality/b1000000-0000-4000-8000-000000000004", "Очистка учебного узла"],
  ["/executor", "С чего начнём рабочий день?"],
  ["/executor/tasks", "Мои задания"],
  ["/executor/tasks/b1000000-0000-4000-8000-000000000004", "Очистка учебного узла"],
];

const overviewHeading: Partial<Record<Role,string>> = {
  director: "Обзор объекта", chief_engineer: "С чего начнём рабочий день?",
  engineer: "Рабочий день инженера", admin: "Рабочее пространство",
};

describe("role access and links on every screen", () => {
  it.each(roles.flatMap(role => routes.map(([path, heading]) => ({role, path, heading}))))(
    "$role → $path", async ({role, path, heading}) => {
      window.localStorage.setItem("fixrate.demo.role", role);
      const {container} = render(<SessionProvider><MemoryRouter initialEntries={[path]}><AppRouter /></MemoryRouter></SessionProvider>);
      const allowed = access[path.split("/")[1]].includes(role);
      const expected = path==="/dispatcher" ? overviewHeading[role]??heading : heading;
      await screen.findByRole("heading", {name: allowed ? expected : "Раздел недоступен"}, {timeout: 5000});
      await waitFor(() => expect(container.querySelector('[data-workspace-loading="true"]')).not.toBeInTheDocument());
      // Permission checks include every rendered link, even in collapsed regions.
      // Avoid jsdom's expensive ancestor visibility walk for each calendar link;
      // this also catches forbidden destinations accidentally hidden with CSS.
      for (const link of screen.getAllByRole("link", {hidden: true})) {
        const href = link.getAttribute("href") ?? "";
        if (!href.startsWith("/")) continue;
        const section = new URL(href, "http://localhost").pathname.split("/")[1];
        if (section && section !== "login") expect(access[section], href).toContain(role);
      }
      if (allowed && role === "executor" && path === "/calendar") {
        const calculate = /^(?:Рассчитать|Пересчитать) график$/;
        expect(screen.queryByText(calculate, {selector:"button"})).not.toBeInTheDocument();
        expect(screen.queryByLabelText(calculate, {selector:"button"})).not.toBeInTheDocument();
      }
    },
  );
});


const businessMenus: [Role, string[]][] = [
  ["director", ["/assistant","/director","/planning","/tasks","/equipment","/reports"]],
  ["chief_engineer", ["/assistant","/chief-engineer","/planning","/tasks","/quality","/equipment","/settings/workforce","/reports"]],
  ["engineer", ["/assistant","/engineer","/planning","/tasks","/quality","/equipment","/settings/workforce","/reports"]],
  ["executor", ["/assistant","/executor","/executor/tasks","/equipment","/executor/reports"]],
];

describe("required business navigation, independently of direct route access", () => {
  it.each(businessMenus)("%s sees the complete permitted menu", async (role, paths) => {
    window.localStorage.setItem("fixrate.demo.role", role);
    render(<SessionProvider><MemoryRouter initialEntries={[role === "executor" ? "/executor" : "/dispatcher"]}><AppRouter /></MemoryRouter></SessionProvider>);
    const menu = await screen.findByRole("navigation", {name: "Основная навигация"});
    const actual = within(menu).getAllByRole("link").map(link => link.getAttribute("href"));
    actual.push(screen.getByRole("link",{name:"ИИ-помощник"}).getAttribute("href"));
    expect(actual.sort()).toEqual([...paths].sort());
  });
});
