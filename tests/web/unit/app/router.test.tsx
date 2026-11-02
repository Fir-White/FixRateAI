import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
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

  it("confirms a quality decision in an accessible modal", async () => {
    const user = userEvent.setup();
    renderAt(
      "/quality/b1000000-0000-4000-8000-000000000004",
      "engineer",
    );

    await screen.findByRole("heading", { name: "Очистка учебного узла" });
    const accept = screen.getByRole("button", { name: "Принять работу" });
    expect(accept).toBeDisabled();

    const reason = screen.getByLabelText(/Причина решения/);
    expect(reason).toHaveAccessibleDescription(/EngineerDecision/);
    await user.type(reason, "Фотографии и чек-лист проверены.");
    await user.click(accept);

    expect(
      screen.getByRole("dialog", { name: "Принять работу?" }),
    ).toBeInTheDocument();

    await user.keyboard("{Escape}");
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
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
    await screen.findByRole("heading", { name: "Панель диспетчера" });
    const canvas = view.container.querySelector(".workspace-aurora canvas");
    await user.click(screen.getByRole("link", { name: "Оборудование" }));
    await screen.findByRole("heading", { name: "Оборудование" });
    expect(view.container.querySelector(".workspace-aurora canvas")).toBe(canvas);
    await user.selectOptions(screen.getByLabelText("Демонстрационная роль"), "executor");
    await screen.findByRole("heading", { name: "Мои задания" });
    expect(view.container.querySelector(".workspace-aurora canvas")).toBe(canvas);
    expect(view.container.querySelectorAll(".ops-sidebar")).toHaveLength(1);
    expect(screen.getAllByRole("navigation")).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: /Меню аккаунта:/ }));
    await user.click(screen.getByRole("button", { name: "Выйти из аккаунта" }));
    await screen.findByRole("heading", { name: "Выберите роль" });
    expect(view.container.querySelector(".workspace-root")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Меню аккаунта:/ })).not.toBeInTheDocument();
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
    heading: "Календарь технического обслуживания",
  },
  {
    path: "/tasks",
    role: "dispatcher",
    heading: "Очередь заданий",
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
