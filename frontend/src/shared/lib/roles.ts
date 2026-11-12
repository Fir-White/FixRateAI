import type { Role } from "@/shared/types/domain";

export const SECTION_ROLES: Record<string, Role[]> = {
  dispatcher: ["director", "chief_engineer", "engineer", "admin", "dispatcher"],
  equipment: ["director", "chief_engineer", "admin", "dispatcher", "engineer", "executor"],
  calendar: ["director", "chief_engineer", "dispatcher", "engineer", "executor"],
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
  director:"Просмотр графика и показателей доступных объектов.",chief_engineer:"Утверждение регламентов, планов и исключений; контроль приёмки.",
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
