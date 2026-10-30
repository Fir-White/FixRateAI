import {
  demoCalendar,
  demoComparisons,
  demoDecisions,
  demoEquipment,
  demoExecutions,
  demoHistory,
  demoPhotoReviews,
  demoTasks,
} from "@/shared/mocks/data";
import type {
  CalendarOccurrence,
  ComparisonRun,
  EngineerDecision,
  Equipment,
  ExecutionReport,
  MaintenanceTask,
  PhotoReview,
  ServiceHistoryItem,
} from "@/shared/types/domain";

const MOCK_DELAY_MS = 140;

function copy<T>(value: T): T {
  return structuredClone(value);
}

function resolve<T>(value: T): Promise<T> {
  return new Promise((resolvePromise) => {
    window.setTimeout(() => resolvePromise(copy(value)), MOCK_DELAY_MS);
  });
}

function reject(message: string): Promise<never> {
  return new Promise((_, rejectPromise) => {
    window.setTimeout(() => rejectPromise(new Error(message)), MOCK_DELAY_MS);
  });
}

export interface EquipmentBundle {
  equipment: Equipment;
  history: ServiceHistoryItem[];
}

export interface TaskBundle {
  task: MaintenanceTask;
  execution: ExecutionReport | null;
  review: PhotoReview | null;
  decision: EngineerDecision | null;
}

export interface ComparisonBundle {
  run: ComparisonRun;
}

async function listEquipment(): Promise<Equipment[]> {
  return resolve(demoEquipment);
}

async function getEquipment(equipmentId: string): Promise<EquipmentBundle> {
  const equipment = demoEquipment.find((item) => item.id === equipmentId);
  if (!equipment) {
    return reject("Оборудование не найдено или недоступно в текущем объекте");
  }
  return resolve({
    equipment,
    history: demoHistory.filter((item) => item.equipmentId === equipmentId),
  });
}

async function listTasks(): Promise<MaintenanceTask[]> {
  return resolve(demoTasks);
}

async function getTask(taskId: string): Promise<TaskBundle> {
  const task = demoTasks.find((item) => item.id === taskId);
  if (!task) {
    return reject("Задание не найдено или недоступно в текущем объекте");
  }
  const execution =
    demoExecutions.find((item) => item.id === task.activeExecutionId) ?? null;
  return resolve({
    task,
    execution,
    review: execution
      ? (demoPhotoReviews.find((item) => item.executionId === execution.id) ??
        null)
      : null,
    decision:
      demoDecisions.find((item) => item.taskId === task.id) ?? null,
  });
}

async function listExecutorTasks(
  executorId: string,
): Promise<MaintenanceTask[]> {
  const assigned = demoTasks.filter((task) =>
    task.assignees.some((assignee) => assignee.executorId === executorId),
  );
  return resolve(assigned);
}

async function getExecutorTask(taskId: string): Promise<TaskBundle> {
  return getTask(taskId);
}

async function listCalendar(
  year: number,
  month: number,
): Promise<CalendarOccurrence[]> {
  if (year !== 2026 || month !== 10) {
    return resolve([]);
  }
  return resolve(demoCalendar);
}

async function listComparisons(): Promise<ComparisonRun[]> {
  return resolve(demoComparisons);
}

async function getComparison(runId: string): Promise<ComparisonBundle> {
  const run = demoComparisons.find((item) => item.runId === runId);
  if (!run) {
    return reject("Запуск сравнения не найден");
  }
  return resolve({ run });
}

async function listQualityQueue(): Promise<MaintenanceTask[]> {
  return resolve(
    demoTasks.filter(
      (task) => task.state === "submitted" || task.state === "rework_required",
    ),
  );
}

async function getQualityBundle(taskId: string): Promise<TaskBundle> {
  const bundle = await getTask(taskId);
  if (!bundle.task.activeExecutionId) {
    return reject("У задания нет попытки выполнения для проверки");
  }
  return bundle;
}

export const maintenanceApi = {
  listEquipment,
  getEquipment,
  listTasks,
  getTask,
  listExecutorTasks,
  getExecutorTask,
  listCalendar,
  listComparisons,
  getComparison,
  listQualityQueue,
  getQualityBundle,
};
