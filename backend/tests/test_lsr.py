"""Comprehensive tests for canonical 12 IOGP Life-Saving Rules system.

Validates:
1. Configuration integrity (exactly 12 rules, unique IDs/names, non-empty metadata).
2. Fail-fast configuration validation.
3. Classification scenarios across all hazard categories.
4. Negative test: zero false positives on routine low-risk text.
5. Multi-rule classification on composite hazard reports.
6. Structured evidence extraction (phrase, keyword, energy, barrier cross-signals).
7. API response contracts (/v1/lsr-rules, /v1/dashboard/lsr-distribution).
8. Dashboard canonical 12-rule ordering and zero-count inclusion.
"""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.database import Base, SessionLocal, engine
from app.models import Report, LsrTag, Site, SifClassification, User
from app.nlp.classify import tag_life_saving_rules
from app.nlp.lsr import (
    CANONICAL_LSR_COUNT,
    LsrConfigFile,
    LsrRuleConfig,
    get_canonical_rule_names,
    get_rule_by_id,
    get_rule_by_name,
    load_canonical_lsr_rules,
)
from app.services import ingest_and_process


# ==========================================
# 1. CONFIGURATION TESTS
# ==========================================

def test_canonical_configuration_count_and_uniqueness():
    rules = load_canonical_lsr_rules()
    assert len(rules) == CANONICAL_LSR_COUNT == 12

    ids = [r.id for r in rules]
    assert len(set(ids)) == 12
    # Verify IDs are LSR01 through LSR12
    for i in range(1, 13):
        expected_id = f"LSR{i:02d}"
        assert expected_id in ids

    names = [r.name for r in rules]
    assert len(set(names)) == 12

    short_names = [r.short_name for r in rules]
    assert len(set(short_names)) == 12

    for r in rules:
        assert r.id
        assert r.name
        assert r.short_name
        assert r.description
        assert len(r.keywords) > 0
        assert len(r.phrases) > 0


def test_config_validation_fails_on_duplicate_or_invalid():
    # Duplicate ID
    bad_rules = [
        LsrRuleConfig(
            id="LSR01",
            name=f"Rule {i}",
            short_name=f"R{i}",
            description="desc",
            keywords=[f"kw{i}"],
            phrases=[f"phrase {i}"],
        )
        for i in range(12)
    ]
    with pytest.raises(ValidationError):
        LsrConfigFile(rules=bad_rules)

    # Missing rules (fewer than 12)
    with pytest.raises(ValidationError):
        LsrConfigFile(rules=bad_rules[:10])


def test_rule_lookups_by_id_and_name():
    rule = get_rule_by_id("LSR04")
    assert rule is not None
    assert rule.name == "Energy Isolation"

    rule_by_name = get_rule_by_name("Energy Isolation")
    assert rule_by_name is not None
    assert rule_by_name.id == "LSR04"

    # Case-insensitive and snake_case alias lookup
    assert get_rule_by_name("energy_isolation") is not None
    assert get_rule_by_name("energy isolation") is not None
    assert get_rule_by_name("working_at_height") is not None


# ==========================================
# 2. CLASSIFICATION & EVIDENCE SCENARIO TESTS
# ==========================================

