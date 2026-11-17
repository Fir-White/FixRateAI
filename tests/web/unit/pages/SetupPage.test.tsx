import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SetupPage } from "@/pages/SetupPage";

afterEach(() => vi.unstubAllGlobals());

describe("First installation", () => {
  it("does not offer another administrator after completion", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ required: false }) }));
    render(<MemoryRouter><SetupPage /></MemoryRouter>);
    expect(await screen.findByRole("link", { name: "Перейти ко входу" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Пароль (от 12 символов)")).not.toBeInTheDocument();
  });

  it("sends the one-time secret only in its protected header and clears fields after success", async () => {
    const fetcher = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ required: true }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ status: "created" }) });
    vi.stubGlobal("fetch", fetcher);
    render(<MemoryRouter><SetupPage /></MemoryRouter>);
    await screen.findByRole("button", { name: "Создать администратора" });
    for (const [label, value] of [["Одноразовый установочный код", "test-one-time-secret"], ["Организация", "TEST company"], ["Первое здание", "TEST building"], ["Имя администратора", "TEST admin"], ["Email", "admin@example.test"], ["Пароль (от 12 символов)", "test-password-at-least-12"]]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    }
    fireEvent.submit(screen.getByRole("form", { name: "Создание первого администратора" }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    const options = fetcher.mock.calls[1][1];
    expect(options.headers["X-FixRate-Setup-Token"]).toBe("test-one-time-secret");
    expect(options.body).not.toContain("test-one-time-secret");
    expect(await screen.findByText("Администратор создан. Войдите с указанными реквизитами.")).toBeInTheDocument();
  });
});
