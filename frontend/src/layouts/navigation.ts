import type { Role } from "@/shared/types/domain";
import type { IconName } from "@/shared/ui/Icon";
import { SECTION_ROLES } from "@/shared/lib/roles";

export interface NavigationItem {
  to: string;
  label: string;
  icon: IconName;
  roles: readonly Role[];
  end?: boolean;
  group?: string;
  activePaths?: readonly string[];
}

// One source for the role-based sidebar links.
export const NAVIGATION_ITEMS: readonly NavigationItem[] = [
  { to: "/assistant", label: "ИИ-помощник", icon: "assistant", roles: ["director","chief_engineer","engineer","dispatcher","admin","executor"], group: "Помощник" },
  { to: "/dispatcher", label: "Рабочий день", icon: "dashboard", roles: SECTION_ROLES.dispatcher, group: "Работа" },
  { to: "/executor", label: "Мой день", icon: "dashboard", roles: SECTION_ROLES.executor, group: "Моя работа", end: true, activePaths: ["/calendar", "/my-shifts"] },
  { to: "/executor/tasks", label: "Мои задания", icon: "tasks", roles: SECTION_ROLES.executor, group: "Моя работа" },
  { to: "/planning", label: "Планирование ТО", icon: "calendar", roles: SECTION_ROLES.planning, group: "Работа", activePaths: ["/calendar", "/comparisons"] },
  { to: "/tasks", label: "Задания", icon: "tasks", roles: SECTION_ROLES.tasks, group: "Работа" },
  { to: "/quality", label: "Приёмка работ", icon: "quality", roles: SECTION_ROLES.quality, group: "Работа" },
  { to: "/equipment", label: "Оборудование", icon: "equipment", roles: SECTION_ROLES.equipment, group: "Подготовка", activePaths: ["/settings/equipment"] },
  { to: "/settings/workforce", label: "Команда и смены", icon: "workforce", roles: SECTION_ROLES.workforce_settings, group: "Подготовка" },
  { to: "/executor/reports", label: "Мои отчёты", icon: "report", roles: SECTION_ROLES.executor, group: "Моя работа" },
  { to: "/reports", label: "Отчёты", icon: "report", roles: SECTION_ROLES.reports, group: "Аналитика" },
];
