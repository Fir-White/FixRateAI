import { Route, Routes } from "react-router-dom";
import { RequireRole, RequireSession } from "@/app/guards";
import { AppShell } from "@/layouts/AppShell";
import { ExecutorLayout } from "@/layouts/ExecutorLayout";
import { LoginPage } from "@/pages/LoginPage";
import { AuthLayout } from "@/pages/AuthLayout";
import { HomeRedirect } from "@/pages/HomeRedirect";
import { DispatcherPage } from "@/pages/DispatcherPage";
import { EquipmentPage } from "@/pages/EquipmentPage";
import { EquipmentDetailPage } from "@/pages/EquipmentDetailPage";
import { CalendarPage } from "@/pages/CalendarPage";
import { TasksPage } from "@/pages/TasksPage";
import { TaskDetailPage } from "@/pages/TaskDetailPage";
import { ComparisonsPage } from "@/pages/ComparisonsPage";
import { ComparisonDetailPage } from "@/pages/ComparisonDetailPage";
import { ExecutorPage } from "@/pages/ExecutorPage";
import { ExecutorTaskPage } from "@/pages/ExecutorTaskPage";
import { QualityPage } from "@/pages/QualityPage";
import { QualityTaskPage } from "@/pages/QualityTaskPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { ServiceSettingsPage } from "@/pages/ServiceSettingsPage";
import { WorkforceSettingsPage } from "@/pages/WorkforceSettingsPage";
import { RegistrationPage } from "@/pages/RegistrationPage";
import { PersonalShiftsPage } from "@/pages/PersonalShiftsPage";
import { SECTION_ROLES } from "@/shared/lib/roles";

export function AppRouter() {
  return (
    <Routes>
      <Route element={<AuthLayout />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegistrationPage />} />
      </Route>

      <Route element={<RequireSession />}>
        <Route path="/" element={<HomeRedirect />} />

        <Route element={<AppShell />}>
          <Route
            path="/dispatcher"
            element={
              <RequireRole roles={SECTION_ROLES.dispatcher}>
                <DispatcherPage />
              </RequireRole>
            }
          />
          <Route path="/equipment" element={<EquipmentPage />} />
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

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
