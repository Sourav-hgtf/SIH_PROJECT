"""Runtime guarantees for the production PII detector dependency."""

from pathlib import Path

import pytest

from app.nlp import preprocess


def test_production_requires_spacy_detector(monkeypatch):
    monkeypatch.setattr(preprocess, "get_pii_detection_mode", lambda: "regex_fallback")

    assert preprocess.verify_pii_detector(require_spacy=False) == "regex_fallback"
    with pytest.raises(RuntimeError, match="en_core_web_sm is not loadable"):
        preprocess.verify_pii_detector(require_spacy=True)


def test_requirements_pin_the_spacy_model_wheel():
    requirements = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text()
    assert "spacy==3.7.5" in requirements
    assert "en_core_web_sm-3.7.1-py3-none-any.whl" in requirements
