import { expect, it } from "vitest";
import { hasPermission } from "@/shared/lib/roles";
import type { SessionProfile } from "@/shared/types/domain";

const session = (role: SessionProfile["role"]): SessionProfile => ({
  userId: role, role, name: "Учебная запись", email: "demo@example.test",
  siteName: "Учебный объект", timezone: "UTC",
});

it("uses the server's MVP permission set without changing the stored role", () => {
  for (const role of ["chief_engineer", "engineer"] as const) {
    const profile = {...session(role), permissionProfile: "mvp" as const, permissions: ["engineering_workspace", "order_table"]};
    expect(hasPermission(profile, "engineering_workspace")).toBe(true);
    expect(hasPermission(profile, "order_table")).toBe(true);
    expect(hasPermission(profile, "site_access")).toBe(false);
    expect(hasPermission(profile, "approve_exception")).toBe(false);
    expect(profile.role).toBe(role);
  }
  expect(hasPermission(session("chief_engineer"), "site_access")).toBe(true);
  expect(hasPermission(session("engineer"), "order_table")).toBe(false);
  expect(hasPermission({...session("executor"), permissionProfile: "mvp"}, "order_table")).toBe(false);
});
