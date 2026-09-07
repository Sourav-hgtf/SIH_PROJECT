"""Deterministic, evidence-grounded Corrective Action Recommendation Engine.

Answers: 'Given this identified safety risk, what practical corrective/preventive
actions should the HSE team consider?'

All recommendations are:
1. Grounded strictly in detected evidence (energy, proximity, barriers, LSRs, clusters).
2. Human-in-the-loop: generated as PENDING_REVIEW; analyst accepts, edits, or rejects.
3. Deterministic and testable offline without external LLM dependencies.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Sequence
from sqlalchemy.orm import Session, joinedload

from app.models import (
    ClusterMember,
    PrecursorCluster,
    PrecursorTriple,
    Recommendation,
    RecommendationFeedback,
    Report,
    Site,
)
from app.priority.engine import score_cluster, score_report
from .config import ActionRuleConfig, RecommendationsConfig, load_recommendations_config
from .schemas import (
    ExecutiveFocusAreaOut,
    RecommendationFeedbackOut,
    RecommendationOut,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class _Candidate:
    def __init__(
        self,
        dedup_key: str,
        category: str,
        title: str,
        action: str,
        rationale: str,
        base_confidence: float,
        evidence: list[str],
        source_signals: dict[str, Any],
        barrier_criticality: float = 0.5,
    ):
        self.dedup_key = dedup_key
        self.category = category
        self.title = title
        self.action = action
        self.rationale = rationale
        self.base_confidence = base_confidence
        self.evidence = evidence
        self.source_signals = source_signals
        self.barrier_criticality = barrier_criticality
        self.supporting_signals_count = len(evidence)

    def merge(self, other: _Candidate) -> None:
        """Merge another candidate with the same deduplication key."""
        for ev in other.evidence:
            if ev not in self.evidence:
                self.evidence.append(ev)
        for k, v in other.source_signals.items():
            if k not in self.source_signals:
                self.source_signals[k] = v
            elif isinstance(self.source_signals[k], list) and isinstance(v, list):
                for item in v:
                    if item not in self.source_signals[k]:
                        self.source_signals[k].append(item)
        self.base_confidence = max(self.base_confidence, other.base_confidence)
        self.barrier_criticality = max(self.barrier_criticality, other.barrier_criticality)
        self.supporting_signals_count = len(self.evidence)


def _match_barrier_rule(barrier_str: str, config: RecommendationsConfig) -> tuple[str, ActionRuleConfig] | None:
    low = barrier_str.lower()
    for b_key, rule in config.evidence_mappings.barriers.items():
        if b_key in low:
            return b_key, rule
    if "lock" in low or "tag" in low or "loto" in low:
        return "loto", config.evidence_mappings.barriers.get("loto") or config.evidence_mappings.barriers["isolation"]
    if "isolate" in low:
        return "isolation", config.evidence_mappings.barriers["isolation"]
    if "guard" in low or "interlock" in low:
        return "interlock", config.evidence_mappings.barriers["interlock"]
    if "permit" in low or "ptw" in low:
        return "permit", config.evidence_mappings.barriers["permit"]
    if "gas" in low or "atmosphere" in low or "toxic" in low or "h2s" in low:
        return "gas_test", config.evidence_mappings.barriers["gas_test"]
    if "harness" in low or "fall" in low:
        return "fall_protection", config.evidence_mappings.barriers["fall_protection"]
    if "fire" in low or "spark" in low:
        return "fire_watch", config.evidence_mappings.barriers["fire_watch"]
    if "exclusion" in low or "perimeter" in low or "barricade" in low:
        return "exclusion_zone", config.evidence_mappings.barriers["exclusion_zone"]
    return None


def _match_proximity_rule(prox_str: str, config: RecommendationsConfig) -> tuple[str, ActionRuleConfig] | None:
    low = prox_str.lower()
    for p_key, rule in config.evidence_mappings.proximity.items():
        if p_key.replace("_", " ") in low or p_key in low:
            return p_key, rule
    if "line of fire" in low:
        return "line_of_fire", config.evidence_mappings.proximity["line_of_fire"]
    if "under" in low and "load" in low:
        return "under_load", config.evidence_mappings.proximity["under_load"]
    if "drop" in low or "falling" in low:
        return "drop_zone", config.evidence_mappings.proximity["drop_zone"]
    return None


def generate_report_recommendations(
    report: Report, db: Session | None = None
) -> list[RecommendationOut]:
    """Deterministically generates evidence-grounded recommendations for a single report."""
    config = load_recommendations_config()
    priority_out = score_report(report, db)
    features = report.classification.features if report.classification and report.classification.features else {}

    energy_types: list[str] = features.get("energy_types", [])
    proximity_hits: list[str] = features.get("proximity_hits", [])
    barrier_failures: list[str] = features.get("barrier_failures", [])

    # Also extract any explicit barrier text from triples
    if report.triples:
        for t in report.triples:
            if t.barrier_failure and t.barrier_failure not in barrier_failures:
                barrier_failures.append(t.barrier_failure)

    lsr_tags = report.lsr_tags or []

    # If absolutely no signals exist in the report, return empty (never fabricate)
    if not (energy_types or proximity_hits or barrier_failures or lsr_tags or (report.classification and report.classification.sif_label)):
        return []

    candidates_map: dict[str, _Candidate] = {}

    # 1. Map Barrier Failures
    for bf in barrier_failures:
        matched = _match_barrier_rule(bf, config)
        if matched:
            key, rule = matched
            dedup = f"barrier_{key}"
            cand = _Candidate(
                dedup_key=dedup,
                category=rule.category,
                title=rule.title,
                action=rule.action,
                rationale=rule.rationale,
                base_confidence=rule.base_confidence,
                evidence=[f"Barrier failure identified: '{bf}'"],
                source_signals={"barriers": [bf]},
                barrier_criticality=0.9,
            )
            if dedup in candidates_map:
                candidates_map[dedup].merge(cand)
            else:
                candidates_map[dedup] = cand

    # 2. Map Energy Types
    for eng in energy_types:
        eng_key = eng.lower()
        if eng_key in config.evidence_mappings.energy:
            rule = config.evidence_mappings.energy[eng_key]
            # Map electrical/pressure energy to isolation if isolation barrier also exists
            dedup = f"energy_{eng_key}"
            if eng_key in ("electrical", "pressure") and "barrier_isolation" in candidates_map:
                dedup = "barrier_isolation"
            cand = _Candidate(
                dedup_key=dedup,
                category=rule.category,
                title=rule.title,
                action=rule.action,
                rationale=rule.rationale,
                base_confidence=rule.base_confidence,
                evidence=[f"Hazardous energy detected: {eng.capitalize()}"],
                source_signals={"energy": [eng]},
                barrier_criticality=0.8,
            )
            if dedup in candidates_map:
                candidates_map[dedup].merge(cand)
            else:
                candidates_map[dedup] = cand

    # 3. Map Proximity / Exposure Hits
    for prox in proximity_hits:
        matched_prox = _match_proximity_rule(prox, config)
        if matched_prox:
            key, rule = matched_prox
            dedup = f"proximity_{key}"
            cand = _Candidate(
                dedup_key=dedup,
                category=rule.category,
                title=rule.title,
                action=rule.action,
                rationale=rule.rationale,
                base_confidence=rule.base_confidence,
                evidence=[f"Line-of-fire/proximity exposure detected: '{prox}'"],
                source_signals={"proximity": [prox]},
                barrier_criticality=0.75,
            )
            if dedup in candidates_map:
                candidates_map[dedup].merge(cand)
            else:
                candidates_map[dedup] = cand

    # 4. Map Canonical Life-Saving Rules
    for tag in lsr_tags:
        rule_id = getattr(tag, "rule_id", None)
        rule_name = getattr(tag, "rule_name", None) or getattr(tag, "lsr_category", "")
        if rule_id and rule_id in config.evidence_mappings.lsr:
            rule = config.evidence_mappings.lsr[rule_id]
            # If it aligns with energy isolation, merge into barrier_isolation
            dedup = f"lsr_{rule_id}"
            if rule_id in ("LSR-04", "LSR-01") and "barrier_isolation" in candidates_map:
                dedup = "barrier_isolation"
            elif rule_id == "LSR-06" and "proximity_line_of_fire" in candidates_map:
                dedup = "proximity_line_of_fire"
            cand = _Candidate(
                dedup_key=dedup,
                category=rule.category,
                title=rule.title,
                action=rule.action,
                rationale=rule.rationale,
                base_confidence=rule.base_confidence,
                evidence=[f"Life-Saving Rule triggered: {rule_id} ({rule_name})"],
                source_signals={"lsr": [rule_id]},
                barrier_criticality=0.85,
            )
            if dedup in candidates_map:
                candidates_map[dedup].merge(cand)
            else:
                candidates_map[dedup] = cand

    if not candidates_map:
        return []

    # Calculate final confidence, ranking score, and sort
    w = config.ranking_weights
    p_norm = priority_out.score / 100.0

    ranked_candidates: list[tuple[float, _Candidate]] = []
    for cand in candidates_map.values():
        # Confidence reflects how strongly evidence supports this rule
        bonus = min(0.10, 0.03 * (cand.supporting_signals_count - 1))
        confidence = min(0.98, max(0.60, cand.base_confidence + bonus))

        # Overall ranking score for prominence
        rank_score = (
            (confidence * w.confidence_weight)
            + (cand.barrier_criticality * w.barrier_criticality_weight)
            + (p_norm * w.priority_boost_weight)
            + (min(1.0, cand.supporting_signals_count * 0.3) * w.cross_signal_weight)
        )
        ranked_candidates.append((rank_score, cand))

    ranked_candidates.sort(key=lambda x: x[0], reverse=True)
    top_candidates = ranked_candidates[: config.max_recommendations_per_report]

    now = _utcnow()
    results: list[RecommendationOut] = []
    for _, c in top_candidates:
        confidence = min(0.98, max(0.60, c.base_confidence + min(0.10, 0.03 * (c.supporting_signals_count - 1))))
        results.append(
            RecommendationOut(
                id=_new_id(),
                report_id=report.id,
                cluster_id=None,
                site_id=report.site_id,
                activity=report.job_type,
                category=c.category,
                title=c.title,
                action=c.action,
                confidence=round(confidence, 2),
                priority=priority_out.tier,
                evidence=c.evidence,
                source_signals=c.source_signals,
                rationale=c.rationale,
                status="PENDING_REVIEW",
                version=config.version,
                created_at=now,
                updated_at=now,
                feedback_history=[],
            )
        )

    return results


def generate_cluster_recommendations(
    cluster: PrecursorCluster, db: Session | None = None
) -> list[RecommendationOut]:
    """Generates systemic, cluster-level corrective actions across participating sites."""
    config = load_recommendations_config()
    priority_out = score_cluster(cluster, db)
    text_corpus = f"{cluster.representative_activity} {cluster.representative_location} {cluster.representative_barrier_failure}".lower()

    site_count = 1
    sif_rate = 0.0
    member_count = cluster.cluster_size
    if db is not None:
        member_reports = (
            db.query(Report)
            .join(PrecursorTriple, PrecursorTriple.report_id == Report.id)
            .join(ClusterMember, ClusterMember.triple_id == PrecursorTriple.id)
            .filter(ClusterMember.cluster_id == cluster.id)
            .all()
        )
        if member_reports:
            member_count = len(member_reports)
            unique_sites = {r.site_id for r in member_reports if r.site_id}
            site_count = max(1, len(unique_sites))
            sifs = sum(1 for r in member_reports if r.classification and r.classification.sif_label)
            sif_rate = round(sifs / member_count, 2)

    cluster_evidence = [
        f"Recurring pattern across {member_count} reports",
        f"Observed across {site_count} operational facility/facilities",
        f"Cluster trend velocity: {cluster.trend_status.upper()}",
    ]
    if sif_rate > 0:
        cluster_evidence.append(f"Cluster SIF potential rate: {int(sif_rate * 100)}%")

    selected_rule_keys: list[str] = []
    if any(k in text_corpus for k in ("lift", "crane", "rigging", "hoist", "sling")):
        selected_rule_keys.append("lifting")
    if any(k in text_corpus for k in ("height", "fall", "scaffold", "elevated", "roof")):
        selected_rule_keys.append("height")
    if any(k in text_corpus for k in ("isolate", "isolation", "loto", "energized", "lock")):
        selected_rule_keys.append("isolation")

    if not selected_rule_keys:
        selected_rule_keys.append("generic_cluster")

    now = _utcnow()
    recommendations: list[RecommendationOut] = []
    for key in selected_rule_keys:
        rule = config.cluster_rules.get(key) or config.cluster_rules["generic_cluster"]
        # Multi-site boost for confidence
        base = rule.base_confidence
        if site_count > 1:
            base += 0.04
        if cluster.trend_status == "growing":
            base += 0.03
        conf = min(0.96, round(base, 2))

        recommendations.append(
            RecommendationOut(
                id=_new_id(),
                report_id=None,
                cluster_id=cluster.id,
                site_id=None,
                activity=cluster.representative_activity,
                category=rule.category,
                title=rule.title,
                action=rule.action,
                confidence=conf,
                priority=priority_out.tier,
                evidence=cluster_evidence,
                source_signals={
                    "cluster_id": cluster.id,
                    "representative_barrier": cluster.representative_barrier_failure,
                    "site_count": site_count,
                    "trend_status": cluster.trend_status,
                },
                rationale=rule.rationale,
                status="PENDING_REVIEW",
                version=config.version,
                created_at=now,
                updated_at=now,
                feedback_history=[],
            )
        )

    return recommendations


def generate_executive_focus_areas(db: Session, limit: int = 5) -> list[ExecutiveFocusAreaOut]:
    """Extracts top strategic HSE focus areas by aggregating high-priority precursor clusters."""
    clusters = db.query(PrecursorCluster).all()
    scored_clusters: list[tuple[float, PrecursorCluster]] = []
    for c in clusters:
        p = score_cluster(c, db)
        scored_clusters.append((p.score, c))

    scored_clusters.sort(key=lambda x: x[0], reverse=True)
    top_clusters = scored_clusters[:limit]

    focus_areas: list[ExecutiveFocusAreaOut] = []
    for score_val, cluster in top_clusters:
        priority_out = score_cluster(cluster, db)
        recs = generate_cluster_recommendations(cluster, db)
        actions = [r.action for r in recs[:2]]

        member_reports = (
            db.query(Report)
            .join(PrecursorTriple, PrecursorTriple.report_id == Report.id)
            .join(ClusterMember, ClusterMember.triple_id == PrecursorTriple.id)
            .filter(ClusterMember.cluster_id == cluster.id)
            .all()
        )
        site_count = len({r.site_id for r in member_reports if r.site_id}) if member_reports else 1
        report_count = len(member_reports) if member_reports else cluster.cluster_size
        sifs = sum(1 for r in member_reports if r.classification and r.classification.sif_label)
        sif_rate = round((sifs / report_count) if report_count else 0.0, 2)

        area_title = f"{cluster.representative_activity.title()} — {cluster.representative_location}"
        focus_areas.append(
            ExecutiveFocusAreaOut(
                area_name=area_title,
                priority_tier=priority_out.tier,
                cluster_id=cluster.id,
                site_count=site_count,
                trend_status=cluster.trend_status,
                report_count=report_count,
                sif_rate=sif_rate,
                recommended_actions=actions,
                primary_barrier_failure=cluster.representative_barrier_failure,
            )
        )

    return focus_areas
