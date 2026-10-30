import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AppRouter } from "@/app/router";
import { SessionProvider } from "@/shared/session/SessionContext";

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
