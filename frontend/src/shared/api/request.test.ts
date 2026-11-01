import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.resetModules();
  document.cookie = "fixrate_csrf=; Max-Age=0; path=/";
});

describe("production HTTP transport", () => {
  it("uses same-origin cookies and CSRF for real mutations", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({saved: true}), {status: 200}));
    vi.stubGlobal("fetch", fetcher);
    document.cookie = "fixrate_csrf=token-for-test; path=/";
    const {request} = await import("./request");
    expect(await request("/api/change", {method: "POST", body: "{}"})).toEqual({saved: true});
    const options = fetcher.mock.calls[0][1];
    expect(options.credentials).toBe("same-origin");
    expect(options.headers.get("X-CSRF-Token")).toBe("token-for-test");
    expect(options.headers.get("Content-Type")).toBe("application/json");
  });
  it("preserves backend errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({detail: "REVISION_CONFLICT"}), {status: 409})));
    const {request} = await import("./request");
    await expect(request("/api/change")).rejects.toThrow("REVISION_CONFLICT");
  });
  it("retains HTTP metadata and validation details without changing the public error message", async () => {
    const details=[{field:"body.email",issue:"Value error"}];
    vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:"Проверьте заполнение полей формы",error:{code:"VALIDATION_ERROR",details}}),{status:422})));
    const {request,ApiError}=await import("./request");
    const failure=await request("/api/change").catch(error=>error);
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({status:422,message:"Проверьте заполнение полей формы",code:"VALIDATION_ERROR",details});
  });
  it("reads tasks from API when demo is disabled", async () => {
    vi.stubEnv("VITE_DEMO_MODE", "false");
    const fetcher = vi.fn().mockResolvedValue(new Response("[]", {status: 200}));
    vi.stubGlobal("fetch", fetcher);
    const {maintenanceApi} = await import("./maintenance");
    expect(await maintenanceApi.listTasks()).toEqual([]);
    expect(fetcher.mock.calls[0][0]).toBe("/api/v1/maintenance/ui/tasks");
  });
  it("never falls back to fixtures on server failure", async () => {
    vi.stubEnv("VITE_DEMO_MODE", "false");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({detail: "Сессия отсутствует"}), {status: 401})));
    const {maintenanceApi} = await import("./maintenance");
    await expect(maintenanceApi.listTasks()).rejects.toThrow("Сессия отсутствует");
  });
});
