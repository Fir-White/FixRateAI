import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { PerformanceOverview } from "@/features/analyst/PerformanceOverview";
import { request } from "@/shared/api/request";

vi.mock("@/shared/api/request", () => ({ DEMO_MODE: false, request: vi.fn() }));
beforeEach(() => { vi.mocked(request).mockReset(); });

const site = {
  siteId: "site-1", siteName: "ЖК «Сосновый парк»", jobs: 117, accepted: 38,
  overdue: 7, slaOnTime: 38, slaEligible: 38, actualPersonHours: "28.000",
  actualReports: 40, plannedNormPersonHours: "56.500", confirmedNormJobs: 117,
  loadPersonMinutes: { "2026-06-13": 180, "2026-11-06": 330, "2026-08-25": 240, "2026-10-20": 120 },
};

it("preserves server KPI values, distinct denominators, and the three largest planned loads", async () => {
  vi.mocked(request).mockResolvedValue([site]);
  render(<PerformanceOverview />);
  const region = await screen.findByRole("region", { name: site.siteName });
  const contents = within(region);
  for (const value of ["117", "7", "28.000", "56.500", "40 отчётов", "117 заданий с подтверждённой единицей"]) {
    expect(contents.getByText(value, { exact: true })).toBeInTheDocument();
  }
  expect(contents.getByText("38", { exact: true, selector: "dd" })).toBeInTheDocument();
  expect(contents.getByText("/ 38").parentElement).toHaveTextContent("38 / 38");
  expect(contents.getAllByRole("listitem").map(item => item.querySelector("time")?.dateTime)).toEqual(["2026-11-06", "2026-08-25", "2026-06-13"]);
  expect(contents.getByText("5.50 чел.-ч")).toBeInTheDocument();
  expect(request).toHaveBeenCalledWith("/api/v1/maintenance/overview");
});

it("distinguishes confirmed zero values from unavailable SLA and norm data", async () => {
  vi.mocked(request).mockResolvedValue([{ ...site, slaEligible: 0, actualPersonHours: "0.000", plannedNormPersonHours: null, confirmedNormJobs: 0, loadPersonMinutes: {} }]);
  render(<PerformanceOverview />);
  expect(await screen.findByText("Нет подтверждённых данных")).toBeInTheDocument();
  expect(screen.getByText("0.000")).toBeInTheDocument();
  expect(screen.getByText("Не подтверждена")).toBeInTheDocument();
  expect(screen.getByText("Нет назначений с подтверждённой длительностью.")).toBeInTheDocument();
});

it("applies the selected month only to the existing XLSX URLs without refetching site metrics", async () => {
  vi.mocked(request).mockResolvedValue([site]);
  render(<PerformanceOverview />);
  await screen.findByText(site.siteName);
  fireEvent.change(screen.getByLabelText("Месяц экспорта"), { target: { value: "2027-02" } });
  expect(screen.getByRole("link", { name: "Скачать месячный график XLSX" })).toHaveAttribute("href", "/api/v1/maintenance/export.xlsx?year=2027&month=2&kind=schedule");
  expect(screen.getByRole("link", { name: "Скачать задания XLSX" })).toHaveAttribute("href", "/api/v1/maintenance/export.xlsx?year=2027&month=2&kind=orders");
  expect(request).toHaveBeenCalledTimes(1);
  expect(screen.getByText("56.500")).toBeInTheDocument();
});

it("reports unavailable data without inventing metrics", async () => {
  vi.mocked(request).mockRejectedValue(new Error("Нет доступа к показателям"));
  await act(async () => { render(<PerformanceOverview />); });
  expect(screen.getByRole("alert")).toHaveTextContent("Нет доступа к показателям");
  expect(screen.queryByRole("definition")).not.toBeInTheDocument();
});
