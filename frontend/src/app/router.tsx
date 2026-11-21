import { lazy, Suspense } from "react";
import { pageLoaders } from "./pageModules";
import { lazyPage } from "./pageModule";
import { createRoutesFromElements, matchRoutes, Navigate, Route, useLocation, useRoutes } from "react-router-dom";
import { RequireRole, RequireSession } from "@/app/guards";
import { LoadingState } from "@/shared/ui/States";
import { AppShell } from "@/layouts/AppShell";
import { ExecutorLayout } from "@/layouts/ExecutorLayout";
import { LoginPage } from "@/pages/LoginPage";
import { RegistrationPage } from "@/pages/RegistrationPage";
const SetupPage = lazy(() => import("@/pages/SetupPage").then(module => ({ default: module.SetupPage })));
import { HomeRedirect } from "@/pages/HomeRedirect";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { SECTION_ROLES } from "@/shared/lib/roles";
import type { Role } from "@/shared/types/domain";

const DispatcherPage = lazyPage(pageLoaders.DispatcherPage);
const AssistantPage = lazyPage(pageLoaders.AssistantPage);
const PlanningPage = lazyPage(pageLoaders.PlanningPage);
const EquipmentPage = lazyPage(pageLoaders.EquipmentPage);
const EquipmentDetailPage = lazyPage(pageLoaders.EquipmentDetailPage);
const CalendarPage = lazyPage(pageLoaders.CalendarPage);
const TasksPage = lazyPage(pageLoaders.TasksPage);
const TaskDetailPage = lazyPage(pageLoaders.TaskDetailPage);
const ComparisonsPage = lazyPage(pageLoaders.ComparisonsPage);
const ReportsPage = lazyPage(pageLoaders.ReportsPage);
const ComparisonDetailPage = lazyPage(pageLoaders.ComparisonDetailPage);
const ExecutorPage = lazyPage(pageLoaders.ExecutorPage);
const ExecutorTaskPage = lazyPage(pageLoaders.ExecutorTaskPage);
const QualityPage = lazyPage(pageLoaders.QualityPage);
const QualityTaskPage = lazyPage(pageLoaders.QualityTaskPage);
const ServiceSettingsPage = lazyPage(pageLoaders.ServiceSettingsPage);
const WorkforceSettingsPage = lazyPage(pageLoaders.WorkforceSettingsPage);
const ProfilePage = lazyPage(pageLoaders.ProfilePage);
const PersonalShiftsPage = lazyPage(pageLoaders.PersonalShiftsPage);

const WorkspaceLayout = lazy(() => import("@/layouts/WorkspaceLayout").then(module => ({ default: module.WorkspaceLayout })));
const AuthLayout = lazy(() => import("@/pages/AuthLayout").then(module => ({ default: module.AuthLayout })));

function WorkspaceAccess() {
  const location = useLocation();
  // Nested executor routes inherit the restriction declared on their parent.
  const match = matchRoutes(routes, location)?.find(({ route }) => route.handle?.roles);
  const roles: readonly Role[] | undefined = match?.route.handle?.roles;

  return (
    <RequireRole roles={roles}>
      <Suspense fallback={<LoadingState label="Загрузка рабочего пространства" />}>
        <WorkspaceLayout />
      </Suspense>
    </RequireRole>
  );
}

const routes = createRoutesFromElements(
  <>
    <Route element={<Suspense fallback={<div className="auth-pending"><LoadingState label="Загрузка входа" /></div>}><AuthLayout /></Suspense>}>
      <Route path="/setup" element={<Suspense fallback={<LoadingState />}><SetupPage /></Suspense>} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegistrationPage />} />
    </Route>

    <Route element={<RequireSession />}>
      <Route element={<WorkspaceAccess />}>
        <Route path="/" element={<HomeRedirect />} />

        <Route element={<AppShell />}>
          <Route path="/assistant" element={<AssistantPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/director" handle={{ roles: ["director"] }} element={<DispatcherPage />} />
          <Route path="/executive" element={<Navigate to="/director" replace />} />
          <Route path="/chief-engineer" handle={{ roles: ["chief_engineer"] }} element={<DispatcherPage />} />
          <Route path="/engineer" handle={{ roles: ["engineer"] }} element={<DispatcherPage />} />
          <Route path="/admin" handle={{ roles: ["admin"] }} element={<DispatcherPage />} />
          <Route path="/dispatcher" handle={{ roles: SECTION_ROLES.dispatcher }} element={<DispatcherPage />} />
          <Route path="/equipment" element={<EquipmentPage />} />
          <Route path="/planning" handle={{ roles: SECTION_ROLES.planning }} element={<PlanningPage />} />
          <Route path="/equipment/:equipmentId" element={<EquipmentDetailPage />} />
          <Route path="/settings/equipment" handle={{ roles: SECTION_ROLES.service_settings }} element={<ServiceSettingsPage />} />
          <Route path="/settings/workforce" handle={{ roles: SECTION_ROLES.workforce_settings }} element={<WorkforceSettingsPage />} />
          <Route path="/my-shifts" handle={{ roles: SECTION_ROLES.executor }} element={<PersonalShiftsPage />} />
          <Route path="/calendar" handle={{ roles: SECTION_ROLES.calendar }} element={<CalendarPage />} />
          <Route path="/tasks" handle={{ roles: SECTION_ROLES.tasks }} element={<TasksPage />} />
          <Route path="/tasks/:taskId" handle={{ roles: SECTION_ROLES.tasks }} element={<TaskDetailPage />} />
          <Route path="/comparisons" handle={{ roles: SECTION_ROLES.comparisons }} element={<ComparisonsPage />} />
          <Route path="/reports" handle={{ roles: SECTION_ROLES.reports }} element={<ReportsPage />} />
          <Route path="/comparisons/:runId" handle={{ roles: SECTION_ROLES.comparisons }} element={<ComparisonDetailPage />} />
          <Route path="/quality" handle={{ roles: SECTION_ROLES.quality }} element={<QualityPage />} />
          <Route path="/quality/:taskId" handle={{ roles: SECTION_ROLES.quality }} element={<QualityTaskPage />} />
        </Route>

        <Route path="/executor" handle={{ roles: SECTION_ROLES.executor }} element={<ExecutorLayout />} >
          <Route index element={<ExecutorPage />} />
          <Route path="tasks/:taskId" element={<ExecutorTaskPage />} />
        </Route>
        </Route>
    </Route>

    <Route path="*" element={<NotFoundPage />} />
  </>,
);

export function AppRouter() {
  return useRoutes(routes);
}
