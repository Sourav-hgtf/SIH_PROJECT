"""Intervention Priority Scoring Engine.

Provides deterministic, explainable 0–100 priority scoring for individual reports
and precursor clusters based on the centralized business rules configuration.
"""
from __future__ import annotations

import math
from typing import Any, Sequence
from sqlalchemy.orm import Session

from app.models import ClusterMember, PrecursorCluster, PrecursorTriple, Report
from .config import PriorityConfig, load_priority_config
from .schemas import (
    PriorityBreakdown,
    PriorityComponent,
    PriorityOut,
    PriorityTier,
)


def _log_norm(count: int, cap: int) -> float:
    """Log-normalize a count against a cap into [0.0, 1.0]."""
    if count <= 0 or cap <= 0:
        return 0.0
    val = math.log(1.0 + float(count)) / math.log(1.0 + float(cap))
    return min(1.0, max(0.0, val))


def _match_barrier_criticality(
    texts: Sequence[str | None], config: PriorityConfig
) -> tuple[float, str | None]:
    """Find the highest matching barrier criticality score across provided text snippets."""
    best_score = 0.0
    best_match = None
    has_any_text = False

    for raw in texts:
        if not raw:
            continue
        has_any_text = True
        lower = raw.lower()
        for keyword, crit_score in config.barrier_criticality.items():
            if keyword in lower:
                if crit_score > best_score:
                    best_score = crit_score
                    best_match = keyword

    if best_match is not None:
        return best_score, best_match

    # If barrier text was present but no specific known barrier matched
    if has_any_text:
        return 0.5, "unclassified barrier"

    return 0.0, None


def _determine_tier(score: float, config: PriorityConfig) -> PriorityTier:
    """Determine the qualitative tier from a 0-100 numerical score."""
    if score >= config.tiers.critical:
        return "CRITICAL"
    if score >= config.tiers.high:
        return "HIGH"
    if score >= config.tiers.medium:
        return "MEDIUM"
    return "LOW"


def _generate_recommendation(tier: PriorityTier, top_component: str) -> str:
    """Generate an actionable HSE recommendation based on tier and primary driver."""
    if tier == "CRITICAL":
        return (
            "Immediate HSE intervention required: Halt related high-risk tasks, "
            "verify critical physical barriers (LOTO/isolation/guarding), and convene emergency safety stand-down."
        )
    if tier == "HIGH":
        return (
            "High-priority action required in current shift/cycle: Conduct field barrier verification, "
            "review job safety analysis (JSA), and brief frontline supervisors."
        )
    if tier == "MEDIUM":
        return (
            "Scheduled action recommended: Review control trends in next weekly HSE meeting, "
            "inspect equipment condition, and reinforce relevant Life-Saving Rules in toolbox talks."
        )
    return "Routine monitoring: Log observation in periodic safety audit register."


