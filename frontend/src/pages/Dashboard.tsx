import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  api,
  type AgreementAnalyticsOut,
  type ErrorAnalysisOut,
  type ExecutiveFocusArea,
  type InterventionEffectivenessOut,
  type LifecycleKpiOut,
  type ModelDriftOut,
  type ModelHealthOut,
  type PrioritySummaryRow,
  type ReviewerAgreementSummaryOut,
} from "../api";
import { PriorityBadge } from "../components/Badges";

type Kpis = { total_reports: number; sif_flagged: number; sif_rate: number; avg_confidence: number; queue_size: number };

export function DashboardPage() {
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [lifecycleKpis, setLifecycleKpis] = useState<LifecycleKpiOut | null>(null);
  const [agreement, setAgreement] = useState<AgreementAnalyticsOut | null>(null);
  const [modelHealth, setModelHealth] = useState<ModelHealthOut | null>(null);
  const [errorAnalysis, setErrorAnalysis] = useState<ErrorAnalysisOut | null>(null);
  const [modelDrift, setModelDrift] = useState<ModelDriftOut | null>(null);
  const [interventionEff, setInterventionEff] = useState<InterventionEffectivenessOut | null>(null);
  const [prioritySummary, setPrioritySummary] = useState<PrioritySummaryRow[]>([]);
  const [focusAreas, setFocusAreas] = useState<ExecutiveFocusArea[]>([]);
  const [density, setDensity] = useState<Array<{ group_label: string; sif_count: number; total_count: number; sif_rate: number }>>([]);
  const [groupBy, setGroupBy] = useState<"site" | "department" | "activity">("site");
  const [lsr, setLsr] = useState<Array<{ lsr_category: string; count: number }>>([]);
  const [trend, setTrend] = useState<Array<{ period: string; sif_count: number; total_count: number; sif_rate: number }>>([]);
  const [humanAgreement, setHumanAgreement] = useState<ReviewerAgreementSummaryOut | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      api.kpis(),
      api.lifecycleKpis(),
      api.agreementAnalytics(),
      api.modelHealth(),
      api.errorAnalysis(),
      api.modelDrift(),
      api.interventionEffectiveness(),
      api.prioritySummary(),
      api.density(groupBy),
      api.lsr(),
      api.trend(),
      api.recommendedFocusAreas(),
      api.reviewerAgreement(),
    ])
      .then(([k, lk, ag, mh, ea, md, ie, p, d, l, t, f, ra]) => {
        setKpis(k);
        setLifecycleKpis(lk);
        setAgreement(ag);
        setModelHealth(mh);
        setErrorAnalysis(ea);
        setModelDrift(md);
        setInterventionEff(ie);
        setPrioritySummary(p);
        setDensity(d);
        setLsr(l);
        setFocusAreas(f);
        setTrend(
          t.map((row) => ({
            ...row,
            sif_rate: row.total_count ? Math.round((row.sif_count / row.total_count) * 100) : 0,
          })),
        );
        setHumanAgreement(ra);
      })
      .catch((e) => setError(String(e.message)));
  }, [groupBy]);


  if (error) return <p className="text-risk-critical p-6">{error}</p>;
  if (!kpis) return <p className="text-warm p-6">Loading executive dashboard…</p>;

  return (
    <div className="space-y-6 pb-12">
      <div>
        <h1 className="text-[24px] font-bold text-ink">HSE Leadership & Governance Dashboard</h1>
        <p className="mt-1 text-sm text-warm">
          Human-in-the-loop decision support: Precursor risk monitoring, formal case lifecycle status, and AI governance metrics.
        </p>
      </div>

      {/* Primary Lifecycle KPI Cards */}
      {lifecycleKpis && (
        <section className="space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wider text-warm">
            Active Case Lifecycle & Operations Status
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
            <div className="rounded-xl border border-amber-200 bg-amber-50/50 p-3 shadow-sm">
              <div className="text-[11px] font-semibold text-amber-900">Pending HSE Review</div>
              <div className="mt-1 text-2xl font-bold font-mono text-amber-950">{lifecycleKpis.pending_review}</div>
              <div className="text-[10px] text-amber-800/80">Requires analyst action</div>
            </div>

            <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-3 shadow-sm">
              <div className="text-[11px] font-semibold text-emerald-900">Confirmed SIF</div>
              <div className="mt-1 text-2xl font-bold font-mono text-emerald-950">{lifecycleKpis.confirmed_sif}</div>
              <div className="text-[10px] text-emerald-800/80">Verified high energy hazard</div>
            </div>

            <div className="rounded-xl border border-purple-200 bg-purple-50/50 p-3 shadow-sm">
              <div className="text-[11px] font-semibold text-purple-900">AI Overrides</div>
              <div className="mt-1 text-2xl font-bold font-mono text-purple-950">{lifecycleKpis.ai_overrides}</div>
              <div className="text-[10px] text-purple-800/80">Analyst adjusted label</div>
            </div>

            <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-3 shadow-sm">
              <div className="text-[11px] font-semibold text-blue-900">Open Actions</div>
              <div className="mt-1 text-2xl font-bold font-mono text-blue-950">{lifecycleKpis.open_actions}</div>
              <div className="text-[10px] text-blue-800/80">Assigned / in progress</div>
            </div>

            <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-3 shadow-sm">
              <div className="text-[11px] font-semibold text-rose-900">Overdue Actions</div>
              <div className="mt-1 text-2xl font-bold font-mono text-rose-950">{lifecycleKpis.overdue_actions}</div>
              <div className="text-[10px] text-rose-800/80">Past target due date</div>
            </div>

            <div className="rounded-xl border border-teal-200 bg-teal-50/50 p-3 shadow-sm">
              <div className="text-[11px] font-semibold text-teal-900">Resolved Cases</div>
              <div className="mt-1 text-2xl font-bold font-mono text-teal-950">{lifecycleKpis.resolved_cases}</div>
              <div className="text-[10px] text-teal-800/80">Formally closed with evidence</div>
            </div>

            <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3 shadow-sm">
              <div className="text-[11px] font-semibold text-slate-800">AI/Human Agreement</div>
              <div className="mt-1 text-2xl font-bold font-mono text-slate-900">
                {lifecycleKpis.agreement_rate > 0 ? `${Math.round(lifecycleKpis.agreement_rate * 100)}%` : "N/A"}
              </div>
              <div className="text-[10px] text-slate-600">Decision concordance</div>
            </div>
          </div>
        </section>
      )}

      {/* AI Governance & Human-in-the-Loop Agreement Card */}
      {agreement && agreement.total_reviewed > 0 && (
        <section className="rounded-xl border border-border bg-white p-5 shadow-card">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-[16px] font-semibold text-ink">AI Model Governance & Concordance</h2>
                <span className="rounded bg-indigo-50 border border-indigo-200 px-2 py-0.5 text-[10px] font-mono text-indigo-800">
                  Human-in-the-Loop Retraining Feed
                </span>
              </div>
              <p className="mt-0.5 text-xs text-warm">
                Tracks safety classification alignment between ML inference and authoritative HSE analyst determinations.
              </p>
            </div>
            <div className="text-right text-xs text-warm">
              Total Reviewed Cases: <strong className="text-ink">{agreement.total_reviewed}</strong>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="rounded-lg bg-slate-50 border border-border/80 p-4 space-y-2">
              <div className="text-xs font-semibold text-ink">Classification Agreement Summary</div>
              <div className="space-y-1.5 pt-1 text-xs">
                <div className="flex justify-between">
                  <span className="text-warm">Confirmed as Predicted:</span>
                  <strong className="text-emerald-700">{agreement.confirm_count} ({Math.round(agreement.agreement_rate * 100)}%)</strong>
                </div>
                <div className="flex justify-between">
                  <span className="text-warm">Analyst Overridden:</span>
                  <strong className="text-purple-700">{agreement.override_count} ({Math.round(agreement.override_rate * 100)}%)</strong>
                </div>
                <div className="flex justify-between border-t border-border/50 pt-1">
                  <span className="text-warm">False Positives (Oversensitized):</span>
                  <strong className="text-amber-700">{agreement.false_positive_count}</strong>
                </div>
                <div className="flex justify-between">
                  <span className="text-warm">False Negatives (Missed Hazards):</span>
                  <strong className="text-rose-700">{agreement.false_negative_count}</strong>
                </div>
              </div>
            </div>

            <div className="md:col-span-2 rounded-lg bg-slate-50 border border-border/80 p-4 space-y-2">
              <div className="text-xs font-semibold text-ink">Override Reason Distribution (Governance Signal)</div>
              {Object.keys(agreement.reason_breakdown).length > 0 ? (
                <div className="space-y-2 pt-1">
                  {Object.entries(agreement.reason_breakdown).map(([reason, count]) => {
                    const pct = Math.round((count / (agreement.override_count || 1)) * 100);
                    return (
                      <div key={reason} className="space-y-0.5">
                        <div className="flex justify-between text-xs">
                          <span className="text-ink truncate max-w-[80%]">{reason}</span>
                          <span className="font-mono text-warm">{count} ({pct}%)</span>
                        </div>
                        <div className="h-1.5 w-full rounded-full bg-slate-200 overflow-hidden">
                          <div className="h-full bg-purple-600 rounded-full" style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-xs italic text-warm pt-2">No analyst overrides recorded in the current dataset.</p>
              )}
            </div>
          </div>
        </section>
      )}

      {/* Model Health & Inter-Rater Reliability Panel */}
      {modelHealth && (
        <section className="rounded-xl border border-border bg-white p-5 shadow-card space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-[16px] font-semibold text-ink">Model Health & Inter-Rater Reliability (Cohen's Kappa)</h2>
                {modelDrift?.has_regression && (
                  <span className="rounded bg-rose-100 border border-rose-300 px-2 py-0.5 text-[10px] font-semibold text-rose-800">
                    Drift Warning: Performance Regression Detected
                  </span>
                )}
              </div>
              <p className="mt-0.5 text-xs text-warm">
                Evaluates statistical concordance between model inference and HSE expert determinations across model iterations.
              </p>
            </div>
            {modelHealth.insufficient_data && (
              <div className="rounded bg-amber-50 border border-amber-200 px-2.5 py-1 text-[11px] text-amber-800 font-medium">
                Insufficient Sample (&lt;10 reviews). Metrics tentative.
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {/* Confusion Matrix Card */}
            <div className="rounded-lg bg-slate-50 border border-border/80 p-4">
              <div className="text-xs font-semibold text-ink mb-2">Confusion Matrix (2×2)</div>
              <div className="grid grid-cols-2 gap-2 text-center text-xs font-mono">
                <div className="rounded border border-emerald-300 bg-emerald-50 p-2">
                  <div className="text-[10px] text-emerald-700 font-sans">True Positives</div>
                  <div className="text-lg font-bold text-emerald-900">{modelHealth.confusion_matrix.tp}</div>
                </div>
                <div className="rounded border border-amber-300 bg-amber-50 p-2">
                  <div className="text-[10px] text-amber-700 font-sans">False Positives</div>
                  <div className="text-lg font-bold text-amber-900">{modelHealth.confusion_matrix.fp}</div>
                </div>
                <div className="rounded border border-rose-300 bg-rose-50 p-2">
                  <div className="text-[10px] text-rose-700 font-sans">False Negatives</div>
                  <div className="text-lg font-bold text-rose-900">{modelHealth.confusion_matrix.fn}</div>
                </div>
                <div className="rounded border border-slate-300 bg-slate-100 p-2">
                  <div className="text-[10px] text-slate-600 font-sans">True Negatives</div>
                  <div className="text-lg font-bold text-slate-800">{modelHealth.confusion_matrix.tn}</div>
                </div>
              </div>
            </div>

            {/* Cohen's Kappa Card */}
            <div className="rounded-lg bg-slate-50 border border-border/80 p-4 flex flex-col justify-between">
              <div>
                <div className="text-xs font-semibold text-ink">AI-to-Human Kappa Index</div>
                <div className="mt-2 text-3xl font-bold font-mono text-indigo-900">{modelHealth.cohen_kappa}</div>
                <div className="mt-1 text-[11px] text-warm">
                  {modelHealth.cohen_kappa >= 0.8
                    ? "Almost Perfect Agreement"
                    : modelHealth.cohen_kappa >= 0.6
                    ? "Substantial Agreement"
                    : modelHealth.cohen_kappa >= 0.4
                    ? "Moderate Agreement"
                    : modelHealth.cohen_kappa >= 0.2
                    ? "Fair Agreement"
                    : "Slight / Poor Agreement"}
                </div>
              </div>
              <div className="mt-3 border-t border-border/60 pt-2 text-[11px] text-warm flex justify-between">
                <span>Agreement Rate:</span>
                <strong className="text-ink">{modelHealth.agreement_rate}%</strong>
              </div>
            </div>

            {/* Human Inter-Rater Reliability Card */}
            {humanAgreement && (
              <div className="rounded-lg bg-slate-50 border border-border/80 p-4 flex flex-col justify-between">
                <div>
                  <div className="text-xs font-semibold text-ink">Human Inter-Rater Kappa</div>
                  <div className="mt-2 text-3xl font-bold font-mono text-indigo-900">{humanAgreement.cohens_kappa}</div>
                  <div className="mt-1 text-[11px] text-warm">
                    {humanAgreement.cohens_kappa >= 0.8
                      ? "Almost Perfect Agreement"
                      : humanAgreement.cohens_kappa >= 0.6
                      ? "Substantial Agreement"
                      : humanAgreement.cohens_kappa >= 0.4
                      ? "Moderate Agreement"
                      : humanAgreement.cohens_kappa >= 0.2
                      ? "Fair Agreement"
                      : "Slight / Poor Agreement"}
                  </div>
                </div>
                <div className="mt-3 border-t border-border/60 pt-2 text-[11px] text-warm flex flex-col gap-1">
                  <div className="flex justify-between">
                    <span>Agreement Rate:</span>
                    <strong className="text-ink">{Math.round(humanAgreement.observed_agreement * 100)}%</strong>
                  </div>
                  <div className="flex justify-between">
                    <span>Pairs Reviewed:</span>
                    <strong className="text-ink">{humanAgreement.total_comparison_pairs}</strong>
                  </div>
                </div>
              </div>
            )}

            {/* Error Rates */}
            <div className="rounded-lg bg-slate-50 border border-border/80 p-4 space-y-3">
              <div className="text-xs font-semibold text-ink">Error Rate Breakdown</div>
              <div className="space-y-2 text-xs">
                <div>
                  <div className="flex justify-between text-warm mb-1">
                    <span>False Positive Rate:</span>
                    <strong className="text-amber-800 font-mono">{modelHealth.false_positive_rate}%</strong>
                  </div>
                  <div className="h-1.5 w-full bg-slate-200 rounded-full overflow-hidden">
                    <div className="h-full bg-amber-500 rounded-full" style={{ width: `${Math.min(modelHealth.false_positive_rate, 100)}%` }} />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-warm mb-1">
                    <span>False Negative Rate:</span>
                    <strong className="text-rose-800 font-mono">{modelHealth.false_negative_rate}%</strong>
                  </div>
                  <div className="h-1.5 w-full bg-slate-200 rounded-full overflow-hidden">
                    <div className="h-full bg-rose-500 rounded-full" style={{ width: `${Math.min(modelHealth.false_negative_rate, 100)}%` }} />
                  </div>
                </div>
              </div>
            </div>

            {/* Model Version Performance */}
            <div className="rounded-lg bg-slate-50 border border-border/80 p-4">
              <div className="text-xs font-semibold text-ink mb-2">Agreement by Model Version</div>
              <div className="space-y-1.5 text-xs">
                {Object.entries(modelHealth.agreement_by_model_version).length > 0 ? (
                  Object.entries(modelHealth.agreement_by_model_version).map(([ver, pct]) => (
                    <div key={ver} className="flex justify-between items-center border-b border-border/40 py-1">
                      <span className="font-mono text-warm text-[11px]">{ver}</span>
                      <span className="font-semibold text-ink">{pct}%</span>
                    </div>
                  ))
                ) : (
                  <p className="text-[11px] text-warm italic">No model versions recorded yet.</p>
                )}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Error Analysis Panel */}
      {errorAnalysis && (
        <section className="rounded-xl border border-border bg-white p-5 shadow-card space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
            <div>
              <h2 className="text-[16px] font-semibold text-ink">Systematic Error Analysis & Hazard Categories</h2>
              <p className="mt-0.5 text-xs text-warm">
                Drill-down into false positive and false negative misclassifications to identify training set gaps.
              </p>
            </div>
            <div className="text-xs text-warm">
              FP: <strong className="text-amber-700">{errorAnalysis.false_positives.length}</strong> | FN: <strong className="text-rose-700">{errorAnalysis.false_negatives.length}</strong>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* False Positives Excerpts */}
            <div className="rounded-lg border border-amber-200 bg-amber-50/30 p-4">
              <div className="text-xs font-bold text-amber-900 mb-2 flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-amber-500"></span>
                <span>False Positives (AI flagged SIF, Analyst marked Non-SIF)</span>
              </div>
              {errorAnalysis.false_positives.length > 0 ? (
                <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                  {errorAnalysis.false_positives.map((item) => (
                    <div key={item.report_id} className="rounded border border-amber-200 bg-white p-2.5 text-xs">
                      <div className="flex justify-between font-mono text-[11px] text-warm mb-1">
                        <Link to={`/reports/${item.report_id}`} className="text-cyan-edge font-semibold hover:underline">
                          #{item.source_report_id}
                        </Link>
                        <span>{item.site_name} | {item.model_version}</span>
                      </div>
                      <p className="text-ink italic line-clamp-2">"{item.excerpt}"</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-warm italic py-3">No false positive cases recorded.</p>
              )}
            </div>

            {/* False Negatives Excerpts */}
            <div className="rounded-lg border border-rose-200 bg-rose-50/30 p-4">
              <div className="text-xs font-bold text-rose-900 mb-2 flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-rose-500"></span>
                <span>False Negatives (AI missed SIF, Analyst marked SIF)</span>
              </div>
              {errorAnalysis.false_negatives.length > 0 ? (
                <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                  {errorAnalysis.false_negatives.map((item) => (
                    <div key={item.report_id} className="rounded border border-rose-200 bg-white p-2.5 text-xs">
                      <div className="flex justify-between font-mono text-[11px] text-warm mb-1">
                        <Link to={`/reports/${item.report_id}`} className="text-cyan-edge font-semibold hover:underline">
                          #{item.source_report_id}
                        </Link>
                        <span>{item.site_name} | {item.model_version}</span>
                      </div>
                      <p className="text-ink italic line-clamp-2">"{item.excerpt}"</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-warm italic py-3">No false negative cases recorded.</p>
              )}
            </div>
          </div>
        </section>
      )}

      {/* Safety Intervention Effectiveness Panel */}
      {interventionEff && (
        <section className="rounded-xl border border-border bg-white p-5 shadow-card space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
            <div>
              <h2 className="text-[16px] font-semibold text-ink">Safety Intervention Effectiveness & Closed-Loop Velocity</h2>
              <p className="mt-0.5 text-xs text-warm">
                Tracks the end-to-end impact of AI-assisted corrective action recommendations on workplace safety.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-3">
            <div className="rounded-lg border border-border bg-slate-50 p-3">
              <div className="text-[11px] font-medium text-warm">Recommendations Generated</div>
              <div className="mt-1 text-2xl font-bold font-mono text-ink">{interventionEff.total_recommendations}</div>
            </div>
            <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-3">
              <div className="text-[11px] font-medium text-blue-900">Acceptance Rate</div>
              <div className="mt-1 text-2xl font-bold font-mono text-blue-950">{interventionEff.acceptance_rate}%</div>
              <div className="text-[10px] text-blue-800">{interventionEff.accepted} accepted/edited</div>
            </div>
            <div className="rounded-lg border border-purple-200 bg-purple-50/50 p-3">
              <div className="text-[11px] font-medium text-purple-900">Implementation Rate</div>
              <div className="mt-1 text-2xl font-bold font-mono text-purple-950">{interventionEff.implementation_rate}%</div>
              <div className="text-[10px] text-purple-800">{interventionEff.implemented} in field</div>
            </div>
            <div className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-3">
              <div className="text-[11px] font-medium text-emerald-900">Case Resolution Rate</div>
              <div className="mt-1 text-2xl font-bold font-mono text-emerald-950">{interventionEff.resolution_rate}%</div>
              <div className="text-[10px] text-emerald-800">{interventionEff.resolved} closed</div>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-100 p-3">
              <div className="text-[11px] font-medium text-slate-700">Mean Days to Resolution</div>
              <div className="mt-1 text-2xl font-bold font-mono text-slate-900">
                {interventionEff.mean_days_to_resolution !== null ? `${interventionEff.mean_days_to_resolution}d` : "N/A"}
              </div>
              <div className="text-[10px] text-slate-600">Velocity metric</div>
            </div>
          </div>
        </section>
      )}


      {/* Intervention Priority Distribution */}
      {prioritySummary.length > 0 && (
        <section className="rounded-xl border border-border bg-white p-5 shadow-card">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
            <div>
              <h2 className="text-[16px] font-semibold text-ink">Intervention Priority Distribution</h2>
              <p className="mt-0.5 text-[12px] text-warm">
                Operational risk ranking (0–100) combining SIF probability, barrier failure criticality, recurrence, and cross-site breadth.
              </p>
            </div>
            <span className="rounded bg-black/5 px-2 py-1 text-[11px] font-mono text-warm">business_rules.yaml: priority-v1</span>
          </div>

          <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
            {prioritySummary.map((p) => (
              <div key={p.tier} className="flex flex-col justify-between rounded-lg border border-border/80 bg-neutral-50/50 p-3">
                <div className="flex items-center justify-between">
                  <PriorityBadge tier={p.tier} compact />
                  <span className="text-xs font-semibold text-warm">{p.percentage}%</span>
                </div>
                <div className="mt-3">
                  <div className="text-2xl font-bold text-ink">{p.count}</div>
                  <div className="text-[11px] text-warm">reports in tier</div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Recommended HSE Focus Areas */}
      {focusAreas.length > 0 && (
        <section className="rounded-xl border border-border bg-white p-5 shadow-card">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-[16px] font-semibold text-ink">Recommended HSE Focus Areas</h2>
                <span className="rounded bg-black/5 px-2 py-0.5 text-[10px] font-mono text-warm">Executive Summary</span>
              </div>
              <p className="mt-0.5 text-[12px] text-warm">
                Top systemic intervention priorities ranked by multi-site precursor recurrence, trend velocity, and SIF potential rate.
              </p>
            </div>
            <span className="text-[11px] text-warm">Strategic Resource Allocation</span>
          </div>

          <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
            {focusAreas.map((area, idx) => (
              <div
                key={idx}
                className="flex flex-col justify-between rounded-lg border border-border/80 bg-neutral-50/40 p-4 transition hover:border-border hover:shadow-xs"
              >
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-mono text-xs font-bold text-warm">#{idx + 1}</span>
                    <PriorityBadge tier={area.priority_tier as any} compact />
                  </div>
                  <h3 className="mt-2 text-[14px] font-semibold leading-snug text-ink">{area.area_name}</h3>
                  <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-warm">
                    <span className="rounded border border-border/60 bg-white px-2 py-0.5">
                      {area.site_count} {area.site_count === 1 ? "site" : "sites"}
                    </span>
                    <span className="rounded border border-border/60 bg-white px-2 py-0.5 font-medium">
                      Trend: {area.trend_status.toUpperCase()}
                    </span>
                    <span className="rounded border border-border/60 bg-white px-2 py-0.5">
                      {area.report_count} reports ({Math.round(area.sif_rate * 100)}% SIF)
                    </span>
                  </div>
                  <div className="mt-2 text-[11px] text-warm">
                    <span className="font-semibold text-ink/80">Primary Barrier:</span> {area.primary_barrier_failure}
                  </div>
                  {area.recommended_actions.length > 0 && (
                    <div className="mt-3 border-t border-border/50 pt-2 text-[11px]">
                      <span className="font-semibold text-ink/80">Recommended Focus:</span>
                      <ul className="mt-1 space-y-1 text-ink/90">
                        {area.recommended_actions.map((act, i) => (
                          <li key={i} className="flex items-start gap-1.5 leading-tight">
                            <span className="h-1.5 w-1.5 rounded-full bg-emerald-600 mt-1.5 shrink-0" />
                            <span>{act}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
                {area.cluster_id && (
                  <div className="mt-3 border-t border-border/40 pt-2 text-right">
                    <Link
                      to={`/clusters/${area.cluster_id}`}
                      className="text-xs font-medium text-cyan-edge hover:underline"
                    >
                      Inspect precursor cluster →
                    </Link>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Density & Life-Saving Rules Distribution */}
      <div className="flex gap-2">
        {(["site", "department", "activity"] as const).map((g) => (
          <button
            key={g}
            onClick={() => setGroupBy(g)}
            className={`rounded-full border px-3 py-1 text-[13px] font-medium capitalize transition ${
              groupBy === g ? "border-soot bg-soot text-white" : "border-border bg-white text-ink hover:bg-slate-50"
            }`}
          >
            {g}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section className="rounded-xl border border-border bg-white p-5 shadow-card">
          <h2 className="text-[18px] font-semibold text-ink">SIF-density ranking</h2>
          <div className="mt-4 h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={density} layout="vertical" margin={{ left: 24, right: 12 }}>
                <CartesianGrid stroke="#e8e6e5" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="group_label" width={120} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="sif_rate" fill="#0c0a09" name="SIF rate" />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <table className="mt-2 w-full text-left text-[12px] text-warm">
            <thead>
              <tr>
                <th className="py-1 font-medium">Group</th>
                <th>SIF</th>
                <th>Total</th>
                <th>Rate</th>
              </tr>
            </thead>
            <tbody>
              {density.map((row) => (
                <tr key={row.group_label} className="border-t border-border">
                  <td className="py-1 text-ink">{row.group_label}</td>
                  <td>{row.sif_count}</td>
                  <td>{row.total_count}</td>
                  <td>{Math.round(row.sif_rate * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="rounded-xl border border-border bg-white p-5 shadow-card">
          <h2 className="text-[18px] font-semibold text-ink">Life-Saving Rule distribution</h2>
          <p className="mt-0.5 text-[12px] text-warm">Unique reports tagged per canonical rule (all 12 IOGP rules represented)</p>
          <div className="mt-4 h-80">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={lsr} margin={{ bottom: 72, left: 8 }}>
                <CartesianGrid stroke="#e8e6e5" />
                <XAxis dataKey="lsr_category" interval={0} angle={-35} textAnchor="end" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip
                  formatter={(value: any) => [`${value} reports`, "Tagged reports"]}
                  labelFormatter={(label) => `Rule: ${label}`}
                />
                <Bar dataKey="count" fill="#3ba6f1" name="Tagged reports" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      </div>

      <section className="rounded-xl border border-border bg-white p-5 shadow-card">
        <h2 className="text-[18px] font-semibold text-ink">Trend: Volume vs SIF-Potential Rate</h2>
        <div className="mt-4 h-72">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={trend}>
              <CartesianGrid stroke="#e8e6e5" />
              <XAxis dataKey="period" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Line yAxisId="left" type="monotone" dataKey="total_count" stroke="#78716c" name="Total reports" dot={false} />
              <Line yAxisId="right" type="monotone" dataKey="sif_rate" stroke="#dc2626" name="SIF rate %" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
  );
}
