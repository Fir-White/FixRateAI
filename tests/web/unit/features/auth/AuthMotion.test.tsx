import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Link, MemoryRouter, Route, Routes, useLocation, useNavigate, useNavigationType } from "react-router-dom";
import type { SessionProfile } from "@/shared/types/domain";
import { StrictMode, useRef } from "react";
import { AuthLayout } from "@/pages/AuthLayout";
import { LoginPage } from "@/pages/LoginPage";
import { HomeRedirect } from "@/pages/HomeRedirect";
import { usePageEntry } from "@/shared/motion/usePageEntry";
import { AUTH_ENTRY_STATE, isAuthEntryNavigation } from "@/shared/motion/authEntry";

type Run = { token: string; finished: Promise<boolean>; finish: () => void; cancel: () => void };
const mocks = vi.hoisted(() => ({ profile: null as SessionProfile | null, signIn: vi.fn(), runs: [] as Run[] }));
vi.mock("@/features/auth/AuroraScene", () => ({ AuroraScene: () => <div data-testid="persistent-aurora" /> }));
vi.mock("@/shared/session/SessionContext", () => ({ useSession: () => ({ profile: mocks.profile, loading: false, signIn: mocks.signIn }) }));
vi.mock("@/shared/api/request", async importOriginal => ({ ...await importOriginal<typeof import("@/shared/api/request")>(), DEMO_MODE: false }));
vi.mock("@/shared/motion/animate", () => ({
  motionDuration: () => 0,
  animateMotion: (_element: HTMLElement, _frames: Keyframe[], token: string) => {
    let resolve!: (completed: boolean) => void;
    const finished = new Promise<boolean>(done => { resolve = done; });
    const run = { token, finished, finish: () => resolve(true), cancel: () => resolve(false) };
    mocks.runs.push(run);
    return run;
  },
}));
beforeEach(() => { mocks.profile = null; mocks.signIn.mockReset(); mocks.runs = []; vi.spyOn(window,"scrollTo").mockImplementation(()=>{}); });
afterEach(()=>vi.restoreAllMocks());
function Controls() {
  const location = useLocation(), navigate = useNavigate();
  return <><output data-testid="location" data-entry={location.state?.fixrateAuthEntry ? "auth" : undefined}>{location.pathname}</output><button onClick={() => navigate(-1)}>History back</button><button onClick={() => navigate(1)}>History forward</button></>;
}
function Registration() { return <><h1 tabIndex={-1}>Регистрация</h1><form aria-label="Registration"><input aria-label="Registration name" /></form><Link to="/login">Return to login</Link></>; }
function Landing() {
  const ref=useRef<HTMLElement>(null), location=useLocation(), type=useNavigationType();
  usePageEntry(ref,location.key,isAuthEntryNavigation(location.state,type));
  return <main ref={ref} tabIndex={-1} data-testid="landing"><h1>Authorized dispatcher</h1></main>;
}
function Tree({initial="/login",from}:{initial?:string;from?:string}) {
  return <MemoryRouter initialEntries={[{pathname:initial,state:from ? {from} : undefined}]}><Controls /><Routes><Route element={<AuthLayout />}><Route path="/login" element={<LoginPage />} /><Route path="/register" element={<Registration />} /></Route><Route path="/" element={<HomeRedirect />} /><Route path="/dispatcher" element={<Landing />} /></Routes></MemoryRouter>;
}
const finish = async (run = mocks.runs.at(-1)!) => { await act(async () => { run.finish(); await run.finished; }); };
const user: SessionProfile = { userId: "test", name: "Test", email: "test@example.test", role: "dispatcher", siteName: "Test", timezone: "UTC" };
const submit = () => {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "test@example.test" } });
  fireEvent.change(screen.getByLabelText("Пароль"), { target: { value: "test-password" } });
  fireEvent.submit(screen.getByRole("form"));
};

it("exits a single inert form, commits the latest page with heading focus and preserves Aurora", async () => {
  render(<StrictMode><Tree /></StrictMode>);
  const aurora = screen.getByTestId("persistent-aurora");
  fireEvent.click(screen.getByRole("link", { name: "Регистрация" }));
  expect(mocks.runs.at(-1)?.token).toBe("--motion-auth-exit");
  expect(screen.queryByRole("form")).toBeNull();
  expect(screen.getAllByRole("form", { hidden: true })).toHaveLength(1);
  expect(document.querySelector(".auth-panel__content")).toHaveAttribute("inert");
  await finish();
  expect(screen.getAllByRole("form")).toHaveLength(1);
  expect(document.querySelector(".auth-panel__content")).not.toHaveAttribute("inert");
  expect(screen.getByRole("heading", { name: "Регистрация" })).toHaveFocus();
  expect(screen.getByTestId("persistent-aurora")).toBe(aurora);
  expect(mocks.runs.at(-1)?.token).toBe("--motion-auth-enter");
  await finish();
  expect(document.querySelector(".auth-page")).toHaveAttribute("data-transition", "idle");
});

