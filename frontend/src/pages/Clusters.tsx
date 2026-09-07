import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type Cluster, type Recommendation, type ReportSummary } from "../api";
import { ConfidenceBar, PriorityBadge, PriorityBreakdownCard, RiskBadge } from "../components/Badges";

function trendMark(status: string) {
  if (status === "growing") return { icon: "▲", cls: "text-risk-medium" };
  if (status === "shrinking") return { icon: "▼", cls: "text-risk-low" };
  return { icon: "▬", cls: "text-warm" };
}

export function ClustersPage() {
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api.clusters().then(setClusters).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-[24px] font-bold text-ink">Semantic Precursor Cluster Explorer</h1>
        <p className="mt-1 text-sm text-warm">
          Recurring activity × location × barrier-failure patterns grouped by ML semantic similarity and ranked by Intervention Priority Score.
        </p>
      </div>

      {error ? <p className="text-sm font-medium text-risk-critical">{error}</p> : null}

      {clusters.length === 0 && !error && (
        <div className="rounded-xl border border-border bg-white p-8 text-center text-warm">
          <p className="text-base font-semibold text-ink">No Precursor Clusters Identified Yet</p>
          <p className="mt-1 text-xs">Run report ingestion or trigger cluster rebuilding to surface recurring hazard patterns.</p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {clusters.map((c) => {
          const t = trendMark(c.trend_status);
          const activityName = c.representative_activity === "-1" ? "Unclustered / Noise" : c.representative_activity;
          const locationName = c.representative_location === "-1" ? "General Site Area" : c.representative_location;

          return (
            <Link
              key={c.id}
              to={`/clusters/${c.id}`}
              className="flex flex-col justify-between rounded-xl border border-border bg-white p-5 shadow-card transition hover:border-border hover:shadow-md"
            >
              <div>
                <div className="flex items-start justify-between gap-2">
                  <h2 className="text-[16px] font-bold leading-snug text-ink">
                    {activityName} · {locationName}
                  </h2>
                  {c.priority && (
                    <PriorityBadge tier={c.priority.tier} score={c.priority.score} compact />
                  )}
                </div>
                <p className="mt-2 text-xs text-warm">{c.representative_barrier_failure}</p>
                {c.priority && (
                  <p className="mt-2 text-[11px] text-warm italic line-clamp-2">
                    {c.priority.explanation_summary}
                  </p>
                )}
              </div>
              <div className="mt-4 flex items-center justify-between border-t border-border/60 pt-3 text-xs">
                <span className="font-semibold text-ink">{c.cluster_size} reports linked</span>
                <span className={`font-semibold ${t.cls}`}>
                  {t.icon} {c.trend_status.toUpperCase()}
                </span>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}


export function ClusterDetailPage() {
  const { id } = useParams();
  const [data, setData] = useState<(Cluster & { member_reports: ReportSummary[] }) | null>(null);
  const [clusterRecs, setClusterRecs] = useState<Recommendation[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;
    api.cluster(id).then(setData).catch((e) => setError(e.message));
    api.clusterRecommendations(id).then(setClusterRecs).catch((e) => console.error("Error loading cluster recs:", e));
  }, [id]);

  if (error) return <p className="text-risk-critical">{error}</p>;
  if (!data) return <p className="text-warm">Loading cluster…</p>;

  return (
    <div>
      <Link to="/clusters" className="text-cyan-edge hover:underline">
        ← All clusters
      </Link>
      <div className="mt-3 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-[24px] font-semibold">{data.representative_activity}</h1>
          <p className="text-warm">
            {data.representative_location} · {data.representative_barrier_failure} · {data.cluster_size} reports
          </p>
        </div>
        {data.priority && <PriorityBadge tier={data.priority.tier} score={data.priority.score} />}
      </div>

      <div className="mt-6 grid grid-cols-[2fr_1fr] gap-4">
        <div className="space-y-4">
          <div className="overflow-hidden rounded-[10px] border border-border bg-white shadow-sm">
            <div className="border-b border-border bg-canvas/40 px-5 py-3 text-xs font-semibold uppercase tracking-wider text-warm">
              Member Reports ({data.member_reports.length})
            </div>
            {data.member_reports.map((row) => (
              <Link
                key={row.id}
                to={`/reports/${row.id}`}
                className="flex items-start gap-4 border-b border-border px-5 py-4 transition hover:bg-canvas"
              >
                <div className="mt-1 w-32 shrink-0 space-y-1">
                  {row.priority ? (
                    <PriorityBadge tier={row.priority.tier} score={row.priority.score} compact />
                  ) : (
                    <RiskBadge sifLabel={row.sif_label} probability={row.sif_probability} />
                  )}
                  <ConfidenceBar value={row.sif_probability} sifLabel={row.sif_label} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-[12px] text-warm">
                    <span className="font-medium text-ink">{row.site_name}</span> · {new Date(row.reported_at).toLocaleDateString()}
                  </div>
                  <p className="mt-1 text-ink">{row.excerpt}</p>
                </div>
              </Link>
            ))}
          </div>
        </div>

        <aside className="space-y-4">
          {data.priority && <PriorityBreakdownCard priority={data.priority} />}

          {/* Cluster-Level Systemic Interventions */}
          {clusterRecs.length > 0 && (
            <section className="rounded-[10px] border border-border bg-white p-5 shadow-card">
              <div className="flex items-center justify-between">
                <h2 className="text-[14px] font-semibold text-ink">Systemic Recommendations</h2>
                <span className="rounded bg-black/5 px-2 py-0.5 text-[10px] font-mono text-warm">Cluster-Level</span>
              </div>
              <p className="mt-1 text-[11px] leading-tight text-warm">
                Targeted preventative controls addressing recurring multi-site barrier failure patterns.
              </p>
              <div className="mt-3 space-y-3">
                {clusterRecs.map((cr) => (
                  <div key={cr.id} className="rounded-lg border border-border bg-canvas/40 p-3">
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="font-semibold uppercase tracking-wider text-warm">{cr.category.replace("_", " ")}</span>
                      <span className="font-medium text-ink">{Math.round(cr.confidence * 100)}% support</span>
                    </div>
                    <h3 className="mt-1 text-xs font-semibold text-ink">{cr.title}</h3>
                    <p className="mt-1 text-xs leading-relaxed text-ink/90 font-medium">{cr.action}</p>
                    <ul className="mt-2 space-y-0.5 border-t border-border/50 pt-1.5 text-[10px] text-warm">
                      {cr.evidence.map((ev, i) => (
                        <li key={i}>• {ev}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}
