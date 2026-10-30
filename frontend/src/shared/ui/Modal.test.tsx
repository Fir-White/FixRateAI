import { useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Button } from "@/shared/ui/Button";
import { Modal } from "@/shared/ui/Modal";

function Harness() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button onClick={() => setOpen(true)}>Открыть</Button>
      <Modal
        open={open}
        title="Подтверждение"
        description="Проверьте решение"
        onClose={() => setOpen(false)}
        footer={<Button>Подтвердить</Button>}
      >
        Содержимое окна
      </Modal>
    </>
  );
}

describe("Modal", () => {
  it("traps focus, closes on Escape and restores focus", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const trigger = screen.getByRole("button", { name: "Открыть" });
    await user.click(trigger);

    const dialog = screen.getByRole("dialog", { name: "Подтверждение" });
    expect(dialog).toContainElement(document.activeElement as HTMLElement);

    await user.tab({ shift: true });
    expect(
      screen.getByRole("button", { name: "Подтвердить" }),
    ).toHaveFocus();

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
  });

  it("does not render a closed dialog", () => {
    render(
      <Modal open={false} title="Закрыто" onClose={() => undefined}>
        Содержимое
      </Modal>,
    );

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
