import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  api,
  getStoredUser,
  type LsrRuleMetadata,
  type Recommendation,
  type ReportDetail,
  type TimelineEventOut,
} from "../api";
import {
  AssessmentComparisonBadge,
  CategoryBadge,
  ConfidenceBar,
  LifecycleBadge,
  LsrChip,
  PriorityBadge,
  PriorityBreakdownCard,
  RecommendationStatusBadge,
  RiskBadge,
} from "../components/Badges";

function HighlightedText({ text, phrases }: { text: string; phrases: Array<{ phrase: string; weight: number }> }) {
  if (!phrases.length) return <p className="whitespace-pre-wrap">{text}</p>;
  const sorted = [...phrases].sort((a, b) => b.phrase.length - a.phrase.length);
  let remaining = text;
  const parts: Array<{ text: string; hit?: { phrase: string; weight: number } }> = [];
  while (remaining.length) {
    let earliest = -1;
    let match: { phrase: string; weight: number } | undefined;
    let index = -1;
    for (const p of sorted) {
      const i = remaining.toLowerCase().indexOf(p.phrase.toLowerCase());
      if (i >= 0 && (earliest < 0 || i < earliest)) {
        earliest = i;
        match = p;
        index = i;
      }
    }
    if (!match || index < 0) {
      parts.push({ text: remaining });
      break;
    }
    if (index > 0) parts.push({ text: remaining.slice(0, index) });
    parts.push({ text: remaining.slice(index, index + match.phrase.length), hit: match });
    remaining = remaining.slice(index + match.phrase.length);
  }
  return (
    <p className="whitespace-pre-wrap leading-7">
      {parts.map((part, i) =>
        part.hit ? (
          <mark
            key={i}
            className="rounded-[4px] bg-risk-critical-wash px-1.5 py-0.5 text-risk-critical"
            title={`Weight ${part.hit.weight}`}
          >
            {part.text}
          </mark>
        ) : (
          <span key={i}>{part.text}</span>
        ),
      )}
    </p>
  );
}

