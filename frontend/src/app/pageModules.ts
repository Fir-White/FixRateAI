import { pageModule } from "./pageModule";

/** Route modules are shared by React.lazy and navigation intent prefetch. */
export const pageLoaders = {
  PlanningPage: pageModule(() => import("@/pages/PlanningPage").then(module => ({ default: module.PlanningPage }))),
  DispatcherPage: pageModule(() => import("@/pages/DispatcherPage").then(module => ({ default: module.DispatcherPage }))),
  EquipmentPage: pageModule(() => import("@/pages/EquipmentPage").then(module => ({ default: module.EquipmentPage }))),
  EquipmentDetailPage: pageModule(() => import("@/pages/EquipmentDetailPage").then(module => ({ default: module.EquipmentDetailPage }))),
  CalendarPage: pageModule(() => import("@/pages/CalendarPage").then(module => ({ default: module.CalendarPage }))),
  TasksPage: pageModule(() => import("@/pages/TasksPage").then(module => ({ default: module.TasksPage }))),
  TaskDetailPage: pageModule(() => import("@/pages/TaskDetailPage").then(module => ({ default: module.TaskDetailPage }))),
  ComparisonsPage: pageModule(() => import("@/pages/ComparisonsPage").then(module => ({ default: module.ComparisonsPage }))),
  ReportsPage: pageModule(() => import("@/pages/ReportsPage").then(module => ({ default: module.ReportsPage }))),
  ComparisonDetailPage: pageModule(() => import("@/pages/ComparisonDetailPage").then(module => ({ default: module.ComparisonDetailPage }))),
  ExecutorPage: pageModule(() => import("@/pages/ExecutorPage").then(module => ({ default: module.ExecutorPage }))),
  ExecutorTaskPage: pageModule(() => import("@/pages/ExecutorTaskPage").then(module => ({ default: module.ExecutorTaskPage }))),
  QualityPage: pageModule(() => import("@/pages/QualityPage").then(module => ({ default: module.QualityPage }))),
  QualityTaskPage: pageModule(() => import("@/pages/QualityTaskPage").then(module => ({ default: module.QualityTaskPage }))),
  ServiceSettingsPage: pageModule(() => import("@/pages/ServiceSettingsPage").then(module => ({ default: module.ServiceSettingsPage }))),
  WorkforceSettingsPage: pageModule(() => import("@/pages/WorkforceSettingsPage").then(module => ({ default: module.WorkforceSettingsPage }))),
  RegistrationPage: pageModule(() => import("@/pages/RegistrationPage").then(module => ({ default: module.RegistrationPage }))),
  ProfilePage: pageModule(() => import("@/pages/ProfilePage").then(module => ({ default: module.ProfilePage }))),
  PersonalShiftsPage: pageModule(() => import("@/pages/PersonalShiftsPage").then(module => ({ default: module.PersonalShiftsPage }))),
};

const byPath: Record<string, () => Promise<unknown>> = {
  "/planning": pageLoaders.PlanningPage,
  "/equipment": pageLoaders.EquipmentPage,
  "/calendar": pageLoaders.CalendarPage,
  "/tasks": pageLoaders.TasksPage,
  "/quality": pageLoaders.QualityPage,
  "/reports": pageLoaders.ReportsPage,
  "/comparisons": pageLoaders.ComparisonsPage,
  "/settings/equipment": pageLoaders.ServiceSettingsPage,
  "/settings/workforce": pageLoaders.WorkforceSettingsPage,
  "/profile": pageLoaders.ProfilePage,
  "/my-shifts": pageLoaders.PersonalShiftsPage,
  "/executor": pageLoaders.ExecutorPage,
  "/chief-engineer": pageLoaders.DispatcherPage,
  "/director": pageLoaders.DispatcherPage,
  "/dispatcher": pageLoaders.DispatcherPage,
  "/admin": pageLoaders.DispatcherPage,
  "/engineer": pageLoaders.DispatcherPage,
  "/register": pageLoaders.RegistrationPage,
};

export function preloadPage(path: string) {
  return byPath[path]?.();
}
