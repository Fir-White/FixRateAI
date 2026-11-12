import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { SidebarAccount } from "@/layouts/SidebarAccount";
import type { SessionProfile } from "@/shared/types/domain";

const profile: SessionProfile = { userId: "user-a", name: "Анна Смирнова", email: "anna@example.test", role: "engineer", siteName: "Объект А", timezone: "Asia/Yekaterinburg" };

describe("sidebar account", () => {
  it("shows the current session and opens a read-only profile with keyboard dismissal", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><SidebarAccount profile={profile} pending={false} onLogout={vi.fn()} /></MemoryRouter>);
    const trigger = screen.getByRole("button", { name: "Меню аккаунта: Анна Смирнова" });
    expect(trigger).toHaveTextContent("АС");
    expect(trigger).toHaveTextContent("Инженер");
    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Мой профиль" })).toHaveFocus();
    await user.keyboard("{Enter}");
    const dialog = screen.getByRole("dialog", { name: "Мой профиль" });
    for (const value of [profile.name, profile.email, profile.siteName, profile.timezone]) expect(within(dialog).getByText(value)).toBeInTheDocument();
    expect(within(dialog).queryByRole("textbox")).not.toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("invokes the real shell callback and prevents repeated logout while pending", async () => {
    const user = userEvent.setup();
    const logout = vi.fn();
    const view = render(<MemoryRouter><SidebarAccount profile={profile} pending={false} onLogout={logout} /></MemoryRouter>);
    await user.click(screen.getByRole("button", { name: /Меню аккаунта:/ }));
    await user.click(screen.getByRole("button", { name: "Выйти из аккаунта" }));
    expect(logout).toHaveBeenCalledOnce();
    view.rerender(<MemoryRouter><SidebarAccount profile={profile} pending onLogout={logout} /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "Выход…" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Выход…" }));
    expect(logout).toHaveBeenCalledOnce();
  });

  it("dismisses on outside interaction and discards the previous user's open profile", async () => {
    const user = userEvent.setup();
    const view = render(<MemoryRouter><SidebarAccount profile={profile} pending={false} onLogout={vi.fn()} /></MemoryRouter>);
    await user.click(screen.getByRole("button", { name: /Меню аккаунта:/ }));
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Меню аккаунта:/ }));
    await user.click(screen.getByRole("button", { name: "Мой профиль" }));
    view.rerender(<MemoryRouter><SidebarAccount profile={{ ...profile, userId: "user-b", name: "Борис Петров", email: "boris@example.test" }} pending={false} onLogout={vi.fn()} /></MemoryRouter>);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByText(profile.email)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Меню аккаунта: Борис Петров" })).toBeInTheDocument();
  });
});