export function ReportDetailPage() {
  const { id } = useParams();
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [timeline, setTimeline] = useState<TimelineEventOut[]>([]);
  const [lsrRules, setLsrRules] = useState<LsrRuleMetadata[]>([]);
  
  // Status messages
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [recActionMessage, setRecActionMessage] = useState("");

  // Review states
  const [confirmNotes, setConfirmNotes] = useState("");
  const [overrideLabel, setOverrideLabel] = useState<boolean>(false);
  const [overrideReason, setOverrideReason] = useState("False positive - no credible fatal exposure");
  const [overrideCustomReason, setOverrideCustomReason] = useState("");
  const [overrideNotes, setOverrideNotes] = useState("");
  const [isOverrideOpen, setIsOverrideOpen] = useState(false);

  // LSR review states
  const [isLsrModalOpen, setIsLsrModalOpen] = useState(false);
  const [selectedLsrIds, setSelectedLsrIds] = useState<string[]>([]);
  const [lsrReason, setLsrReason] = useState("");

  // Precursor review states
  const [isPrecursorModalOpen, setIsPrecursorModalOpen] = useState(false);
  const [precActivity, setPrecActivity] = useState("");
  const [precLocation, setPrecLocation] = useState("");
  const [precBarrier, setPrecBarrier] = useState("");
  const [precComment, setPrecComment] = useState("");

  // Priority review states
  const [isPriorityModalOpen, setIsPriorityModalOpen] = useState(false);
  const [adjPriorityTier, setAdjPriorityTier] = useState("HIGH");
  const [priorityAdjReason, setPriorityAdjReason] = useState("");

  // Case resolution & reopen states
  const [isResolveModalOpen, setIsResolveModalOpen] = useState(false);
  const [resNotes, setResNotes] = useState("");
  const [resEvidence, setResEvidence] = useState("");
  const [isReopenModalOpen, setIsReopenModalOpen] = useState(false);
  const [reopenReason, setReopenReason] = useState("");

  // Recommendation actions
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editAction, setEditAction] = useState("");
  const [editTitle, setEditTitle] = useState("");
  const [editReason, setEditReason] = useState("");
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  const user = getStoredUser();
  const canReview = user?.role === "analyst" || user?.role === "site_manager" || user?.role === "admin";

  function reload() {
    if (!id) return;
    api.report(id)
      .then((data) => {
        setReport(data);
        setOverrideLabel(!data.sif_label);
        const ruleIds = data.lsr_tags.map((t) => t.rule_id).filter(Boolean) as string[];
        setSelectedLsrIds(ruleIds);
      })
      .catch((e) => setError(e.message));

    api.reportTimeline(id)
      .then(setTimeline)
      .catch((e) => console.error("Could not load timeline:", e));
  }

  function loadRecs() {
    if (!id) return;
    api.reportRecommendations(id)
      .then(setRecommendations)
      .catch((e) => console.error("Could not load recommendations:", e));
  }

  useEffect(() => {
    reload();
    loadRecs();
    api.lsrRules().then(setLsrRules).catch(console.error);
  }, [id]);

  // SIF Confirm
  async function handleConfirmSif(e: FormEvent) {
    e.preventDefault();
    if (!id) return;
    setError("");
    setMessage("");
    try {
      await api.confirmReport(id, { notes: confirmNotes || "HSE Analyst confirmed AI SIF assessment." });
      setMessage("SIF assessment confirmed. Lifecycle advanced to CONFIRMED.");
      setConfirmNotes("");
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to confirm assessment");
    }
  }

  // SIF Override
  async function handleOverrideSif(e: FormEvent) {
    e.preventDefault();
    if (!id) return;
    const finalReason = overrideReason === "Other" ? overrideCustomReason : overrideReason;
    if (!finalReason.trim()) {
      setError("A documented reason is mandatory to override the AI classification.");
      return;
    }
    setError("");
    setMessage("");
    try {
      await api.overrideReport(id, {
        final_sif_label: overrideLabel,
        reason: finalReason,
        notes: overrideNotes || undefined,
      });
      setMessage("AI assessment overridden. Analyst decision and rationale saved to audit log.");
      setIsOverrideOpen(false);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to override assessment");
    }
  }

  // LSR Review
  async function handleSaveLsrReview() {
    if (!id) return;
    try {
      await api.lsrReview(id, {
        selected_rule_ids: selectedLsrIds,
        reason: lsrReason || undefined,
      });
      setIsLsrModalOpen(false);
      setMessage("Life-Saving Rules tags updated with analyst verification.");
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save LSR review");
    }
  }

  // Precursor Review
  async function handleSavePrecursorReview() {
    if (!id) return;
    try {
      await api.precursorReview(id, {
        activity: precActivity || undefined,
        location_asset: precLocation || undefined,
        barrier_failure: precBarrier || undefined,
        comment: precComment || undefined,
      });
      setIsPrecursorModalOpen(false);
      setMessage("Precursor feedback saved for safety modeling and retraining.");
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save precursor review");
    }
  }

  // Priority Review
  async function handleSavePriorityReview() {
    if (!id || !priorityAdjReason.trim()) {
      alert("A reason is mandatory to adjust the priority tier.");
      return;
    }
    try {
      await api.priorityReview(id, {
        priority_tier: adjPriorityTier,
        reason: priorityAdjReason,
      });
      setIsPriorityModalOpen(false);
      setMessage("Priority tier adjusted and recorded.");
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to adjust priority");
    }
  }

  // Resolve Case
  async function handleResolveCase() {
    if (!id || !resNotes.trim()) {
      alert("Resolution notes and verification evidence are mandatory.");
      return;
    }
    try {
      await api.resolveReport(id, {
        resolution_notes: resNotes,
        evidence_reference: resEvidence || undefined,
      });
      setIsResolveModalOpen(false);
      setMessage("Case formally marked as RESOLVED with audit verification.");
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to resolve case");
    }
  }

  // Reopen Case
  async function handleReopenCase() {
    if (!id || !reopenReason.trim()) {
      alert("A justification is mandatory to reopen a resolved case.");
      return;
    }
    try {
      await api.reopenReport(id, { reason: reopenReason });
      setIsReopenModalOpen(false);
      setMessage("Case REOPENED for further HSE review.");
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reopen case");
    }
  }

  // Recommendation actions
  async function handleAcceptRec(recId: string) {
    try {
      setRecActionMessage("");
      await api.acceptRecommendation(recId);
      loadRecs();
      reload();
      setRecActionMessage("Recommendation accepted by HSE analyst.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to accept");
    }
  }

  async function handleSaveEditRec(recId: string) {
    if (!editAction.trim()) return;
    try {
      setRecActionMessage("");
      await api.editRecommendation(recId, {
        edited_title: editTitle || undefined,
        edited_action: editAction,
        reason: editReason || undefined,
      });
      setEditingId(null);
      loadRecs();
      reload();
      setRecActionMessage("Recommendation modification recorded.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save edit");
    }
  }

  async function handleRejectRec(recId: string) {
    if (!rejectReason.trim()) {
      alert("A reason is mandatory to reject a recommendation.");
      return;
    }
    try {
      setRecActionMessage("");
      await api.rejectRecommendation(recId, rejectReason);
      setRejectingId(null);
      setRejectReason("");
      loadRecs();
      reload();
      setRecActionMessage("Recommendation rejected with documented rationale.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reject");
    }
  }

  async function handleImplementRec(recId: string) {
    const owner = prompt("Assign owner for this action (e.g. Site HSE Lead / Rig Superintendent):");
    if (owner === null) return;
    try {
      setRecActionMessage("");
      await api.implementRecommendation(recId, {
        assigned_owner: owner || "Site HSE Team",
        resolution_notes: "Action assigned and implemented in field.",
      });
      loadRecs();
      reload();
      setRecActionMessage("Action marked as implemented.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to implement");
    }
  }

  async function handleResolveRec(recId: string) {
    const notes = prompt("Enter resolution verification notes:");
    if (notes === null) return;
    try {
      setRecActionMessage("");
      await api.resolveRecommendation(recId, { resolution_notes: notes || "Verification completed." });
      loadRecs();
      reload();
      setRecActionMessage("Recommendation successfully resolved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to resolve");
    }
  }

  if (error && !report) return <p className="text-risk-critical p-6">{error}</p>;
  if (!report) return <p className="text-warm p-6">Loading report review workspace…</p>;

  return (
    <div className="space-y-6 pb-12">
      {/* Top Breadcrumb & Actions */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border pb-4">
        <div>
          <Link to="/triage" className="text-[13px] font-medium text-cyan-edge hover:underline">
            ← Back to Triage Queue
          </Link>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <h1 className="text-[22px] font-bold text-ink">
              HSE Case Workspace: <span className="font-mono text-cyan-edge">{report.id}</span>
            </h1>
            <LifecycleBadge status={report.lifecycle_status} />
            <AssessmentComparisonBadge
              aiLabel={report.sif_label}
              finalLabel={report.final_sif_label}
              decision={report.review?.decision}
            />
          </div>
          <p className="mt-0.5 text-[13px] text-warm">
            Site: <strong className="text-ink">{report.site_name || report.site_id}</strong> · Department:{" "}
            <strong className="text-ink">{report.department || "General"}</strong> · Shift:{" "}
            <strong className="text-ink">{report.shift || "—"}</strong> · Type:{" "}
            <strong className="text-ink">{report.report_type.replace("_", "/")}</strong>
          </p>
        </div>

        {/* Global Case Actions */}
        <div className="flex flex-wrap items-center gap-2">
          {report.lifecycle_status !== "RESOLVED" ? (
            <button
              onClick={() => setIsResolveModalOpen(true)}
              className="rounded-lg bg-teal-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-teal-700 transition"
            >
              Formal Case Resolution
            </button>
          ) : (
            <button
              onClick={() => setIsReopenModalOpen(true)}
              className="rounded-lg bg-rose-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-rose-700 transition"
            >
              Reopen Case
            </button>
          )}
        </div>
      </div>

      {message && (
        <div className="rounded-lg bg-emerald-50 border border-emerald-300 p-3 text-sm font-medium text-emerald-900 flex items-center justify-between">
          <span>{message}</span>
          <button onClick={() => setMessage("")} className="text-xs text-emerald-700 underline">Dismiss</button>
        </div>
      )}

      {error && (
        <div className="rounded-lg bg-rose-50 border border-rose-300 p-3 text-sm font-medium text-rose-900 flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError("")} className="text-xs text-rose-700 underline">Dismiss</button>
        </div>
      )}

      {/* Main Two-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-[1.9fr_1.1fr] gap-6 items-start">
        {/* Left Column: Report Evidence, AI Assessment, Corrective Actions */}
        <div className="space-y-6">
          {/* Section 1: Report Evidence */}
          <section className="rounded-xl border border-border bg-white p-5 shadow-card">
            <div className="flex items-center justify-between border-b border-border pb-2.5">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-warm">
                1. Incident Narrative & Highlighted Evidence
              </h2>
              <span className="text-[11px] text-warm font-mono">PII-Redacted</span>
            </div>
            <div className="mt-3 text-sm text-ink leading-relaxed">
              <HighlightedText text={report.raw_text_redacted} phrases={report.contributing_phrases} />
            </div>
            {report.contributing_phrases.length > 0 && (
              <div className="mt-4 pt-3 border-t border-border/60">
                <span className="text-xs font-semibold text-warm">Top ML Salient Terms: </span>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {report.contributing_phrases.map((p, i) => (
                    <span
                      key={i}
                      className="rounded bg-rose-50 border border-rose-200 px-2 py-0.5 text-xs font-medium text-rose-800"
                    >
                      {p.phrase} <span className="text-[10px] text-rose-600 font-mono">({p.weight > 0 ? `+${p.weight.toFixed(2)}` : p.weight.toFixed(2)})</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </section>

          {/* Section 2: AI Safety Assessment (Immutable Baseline) */}
          <section className="rounded-xl border border-indigo-200 bg-indigo-50/20 p-5 shadow-card">
            <div className="flex items-center justify-between border-b border-indigo-100 pb-2.5">
              <div className="flex items-center gap-2">
                <span className="rounded bg-indigo-600 text-white text-[10px] font-bold px-2 py-0.5 uppercase tracking-wider">
                  AI Assessment
                </span>
                <h2 className="text-sm font-semibold text-indigo-950">
                  2. Automated SIF & Precursor Evaluation
                </h2>
              </div>
              <span className="text-xs font-mono text-indigo-800">
                Model: {report.model_version || "tfidf-logreg-v1"}
              </span>
            </div>

            <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="rounded-lg bg-white border border-indigo-100 p-3">
                <div className="text-[11px] font-medium text-warm">AI SIF Probability</div>
                <div className="mt-1 flex items-baseline gap-1.5">
                  <span className="text-xl font-bold font-mono text-ink">
                    {Math.round((report.sif_probability ?? 0) * 100)}%
                  </span>
                  <ConfidenceBar value={report.sif_probability} sifLabel={report.sif_label} />
                </div>
              </div>

              <div className="rounded-lg bg-white border border-indigo-100 p-3">
                <div className="text-[11px] font-medium text-warm">AI Classification</div>
                <div className="mt-1">
                  <RiskBadge sifLabel={report.sif_label} probability={report.sif_probability} />
                </div>
              </div>

              <div className="rounded-lg bg-white border border-indigo-100 p-3">
                <div className="text-[11px] font-medium text-warm">AI Priority Tier</div>
                <div className="mt-1">
                  <PriorityBadge tier={report.priority?.tier} score={report.priority?.score} compact />
                </div>
              </div>

              <div className="rounded-lg bg-white border border-indigo-100 p-3">
                <div className="text-[11px] font-medium text-warm">Safety Precursor Cluster</div>
                <div className="mt-1">
                  {report.cluster_id ? (
                    <Link
                      to={`/clusters/${report.cluster_id}`}
                      className="text-xs font-semibold text-cyan-edge hover:underline"
                    >
                      Cluster #{report.cluster_id.slice(-4)} →
                    </Link>
                  ) : (
                    <span className="text-xs text-warm">Isolated occurrence</span>
                  )}
                </div>
              </div>
            </div>

            <div className="mt-3 text-[11px] text-indigo-900/80 bg-indigo-100/50 rounded-md p-2">
              🔒 <strong>AI Result Immutability Guarantee:</strong> Original model probability and features remain permanent and are never overwritten by analyst actions.
            </div>
          </section>

          {/* Section 3: AI-Assisted Corrective Actions & Implementation */}
          <section className="rounded-xl border border-border bg-white p-5 shadow-card">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-[15px] font-semibold text-ink">3. Corrective & Preventive Action Plan</h2>
                  <span className="rounded bg-black/5 px-2 py-0.5 text-[10px] font-mono text-warm">
                    Evidence-Assisted
                  </span>
                </div>
                <p className="mt-0.5 text-[12px] text-warm">
                  Specific engineering and administrative barrier recommendations with full execution lifecycle.
                </p>
              </div>
            </div>

            {recActionMessage && (
              <div className="mt-3 rounded-md bg-emerald-50 p-2.5 text-xs font-medium text-emerald-800">
                {recActionMessage}
              </div>
            )}

            <div className="mt-4 space-y-4">
              {recommendations.length > 0 ? (
                recommendations.map((rec) => {
                  const isEditing = editingId === rec.id;
                  const isRejecting = rejectingId === rec.id;

                  return (
                    <div
                      key={rec.id}
                      className="rounded-lg border border-border bg-slate-50/50 p-4 transition hover:border-border/90"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-2 border-b border-border/60 pb-2.5">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <CategoryBadge category={rec.category} />
                            <h3 className="text-sm font-semibold text-ink">{rec.title}</h3>
                          </div>
                          <div className="flex items-center gap-3 text-[11px] text-warm">
                            <span>Target: <strong className="text-ink">{rec.activity || "Field Operation"}</strong></span>
                            {rec.assigned_owner && (
                              <span>Owner: <strong className="text-indigo-700">{rec.assigned_owner}</strong></span>
                            )}
                            {rec.due_date && (
                              <span>Due: <strong className="text-amber-700">{new Date(rec.due_date).toLocaleDateString()}</strong></span>
                            )}
                          </div>
                        </div>
                        <RecommendationStatusBadge status={rec.status} />
                      </div>

                      <div className="mt-3 text-xs leading-relaxed text-ink">
                        {isEditing ? (
                          <div className="space-y-2">
                            <input
                              type="text"
                              className="w-full rounded border border-muted p-2 text-xs"
                              placeholder="Title"
                              value={editTitle}
                              onChange={(e) => setEditTitle(e.target.value)}
                            />
                            <textarea
                              className="w-full rounded border border-muted p-2 text-xs"
                              rows={3}
                              placeholder="Action text"
                              value={editAction}
                              onChange={(e) => setEditAction(e.target.value)}
                            />
                            <input
                              type="text"
                              className="w-full rounded border border-muted p-2 text-xs"
                              placeholder="Reason for change (optional)"
                              value={editReason}
                              onChange={(e) => setEditReason(e.target.value)}
                            />
                            <div className="flex gap-2">
                              <button
                                onClick={() => handleSaveEditRec(rec.id)}
                                className="rounded bg-indigo-600 px-3 py-1 text-xs font-semibold text-white hover:bg-indigo-700"
                              >
                                Save Changes
                              </button>
                              <button
                                onClick={() => setEditingId(null)}
                                className="rounded border border-muted px-3 py-1 text-xs text-warm hover:bg-muted"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : (
                          <p className="font-medium">{rec.action}</p>
                        )}
                      </div>

                      {rec.rationale && !isEditing && (
                        <div className="mt-2 text-[11px] text-warm italic bg-white p-2 rounded border border-border/40">
                          <strong>Rationale:</strong> {rec.rationale}
                        </div>
                      )}

                      {rec.resolution_notes && (
                        <div className="mt-2 text-[11px] text-teal-800 bg-teal-50/70 p-2 rounded border border-teal-200">
                          <strong>Verification Notes:</strong> {rec.resolution_notes}
                        </div>
                      )}

                      {/* Reject Form */}
                      {isRejecting && (
                        <div className="mt-3 rounded border border-rose-200 bg-rose-50 p-3 space-y-2">
                          <div className="text-xs font-semibold text-rose-900">Reason for Rejection (Required):</div>
                          <input
                            type="text"
                            className="w-full rounded border border-rose-300 p-2 text-xs"
                            placeholder="e.g. Existing barrier is already certified; redundant action"
                            value={rejectReason}
                            onChange={(e) => setRejectReason(e.target.value)}
                          />
                          <div className="flex gap-2">
                            <button
                              onClick={() => handleRejectRec(rec.id)}
                              className="rounded bg-rose-600 px-3 py-1 text-xs font-semibold text-white hover:bg-rose-700"
                            >
                              Confirm Rejection
                            </button>
                            <button
                              onClick={() => setRejectingId(null)}
                              className="rounded border border-rose-300 px-3 py-1 text-xs text-rose-800 hover:bg-rose-100"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      )}

                      {/* Action buttons */}
                      {canReview && !isEditing && !isRejecting && (
                        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border/40 pt-2.5">
                          {rec.status === "PENDING_REVIEW" && (
                            <>
                              <button
                                onClick={() => handleAcceptRec(rec.id)}
                                className="rounded bg-emerald-600 px-3 py-1 text-xs font-semibold text-white shadow-xs hover:bg-emerald-700"
                              >
                                Accept Action
                              </button>
                              <button
                                onClick={() => {
                                  setEditingId(rec.id);
                                  setEditAction(rec.action);
                                  setEditTitle(rec.title);
                                  setEditReason("");
                                }}
                                className="rounded border border-indigo-300 px-3 py-1 text-xs font-semibold text-indigo-700 hover:bg-indigo-50"
                              >
                                Edit
                              </button>
                              <button
                                onClick={() => {
                                  setRejectingId(rec.id);
                                  setRejectReason("");
                                }}
                                className="rounded border border-rose-300 px-3 py-1 text-xs font-semibold text-rose-700 hover:bg-rose-50"
                              >
                                Reject
                              </button>
                            </>
                          )}

                          {(rec.status === "ACCEPTED" || rec.status === "EDITED") && (
                            <button
                              onClick={() => handleImplementRec(rec.id)}
                              className="rounded bg-purple-600 px-3 py-1 text-xs font-semibold text-white shadow-xs hover:bg-purple-700"
                            >
                              Assign & Mark Implemented
                            </button>
                          )}

                          {rec.status === "IMPLEMENTED" && (
                            <button
                              onClick={() => handleResolveRec(rec.id)}
                              className="rounded bg-teal-600 px-3 py-1 text-xs font-semibold text-white shadow-xs hover:bg-teal-700"
                            >
                              Verify & Resolve
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })
              ) : (
                <p className="text-xs italic text-warm">No active action recommendations for this case.</p>
              )}
            </div>
          </section>
        </div>

        {/* Right Column: HSE Review Controls, Life-Saving Rules, Case Timeline */}
        <div className="space-y-6">
          {/* Section 4: HSE Decision Workspace */}
          {canReview && (
            <section className="rounded-xl border-2 border-cyan-edge/40 bg-white p-5 shadow-card space-y-4">
              <div className="border-b border-border pb-2.5">
                <div className="flex items-center gap-2">
                  <span className="rounded bg-cyan-edge text-white text-[10px] font-bold px-2 py-0.5 uppercase tracking-wider">
                    HSE Decision
                  </span>
                  <h2 className="text-sm font-semibold text-ink">4. Analyst Confirmation & Override</h2>
                </div>
                <p className="text-[11px] text-warm mt-0.5">
                  Make the authoritative safety determination without altering AI baseline records.
                </p>
              </div>

              {/* Current Decision Summary */}
              {report.review ? (
                <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-ink">Current Decision:</span>
                    <span className="font-bold text-indigo-700">{report.review.decision}</span>
                  </div>
                  <div className="text-xs text-warm">
                    Final Label: <strong className="text-ink">{report.final_sif_label ? "SIF Potential" : "Non-SIF"}</strong>
                  </div>
                  {report.review.reason && (
                    <div className="text-xs text-warm">
                      Reason: <span className="italic text-ink">{report.review.reason}</span>
                    </div>
                  )}
                  {report.review.notes && (
                    <div className="text-xs text-warm">
                      Notes: <span>{report.review.notes}</span>
                    </div>
                  )}
                </div>
              ) : null}

              {/* Confirm / Override Actions */}
              {!isOverrideOpen ? (
                <div className="space-y-3">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-ink">Analyst Review Notes (Optional):</label>
                    <textarea
                      className="w-full rounded-md border border-muted p-2 text-xs outline-none focus:ring-1 focus:ring-cyan-edge"
                      rows={2}
                      placeholder="e.g. Verified evidence aligns with well control SIF criteria."
                      value={confirmNotes}
                      onChange={(e) => setConfirmNotes(e.target.value)}
                    />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={handleConfirmSif}
                      className="flex-1 rounded-md bg-emerald-600 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-700 transition"
                    >
                      Confirm AI Assessment
                    </button>
                    <button
                      onClick={() => setIsOverrideOpen(true)}
                      className="flex-1 rounded-md border border-rose-400 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-800 hover:bg-rose-100 transition"
                    >
                      Override AI Assessment
                    </button>
                  </div>
                </div>
              ) : (
                /* Override Form */
                <form onSubmit={handleOverrideSif} className="space-y-3 rounded-lg border border-rose-300 bg-rose-50/50 p-3">
                  <div className="text-xs font-bold text-rose-950">Override AI Safety Assessment</div>

                  <div className="space-y-1">
                    <label className="text-[11px] font-semibold text-rose-900">Final SIF Determination:</label>
                    <div className="flex gap-4">
                      <label className="flex items-center gap-1.5 text-xs text-ink cursor-pointer">
                        <input
                          type="radio"
                          name="override_sif"
                          checked={overrideLabel === true}
                          onChange={() => setOverrideLabel(true)}
                        />
                        <span>SIF Potential</span>
                      </label>
                      <label className="flex items-center gap-1.5 text-xs text-ink cursor-pointer">
                        <input
                          type="radio"
                          name="override_sif"
                          checked={overrideLabel === false}
                          onChange={() => setOverrideLabel(false)}
                        />
                        <span>Non-SIF</span>
                      </label>
                    </div>
                  </div>

                  <div className="space-y-1">
                    <label className="text-[11px] font-semibold text-rose-900">Reason for Override (Mandatory):</label>
                    <select
                      className="w-full rounded border border-rose-300 bg-white p-1.5 text-xs"
                      value={overrideReason}
                      onChange={(e) => setOverrideReason(e.target.value)}
                    >
                      <option value="False positive - no credible fatal exposure">False positive — no credible fatal exposure</option>
                      <option value="False negative - high energy hazard was omitted">False negative — high energy hazard was omitted</option>
                      <option value="Insufficient evidence in report">Insufficient evidence in report</option>
                      <option value="Context misunderstood by NLP">Context misunderstood by NLP</option>
                      <option value="Incorrect barrier failure interpretation">Incorrect barrier failure interpretation</option>
                      <option value="Other">Other (specify below)</option>
                    </select>
                  </div>

                  {overrideReason === "Other" && (
                    <input
                      type="text"
                      className="w-full rounded border border-rose-300 bg-white p-1.5 text-xs"
                      placeholder="Specify custom override reason"
                      value={overrideCustomReason}
                      onChange={(e) => setOverrideCustomReason(e.target.value)}
                    />
                  )}

                  <div className="space-y-1">
                    <label className="text-[11px] font-semibold text-rose-900">Detailed Justification Notes:</label>
                    <textarea
                      className="w-full rounded border border-rose-300 bg-white p-1.5 text-xs"
                      rows={2}
                      placeholder="Explain the operational context and barrier rationale..."
                      value={overrideNotes}
                      onChange={(e) => setOverrideNotes(e.target.value)}
                    />
                  </div>

                  <div className="flex gap-2 pt-1">
                    <button
                      type="submit"
                      className="rounded bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-rose-700"
                    >
                      Save Override
                    </button>
                    <button
                      type="button"
                      onClick={() => setIsOverrideOpen(false)}
                      className="rounded border border-rose-300 px-3 py-1.5 text-xs text-rose-800 hover:bg-rose-100"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}

              {/* Auxiliary Reviews: LSR, Precursor, Priority */}
              <div className="pt-2 border-t border-border flex flex-wrap gap-2">
                <button
                  onClick={() => setIsLsrModalOpen(true)}
                  className="rounded-md border border-border px-2.5 py-1 text-[11px] font-medium text-ink hover:bg-muted"
                >
                  Review LSR Tags
                </button>
                <button
                  onClick={() => setIsPrecursorModalOpen(true)}
                  className="rounded-md border border-border px-2.5 py-1 text-[11px] font-medium text-ink hover:bg-muted"
                >
                  Correct Precursors
                </button>
                <button
                  onClick={() => setIsPriorityModalOpen(true)}
                  className="rounded-md border border-border px-2.5 py-1 text-[11px] font-medium text-ink hover:bg-muted"
                >
                  Adjust Priority
                </button>
              </div>
            </section>
          )}

          {/* Section 5: Life-Saving Rules Inspection */}
          <section className="rounded-xl border border-border bg-white p-5 shadow-card">
            <div className="flex items-center justify-between border-b border-border pb-2.5">
              <h2 className="text-sm font-semibold text-ink">Life-Saving Rules (IOGP)</h2>
              <span className="text-[11px] font-medium text-warm">Canonical 12</span>
            </div>

            <div className="mt-3 space-y-2.5">
              {report.lsr_tags.length > 0 ? (
                report.lsr_tags.map((t) => (
                  <div
                    key={`${t.rule_id || t.lsr_category}-${t.source}`}
                    className="rounded-lg border border-border bg-slate-50/70 p-3"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        {t.rule_id && (
                          <span className="mr-1.5 inline-block rounded bg-cyan-edge/10 px-1.5 py-0.5 text-[10px] font-bold text-cyan-edge">
                            {t.rule_id}
                          </span>
                        )}
                        <span className="text-xs font-semibold text-ink">{t.rule_name || t.lsr_category}</span>
                      </div>
                      <span className="text-[10px] font-mono rounded bg-white px-1.5 py-0.5 border border-border text-warm">
                        {t.source === "analyst" ? "Analyst Verified" : `${Math.round(t.confidence * 100)}% AI`}
                      </span>
                    </div>

                    {t.evidence && t.evidence.length > 0 && (
                      <div className="mt-2 text-[11px] space-y-0.5 text-warm">
                        {t.evidence.map((ev, idx) => (
                          <div key={idx} className="flex items-baseline gap-1">
                            <span className="text-[9px] font-bold uppercase text-slate-500">[{ev.type}]</span>
                            <span className="text-ink">{ev.text}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))
              ) : (
                <p className="text-xs italic text-warm">No Life-Saving Rules tagged for this case.</p>
              )}
            </div>
          </section>

          {/* Section 6: Priority Component Card */}
          {report.priority && <PriorityBreakdownCard priority={report.priority} />}

          {/* Section 7: Case Timeline & Audit Trail */}
          <section className="rounded-xl border border-border bg-white p-5 shadow-card">
            <div className="flex items-center justify-between border-b border-border pb-2.5">
              <h2 className="text-sm font-semibold text-ink">Case Timeline & Audit Trail</h2>
              <span className="text-[11px] text-warm">{timeline.length} Events</span>
            </div>

            <div className="mt-3 relative pl-4 border-l-2 border-slate-200 space-y-4">
              {timeline.map((ev) => (
                <div key={ev.id} className="relative group">
                  <div className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full bg-cyan-edge border-2 border-white" />
                  <div className="text-xs font-semibold text-ink">{ev.title}</div>
                  <div className="text-[11px] text-warm">{ev.description}</div>
                  <div className="text-[10px] text-warm/70 mt-0.5 font-mono">
                    {new Date(ev.timestamp).toLocaleString()} {ev.user_name ? `· by ${ev.user_name}` : ""}
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>

      {/* MODALS */}

      {/* LSR Review Modal */}
      {isLsrModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="w-full max-w-xl rounded-xl bg-white p-6 shadow-2xl space-y-4 max-h-[85vh] overflow-y-auto">
            <div className="border-b border-border pb-2">
              <h3 className="text-base font-bold text-ink">Review & Edit Life-Saving Rules</h3>
              <p className="text-xs text-warm">
                Select applicable rules from the canonical 12 IOGP Life-Saving Rules taxonomy.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {lsrRules.map((rule) => {
                const isChecked = selectedLsrIds.includes(rule.rule_id);
                return (
                  <label
                    key={rule.rule_id}
                    className={`flex items-start gap-2 rounded-lg border p-2.5 cursor-pointer text-xs transition ${
                      isChecked ? "border-cyan-edge bg-cyan-edge/5" : "border-border hover:bg-slate-50"
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="mt-0.5"
                      checked={isChecked}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedLsrIds([...selectedLsrIds, rule.rule_id]);
                        } else {
                          setSelectedLsrIds(selectedLsrIds.filter((id) => id !== rule.rule_id));
                        }
                      }}
                    />
                    <div>
                      <div className="font-semibold text-ink">
                        <span className="text-cyan-edge mr-1">{rule.rule_id}</span>
                        {rule.name}
                      </div>
                      <div className="text-[10px] text-warm line-clamp-1">{rule.description}</div>
                    </div>
                  </label>
                );
              })}
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-ink">Rationale for Tag Modification:</label>
              <input
                type="text"
                className="w-full rounded border border-muted p-2 text-xs"
                placeholder="e.g. High pressure line rupture warrants Line of Fire rule"
                value={lsrReason}
                onChange={(e) => setLsrReason(e.target.value)}
              />
            </div>

            <div className="flex justify-end gap-2 border-t border-border pt-3">
              <button
                onClick={() => setIsLsrModalOpen(false)}
                className="rounded-md border border-border px-4 py-1.5 text-xs text-warm hover:bg-muted"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveLsrReview}
                className="rounded-md bg-cyan-edge px-4 py-1.5 text-xs font-semibold text-white hover:opacity-90"
              >
                Save LSR Selection
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Precursor Review Modal */}
      {isPrecursorModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-2xl space-y-4">
            <div className="border-b border-border pb-2">
              <h3 className="text-base font-bold text-ink">Correct Precursor Information</h3>
              <p className="text-xs text-warm">Structured feedback for precursor extraction and clustering.</p>
            </div>

            <div className="space-y-3">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-ink">Operational Activity:</label>
                <input
                  type="text"
                  className="w-full rounded border border-muted p-2 text-xs"
                  placeholder="e.g. Coil Tubing / Well Intervention"
                  value={precActivity}
                  onChange={(e) => setPrecActivity(e.target.value)}
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-ink">Location / Asset:</label>
                <input
                  type="text"
                  className="w-full rounded border border-muted p-2 text-xs"
                  placeholder="e.g. Wellhead Cellar Deck"
                  value={precLocation}
                  onChange={(e) => setPrecLocation(e.target.value)}
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-ink">Barrier Failure / Precursor:</label>
                <input
                  type="text"
                  className="w-full rounded border border-muted p-2 text-xs"
                  placeholder="e.g. Lubricator pack-off seal leakage"
                  value={precBarrier}
                  onChange={(e) => setPrecBarrier(e.target.value)}
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-ink">Comments:</label>
                <input
                  type="text"
                  className="w-full rounded border border-muted p-2 text-xs"
                  placeholder="Additional context on the barrier failure"
                  value={precComment}
                  onChange={(e) => setPrecComment(e.target.value)}
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 border-t border-border pt-3">
              <button
                onClick={() => setIsPrecursorModalOpen(false)}
                className="rounded-md border border-border px-4 py-1.5 text-xs text-warm hover:bg-muted"
              >
                Cancel
              </button>
              <button
                onClick={handleSavePrecursorReview}
                className="rounded-md bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700"
              >
                Save Precursor Feedback
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Priority Review Modal */}
      {isPriorityModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-2xl space-y-4">
            <div className="border-b border-border pb-2">
              <h3 className="text-base font-bold text-ink">Adjust Priority Tier</h3>
              <p className="text-xs text-warm">
                AI Calculated Score: <strong>{report.priority?.score.toFixed(1) || "N/A"}</strong> ({report.priority?.tier})
              </p>
            </div>

            <div className="space-y-3">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-ink">Adjusted Priority Tier:</label>
                <select
                  className="w-full rounded border border-muted p-2 text-xs"
                  value={adjPriorityTier}
                  onChange={(e) => setAdjPriorityTier(e.target.value)}
                >
                  <option value="CRITICAL">CRITICAL</option>
                  <option value="HIGH">HIGH</option>
                  <option value="MEDIUM">MEDIUM</option>
                  <option value="LOW">LOW</option>
                </select>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-ink">Reason for Adjustment (Mandatory):</label>
                <textarea
                  className="w-full rounded border border-muted p-2 text-xs"
                  rows={3}
                  placeholder="Explain why field conditions warrant priority elevation or de-escalation..."
                  value={priorityAdjReason}
                  onChange={(e) => setPriorityAdjReason(e.target.value)}
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 border-t border-border pt-3">
              <button
                onClick={() => setIsPriorityModalOpen(false)}
                className="rounded-md border border-border px-4 py-1.5 text-xs text-warm hover:bg-muted"
              >
                Cancel
              </button>
              <button
                onClick={handleSavePriorityReview}
                className="rounded-md bg-amber-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-amber-700"
              >
                Save Adjusted Priority
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Case Resolution Modal */}
      {isResolveModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-2xl space-y-4">
            <div className="border-b border-border pb-2">
              <h3 className="text-base font-bold text-teal-950">Formal Case Resolution</h3>
              <p className="text-xs text-warm">
                Close this HSE case with documented verification evidence and closure notes.
              </p>
            </div>

            <div className="space-y-3">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-ink">Resolution Notes (Mandatory):</label>
                <textarea
                  className="w-full rounded border border-muted p-2 text-xs"
                  rows={3}
                  placeholder="Detail how physical barriers were verified and corrective actions closed out..."
                  value={resNotes}
                  onChange={(e) => setResNotes(e.target.value)}
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-ink">Evidence / Audit Reference (Optional):</label>
                <input
                  type="text"
                  className="w-full rounded border border-muted p-2 text-xs"
                  placeholder="e.g. Work Order #WO-9942 / Signed JSA Certificate"
                  value={resEvidence}
                  onChange={(e) => setResEvidence(e.target.value)}
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 border-t border-border pt-3">
              <button
                onClick={() => setIsResolveModalOpen(false)}
                className="rounded-md border border-border px-4 py-1.5 text-xs text-warm hover:bg-muted"
              >
                Cancel
              </button>
              <button
                onClick={handleResolveCase}
                className="rounded-md bg-teal-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-teal-700"
              >
                Confirm Resolution
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Case Reopen Modal */}
      {isReopenModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-2xl space-y-4">
            <div className="border-b border-border pb-2">
              <h3 className="text-base font-bold text-rose-950">Reopen Resolved Case</h3>
              <p className="text-xs text-warm">Return case to HSE Review if recurring hazards or new signals appear.</p>
            </div>

            <div className="space-y-3">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-ink">Reason for Reopening (Mandatory):</label>
                <textarea
                  className="w-full rounded border border-rose-300 p-2 text-xs"
                  rows={3}
                  placeholder="e.g. Recurring pressure anomaly detected during subsequent shift..."
                  value={reopenReason}
                  onChange={(e) => setReopenReason(e.target.value)}
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 border-t border-border pt-3">
              <button
                onClick={() => setIsReopenModalOpen(false)}
                className="rounded-md border border-border px-4 py-1.5 text-xs text-warm hover:bg-muted"
              >
                Cancel
              </button>
              <button
                onClick={handleReopenCase}
                className="rounded-md bg-rose-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-rose-700"
              >
                ↺ Reopen Case
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
