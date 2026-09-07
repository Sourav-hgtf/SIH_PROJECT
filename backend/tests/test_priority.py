"""Unit tests for the Intervention Priority Scoring engine."""
from datetime import datetime, timezone
import pytest

from app.models import (
    ClusterMember,
    LsrTag,
    PrecursorCluster,
    PrecursorTriple,
    Report,
    SifClassification,
    Site,
)
from app.priority import load_priority_config, score_cluster, score_report
from app.priority.engine import _log_norm, _match_barrier_criticality


def test_priority_config_loading():
    """Verify that configs/business_rules.yaml loads with valid weights and tiers."""
    config = load_priority_config()
    assert config.version == "priority-v1"

    # Weights sum to 1.0
    w = config.weights
    total_weight = (
        w.sif_probability
        + w.barrier_criticality
        + w.recurrence
        + w.trend
        + w.exposure
        + w.cross_site
    )
    assert abs(total_weight - 1.0) < 1e-4

    # Tier thresholds order: critical > high > medium > 0
    assert config.tiers.critical > config.tiers.high > config.tiers.medium >= 0

    # Trend scores valid
    assert config.trend_scores.growing > config.trend_scores.stable > config.trend_scores.shrinking


def test_log_norm_helper():
    """Check log normalization behaviour."""
    assert _log_norm(0, 10) == 0.0
    assert _log_norm(-5, 10) == 0.0
    assert _log_norm(10, 10) == 1.0
    assert _log_norm(50, 10) == 1.0  # Clamped at 1.0
    assert 0.0 < _log_norm(5, 10) < 1.0


def test_barrier_criticality_matching():
    """Test matching barrier keywords from text snippets."""
    config = load_priority_config()

    # Known critical barrier: LOTO / isolation
    score, match = _match_barrier_criticality(["Technician bypassed LOTO on valve"], config)
    assert score == 1.0
    assert match == "loto"

    # Known high-criticality barrier: Interlock bypassed
    score, match = _match_barrier_criticality(["Guard interlock was bypassed"], config)
    assert score == 0.9
    assert match in ("interlock", "bypassed", "bypass")

    # Unclassified barrier text
    score, match = _match_barrier_criticality(["Unspecified safety issue"], config)
    assert score == 0.5
    assert match == "unclassified barrier"

    # Empty text
    score, match = _match_barrier_criticality([], config)
    assert score == 0.0
    assert match is None


def test_report_priority_monotonicity_sif():
    """Higher SIF probability must strictly increase total priority score."""
    r_low = Report(
        id="rep-low",
        source_report_id="SRC-1",
        report_type="near_miss",
        site_id="site-1",
        raw_text_redacted="Routine slip hazard",
        reported_at=datetime.now(timezone.utc),
    )
    r_low.classification = SifClassification(
        report_id="rep-low",
        sif_probability=0.10,
        sif_label=False,
    )

    r_high = Report(
        id="rep-high",
        source_report_id="SRC-2",
        report_type="near_miss",
        site_id="site-1",
        raw_text_redacted="Routine slip hazard",
        reported_at=datetime.now(timezone.utc),
    )
    r_high.classification = SifClassification(
        report_id="rep-high",
        sif_probability=0.90,
        sif_label=True,
    )

    p_low = score_report(r_low)
    p_high = score_report(r_high)

    assert p_high.score > p_low.score
    assert p_high.components.sif_probability.score > p_low.components.sif_probability.score


def test_report_priority_barrier_impact():
    """Critical barrier failure must produce higher score than absent barrier."""
    r_no_barrier = Report(
        id="rep-nb",
        source_report_id="SRC-3",
        report_type="near_miss",
        site_id="site-1",
        raw_text_redacted="General cleanup required in aisle",
        reported_at=datetime.now(timezone.utc),
    )
    r_no_barrier.classification = SifClassification(
        report_id="rep-nb",
        sif_probability=0.50,
        sif_label=True,
    )

    r_barrier = Report(
        id="rep-b",
        source_report_id="SRC-4",
        report_type="near_miss",
        site_id="site-1",
        raw_text_redacted="Energy isolation was not performed and LOTO missing",
        reported_at=datetime.now(timezone.utc),
    )
    r_barrier.classification = SifClassification(
        report_id="rep-b",
        sif_probability=0.50,
        sif_label=True,
    )

    p_nb = score_report(r_no_barrier)
    p_b = score_report(r_barrier)

    assert p_b.score > p_nb.score
    assert p_b.components.barrier_criticality.score == 1.0


def test_tier_boundaries():
    """Verify correct tier assignment according to config thresholds."""
    config = load_priority_config()

    # Extreme critical case
    r_crit = Report(
        id="rep-crit",
        source_report_id="SRC-5",
        report_type="near_miss",
        site_id="site-1",
        raw_text_redacted="Isolation failure and bypass on high pressure gas valve",
        reported_at=datetime.now(timezone.utc),
    )
    r_crit.classification = SifClassification(
        report_id="rep-crit",
        sif_probability=0.95,
        sif_label=True,
    )
    p_crit = score_report(r_crit)
    assert p_crit.score >= config.tiers.critical or p_crit.score >= config.tiers.high
    assert p_crit.tier in ("CRITICAL", "HIGH")
    assert "intervention required" in p_crit.action_recommendation.lower() or "action" in p_crit.action_recommendation.lower()


def test_cluster_priority_scoring():
    """Test priority score calculation on precursor clusters."""
    cluster = PrecursorCluster(
        id="cl-1",
        representative_activity="Pipe cutting",
        representative_location="Unit 4",
        representative_barrier_failure="LOTO isolation missing",
        cluster_size=8,
        trend_status="growing",
        first_seen_at=datetime.now(timezone.utc),
        last_updated_at=datetime.now(timezone.utc),
    )

    p_cluster = score_cluster(cluster)
    assert p_cluster.score > 0
    assert p_cluster.components.recurrence.raw_value == 8
    assert p_cluster.components.trend.raw_value == "growing"
    assert p_cluster.components.trend.score == 1.0
    assert p_cluster.components.barrier_criticality.score == 1.0
    assert p_cluster.version == "priority-v1"


def test_graceful_degradation_missing_fields():
    """Verify that incomplete or sparse reports score safely without crashing."""
    bare_report = Report(
        id="rep-bare",
        source_report_id="SRC-BARE",
        report_type="ua_uc",
        site_id="site-1",
        raw_text_redacted="",
        reported_at=datetime.now(timezone.utc),
    )
    p = score_report(bare_report)
    assert 0.0 <= p.score <= 100.0
    assert p.tier in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
    assert p.components.sif_probability.score == 0.0
    assert p.components.barrier_criticality.score == 0.0
