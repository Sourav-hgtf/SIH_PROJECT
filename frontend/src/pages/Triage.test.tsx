import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

const { api, getStoredUser } = vi.hoisted(() => ({
  api: {
    sites: vi.fn(), lifecycleKpis: vi.fn(), triageProgress: vi.fn(), reports: vi.fn(),
    confirmReport: vi.fn(), overrideReport: vi.fn(),
  },
  getStoredUser: vi.fn(),
}));
vi.mock("../api", () => ({ api, getStoredUser }));
import { TriagePage } from "./Triage";

const report = {
  id: "report-1", report_type: "near_miss", site_id: "site-a", site_name: "Alpha", department: "Operations",
  reported_at: "2026-01-01T00:00:00Z", sif_label: true, sif_probability: 0.91, lsr_tags: [],
  excerpt: "A crane lift had insufficient exclusion-zone control.", lifecycle_status: "AI_ANALYZED" as const,
  ai_prediction: { ai_label: true, ai_probability: 0.91, model_version: "semantic-v1" }, precursor_summary: "crane lifting | yard | exclusion zone",
};

describe("TriagePage", () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset());
    getStoredUser.mockReturnValue({ role: "analyst" });
    api.sites.mockResolvedValue([]);
    api.lifecycleKpis.mockResolvedValue({ pending_review: 1, confirmed_sif: 2, ai_overrides: 1, open_actions: 0, resolved_cases: 0, reopened_cases: 0, total_cases: 4 });
    api.triageProgress.mockResolvedValue({ reviewed: 3, remaining: 1, confirmed_sif: 2, overridden: 1 });
    api.reports.mockResolvedValue({ items: [report], total: 1 });
    api.confirmReport.mockResolvedValue({});
    api.overrideReport.mockResolvedValue({});
  });

  const renderPage = () => render(<MemoryRouter><TriagePage /></MemoryRouter>);

  it("shows prediction evidence and progress, then confirms without mutating the prediction", async () => {
    renderPage();
    expect(await screen.findByText("report-1")).toBeInTheDocument();
    expect(screen.getByText("Reviewed")).toBeInTheDocument();
    expect(screen.getByText(/crane lift had insufficient/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirm SIF" }));
    await waitFor(() => expect(api.confirmReport).toHaveBeenCalledWith("report-1", { notes: undefined }));
    expect(api.overrideReport).not.toHaveBeenCalled();
  });

  it("requires a comment before an analyst overrides the immutable AI decision", async () => {
    renderPage();
    await screen.findByText("report-1");
    fireEvent.click(screen.getByRole("button", { name: "Mark Non-SIF" }));
    expect(await screen.findByText(/Add an analyst comment/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Analyst comment for report-1"), { target: { value: "No credible fatal exposure" } });
    fireEvent.click(screen.getByRole("button", { name: "Mark Non-SIF" }));
    await waitFor(() => expect(api.overrideReport).toHaveBeenCalledWith("report-1", expect.objectContaining({ final_sif_label: false, reason: "No credible fatal exposure" })));
  });
});
