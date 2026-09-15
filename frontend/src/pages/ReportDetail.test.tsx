import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

const { api, getStoredUser } = vi.hoisted(() => ({
  api: { report: vi.fn(), reportTimeline: vi.fn(), reportRecommendations: vi.fn(), lsrRules: vi.fn() },
  getStoredUser: vi.fn(),
}));
vi.mock("../api", () => ({ api, getStoredUser }));
import { ReportDetailPage } from "./ReportDetail";

const renderPage = () => render(
  <MemoryRouter initialEntries={["/reports/report-1"]}>
    <Routes><Route path="/reports/:id" element={<ReportDetailPage />} /></Routes>
  </MemoryRouter>,
);

describe("ReportDetailPage", () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset());
    getStoredUser.mockReturnValue({ role: "analyst" });
    api.reportTimeline.mockResolvedValue([]);
    api.reportRecommendations.mockResolvedValue([]);
    api.lsrRules.mockResolvedValue([]);
  });

  it("shows a loading state while report evidence is requested", () => {
    api.report.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByText("Loading report review workspace…")).toBeInTheDocument();
  });

  it("shows a safe error state when the report cannot be loaded", async () => {
    api.report.mockRejectedValue(new Error("not available"));
    renderPage();
    expect(await screen.findByText(/Unable to load report review workspace: not available/)).toBeInTheDocument();
  });
});
