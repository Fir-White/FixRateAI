import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppRouter } from "@/app/router";
import { SessionProvider } from "@/shared/session/SessionContext";

afterEach(() => vi.unstubAllGlobals());

function renderAt(path: string, role: string) {
  window.localStorage.setItem("fixrate.demo.role", role);
  return render(
    <SessionProvider>
      <MemoryRouter initialEntries={[path]}>
        <AppRouter />
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
    expect(await screen.findByRole("heading", {name: "Панель диспетчера"})).toBeInTheDocument();
  });

  it("opens the dispatcher panel and navigates to equipment", async () => {
    const user = userEvent.setup();
    renderAt("/dispatcher", "dispatcher");

    expect(
      await screen.findByRole("heading", { name: "Панель диспетчера" }),
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

  it.each([["director", "Панель диспетчера"], ["executor", "Мои задания"], ["engineer", "Контроль качества и приёмка"]])("returns %s to their home when no workspace history exists", async (role, heading) => {
    const user=userEvent.setup();window.localStorage.setItem("fixrate.demo.role",role);
    render(<SessionProvider><MemoryRouter initialEntries={["/equipment", "/profile"]} initialIndex={1}><AppRouter /></MemoryRouter></SessionProvider>);
    await screen.findByRole("heading",{name:"Мой профиль"});
    await user.click(screen.getByRole("button",{name:"Назад"}));
    expect(await screen.findByRole("heading",{name:heading})).toBeInTheDocument();
    expect(screen.queryByRole("button",{name:"Назад"})).not.toBeInTheDocument();
  });

  it("returns through previously visited sections without looping", async () => {
    const user=userEvent.setup();renderAt("/executor", "executor");
    await screen.findByRole("heading",{name:"Мои задания"});
    await user.click(screen.getByRole("link",{name:"Оборудование"}));
    await screen.findByRole("heading",{name:"Оборудование"});
    await user.click(screen.getByRole("link",{name:"Учётная запись"}));
    await screen.findByRole("heading",{name:"Мой профиль"});
    await user.click(screen.getByRole("button",{name:"Назад"}));
    await screen.findByRole("heading",{name:"Оборудование"});
    await user.click(screen.getByRole("button",{name:"Назад"}));
    await screen.findByRole("heading",{name:"Мои задания"});
    expect(screen.queryByRole("button",{name:"Назад"})).not.toBeInTheDocument();
  });

  it("restores search and hash from the previous workspace page", async () => {
    const user=userEvent.setup();window.localStorage.setItem("fixrate.demo.role","executor");
    function LocationProbe(){const location=useLocation();return <output data-testid="route-location">{location.pathname+location.search+location.hash}</output>;}
    render(<SessionProvider><MemoryRouter initialEntries={["/equipment?filter=active#list"]}><AppRouter /><LocationProbe /></MemoryRouter></SessionProvider>);
    await screen.findByRole("heading",{name:"Оборудование"});
    await user.click(screen.getByRole("link",{name:"Учётная запись"}));
    await screen.findByRole("heading",{name:"Мой профиль"});
    await user.click(screen.getByRole("button",{name:"Назад"}));
    await waitFor(()=>expect(screen.getByTestId("route-location")).toHaveTextContent("/equipment?filter=active#list"));
  });

  it("switches sidebar width using the logo", async () => {
    const user=userEvent.setup();const view=renderAt("/dispatcher", "dispatcher");
    await screen.findByRole("heading",{name:"Панель диспетчера"});
    const side=view.container.querySelector(".ops-sidebar")!;
    const toggle=view.container.querySelector<HTMLButtonElement>(".ops-sidebar-brand-control")!;
    expect(toggle.closest("aside")).toBe(side);
    const before=side.getAttribute("data-expanded");
    await user.click(toggle);
    expect(side.getAttribute("data-expanded")).not.toBe(before);
    expect(toggle.getAttribute("aria-expanded")).toBe(side.getAttribute("data-expanded"));
    await user.click(toggle);
    expect(side.getAttribute("data-expanded")).toBe(before);
  });

  it("blocks a route outside the current role", async () => {
    renderAt("/quality", "executor");

    expect(
      await screen.findByRole("heading", {
        name: "Раздел недоступен для текущей роли",
      }),
    ).toBeInTheDocument();
  });

  it("opens mobile navigation and closes it with Escape", async () => {
    vi.stubGlobal("matchMedia", vi.fn((query: string) => ({
      matches: query === "(max-width: 1023px)", media: query,
      addEventListener: vi.fn(), removeEventListener: vi.fn(),
    })));
    const user = userEvent.setup();
    renderAt("/dispatcher", "dispatcher");

    await screen.findByRole("heading", { name: "Панель диспетчера" });
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
    expect(await screen.findByLabelText("Панель диспетчера")).toBeVisible();
    const canvas = view.container.querySelector(".workspace-aurora canvas");
    await user.click(screen.getByLabelText("Оборудование"));
    expect(await screen.findByText("Оборудование", { selector: "h1" })).toBeVisible();
    expect(view.container.querySelector(".workspace-aurora canvas")).toBe(canvas);
    await user.selectOptions(screen.getByLabelText("Демонстрационная роль"), "executor");
    expect(await screen.findByText("Мои задания", { selector: "h1" })).toBeVisible();
    expect(view.container.querySelector(".workspace-aurora canvas")).toBe(canvas);
    expect(view.container.querySelectorAll(".ops-sidebar")).toHaveLength(1);
    expect(screen.getAllByRole("navigation")).toHaveLength(1);
    await user.click(screen.getByLabelText("Учётная запись"));
    await screen.findByRole("heading", { name: "Мой профиль" });
    await user.click(screen.getByRole("button", { name: "Выйти из аккаунта" }));
    await screen.findByRole("heading", { name: "Выберите роль" });
    expect(view.container.querySelector(".workspace-root")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Учётная запись" })).not.toBeInTheDocument();
    expect(window.localStorage.getItem("fixrate.demo.role")).toBeNull();
  });
});

const PAGE_ROUTES: { path: string; role: string; heading: string }[] = [
  {
    path: "/dispatcher",
    role: "dispatcher",
    heading: "Панель диспетчера",
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
    heading: "Контроль качества и приёмка",
  },
  {
    path: "/quality/b1000000-0000-4000-8000-000000000004",
    role: "engineer",
    heading: "Очистка учебного узла",
  },
  {
    path: "/executor",
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