def _build_priority_out(
    sif_prob: float,
    barrier_score: float,
    matched_barrier: str | None,
    recurrence_count: int,
    trend_status: str,
    exposure_count: int,
    site_count: int,
    config: PriorityConfig,
) -> PriorityOut:
    """Core deterministic calculation producing a PriorityOut instance."""
    weights = config.weights

    # 1. SIF Probability Component
    sif_norm = min(1.0, max(0.0, float(sif_prob)))
    sif_weighted = sif_norm * weights.sif_probability * 100.0
    sif_comp = PriorityComponent(
        name="SIF Potential",
        raw_value=round(sif_prob, 3),
        score=round(sif_norm, 4),
        weight=weights.sif_probability,
        weighted_score=round(sif_weighted, 2),
        description=f"ML SIF probability of {sif_prob:.1%} contributes {sif_weighted:.1f} pts.",
    )

    # 2. Barrier Criticality Component
    barrier_norm = min(1.0, max(0.0, float(barrier_score)))
    barrier_weighted = barrier_norm * weights.barrier_criticality * 100.0
    barrier_desc = (
        f"Critical barrier '{matched_barrier}' matched (criticality {barrier_score:.2f}) contributes {barrier_weighted:.1f} pts."
        if matched_barrier
        else "No critical barrier failure identified (0 pts)."
    )
    barrier_comp = PriorityComponent(
        name="Barrier Criticality",
        raw_value=matched_barrier or "None",
        score=round(barrier_norm, 4),
        weight=weights.barrier_criticality,
        weighted_score=round(barrier_weighted, 2),
        description=barrier_desc,
    )

    # 3. Recurrence Component
    rec_norm = _log_norm(recurrence_count, config.normalization.recurrence_cap)
    rec_weighted = rec_norm * weights.recurrence * 100.0
    rec_comp = PriorityComponent(
        name="Recurrence",
        raw_value=recurrence_count,
        score=round(rec_norm, 4),
        weight=weights.recurrence,
        weighted_score=round(rec_weighted, 2),
        description=f"Pattern recurrence of {recurrence_count} occurrences (cap={config.normalization.recurrence_cap}) contributes {rec_weighted:.1f} pts.",
    )

    # 4. Trend Component
    trend_val = getattr(config.trend_scores, trend_status.lower(), config.trend_scores.insufficient_data)
    trend_weighted = trend_val * weights.trend * 100.0
    trend_comp = PriorityComponent(
        name="Trend Velocity",
        raw_value=trend_status,
        score=round(trend_val, 4),
        weight=weights.trend,
        weighted_score=round(trend_weighted, 2),
        description=f"Cluster trend status '{trend_status}' (velocity factor {trend_val:.2f}) contributes {trend_weighted:.1f} pts.",
    )

    # 5. Exposure Component
    exp_norm = _log_norm(exposure_count, config.normalization.exposure_cap)
    exp_weighted = exp_norm * weights.exposure * 100.0
    exp_comp = PriorityComponent(
        name="Exposure Volume",
        raw_value=exposure_count,
        score=round(exp_norm, 4),
        weight=weights.exposure,
        weighted_score=round(exp_weighted, 2),
        description=f"Operational exposure of {exposure_count} reports (cap={config.normalization.exposure_cap}) contributes {exp_weighted:.1f} pts.",
    )

    # 6. Cross-Site Component
    if config.cross_site.enabled and config.cross_site.max_sites > 0:
        cs_norm = min(1.0, max(0.0, float(site_count) / float(config.cross_site.max_sites)))
    else:
        cs_norm = 0.0
    cs_weighted = cs_norm * weights.cross_site * 100.0
    cs_comp = PriorityComponent(
        name="Cross-Site Breadth",
        raw_value=site_count,
        score=round(cs_norm, 4),
        weight=weights.cross_site,
        weighted_score=round(cs_weighted, 2),
        description=f"Observed across {site_count} distinct site(s) contributes {cs_weighted:.1f} pts.",
    )

    # Compute Total Priority Score
    raw_total = (
        sif_norm * weights.sif_probability
        + barrier_norm * weights.barrier_criticality
        + rec_norm * weights.recurrence
        + trend_val * weights.trend
        + exp_norm * weights.exposure
        + cs_norm * weights.cross_site
    ) * 100.0

    final_score = round(min(100.0, max(0.0, raw_total)), 1)
    tier = _determine_tier(final_score, config)

    # Identify primary driver for explanation
    components_list = [
        ("SIF probability", sif_weighted),
        (f"barrier failure ({matched_barrier})" if matched_barrier else "barrier status", barrier_weighted),
        ("pattern recurrence", rec_weighted),
        ("worsening trend", trend_weighted),
        ("exposure volume", exp_weighted),
        ("cross-site spread", cs_weighted),
    ]
    components_list.sort(key=lambda x: x[1], reverse=True)
    top_driver_name = components_list[0][0]
    second_driver_name = components_list[1][0]

    explanation = (
        f"{tier} priority ({final_score:.1f}/100) primarily driven by {top_driver_name} "
        f"and {second_driver_name}."
    )

    breakdown = PriorityBreakdown(
        sif_probability=sif_comp,
        barrier_criticality=barrier_comp,
        recurrence=rec_comp,
        trend=trend_comp,
        exposure=exp_comp,
        cross_site=cs_comp,
    )

    return PriorityOut(
        score=final_score,
        tier=tier,
        version=config.version,
        explanation_summary=explanation,
        action_recommendation=_generate_recommendation(tier, top_driver_name),
        components=breakdown,
    )


