export function riskTier(sifLabel?: boolean | null, probability?: number | null): "critical" | "medium" | "low" | "unclassified" {
  if (sifLabel == null) return "unclassified";
  if (sifLabel && (probability ?? 0) >= 0.7) return "critical";
  if (sifLabel) return "medium";
  return "low";
}

export function RiskBadge({ sifLabel, probability }: { sifLabel?: boolean | null; probability?: number | null }) {
  const tier = riskTier(sifLabel, probability);
  const map = {
    critical: { label: "Critical SIF", dot: "bg-rose-500", cls: "bg-rose-50 text-rose-800 border-rose-200" },
    medium: { label: "Medium SIF", dot: "bg-amber-500", cls: "bg-amber-50 text-amber-800 border-amber-200" },
    low: { label: "Low Risk", dot: "bg-emerald-500", cls: "bg-emerald-50 text-emerald-800 border-emerald-200" },
    unclassified: { label: "Unclassified", dot: "bg-slate-400", cls: "bg-slate-50 text-slate-700 border-slate-200" },
  }[tier];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold tracking-wide ${map.cls}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${map.dot}`} />
      <span>{map.label}</span>
    </span>
  );
}


export function ConfidenceBar({ value, sifLabel }: { value?: number | null; sifLabel?: boolean | null }) {
  const pct = Math.round((value ?? 0) * 100);
  const tier = riskTier(sifLabel, value);
  const fill =
    tier === "critical" ? "bg-risk-critical" : tier === "medium" ? "bg-risk-medium" : tier === "low" ? "bg-risk-low" : "bg-ash";
  return (
    <span className="inline-flex items-center gap-2">
      <span className="h-1.5 w-10 overflow-hidden rounded-full bg-muted">
        <span className={`block h-full ${fill}`} style={{ width: `${pct}%` }} />
      </span>
      <span className="text-[11px] text-warm">{pct}%</span>
    </span>
  );
}

export function LsrChip({
  label,
  source,
  ruleId,
  confidence,
}: {
  label: string;
  source?: string;
  ruleId?: string;
  confidence?: number;
}) {
  const confText = confidence != null ? `${Math.round(confidence * 100)}%` : null;
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-cyan-edge bg-cyan-edge/5 px-2.5 py-0.5 text-[11px] font-medium text-ink"
      title={`${ruleId ? `${ruleId}: ` : ""}${label}${source ? ` (Source: ${source})` : ""}${confText ? ` - Classifier confidence: ${confText}` : ""}`}
    >
      {ruleId ? <span className="font-semibold text-cyan-edge">{ruleId}</span> : null}
      <span>{label}</span>
      {confText ? <span className="rounded bg-black/5 px-1 py-0.2 text-[10px] text-warm">{confText}</span> : null}
    </span>
  );
}

import type { PriorityOut, PriorityTier } from "../api";

export function PriorityBadge({
  tier,
  score,
  compact = false,
}: {
  tier?: PriorityTier | null;
  score?: number | null;
  compact?: boolean;
}) {
  if (!tier) {
    return (
      <span className="inline-flex items-center rounded-md bg-muted px-2 py-0.5 text-[11px] text-warm">
        Unscored
      </span>
    );
  }

  const map = {
    CRITICAL: {
      bg: "bg-red-500/10 text-red-700 border-red-500/30",
      dot: "bg-red-600",
      label: "Critical",
    },
    HIGH: {
      bg: "bg-amber-500/10 text-amber-700 border-amber-500/30",
      dot: "bg-amber-600",
      label: "High",
    },
    MEDIUM: {
      bg: "bg-blue-500/10 text-blue-700 border-blue-500/30",
      dot: "bg-blue-600",
      label: "Medium",
    },
    LOW: {
      bg: "bg-emerald-500/10 text-emerald-700 border-emerald-500/30",
      dot: "bg-emerald-600",
      label: "Low",
    },
  }[tier];

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold tracking-wide ${map.bg}`}
      title={`Intervention Priority Score: ${score != null ? score.toFixed(1) : "N/A"}/100 (${tier} tier)`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${map.dot}`} />
      <span>{map.label} Priority</span>
      {score != null && !compact ? (
        <span className="font-mono text-[11px] opacity-80">({score.toFixed(1)})</span>
      ) : null}
    </span>
  );
}

export function PriorityBreakdownCard({ priority }: { priority: PriorityOut }) {
  const comps = priority.components;
  const items = [
    { key: "sif", comp: comps.sif_probability, label: "SIF Potential (ML)" },
    { key: "barrier", comp: comps.barrier_criticality, label: "Critical Barrier Status" },
    { key: "recurrence", comp: comps.recurrence, label: "Pattern Recurrence" },
    { key: "trend", comp: comps.trend, label: "Trend Velocity" },
    { key: "exposure", comp: comps.exposure, label: "Operational Exposure" },
    { key: "cross_site", comp: comps.cross_site, label: "Cross-Site Breadth" },
  ];

  return (
    <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Intervention Priority Score
          </div>
          <div className="flex items-baseline gap-2 pt-0.5">
            <span className="font-mono text-2xl font-bold text-foreground">
              {priority.score.toFixed(1)}
            </span>
            <span className="text-xs text-muted-foreground">/ 100</span>
            <PriorityBadge tier={priority.tier} score={priority.score} compact />
          </div>
        </div>
        <div className="text-right text-[11px] text-muted-foreground">
          Engine: <span className="font-mono font-medium">{priority.version}</span>
        </div>
      </div>

      <div className="mt-3 rounded-lg bg-accent/40 p-2.5 text-xs text-foreground/90">
        <div className="font-medium text-foreground">{priority.explanation_summary}</div>
        <div className="mt-1 text-[11px] text-muted-foreground">
          <span className="font-semibold text-foreground">Recommended Action:</span> {priority.action_recommendation}
        </div>
      </div>

      <div className="mt-4 space-y-2.5">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Score Component Breakdown
        </div>
        {items.map(({ key, comp, label }) => {
          const pct = Math.round(comp.score * 100);
          return (
            <div key={key} className="space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="font-medium text-foreground">{label}</span>
                <span className="font-mono text-muted-foreground">
                  +{comp.weighted_score.toFixed(1)} pts{" "}
                  <span className="text-[10px] text-muted-foreground/70">
                    ({(comp.weight * 100).toFixed(0)}% wt · raw: {String(comp.raw_value)})
                  </span>
                </span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary/70 transition-all duration-300"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <div className="text-[10px] text-muted-foreground">{comp.description}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function RecommendationStatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    PENDING_REVIEW: { label: "Pending Review", cls: "bg-amber-100 text-amber-800 border-amber-300" },
    ACCEPTED: { label: "Accepted by HSE", cls: "bg-emerald-100 text-emerald-800 border-emerald-300" },
    EDITED: { label: "Edited by HSE", cls: "bg-blue-100 text-blue-800 border-blue-300" },
    REJECTED: { label: "Rejected", cls: "bg-rose-100 text-rose-800 border-rose-300" },
    IMPLEMENTED: { label: "Implemented", cls: "bg-purple-100 text-purple-800 border-purple-300" },
    RESOLVED: { label: "Resolved", cls: "bg-teal-100 text-teal-800 border-teal-300" },
  };
  const item = map[status] || { label: status, cls: "bg-gray-100 text-gray-800 border-gray-300" };
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${item.cls}`}>
      {item.label}
    </span>
  );
}

