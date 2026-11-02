import type { Role } from "@/shared/types/domain";
import type { IconName } from "@/shared/ui/Icon";

export interface NavigationItem {
  to: string;
  label: string;
  icon: IconName;
  roles: readonly Role[];
  end?: boolean;
}

// One source for the role-based sidebar links.
export const NAVIGATION_ITEMS: readonly NavigationItem[] = [
  { to: "/dispatcher", label: "Панель диспетчера", icon: "dashboard", roles: ["admin", "dispatcher"] },
  { to: "/quality", label: "Контроль качества", icon: "quality", roles: ["engineer"] },
  { to: "/executor", label: "Мои задания", icon: "executor", roles: ["executor"], end: true },
  { to: "/calendar", label: "Календарь ТО", icon: "calendar", roles: ["dispatcher", "engineer", "executor"] },
  { to: "/equipment", label: "Оборудование", icon: "equipment", roles: ["admin", "dispatcher", "engineer", "executor"] },
  { to: "/tasks", label: "Задания", icon: "tasks", roles: ["dispatcher", "engineer"] },
  { to: "/comparisons", label: "Прогнозы", icon: "forecast", roles: ["dispatcher", "engineer"] },
  { to: "/reports", label: "Отчёты", icon: "report", roles: ["dispatcher", "engineer"] },
  { to: "/settings/equipment", label: "Настройка обслуживания", icon: "calendar", roles: ["admin", "dispatcher", "engineer"] },
  { to: "/settings/workforce", label: "Сотрудники и смены", icon: "executor", roles: ["admin", "dispatcher", "engineer"] },
  { to: "/my-shifts", label: "Мои смены", icon: "calendar", roles: ["executor"] },
];
