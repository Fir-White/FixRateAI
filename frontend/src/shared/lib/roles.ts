import type { Role } from "@/shared/types/domain";

export const SECTION_ROLES: Record<string, Role[]> = {
  dispatcher: ["admin", "dispatcher"],
  equipment: ["admin", "dispatcher", "engineer", "executor"],
  calendar: ["dispatcher", "engineer", "executor"],
  tasks: ["dispatcher", "engineer"],
  comparisons: ["dispatcher", "engineer"],
  quality: ["engineer"],
  executor: ["executor"],
};

export function canOpenSection(role: Role | undefined, section: string): boolean {
  return !!role && !!SECTION_ROLES[section]?.includes(role);
}

export function taskPathForRole(role: Role | undefined, taskId: string): string | null {
  if (role === "executor") return `/executor/tasks/${taskId}`;
  return canOpenSection(role, "tasks") ? `/tasks/${taskId}` : null;
}

export const ROLE_LABELS: Record<Role, string> = {
  admin: "Администратор",
  dispatcher: "Диспетчер",
  engineer: "Инженер",
  executor: "Исполнитель",
};

export const ROLE_DESCRIPTIONS: Record<Role, string> = {
  admin: "Справочники и доступы. Приёмка требует отдельной роли инженера.",
  dispatcher: "Очередь работ, назначения и контроль просрочек.",
  engineer: "Регламенты, прогнозы, проверка фото и приёмка работ.",
  executor: "Назначенные задания, чек-лист и фотоотчёт.",
};

export function homePathForRole(role: Role): string {
  switch (role) {
    case "executor":
      return "/executor";
    case "engineer":
      return "/quality";
    case "admin":
    case "dispatcher":
      return "/dispatcher";
  }
}
