import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, getStoredUser, type LifecycleKpiOut, type ReportSummary } from "../api";
import {
  AssessmentComparisonBadge,
  AiPredictionBadge,
  AnalystDecisionBadge,
  ConfidenceBar,
  LifecycleBadge,
  LsrChip,
  PriorityBadge,
  RiskBadge,
} from "../components/Badges";

type LifecycleTab = "PENDING_REVIEW" | "REVIEWED" | "OPEN_ACTIONS" | "RESOLVED" | "REOPENED" | "ALL";

export function TriagePage() {
  const [items, setItems] = useState<ReportSummary[]>([]);
  const [kpis, setKpis] = useState<LifecycleKpiOut | null>(null);
  const [activeTab, setActiveTab] = useState<LifecycleTab>("PENDING_REVIEW");
  const [sortBy, setSortBy] = useState<"priority" | "sif" | "date">("priority");
  const [siteFilter, setSiteFilter] = useState<string>("all");
  const [sites, setSites] = useState<Array<{ id: string; name: string }>>([]);
  const [error, setError] = useState("");
  const user = getStoredUser();
  const canAct = user?.role === "analyst" || user?.role === "site_manager" || user?.role === "admin";

  useEffect(() => {
    api.sites().then(setSites).catch(console.error);
    api.lifecycleKpis().then(setKpis).catch(console.error);
  }, []);

  useEffect(() => {
    // Determine backend query params based on tab
    let statusFilter: string | undefined = undefined;
    if (activeTab === "PENDING_REVIEW") statusFilter = "AI_ANALYZED";
    else if (activeTab === "REVIEWED") statusFilter = "CONFIRMED";
    else if (activeTab === "OPEN_ACTIONS") statusFilter = "ACTION_ASSIGNED";
    else if (activeTab === "RESOLVED") statusFilter = "RESOLVED";
    else if (activeTab === "REOPENED") statusFilter = "REOPENED";

    api
      .reports({
        lifecycle_status: statusFilter,
        site_id: siteFilter !== "all" ? siteFilter : undefined,
        page_size: 100,
      })
      .then((res) => {
        let filtered = res.items;
        if (activeTab === "PENDING_REVIEW") {
          filtered = res.items.filter(
            (r) => !r.lifecycle_status || ["INGESTED", "AI_ANALYZED", "HSE_REVIEW"].includes(r.lifecycle_status),
          );
        } else if (activeTab === "REVIEWED") {
          filtered = res.items.filter((r) => ["CONFIRMED", "OVERRIDDEN"].includes(r.lifecycle_status ?? ""));
        } else if (activeTab === "OPEN_ACTIONS") {
          filtered = res.items.filter((r) => ["ACTION_ASSIGNED", "IN_PROGRESS"].includes(r.lifecycle_status ?? ""));
        }

        const sorted = [...filtered].sort((a, b) => {
          if (sortBy === "priority") {
            const pDiff = (b.priority?.score ?? 0) - (a.priority?.score ?? 0);
            if (pDiff !== 0) return pDiff;
            return (b.sif_probability ?? 0) - (a.sif_probability ?? 0);
          }
          if (sortBy === "sif") {
            return (b.sif_probability ?? 0) - (a.sif_probability ?? 0);
          }
          return new Date(b.reported_at).getTime() - new Date(a.reported_at).getTime();
        });
        setItems(sorted);
      })
      .catch((e) => setError(e.message));
  }, [activeTab, sortBy, siteFilter]);

  const tabs: Array<{ id: LifecycleTab; label: string; count?: number; color: string }> = [
    {
      id: "PENDING_REVIEW",
      label: "Pending Review",
      count: kpis?.pending_review,
      color: "bg-amber-100 text-amber-900 border-amber-300",
    },
    {
      id: "REVIEWED",
      label: "Reviewed (Confirmed/Overridden)",
      count: (kpis?.confirmed_sif ?? 0) + (kpis?.ai_overrides ?? 0),
      color: "bg-emerald-100 text-emerald-900 border-emerald-300",
    },
    {
      id: "OPEN_ACTIONS",
      label: "Open Actions",
      count: kpis?.open_actions,
      color: "bg-blue-100 text-blue-900 border-blue-300",
    },
    {
      id: "RESOLVED",
      label: "Resolved",
      count: kpis?.resolved_cases,
      color: "bg-teal-100 text-teal-900 border-teal-300",
    },
    {
      id: "REOPENED",
      label: "Reopened",
      count: kpis?.reopened_cases,
      color: "bg-rose-100 text-rose-900 border-rose-300",
    },
    {
      id: "ALL",
      label: "All Cases",
      count: kpis?.total_cases,
      color: "bg-slate-100 text-slate-900 border-slate-300",
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-[24px] font-bold text-ink">HSE Triage & Review Queue</h1>
          <p className="mt-1 text-sm text-warm">
            Deterministic prioritization: Prioritized by Intervention Priority Score, SIF ML probability, and exposure severity.
          </p>
        </div>

        {/* Filters & Sorting */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs text-warm">
            <span>Site:</span>
            <select
              className="rounded-lg border border-border bg-white px-2.5 py-1 text-xs font-medium text-ink"
              value={siteFilter}
              onChange={(e) => setSiteFilter(e.target.value)}
            >
              <option value="all">All Sites</option>
              {sites.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-1.5 text-xs text-warm">
            <span>Rank by:</span>
            <select
              className="rounded-lg border border-border bg-white px-2.5 py-1 text-xs font-medium text-ink"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as "priority" | "sif" | "date")}
            >
              <option value="priority">Intervention Priority Score (0–100)</option>
              <option value="sif">SIF ML Probability</option>
              <option value="date">Most Recent Date</option>
            </select>
          </div>
        </div>
      </div>

      {/* Lifecycle Filter Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-border pb-3">
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
                isActive
                  ? "border-cyan-edge bg-cyan-edge text-white shadow-xs"
                  : "border-border bg-white text-ink hover:bg-slate-50"
              }`}
            >
              <span>{tab.label}</span>
              {tab.count !== undefined && (
                <span
                  className={`rounded-full px-1.5 py-0.2 text-[10px] font-bold ${
                    isActive ? "bg-white/20 text-white" : "bg-slate-100 text-warm"
                  }`}
                >
                  {tab.count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {error && <p className="text-sm font-medium text-risk-critical">{error}</p>}

      {/* Case List */}
      <div className="overflow-hidden rounded-xl border border-border bg-white shadow-card">
        {items.length > 0 ? (
          items.map((row) => (
            <Link
              key={row.id}
              to={`/reports/${row.id}`}
              className="flex flex-col sm:flex-row items-start gap-4 border-b border-border/70 p-5 transition hover:bg-slate-50/80"
            >
              {/* Priority & Score Column */}
              <div className="w-full sm:w-40 shrink-0 space-y-2">
                {row.priority ? (
                  <PriorityBadge tier={row.priority.tier} score={row.priority.score} />
                ) : (
                  <RiskBadge sifLabel={row.sif_label} probability={row.sif_probability} />
                )}
                <div className="pt-1">
                  <div className="text-[10px] uppercase font-semibold tracking-wider text-warm">SIF ML Prob</div>
                  <ConfidenceBar value={row.sif_probability} sifLabel={row.sif_label} />
                </div>
              </div>

              {/* Incident Body */}
              <div className="min-w-0 flex-1 space-y-2">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="font-mono font-bold text-cyan-edge">{row.id}</span>
                  <span className="font-semibold text-ink">{row.site_name || row.site_id}</span>
                  <span className="text-warm">·</span>
                  <span className="text-warm">{row.department || "General"}</span>
                  <span className="text-warm">·</span>
                  <span className="uppercase text-warm">{row.report_type.replace("_", "/")}</span>
                  <span className="text-warm">·</span>
                  <span className="text-warm">{new Date(row.reported_at).toLocaleDateString()}</span>
                  <LifecycleBadge status={row.lifecycle_status} />
<AssessmentComparisonBadge
                     aiLabel={row.sif_label}
                     finalLabel={row.final_sif_label}
                     decision={row.review?.decision}
                   />
                   {row.ai_prediction && (
                     <AiPredictionBadge
                       aiLabel={row.ai_prediction.ai_label}
                       aiProbability={row.ai_prediction.ai_probability}
                       modelVersion={row.ai_prediction.model_version}
                     />
                   )}
                   {row.analyst_decision && (
                     <AnalystDecisionBadge
                       action={row.analyst_decision.review_action}
                       analystLabel={row.analyst_decision.analyst_label}
                       reviewedAt={row.analyst_decision.reviewed_at}
                     />
                   )}
                </div>

                <p className="text-sm text-ink leading-relaxed">{row.excerpt}</p>

                {row.priority && (
                  <div className="text-[11px] text-warm">
                    <span className="font-semibold text-ink">Priority Driver:</span> {row.priority.explanation_summary}
                  </div>
                )}

                {row.priority && (row.priority.tier === "CRITICAL" || row.priority.tier === "HIGH") && (
                  <div className="rounded-md border border-amber-200 bg-amber-50/70 px-3 py-1.5 text-xs text-amber-950">
                    <span className="font-semibold text-amber-900">⚡ Recommended Action Focus: </span>
                    {row.priority.action_recommendation}
                  </div>
                )}

                {/* LSR Chips */}
                {row.lsr_tags && row.lsr_tags.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {row.lsr_tags.map((t, idx) => (
                      <LsrChip
                        key={idx}
                        ruleId={t.rule_id}
                        label={t.rule_name || t.lsr_category}
                        confidence={t.confidence}
                        source={t.source}
                      />
                    ))}
                  </div>
                )}
              </div>

              {/* Right CTA */}
              <div className="shrink-0 self-center">
                <span className="rounded-lg border border-border px-3 py-1.5 text-xs font-semibold text-cyan-edge hover:bg-cyan-edge/10 transition">
                  Review Case →
                </span>
              </div>
            </Link>
          ))
        ) : (
          <div className="p-12 text-center text-sm text-warm">
            No reports found matching the selected filter criteria.
          </div>
        )}
      </div>
    </div>
  );
}
