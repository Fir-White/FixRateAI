import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { IncidentWorkspace } from "@/features/analyst/AnalystPanels";
import { request } from "@/shared/api/request";

const session=vi.hoisted(()=>({role:"executor"}));
vi.mock("@/shared/api/request",()=>({DEMO_MODE:false,request:vi.fn()}));
vi.mock("@/shared/session/SessionContext",()=>({useSession:()=>({profile:{role:session.role}})}));
beforeEach(()=>{session.role="executor";vi.mocked(request).mockReset();vi.mocked(request).mockResolvedValue([]);vi.stubGlobal("URL",class extends URL{static createObjectURL=()=>"blob:photo";static revokeObjectURL=()=>{};});});
afterEach(()=>{vi.unstubAllGlobals();});

it("submits an incident with the real equipment, description and original file then resets successful fields",async()=>{
  const user=userEvent.setup();render(<IncidentWorkspace equipmentId="equipment-1"/>);
  await screen.findByText("По этому оборудованию обращений пока нет.");
  const submit=screen.getByRole("button",{name:"Создать обращение"});expect(submit).toHaveAttribute("type","submit");expect(submit).toBeDisabled();
  fireEvent.change(screen.getByLabelText(/Что обнаружено/),{target:{value:"Подтекает соединение"}});
  const file=new File(["original bytes"],"defect.png",{type:"image/png"});await user.upload(screen.getByLabelText("Фото дефекта",{exact:true}),file);
  await user.click(submit);
  await waitFor(()=>expect(request).toHaveBeenCalledWith("/api/v1/maintenance/incidents",expect.objectContaining({method:"POST",body:expect.any(FormData)})));
  const call=vi.mocked(request).mock.calls.find(([,options])=>options?.method==="POST")!;
  const body=call[1]!.body as FormData;
  expect(body.get("equipment_id")).toBe("equipment-1");expect(body.get("description")).toBe("Подтекает соединение");expect(body.get("file")).toBe(file);
  expect(await screen.findByText("Обращение создано.")).toBeInTheDocument();
  expect(screen.getByLabelText(/Что обнаружено/)).toHaveValue("");expect(screen.queryByText("defect.png")).not.toBeInTheDocument();
});

it("keeps the entered report when the server rejects it",async()=>{
  vi.mocked(request).mockImplementation(async(_url,options)=>{if(options?.method==="POST")throw new Error("Нет связи с сервером");return [] as never;});
  render(<IncidentWorkspace equipmentId="equipment-1"/>);
  fireEvent.change(screen.getByLabelText(/Что обнаружено/),{target:{value:"Не работает индикация"}});
  fireEvent.click(screen.getByRole("button",{name:"Создать обращение"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("Нет связи с сервером");
  expect(screen.getByLabelText(/Что обнаружено/)).toHaveValue("Не работает индикация");
});

it("does not expose incident mutations to the director",async()=>{
  session.role="director";render(<IncidentWorkspace equipmentId="equipment-1"/>);
  await screen.findByText("По этому оборудованию обращений пока нет.");
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();expect(screen.queryByRole("button",{name:"Создать обращение"})).not.toBeInTheDocument();
  expect(vi.mocked(request).mock.calls.every(([,options])=>!options?.method||options.method==="GET")).toBe(true);
});