export function CategoryBadge({ category }: { category: string }) {
  const clean = category.replace(/_/g, " ");
  return (
    <span className="inline-flex items-center rounded bg-slate-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-700">
      {clean}
    </span>
  );
}

export function LifecycleBadge({ status }: { status?: string | null }) {
  if (!status) {
    return (
      <span className="inline-flex items-center rounded-full border border-slate-300 bg-slate-100 px-2.5 py-0.5 text-[11px] font-semibold text-slate-700">
        AI_ANALYZED
      </span>
    );
  }

  const map: Record<string, { label: string; cls: string; dot: string }> = {
    INGESTED: { label: "Ingested", cls: "bg-slate-100 text-slate-700 border-slate-300", dot: "bg-slate-400" },
    AI_ANALYZED: { label: "AI Analyzed", cls: "bg-indigo-50 text-indigo-700 border-indigo-200", dot: "bg-indigo-500" },
    HSE_REVIEW: { label: "Pending HSE Review", cls: "bg-amber-50 text-amber-800 border-amber-300", dot: "bg-amber-500 animate-pulse" },
    CONFIRMED: { label: "HSE Confirmed", cls: "bg-emerald-50 text-emerald-800 border-emerald-300", dot: "bg-emerald-600" },
    OVERRIDDEN: { label: "HSE Overridden", cls: "bg-purple-50 text-purple-800 border-purple-300", dot: "bg-purple-600" },
    ACTION_ASSIGNED: { label: "Action Assigned", cls: "bg-blue-50 text-blue-800 border-blue-300", dot: "bg-blue-600" },
    IN_PROGRESS: { label: "In Progress", cls: "bg-cyan-50 text-cyan-800 border-cyan-300", dot: "bg-cyan-600" },
    RESOLVED: { label: "Resolved", cls: "bg-teal-50 text-teal-800 border-teal-300", dot: "bg-teal-600" },
    REOPENED: { label: "Reopened", cls: "bg-rose-50 text-rose-800 border-rose-300", dot: "bg-rose-600 animate-pulse" },
    REJECTED: { label: "Rejected", cls: "bg-zinc-100 text-zinc-700 border-zinc-300", dot: "bg-zinc-500" },
  };

  const item = map[status] || { label: status, cls: "bg-gray-100 text-gray-700 border-gray-300", dot: "bg-gray-400" };

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold tracking-wide ${item.cls}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${item.dot}`} />
      <span>{item.label}</span>
    </span>
  );
}

export function AssessmentComparisonBadge({
  aiLabel,
  finalLabel,
  decision,
}: {
  aiLabel?: boolean | null;
  finalLabel?: boolean | null;
  decision?: string | null;
}) {
  if (decision === "OVERRIDDEN") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-md border border-purple-300 bg-purple-50 px-2 py-0.5 text-[11px] font-medium text-purple-800">
        <span>AI: {aiLabel ? "SIF" : "Non-SIF"}</span>
        <span>→</span>
        <span className="font-bold text-purple-900">Analyst: {finalLabel ? "SIF" : "Non-SIF"}</span>
      </span>
    );
  }
  if (decision === "CONFIRMED") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-emerald-300 bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-800">
        <span>Confirmed {finalLabel ?? aiLabel ? "SIF Potential" : "Non-SIF"}</span>
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-md border border-amber-300 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800">
      <span>AI Assessment: {aiLabel ? "SIF Potential" : "Non-SIF"} (Pending Review)</span>
    </span>
  );
}

export function AiPredictionBadge({
  aiLabel,
  aiProbability,
  modelVersion,
}: {
  aiLabel?: boolean | null;
  aiProbability?: number | null;
  modelVersion?: string | null;
}) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md border border-indigo-300 bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-800" title={`Model: ${modelVersion || "unknown"}`}>
      <span>AI: {aiLabel ? "SIF" : "Non-SIF"}</span>
      <span className="font-mono">{aiProbability != null ? Math.round(aiProbability * 100) : "—"}%</span>
    </span>
  );
}

export function AnalystDecisionBadge({
  action,
  analystLabel,
  reviewedAt,
}: {
  action?: string | null;
  analystLabel?: boolean | null;
  reviewedAt?: string | null;
}) {
  if (!action) return null;
  const label = analystLabel === true ? "SIF" : analystLabel === false ? "Non-SIF" : "—";
  return (
    <span className="inline-flex items-center gap-1 rounded-md border border-cyan-300 bg-cyan-50 px-2 py-0.5 text-[11px] font-medium text-cyan-800">
      <span>Analyst: {label}</span>
      <span>({action})</span>
    </span>
  );
}