def score_report(report: Report, db: Session | None = None) -> PriorityOut:
    """Calculate the deterministic Intervention Priority Score for a single incident report."""
    config = load_priority_config()

    # 1. SIF Probability
    sif_prob = 0.0
    if report.classification and report.classification.sif_probability is not None:
        sif_prob = float(report.classification.sif_probability)

    # 2. Barrier Failure Extraction
    barrier_texts = [report.raw_text_redacted]
    if report.triples:
        for t in report.triples:
            if t.barrier_failure:
                barrier_texts.append(t.barrier_failure)
    if report.lsr_tags:
        for tag in report.lsr_tags:
            if tag.evidence:
                for ev in tag.evidence:
                    if isinstance(ev, dict) and "text" in ev:
                        barrier_texts.append(ev["text"])
                    elif isinstance(ev, str):
                        barrier_texts.append(ev)

    barrier_score, matched_barrier = _match_barrier_criticality(barrier_texts, config)

    # 3. Cluster Association (Recurrence, Trend, Exposure, Cross-Site)
    recurrence_count = 1
    trend_status = "insufficient_data"
    exposure_count = 1
    site_count = 1

    cluster: PrecursorCluster | None = None
    if db is not None:
        triple = db.query(PrecursorTriple).filter(PrecursorTriple.report_id == report.id).first()
        if triple:
            member = db.query(ClusterMember).filter(ClusterMember.triple_id == triple.id).first()
            if member:
                cluster = db.get(PrecursorCluster, member.cluster_id)

    if cluster:
        recurrence_count = max(1, cluster.cluster_size)
        trend_status = cluster.trend_status or "stable"
        exposure_count = max(1, cluster.cluster_size)

        if db is not None:
            # Count distinct sites associated with this cluster
            sites = (
                db.query(Report.site_id)
                .join(PrecursorTriple, PrecursorTriple.report_id == Report.id)
                .join(ClusterMember, ClusterMember.triple_id == PrecursorTriple.id)
                .filter(ClusterMember.cluster_id == cluster.id)
                .distinct()
                .all()
            )
            site_count = max(1, len(sites))

    return _build_priority_out(
        sif_prob=sif_prob,
        barrier_score=barrier_score,
        matched_barrier=matched_barrier,
        recurrence_count=recurrence_count,
        trend_status=trend_status,
        exposure_count=exposure_count,
        site_count=site_count,
        config=config,
    )


def score_cluster(cluster: PrecursorCluster, db: Session | None = None) -> PriorityOut:
    """Calculate the deterministic Intervention Priority Score for a precursor cluster."""
    config = load_priority_config()

    # 1. SIF Probability across members
    sif_prob = 0.0
    member_reports: list[Report] = []
    site_count = 1

    if db is not None:
        member_reports = (
            db.query(Report)
            .join(PrecursorTriple, PrecursorTriple.report_id == Report.id)
            .join(ClusterMember, ClusterMember.triple_id == PrecursorTriple.id)
            .filter(ClusterMember.cluster_id == cluster.id)
            .all()
        )
        if member_reports:
            sif_probs = [
                r.classification.sif_probability
                for r in member_reports
                if r.classification and r.classification.sif_probability is not None
            ]
            if sif_probs:
                # Use max SIF probability in cluster to ensure highest safety posture
                sif_prob = max(sif_probs)
            unique_sites = {r.site_id for r in member_reports if r.site_id}
            site_count = max(1, len(unique_sites))

    # 2. Barrier Failure from Cluster
    barrier_texts = [cluster.representative_barrier_failure]
    for r in member_reports:
        if r.raw_text_redacted:
            barrier_texts.append(r.raw_text_redacted)

    barrier_score, matched_barrier = _match_barrier_criticality(barrier_texts, config)

    # 3. Recurrence, Trend, Exposure
    recurrence_count = max(1, cluster.cluster_size)
    trend_status = cluster.trend_status or "stable"
    exposure_count = max(1, len(member_reports) if member_reports else cluster.cluster_size)

    return _build_priority_out(
        sif_prob=sif_prob,
        barrier_score=barrier_score,
        matched_barrier=matched_barrier,
        recurrence_count=recurrence_count,
        trend_status=trend_status,
        exposure_count=exposure_count,
        site_count=site_count,
        config=config,
    )
