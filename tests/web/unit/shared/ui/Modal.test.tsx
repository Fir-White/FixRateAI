import { useState } from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
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
  it('skips hidden steps and closed details while trapping focus',async()=>{
    const user=userEvent.setup();
    render(<Modal open title="Этапы" onClose={()=>{}}><button>Последнее видимое действие</button><div hidden inert><button>Скрытый этап</button></div><details><summary>Дополнительно</summary><button>Закрытая форма</button></details></Modal>);
    const dialog=screen.getByRole('dialog',{name:'Этапы'});
    within(dialog).getByText('Дополнительно').focus();
    await user.tab();
    expect(within(dialog).getByRole('button',{name:'Закрыть окно'})).toHaveFocus();
  });

  it('handles Escape only in the most recently opened dialog',()=>{
    const outer=vi.fn(),inner=vi.fn();
    function Nested(){const [open,setOpen]=useState(false);return <Modal open title="Внешнее" onClose={outer}><button onClick={()=>setOpen(true)}>Открыть вложенное</button><Modal open={open} title="Вложенное" onClose={inner}>Подтверждение</Modal></Modal>;}
    render(<Nested/>);fireEvent.click(screen.getByRole('button',{name:'Открыть вложенное'}));
    fireEvent.keyDown(document,{key:'Escape'});
    expect(inner).toHaveBeenCalledOnce();expect(outer).not.toHaveBeenCalled();
  });
  it("traps focus, closes on Escape and restores focus", async () => {
    const user = userEvent.setup();
    const previousOverflow=document.body.style.overflow;
    render(<Harness />);

    const trigger = screen.getByRole("button", { name: "Открыть" });
    await user.click(trigger);

    const dialog = screen.getByRole("dialog", { name: "Подтверждение" });
    expect(document.body.style.overflow).toBe("hidden");
    expect(dialog).toContainElement(document.activeElement as HTMLElement);

    await user.tab({ shift: true });
    expect(
      screen.getByRole("button", { name: "Подтвердить" }),
    ).toHaveFocus();

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
    expect(document.body.style.overflow).toBe(previousOverflow);
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
