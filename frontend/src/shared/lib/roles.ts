import type { Role } from "@/shared/types/domain";

export const SECTION_ROLES: Record<string, Role[]> = {
  dispatcher: ["executive", "chief_engineer", "engineer", "admin", "dispatcher"],
  equipment: ["executive", "chief_engineer", "admin", "dispatcher", "engineer", "executor"],
  calendar: ["executive", "chief_engineer", "dispatcher", "engineer", "executor"],
  tasks: ["executive", "chief_engineer", "dispatcher", "engineer"],
  comparisons: ["executive", "chief_engineer", "dispatcher", "engineer"],
  reports: ["executive", "chief_engineer", "dispatcher", "engineer"],
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
  executive:"Руководитель",chief_engineer:"Главный инженер",
  admin: "Администратор",
  dispatcher: "Диспетчер",
  engineer: "Инженер",
  executor: "Исполнитель",
};

export const ROLE_DESCRIPTIONS: Record<Role, string> = {
  executive:"Просмотр графика и показателей доступных объектов.",chief_engineer:"Утверждение регламентов, планов и исключений; контроль приёмки.",
  admin: "Справочники и доступы. Приёмка требует отдельной роли инженера.",
  dispatcher: "Очередь работ, назначения и контроль просрочек.",
  engineer: "Оперативное планирование, назначения, прогнозы и приёмка работ.",
  executor: "Назначенные задания, чек-лист и фотоотчёт.",
};

export function homePathForRole(role: Role): string {
  switch (role) {
    case "executor":
      return "/executor";
    case "chief_engineer":
    case "executive":
      return "/dispatcher";
    case "engineer":
      return "/quality";
    case "admin":
    case "dispatcher":
      return "/dispatcher";
  }
}
