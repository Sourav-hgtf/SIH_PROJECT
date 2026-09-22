"""test_multilingual_fallback.py - Unit and integration tests for safe multilingual fallback.

Verifies:
1. Script detection: majority-Devanagari, majority-Assamese, and English.
2. Preprocessing fallback: sets language_unsupported=True and routes to
   classification_state="LANGUAGE_UNSUPPORTED_NEEDS_REVIEW" and requires_analyst_review=True.
3. classify_sif and predict_sif_details fallback for unsupported languages.
4. Full process_report_text pipeline gracefully returns empty LSR tags and precursors.
5. Real Hindi sentence vs real English sentence classification comparison.
6. Real Assamese sentence classification verification.
7. /predict endpoint HTTP response with valid token.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

from app.nlp.classify import classify_sif, tag_life_saving_rules
from app.nlp.decision import requires_analyst_review
from app.nlp.model import predict_sif_details
from app.nlp.pipeline import process_report_text
from app.nlp.precursors import extract_precursor
from app.nlp.preprocess import (
    detect_unsupported_language_script,
    preprocess,
)

# Real domain-specific test narratives
HINDI_REPORT = "मचान पर काम करते समय सुरक्षा हार्नेस नहीं पहना गया था।"
ASSAMESE_REPORT = "উচ্চতাত কাম কৰাৰ সময়ত সুৰক্ষা বেল্ট ব্যৱহাৰ কৰা হোৱা নাছিল।"
ENGLISH_SIF_REPORT = "Worker entered a confined space without gas testing."
ENGLISH_SAFE_REPORT = "Permit to work was valid and safety barrier was inspected."


def test_detect_unsupported_language_script():
    """Verify script detection for Devanagari, Assamese, and English."""
    assert detect_unsupported_language_script(HINDI_REPORT) == "devanagari"
    assert detect_unsupported_language_script(ASSAMESE_REPORT) == "assamese"
    assert detect_unsupported_language_script(ENGLISH_SIF_REPORT) is None
    assert detect_unsupported_language_script(ENGLISH_SAFE_REPORT) is None
    assert detect_unsupported_language_script("") is None
    assert detect_unsupported_language_script("   ") is None
    assert detect_unsupported_language_script("12345 67890 !@#$%") is None


def test_preprocess_multilingual_fallback():
    """Verify preprocess marks unsupported languages with required review."""
    # Hindi
    prep_hi = preprocess(HINDI_REPORT)
    assert prep_hi["language_unsupported"] is True
    assert prep_hi["detected_script"] == "devanagari"
    assert prep_hi["classification_state"] == "LANGUAGE_UNSUPPORTED_NEEDS_REVIEW"
    assert prep_hi["requires_analyst_review"] is True
    assert prep_hi["negation_detection_enabled"] is False

    # Assamese
    prep_as = preprocess(ASSAMESE_REPORT)
    assert prep_as["language_unsupported"] is True
    assert prep_as["detected_script"] == "assamese"
    assert prep_as["classification_state"] == "LANGUAGE_UNSUPPORTED_NEEDS_REVIEW"
    assert prep_as["requires_analyst_review"] is True

    # English
    prep_en = preprocess(ENGLISH_SIF_REPORT)
    assert prep_en["language_unsupported"] is False
    assert prep_en["detected_script"] is None
    assert prep_en["classification_state"] is None
    assert prep_en["requires_analyst_review"] is False


def test_classify_sif_hindi_fallback():
    """Verify classify_sif routes real Hindi text to LANGUAGE_UNSUPPORTED_NEEDS_REVIEW."""
    result = classify_sif(HINDI_REPORT)
    assert result["classification_state"] == "LANGUAGE_UNSUPPORTED_NEEDS_REVIEW"
    assert result["requires_analyst_review"] is True
    assert result["sif_label"] is False
    assert result["language_unsupported"] is True
    assert result["detected_script"] == "devanagari"
    assert result["calibration_status"] == "LANGUAGE_UNSUPPORTED"


def test_classify_sif_assamese_fallback():
    """Verify classify_sif routes real Assamese text to LANGUAGE_UNSUPPORTED_NEEDS_REVIEW."""
    result = classify_sif(ASSAMESE_REPORT)
    assert result["classification_state"] == "LANGUAGE_UNSUPPORTED_NEEDS_REVIEW"
    assert result["requires_analyst_review"] is True
    assert result["sif_label"] is False
    assert result["language_unsupported"] is True
    assert result["detected_script"] == "assamese"


def test_classify_sif_english_normal():
    """Verify real English SIF text is normally classified without fallback."""
    result = classify_sif(ENGLISH_SIF_REPORT)
    assert result["classification_state"] == "SIF_LIKELY"
    assert result["sif_label"] is True
    assert result.get("language_unsupported") is not True


def test_predict_sif_details_multilingual_fallback():
    """Verify predict_sif_details safely routes non-English text to analyst review."""
    details_hi = predict_sif_details(HINDI_REPORT)
    assert details_hi["classification_state"] == "LANGUAGE_UNSUPPORTED_NEEDS_REVIEW"
    assert details_hi["requires_analyst_review"] is True
    assert details_hi["sif_potential"] is False
    assert details_hi["calibration_status"] == "LANGUAGE_UNSUPPORTED"

    details_en = predict_sif_details(ENGLISH_SIF_REPORT)
    assert details_en["classification_state"] == "SIF_LIKELY"
    assert details_en["sif_potential"] is True


def test_pipeline_process_report_text_multilingual():
    """Verify full NLP pipeline gracefully handles multilingual reports without hallucinations."""
    res_hi = process_report_text(HINDI_REPORT)
    assert res_hi["language_unsupported"] is True
    assert res_hi["detected_script"] == "devanagari"
    assert res_hi["classification"]["classification_state"] == "LANGUAGE_UNSUPPORTED_NEEDS_REVIEW"
    assert res_hi["classification"]["requires_analyst_review"] is True
    assert res_hi["lsr_tags"] == []
    assert res_hi["triple"] is None
    assert res_hi["precursor"] is None

    res_en = process_report_text(ENGLISH_SIF_REPORT)
    assert res_en["language_unsupported"] is False
    assert res_en["classification"]["classification_state"] == "SIF_LIKELY"
    assert len(res_en["lsr_tags"]) > 0


def test_tag_life_saving_rules_and_precursors_multilingual():
    """Verify LSR tagger and precursor extractor bypass unsupported scripts safely."""
    assert tag_life_saving_rules(HINDI_REPORT) == []
    assert tag_life_saving_rules(ASSAMESE_REPORT) == []

    prec_hi = extract_precursor(HINDI_REPORT)
    assert prec_hi.activity is None
    assert prec_hi.extraction_method == "unsupported_language"


def test_requires_analyst_review_decision_function():
    """Verify requires_analyst_review returns True for LANGUAGE_UNSUPPORTED_NEEDS_REVIEW."""
    assert requires_analyst_review("LANGUAGE_UNSUPPORTED_NEEDS_REVIEW") is True
    assert requires_analyst_review("UNCERTAIN") is True
    assert requires_analyst_review("SIF_LIKELY") is False
    assert requires_analyst_review("NON_SIF") is False


client = TestClient(app)


@pytest.fixture(scope="module")
def analyst_headers():
    from app.database import SessionLocal
    from app.models import User
    from app.auth import create_token, hash_password

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "analyst").first()
        if not user:
            user = User(
                username="analyst",
                password_hash=hash_password("analyst123"),
                role="analyst",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        token = create_token(user.id, "access", 60)
        return {"Authorization": f"Bearer {token}"}
    finally:
        db.close()


def test_predict_endpoint_multilingual(analyst_headers: dict[str, str]):
    """Verify POST /predict HTTP endpoint returns valid LANGUAGE_UNSUPPORTED_NEEDS_REVIEW schema."""
    resp_hi = client.post("/predict", json={"text": HINDI_REPORT}, headers=analyst_headers)
    assert resp_hi.status_code == 200
    data_hi = resp_hi.json()
    assert data_hi["classification_state"] == "LANGUAGE_UNSUPPORTED_NEEDS_REVIEW"
    assert data_hi["requires_analyst_review"] is True
    assert data_hi["sif_potential"] is False

    resp_en = client.post("/predict", json={"text": ENGLISH_SIF_REPORT}, headers=analyst_headers)
    assert resp_en.status_code == 200
    data_en = resp_en.json()
    assert data_en["classification_state"] == "SIF_LIKELY"
    assert data_en["sif_potential"] is True

