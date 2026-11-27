import type { Role, SessionProfile } from "@/shared/types/domain";

export const SECTION_ROLES: Record<string, Role[]> = {
  dispatcher: ["director", "chief_engineer", "engineer", "admin", "dispatcher"],
  equipment: ["director", "chief_engineer", "admin", "dispatcher", "engineer", "executor"],
  calendar: ["director", "chief_engineer", "dispatcher", "engineer", "executor"],
  planning: ["director", "chief_engineer", "dispatcher", "engineer", "admin"],
  tasks: ["director", "chief_engineer", "dispatcher", "engineer"],
  comparisons: ["director", "chief_engineer", "dispatcher", "engineer"],
  reports: ["director", "chief_engineer", "dispatcher", "engineer"],
  quality: ["chief_engineer", "engineer"],
  executor: ["executor"],
  service_settings: ["chief_engineer", "admin", "dispatcher", "engineer"],
  workforce_settings: ["chief_engineer", "admin", "dispatcher", "engineer"],
};

export function canOpenSection(role: Role | undefined, section: string): boolean {
  return !!role && !!SECTION_ROLES[section]?.includes(role);
}

const legacyPermissions = {
  engineering_workspace: ["chief_engineer"],
  order_table: ["chief_engineer"],
  review_report: ["chief_engineer"],
  edit_plan: ["chief_engineer","dispatcher","admin"],
  edit_equipment: ["chief_engineer","admin"],
  edit_service: ["chief_engineer","admin"],
  prepare_catalog: ["chief_engineer","admin"],
  edit_source_workbook: ["chief_engineer"],
  site_access: ["chief_engineer","admin"],
  approve_exception: ["chief_engineer"],
} satisfies Record<string, Role[]>;

export function hasPermission(profile: SessionProfile | null | undefined, permission: keyof typeof legacyPermissions): boolean {
  if (!profile) return false;
  if (profile.permissionProfile === "mvp") return profile.permissions?.includes(permission) === true;
  return (legacyPermissions[permission] as readonly Role[]).includes(profile.role);
}

export function taskPathForRole(role: Role | undefined, taskId: string): string | null {
  if (role === "executor") return `/executor/tasks/${taskId}`;
  return canOpenSection(role, "tasks") ? `/tasks/${taskId}` : null;
}

export const canOperate = (role: Role | undefined) => !!role && ["chief_engineer","engineer","dispatcher"].includes(role);

export const ROLE_LABELS: Record<Role, string> = {
  director:"Руководитель",chief_engineer:"Главный инженер",
  admin: "Администратор",
  dispatcher: "Диспетчер",
  engineer: "Инженер",
  executor: "Исполнитель",
};

export const ROLE_DESCRIPTIONS: Record<Role, string> = {
  director:"Просмотр графика и показателей доступных объектов.",chief_engineer:"Регламенты, планирование, назначения, приёмка и доступы сотрудников.",
  admin: "Справочники и доступы. Приёмка требует отдельной роли инженера.",
  dispatcher: "Очередь работ, назначения и контроль просрочек.",
  engineer: "Оперативное планирование, назначения, прогнозы и приёмка работ.",
  executor: "Назначенные задания, чек-лист и фотоотчёт.",
};

export function homePathForRole(role: Role): string {
  switch (role) {
    case "director": return "/director";
    case "chief_engineer": return "/chief-engineer";
    case "engineer": return "/engineer";
    case "executor": return "/executor";
    case "admin": return "/admin";
    case "dispatcher": return "/dispatcher";
  }
}
