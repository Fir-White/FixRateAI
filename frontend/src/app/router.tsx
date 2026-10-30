import { Route, Routes } from "react-router-dom";
import { RequireRole, RequireSession } from "@/app/guards";
import { AppShell } from "@/layouts/AppShell";
import { ExecutorLayout } from "@/layouts/ExecutorLayout";
import { LoginPage } from "@/pages/LoginPage";
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

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<RequireSession />}>
        <Route path="/" element={<HomeRedirect />} />

        <Route element={<AppShell />}>
          <Route
            path="/dispatcher"
            element={
              <RequireRole roles={["admin", "dispatcher"]}>
                <DispatcherPage />
              </RequireRole>
            }
          />
          <Route path="/equipment" element={<EquipmentPage />} />
          <Route path="/equipment/:equipmentId" element={<EquipmentDetailPage />} />
          <Route
            path="/calendar"
            element={
              <RequireRole roles={["dispatcher", "engineer", "executor"]}>
                <CalendarPage />
              </RequireRole>
            }
          />
          <Route
            path="/tasks"
            element={
              <RequireRole roles={["dispatcher", "engineer"]}>
                <TasksPage />
              </RequireRole>
            }
          />
          <Route
            path="/tasks/:taskId"
            element={
              <RequireRole roles={["dispatcher", "engineer"]}>
                <TaskDetailPage />
              </RequireRole>
            }
          />
          <Route
            path="/comparisons"
            element={
              <RequireRole roles={["dispatcher", "engineer"]}>
                <ComparisonsPage />
              </RequireRole>
            }
          />
          <Route
            path="/comparisons/:runId"
            element={
              <RequireRole roles={["dispatcher", "engineer"]}>
                <ComparisonDetailPage />
              </RequireRole>
            }
          />
          <Route
            path="/quality"
            element={
              <RequireRole roles={["engineer"]}>
                <QualityPage />
              </RequireRole>
            }
          />
          <Route
            path="/quality/:taskId"
            element={
              <RequireRole roles={["engineer"]}>
                <QualityTaskPage />
              </RequireRole>
            }
          />
        </Route>

        <Route
          path="/executor"
          element={
            <RequireRole roles={["executor"]}>
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
