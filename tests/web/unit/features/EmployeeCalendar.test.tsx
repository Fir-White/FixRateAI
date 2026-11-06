import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { EmployeeCalendar, shiftTasks } from "@/features/workforce/EmployeeCalendar";
import { managementApi } from "@/shared/api/management";
import { demoTasks } from "@/shared/mocks/data";

vi.mock("@/shared/api/management",()=>({managementApi:{workerCalendar:vi.fn()}}));
const row={start_at:"2026-11-06T17:00:00Z",end_at:"2026-11-07T01:00:00Z",status:"available"};
const task={...demoTasks[0],id:"own-task",title:"Проверка насоса",equipmentName:"Насос № 1",scheduledStart:"2026-11-06T18:00:00Z",scheduledEnd:"2026-11-06T19:00:00Z",assignees:[{executorId:"exec",name:"Исполнитель",qualifications:[]}]};
beforeEach(()=>{vi.mocked(managementApi.workerCalendar).mockReset();});
function mount(tasks= [task]){return render(<MemoryRouter><EmployeeCalendar personal person={{user_id:"exec"}} today="2026-11-07" timezone="Asia/Yekaterinburg" tasks={tasks}/></MemoryRouter>);}

it("shows exact site-local hours, overnight finish, duration, and real linked task context",async()=>{
  vi.mocked(managementApi.workerCalendar).mockResolvedValue({intervals:[row],diagnostics:[]});mount();
  expect(await screen.findByRole("heading",{name:/22:00.*06:00/})).toHaveTextContent("до 7 ноября");
  expect(screen.getByText(/^8 ч/, {selector:"p"})).toBeInTheDocument();
  const link=screen.getByRole("link",{name:/Проверка насоса/});expect(link).toHaveAttribute("href","/executor/tasks/own-task");
  expect(link).toHaveTextContent("Насос № 1");
  expect(managementApi.workerCalendar).toHaveBeenCalledWith("exec","2026-11-02","2026-11-08");
});

it("matches assignments only by their real time overlap and assignee, never by an obligation date",()=>{
  expect(shiftTasks(row,[task,{...task,id:"other-user",assignees:[]},{...task,id:"outside",scheduledStart:"2026-11-06T14:00:00Z",scheduledEnd:"2026-11-06T15:00:00Z"},{...task,id:"due-only",scheduledStart:null,scheduledEnd:null,mandatoryDueDate:"2026-11-06"}],"exec").map(value=>value.id)).toEqual(["own-task"]);
});

it("keeps unavailable intervals and diagnostics visible without declaring them working shifts",async()=>{
  vi.mocked(managementApi.workerCalendar).mockResolvedValue({intervals:[{...row,status:"unavailable"}],diagnostics:[{date:"2026-11-07",explanation:"Не удалось однозначно определить местное время"}]});mount();
  expect(await screen.findByText("Есть ограничения расчёта")).toBeInTheDocument();
  expect(screen.getAllByText("Не работает").length).toBeGreaterThan(0);
  expect(screen.getByRole("alert")).toHaveTextContent("Не удалось однозначно определить местное время");
  expect(screen.queryByText("По графику")).not.toBeInTheDocument();
});

it("provides week navigation and a truthful empty state",async()=>{
  vi.mocked(managementApi.workerCalendar).mockResolvedValue({intervals:[],diagnostics:[]});mount([]);
  expect(await screen.findByText("На этот период смен нет")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:"Следующая неделя"}));
  await waitFor(()=>expect(managementApi.workerCalendar).toHaveBeenLastCalledWith("exec","2026-11-09","2026-11-15"));
});

it("reports a calendar request failure without inventing counts or intervals",async()=>{
  vi.mocked(managementApi.workerCalendar).mockRejectedValue(new Error("Нет связи с сервером"));mount();
  expect(await screen.findByRole("alert")).toHaveTextContent("Нет связи с сервером");
  expect(screen.queryByText("На этот период смен нет")).not.toBeInTheDocument();
  expect(screen.getByRole("button",{name:"Повторить загрузку смен"})).toBeInTheDocument();
});
