import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

const { api } = vi.hoisted(() => ({
  api: {
    kpis: vi.fn(), lifecycleKpis: vi.fn(), agreementAnalytics: vi.fn(), modelHealth: vi.fn(), errorAnalysis: vi.fn(), modelDrift: vi.fn(), interventionEffectiveness: vi.fn(), prioritySummary: vi.fn(), density: vi.fn(), lsr: vi.fn(), trend: vi.fn(), recommendedFocusAreas: vi.fn(), reviewerAgreement: vi.fn(), sites: vi.fn(), dashboardFilterOptions: vi.fn(), lsrRules: vi.fn(),
  },
}));
vi.mock("../api", () => ({ api }));
import { DashboardPage } from "./Dashboard";

const deferred = () => new Promise<never>(() => undefined);
const loadDashboard = () => {
  api.kpis.mockResolvedValue({ total_reports: 0, sif_flagged: 0, sif_rate: 0, avg_confidence: 0, queue_size: 0, high_risk_reports: 0, top_risk_site: null, top_lsr: null, top_precursor_pattern: null });
  api.lifecycleKpis.mockResolvedValue(null); api.agreementAnalytics.mockResolvedValue(null); api.modelHealth.mockResolvedValue(null); api.errorAnalysis.mockResolvedValue(null); api.modelDrift.mockResolvedValue(null); api.interventionEffectiveness.mockResolvedValue(null); api.prioritySummary.mockResolvedValue([]); api.density.mockResolvedValue([]); api.lsr.mockResolvedValue([]); api.trend.mockResolvedValue([]); api.recommendedFocusAreas.mockResolvedValue([]); api.reviewerAgreement.mockResolvedValue(null); api.sites.mockResolvedValue([{ id: "site-a", name: "Alpha" }]); api.dashboardFilterOptions.mockResolvedValue({ departments: ["Operations"] }); api.lsrRules.mockResolvedValue([]);
};

describe("DashboardPage", () => {
  beforeEach(() => { Object.values(api).forEach((fn) => fn.mockReset()); });
  it("shows a loading state before dashboard data arrives", () => {
    Object.values(api).forEach((fn) => fn.mockReturnValue(deferred()));
    render(<DashboardPage />);
    expect(screen.getByText("Loading executive dashboard…")).toBeInTheDocument();
  });
  it("shows the empty filtered state using backend KPIs", async () => {
    loadDashboard(); render(<DashboardPage />);
    expect(await screen.findByText(/No reports match the active filters/)).toBeInTheDocument();
    expect(screen.getByText("Clear filters")).toBeDisabled();
  });
  it("passes the shared site filter to the KPI query and displays it", async () => {
    loadDashboard(); render(<DashboardPage />);
    await screen.findByText("Alpha");
    fireEvent.change(screen.getByLabelText("Site"), { target: { value: "site-a" } });
    await waitFor(() => expect(api.kpis).toHaveBeenLastCalledWith({ site_id: "site-a" }));
    expect(screen.getByText(/site id: site-a/)).toBeInTheDocument();
  });
  it("renders a safe error state when KPI loading fails", async () => {
    loadDashboard(); api.kpis.mockRejectedValue(new Error("offline")); render(<DashboardPage />);
    expect(await screen.findByText(/Unable to load the dashboard: offline/)).toBeInTheDocument();
  });
});
