import type { Role } from "@/shared/types/domain";
import type { IconName } from "@/shared/ui/Icon";
import { SECTION_ROLES } from "@/shared/lib/roles";

export interface NavigationItem {
  to: string;
  label: string;
  icon: IconName;
  roles: readonly Role[];
  end?: boolean;
}

// One source for the role-based sidebar links.
export const NAVIGATION_ITEMS: readonly NavigationItem[] = [
  { to: "/dispatcher", label: "Обзор", icon: "dashboard", roles: SECTION_ROLES.dispatcher },
  { to: "/quality", label: "Контроль качества", icon: "quality", roles: SECTION_ROLES.quality },
  { to: "/executor", label: "Мои задания", icon: "executor", roles: SECTION_ROLES.executor, end: true },
  { to: "/calendar", label: "Календарь ТО", icon: "calendar", roles: SECTION_ROLES.calendar },
  { to: "/equipment", label: "Оборудование", icon: "equipment", roles: SECTION_ROLES.equipment },
  { to: "/tasks", label: "Задания", icon: "tasks", roles: SECTION_ROLES.tasks },
  { to: "/comparisons", label: "Прогнозы", icon: "forecast", roles: SECTION_ROLES.comparisons },
  { to: "/reports", label: "Отчёты", icon: "report", roles: SECTION_ROLES.reports },
  { to: "/settings/equipment", label: "Настройка обслуживания", icon: "calendar", roles: SECTION_ROLES.service_settings },
  { to: "/settings/workforce", label: "Сотрудники и смены", icon: "executor", roles: SECTION_ROLES.workforce_settings },
  { to: "/my-shifts", label: "Мои смены", icon: "calendar", roles: SECTION_ROLES.executor },
];
