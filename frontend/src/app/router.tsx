import { lazy, Suspense } from "react";
import { pageLoaders } from "./pageModules";
import { lazyPage } from "./pageModule";
import { Navigate, Route, Routes } from "react-router-dom";
import { RequireRole, RequireSession } from "@/app/guards";
import { LoadingState } from "@/shared/ui/States";
import { AppShell } from "@/layouts/AppShell";
import { ExecutorLayout } from "@/layouts/ExecutorLayout";
import { LoginPage } from "@/pages/LoginPage";
import { AuthLayout } from "@/pages/AuthLayout";
import { HomeRedirect } from "@/pages/HomeRedirect";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { SECTION_ROLES } from "@/shared/lib/roles";

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
const RegistrationPage = lazyPage(pageLoaders.RegistrationPage);
const ProfilePage = lazyPage(pageLoaders.ProfilePage);
const PersonalShiftsPage = lazyPage(pageLoaders.PersonalShiftsPage);

const WorkspaceLayout = lazy(() => import("@/layouts/WorkspaceLayout").then(module => ({ default: module.WorkspaceLayout })));

export function AppRouter() {
  return (
    <Routes>
      <Route element={<AuthLayout />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegistrationPage />} />
      </Route>

      <Route element={<RequireSession />}>
        <Route element={<Suspense fallback={<LoadingState label="Загрузка рабочего пространства" />}><WorkspaceLayout /></Suspense>}>
        <Route path="/" element={<HomeRedirect />} />

        <Route element={<AppShell />}>
          <Route path="/assistant" element={<AssistantPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/director" element={<RequireRole roles={["director"]}><DispatcherPage /></RequireRole>} />
          <Route path="/executive" element={<Navigate to="/director" replace />} />
          <Route path="/chief-engineer" element={<RequireRole roles={["chief_engineer"]}><DispatcherPage /></RequireRole>} />
          <Route path="/engineer" element={<RequireRole roles={["engineer"]}><DispatcherPage /></RequireRole>} />
          <Route path="/admin" element={<RequireRole roles={["admin"]}><DispatcherPage /></RequireRole>} />
          <Route
            path="/dispatcher"
            element={
              <RequireRole roles={SECTION_ROLES.dispatcher}>
                <DispatcherPage />
              </RequireRole>
            }
          />
          <Route path="/equipment" element={<EquipmentPage />} />
          <Route path="/planning" element={<RequireRole roles={SECTION_ROLES.planning}><PlanningPage /></RequireRole>} />
          <Route path="/equipment/:equipmentId" element={<EquipmentDetailPage />} />
          <Route path="/settings/equipment" element={<RequireRole roles={SECTION_ROLES.service_settings}><ServiceSettingsPage /></RequireRole>} />
          <Route path="/settings/workforce" element={<RequireRole roles={SECTION_ROLES.workforce_settings}><WorkforceSettingsPage /></RequireRole>} />
          <Route path="/my-shifts" element={<RequireRole roles={SECTION_ROLES.executor}><PersonalShiftsPage /></RequireRole>} />
          <Route
            path="/calendar"
            element={
              <RequireRole roles={SECTION_ROLES.calendar}>
                <CalendarPage />
              </RequireRole>
            }
          />
          <Route
            path="/tasks"
            element={
              <RequireRole roles={SECTION_ROLES.tasks}>
                <TasksPage />
              </RequireRole>
            }
          />
          <Route
            path="/tasks/:taskId"
            element={
              <RequireRole roles={SECTION_ROLES.tasks}>
                <TaskDetailPage />
              </RequireRole>
            }
          />
          <Route
            path="/comparisons"
            element={
              <RequireRole roles={SECTION_ROLES.comparisons}>
                <ComparisonsPage />
              </RequireRole>
            }
          />
          <Route path="/reports" element={<RequireRole roles={SECTION_ROLES.reports}><ReportsPage /></RequireRole>} />
          <Route
            path="/comparisons/:runId"
            element={
              <RequireRole roles={SECTION_ROLES.comparisons}>
                <ComparisonDetailPage />
              </RequireRole>
            }
          />
          <Route
            path="/quality"
            element={
              <RequireRole roles={SECTION_ROLES.quality}>
                <QualityPage />
              </RequireRole>
            }
          />
          <Route
            path="/quality/:taskId"
            element={
              <RequireRole roles={SECTION_ROLES.quality}>
                <QualityTaskPage />
              </RequireRole>
            }
          />
        </Route>

        <Route
          path="/executor"
          element={
            <RequireRole roles={SECTION_ROLES.executor}>
              <ExecutorLayout />
            </RequireRole>
          }
        >
          <Route index element={<ExecutorPage />} />
          <Route path="tasks/:taskId" element={<ExecutorTaskPage />} />
        </Route>
        </Route>
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
