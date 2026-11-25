import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { pageLoaders } from "@/app/pageModules";
import { AppRouter } from "@/app/router";
import { SessionProvider } from "@/shared/session/SessionContext";

afterEach(() => vi.unstubAllGlobals());
// Route assertions test page behavior; cold module loading has separate coverage.
beforeAll(async () => { await Promise.all([...Object.values(pageLoaders).map(load=>load()),import("@/shared/api/maintenance.demo")]); },15000);

function HistoryBack() {
  const navigate = useNavigate();
  return <button type="button" onClick={() => navigate(-1)}>Назад в истории браузера</button>;
}

const pageHeading = (title: string) => screen.findByText(title, {selector:"h1,h2"});
const headerLink = (label: string) => screen.getByLabelText(label, {selector:"a"});

function renderAt(path: string, role: string, history = false) {
  window.localStorage.setItem("fixrate.demo.role", role);
  return render(
    <SessionProvider>
      <MemoryRouter initialEntries={[path]}>
        <AppRouter />
        {history && <HistoryBack />}
      </MemoryRouter>
    </SessionProvider>,
  );
}

describe("app routes", () => {
  it("redirects the legacy executive URL to the director home", async () => {
    window.localStorage.setItem("fixrate.demo.role", "director");
    function LocationProbe() { const location = useLocation(); return <output data-testid="director-path">{location.pathname}</output>; }
    render(<SessionProvider><MemoryRouter initialEntries={["/executive"]}><AppRouter /><LocationProbe /></MemoryRouter></SessionProvider>);
    await waitFor(() => expect(screen.getByTestId("director-path")).toHaveTextContent("/director"));
    expect(await screen.findByRole("heading", {name: "Обзор объекта"}, {timeout:5000})).toBeInTheDocument();
  });

  it("opens the dispatcher panel and navigates to equipment", async () => {
    const user = userEvent.setup();
    renderAt("/dispatcher", "dispatcher");

    expect(
      await screen.findByRole("heading", { name: "Рабочий день диспетчера" }),
    ).toBeInTheDocument();

    const equipmentLinks = screen.getAllByRole("link", {
      name: "Оборудование",
    });
    await user.click(equipmentLinks[0]);

    expect(
      await screen.findByRole("heading", { name: "Оборудование" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Тепловой пункт №1")).toBeInTheDocument();
  });

  it.each([["director", "Обзор объекта"], ["executor", "С чего начнём рабочий день?"], ["engineer", "Рабочий день инженера"]])("returns %s to their role home from a direct link", async (role, heading) => {
    const user=userEvent.setup();window.localStorage.setItem("fixrate.demo.role",role);
    render(<SessionProvider><MemoryRouter initialEntries={["/equipment", "/profile"]} initialIndex={1}><AppRouter /></MemoryRouter></SessionProvider>);
    await screen.findByRole("heading",{name:"Мой профиль"});
    await user.click(screen.getByRole("link",{name:"FixRate AI"}));
    expect(await screen.findByRole("heading",{name:heading})).toBeInTheDocument();
    expect(screen.queryByRole("button",{name:"Назад"})).not.toBeInTheDocument();
  });

  it("returns through previously visited sections without looping", async () => {
    const user=userEvent.setup();renderAt("/executor", "executor", true);
    const back=()=>screen.getByText("Назад в истории браузера",{selector:"button"});
    await pageHeading("С чего начнём рабочий день?");
    await user.click(headerLink("Оборудование"));
    await pageHeading("Оборудование");
    await user.click(headerLink("Учётная запись"));
    await pageHeading("Мой профиль");
    await user.click(back());
    await pageHeading("Оборудование");
    await user.click(back());
    expect(await pageHeading("С чего начнём рабочий день?")).toBeVisible();
    expect(screen.queryByText("Назад",{selector:"button"})).not.toBeInTheDocument();
  });

  it("restores search and hash from the previous workspace page", async () => {
    const user=userEvent.setup();window.localStorage.setItem("fixrate.demo.role","executor");
    function LocationProbe(){const location=useLocation();return <output data-testid="route-location">{location.pathname+location.search+location.hash}</output>;}
    render(<SessionProvider><MemoryRouter initialEntries={["/equipment?filter=active#list"]}><AppRouter /><LocationProbe /><HistoryBack /></MemoryRouter></SessionProvider>);
    await pageHeading("Оборудование");
    await user.click(headerLink("Учётная запись"));
    await pageHeading("Мой профиль");
    await user.click(screen.getByText("Назад в истории браузера",{selector:"button"}));
    await waitFor(()=>expect(screen.getByTestId("route-location")).toHaveTextContent("/equipment?filter=active#list"));
  });

  it("highlights the current section and sends the logo link to the role home", async () => {
    const user=userEvent.setup();
    renderAt("/dispatcher", "dispatcher");
    await pageHeading("Рабочий день диспетчера");
    expect(headerLink("Рабочий день")).toHaveAttribute("aria-current", "page");
    await user.click(headerLink("Оборудование"));
    await pageHeading("Оборудование");
    expect(headerLink("Оборудование")).toHaveAttribute("aria-current", "page");
    await user.click(headerLink("FixRate AI"));
    expect(await pageHeading("Рабочий день диспетчера")).toBeVisible();
  });

  it("blocks a route outside the current role", async () => {
    renderAt("/quality", "executor");

    expect(
      await screen.findByRole("heading", {
        name: "Раздел недоступен",
      }),
    ).toBeInTheDocument();
  });

  it("opens mobile navigation and closes it with Escape", async () => {
    vi.stubGlobal("matchMedia", vi.fn((query: string) => ({
      matches: query === "(max-width: 1099px)", media: query,
      addEventListener: vi.fn(), removeEventListener: vi.fn(),
    })));
    const user = userEvent.setup();
    renderAt("/dispatcher", "dispatcher");

    await screen.findByRole("heading", { name: "Рабочий день диспетчера" });
    await user.click(screen.getByRole("button", { name: "Открыть меню" }));

    expect(
      screen.getByRole("dialog", { name: "Мобильная навигация" }),
    ).toBeInTheDocument();

    await user.keyboard("{Escape}");
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Мобильная навигация" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("keeps quality decisions unavailable in demo mode", async () => {
    renderAt(
      "/quality/b1000000-0000-4000-8000-000000000004",
      "engineer",
    );

    await screen.findByRole("heading", { name: "Очистка учебного узла" });
    expect(screen.queryByRole("button", { name: "Принять работу" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Вернуть на доработку" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Причина решения/)).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("redirects to login without a session", async () => {
    render(
      <SessionProvider>
        <MemoryRouter initialEntries={["/tasks"]}>
          <AppRouter />
        </MemoryRouter>
      </SessionProvider>,
    );

    expect(
      await screen.findByRole("heading", { name: "Выберите роль" }),
    ).toBeInTheDocument();
  });

  it("retains one background across sections and executor shell, then removes session UI on logout", async () => {
    const user = userEvent.setup();
    const view = renderAt("/dispatcher", "dispatcher");
    expect(await pageHeading("Рабочий день диспетчера")).toBeVisible();
    const workspace = view.container.querySelector(".workspace-root");
    expect(workspace).toBeInTheDocument();
    await user.click(screen.getByLabelText("Оборудование"));
    expect(await screen.findByText("Оборудование", { selector: "h1" })).toBeVisible();
    expect(view.container.querySelector(".workspace-root")).toBe(workspace);
    fireEvent.change(screen.getByLabelText("Демонстрационная роль"), {target:{value:"executor"}});
    expect(await screen.findByText("С чего начнём рабочий день?", { selector: "h1" })).toBeVisible();
    expect(view.container.querySelector(".workspace-root")).toBe(workspace);
    expect(view.container.querySelectorAll(".ops-sidebar")).toHaveLength(0);
    expect(screen.getAllByRole("navigation", {hidden:true})).toHaveLength(1);
    await user.click(screen.getByLabelText("Учётная запись"));
    await pageHeading("Мой профиль");
    await user.click(screen.getByText("Выйти из аккаунта",{selector:"button"}));
    await pageHeading("Выберите роль");
    expect(view.container.querySelector(".workspace-root")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Учётная запись" })).not.toBeInTheDocument();
    expect(window.localStorage.getItem("fixrate.demo.role")).toBeNull();
  });
});

const PAGE_ROUTES: { path: string; role: string; heading: string }[] = [
  {
    path: "/dispatcher",
    role: "dispatcher",
    heading: "Рабочий день диспетчера",
  },
  {
    path: "/equipment/e1000000-0000-4000-8000-000000000001",
    role: "dispatcher",
    heading: "Тепловой пункт №1",
  },
  {
    path: "/calendar",
    role: "dispatcher",
    heading: "График ТО и ППР",
  },
  {
    path: "/tasks",
    role: "dispatcher",
    heading: "Наряды и назначения",
  },
  {
    path: "/tasks/b1000000-0000-4000-8000-000000000001",
    role: "dispatcher",
    heading: "Ежедневный обход теплового пункта",
  },
  {
    path: "/comparisons",
    role: "engineer",
    heading: "Сравнение прогнозов",
  },
  {
    path: "/comparisons/c1000000-0000-4000-8000-000000000001",
    role: "engineer",
    heading: "Учебный узел очистки",
  },
  {
    path: "/quality",
    role: "engineer",
    heading: "Приёмка работ",
  },
  {
    path: "/quality/b1000000-0000-4000-8000-000000000004",
    role: "engineer",
    heading: "Очистка учебного узла",
  },
  {
    path: "/executor",
    role: "executor",
    heading: "С чего начнём рабочий день?",
  },
  {
    path: "/executor/tasks",
    role: "executor",
    heading: "Мои задания",
  },
  {
    path: "/executor/tasks/b1000000-0000-4000-8000-000000000004",
    role: "executor",
    heading: "Очистка учебного узла",
  },
];

describe("page routes", () => {
  it.each(PAGE_ROUTES)("renders $path", async ({ path, role, heading }) => {
    renderAt(path, role);

    expect(
      await screen.findByRole("heading", { name: heading }),
    ).toBeInTheDocument();
  });
});