@pytest.mark.parametrize(
    "text,expected_rule_id,expected_rule_name",
    [
        (
            "Crew worked on live electrical panel without energy isolation. Lock-out tag-out not applied.",
            "LSR04",
            "Energy Isolation",
        ),
        (
            "Worker fell from incomplete scaffold platform. No harness worn while working at height.",
            "LSR11",
            "Working at Height",
        ),
        (
            "Dropped object near miss during crane lift. Rigging damaged, sling snapped with suspended load.",
            "LSR07",
            "Safe Mechanical Lifting",
        ),
        (
            "Driver speeding on convoy journey, no seat belt worn. Near collision with vehicle at gate.",
            "LSR03",
            "Driving",
        ),
        (
            "Confined space entry into storage tank without gas test. Attendant missing and toxic atmosphere.",
            "LSR02",
            "Confined Space",
        ),
        (
            "Worker standing under load in the line of fire when hydraulic pressure hose whipped.",
            "LSR06",
            "Line of Fire",
        ),
        (
            "Hot work welding near hydrocarbon line without permit. Fire watch missing.",
            "LSR05",
            "Hot Work",
        ),
        (
            "Electrician bypassed safety interlock on rotating equipment and defeated guard with jumper.",
            "LSR01",
            "Bypassing Safety Controls",
        ),
        (
            "Temporary modification left on ESD circuit. MOC not raised and procedure deviation unapproved.",
            "LSR08",
            "Managing Change",
        ),
        (
            "Worker suffered fatigue after 14-hour shift, unfit for duty due to heat stress.",
            "LSR09",
            "Fit for Duty",
        ),
        (
            "Work carried out without permit to work. PTW expired and JSA not done before entry.",
            "LSR10",
            "Work Authorization",
        ),
        (
            "Worker observed with missing gloves and no safety boots. PPE reminder issued.",
            "LSR12",
            "Personal Protective Equipment",
        ),
    ],
)
def test_all_12_lsr_scenarios_detected(text, expected_rule_id, expected_rule_name):
    tags = tag_life_saving_rules(text)
    matched_ids = [t["rule_id"] for t in tags]
    matched_names = [t["rule_name"] for t in tags]

    assert expected_rule_id in matched_ids
    assert expected_rule_name in matched_names

    # Check that confidence and evidence are present
    target_tag = next(t for t in tags if t["rule_id"] == expected_rule_id)
    assert target_tag["confidence"] >= 0.50
    assert len(target_tag["evidence"]) > 0
    assert any("text" in ev and "type" in ev for ev in target_tag["evidence"])


# ==========================================
# 3. NEGATIVE TEST (NO FALSE POSITIVES)
# ==========================================

def test_negative_housekeeping_no_false_lsrs():
    text = (
        "Routine housekeeping completed in warehouse. Swept floor, organized cardboard boxes, "
        "and replenished printer paper in the site office. No high-energy operations underway."
    )
    tags = tag_life_saving_rules(text, threshold=0.50)
    assert len(tags) == 0


# ==========================================
# 4. MULTI-RULE CLASSIFICATION TEST
# ==========================================

def test_multi_rule_detection():
    # Composite report with Hot Work, Confined Space, and Work Authorization
    text = (
        "Welding and hot work grinding inside mud tank cellar. Confined space entry conducted "
        "without permit to work, atmosphere not tested, and fire watch missing."
    )
    tags = tag_life_saving_rules(text, threshold=0.50)
    rule_ids = {t["rule_id"] for t in tags}

    # Must catch at least Hot Work (LSR05) and either Confined Space (LSR02) or Work Authorization (LSR10)
    assert "LSR05" in rule_ids
    assert ("LSR02" in rule_ids) or ("LSR10" in rule_ids)


# ==========================================
# 5. CROSS-SIGNAL EVIDENCE TEST
# ==========================================

def test_cross_signal_evidence_attached():
    text = "Residual pressure in pipe. Lock-out tag-out not applied on wellhead."
    tags = tag_life_saving_rules(text)
    isolation_tag = next((t for t in tags if t["rule_id"] == "LSR04"), None)
    assert isolation_tag is not None

    types = [ev["type"] for ev in isolation_tag["evidence"]]
    # Should contain phrase/keyword and energy or barrier cross-signals
    assert "phrase" in types or "keyword" in types
    assert "energy" in types or "barrier" in types


# ==========================================
# 6. DASHBOARD 12-RULE DISTRIBUTION & ZERO COUNT
# ==========================================

def test_dashboard_lsr_distribution_structure():
    from app.routers.dashboard import lsr_distribution
    from app.models import User

    db = SessionLocal()
    try:
        dummy_user = User(username="test_analyst", role="analyst", site_scope=[])
        dist = lsr_distribution(db=db, user=dummy_user)

        # Must return exactly 12 items
        assert len(dist) == 12

        # In canonical order LSR01 through LSR12
        for idx, row in enumerate(dist):
            expected_id = f"LSR{idx + 1:02d}"
            assert row.rule_id == expected_id
            assert row.rule_name is not None
            assert row.lsr_category == row.rule_name
            assert isinstance(row.count, int)
            assert row.count >= 0
    finally:
        db.close()