it("cancels stale route exits during rapid Back/Forward without committing an obsolete form", async () => {
  render(<Tree />);
  fireEvent.click(screen.getByRole("link", { name: "Регистрация" }));
  const obsolete = mocks.runs.at(-1)!;
  fireEvent.click(screen.getByRole("button", { name: "History back" }));
  await finish(obsolete);
  expect(screen.getByTestId("location")).toHaveTextContent("/login");
  expect(screen.getByRole("form", { name: "Вход в систему" })).toBeVisible();
  expect(document.querySelector(".auth-panel__content")).not.toHaveAttribute("inert");
  fireEvent.click(screen.getByRole("button", { name: "History forward" }));
  await finish();
  expect(screen.getByRole("heading", { name: "Регистрация" })).toHaveFocus();
});

it("does not auto-redirect a retained outgoing login when a session arrives on the registration URL", async () => {
  const view = render(<Tree />);
  fireEvent.click(screen.getByRole("link", { name: "Регистрация" }));
  mocks.profile = user;
  view.rerender(<Tree />);
  expect(screen.getByTestId("location")).toHaveTextContent("/register");
  await finish();
  expect(screen.getByRole("heading", { name: "Регистрация" })).toHaveFocus();
});

it.each([["/login",undefined],["/login/",undefined],["/login","/"]])("waits for confirmed success from %s returning to %s and its short exit despite the profile updating first", async (initial,from) => {
  let resolve!: (profile: SessionProfile) => void;
  mocks.signIn.mockReturnValue(new Promise<SessionProfile>(done => { resolve = done; }));
  const view = render(<Tree initial={initial} from={from} />);
  submit();
  expect(mocks.runs).toHaveLength(0);
  expect(screen.getByRole("form")).toHaveAttribute("aria-busy", "true");
  mocks.profile = user;
  view.rerender(<Tree initial={initial} from={from} />);
  expect(screen.getByTestId("location")).toHaveTextContent("/login");
  await act(async () => { resolve(user); });
  expect(mocks.runs.at(-1)?.token).toBe("--motion-success-exit");
  expect(screen.getByTestId("location")).toHaveTextContent("/login");
  await finish();
  expect(screen.getByRole("heading", { name: "Authorized dispatcher" })).toBeVisible();
  expect(screen.getByTestId("location")).toHaveAttribute("data-entry","auth");
  expect(screen.getByTestId("landing")).toHaveFocus();
});

it.each(["reload","history back"])("does not reset scroll or steal app focus for a persisted auth-entry marker on %s",mode=>{
  render(<MemoryRouter initialEntries={mode==="reload" ? [{pathname:"/dispatcher",state:AUTH_ENTRY_STATE}] : [{pathname:"/dispatcher",state:AUTH_ENTRY_STATE},"/other"]} initialIndex={mode==="reload" ? 0 : 1}><Controls /><Routes><Route path="/dispatcher" element={<Landing />} /><Route path="/other" element={<h1>Other page</h1>} /></Routes></MemoryRouter>);
  if(mode==="history back") fireEvent.click(screen.getByRole("button",{name:"History back"}));
  expect(screen.getByRole("heading",{name:"Authorized dispatcher"})).toBeVisible();
  expect(window.scrollTo).not.toHaveBeenCalled();
  expect(screen.getByTestId("landing")).not.toHaveFocus();
});

it("redirects an already authenticated direct trailing-slash login",()=>{
  mocks.profile=user;
  render(<Tree initial="/login/" />);
  expect(screen.getByRole("heading",{name:"Authorized dispatcher"})).toBeVisible();
});

it("ignores a completed login request after its page has left instead of navigating over registration", async () => {
  let resolve!: (profile: SessionProfile) => void;
  mocks.signIn.mockReturnValue(new Promise<SessionProfile>(done => { resolve = done; }));
  const view = render(<Tree />);
  submit();
  fireEvent.click(screen.getByRole("link", { name: "Регистрация" }));
  await finish();
  mocks.profile = user;
  view.rerender(<Tree />);
  await act(async () => { resolve(user); });
  expect(screen.getByTestId("location")).toHaveTextContent("/register");
  expect(screen.getByRole("heading", { name: "Регистрация" })).toBeVisible();
  expect(mocks.runs.some(run => run.token === "--motion-success-exit")).toBe(false);
});
