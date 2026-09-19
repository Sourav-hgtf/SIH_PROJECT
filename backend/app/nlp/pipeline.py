from app.nlp.classify import classify_sif, tag_life_saving_rules
from app.nlp.precursors import extract_precursor
from app.nlp.preprocess import preprocess


def process_report_text(
    raw_text: str,
    equipment: str | None = None,
    job_type: str | None = None,
    threshold: float = 0.45,
) -> dict:
    """Full NLP pipeline: preprocess → classify SIF → tag LSR → extract precursors (semantic)."""
    cleaned = preprocess(raw_text)
    if cleaned.get("language_unsupported"):
        classification = classify_sif(cleaned["processed_text"], threshold=threshold)
        return {
            **cleaned,
            "classification": classification,
            "lsr_tags": [],
            "triple": None,
            "precursor": None,
        }

    classification = classify_sif(cleaned["processed_text"], threshold=threshold)
    tags = tag_life_saving_rules(cleaned["processed_text"])

    # Always extract precursors (not just for SIF-labelled reports);
    # semantic engine returns None fields rather than hallucinating.
    precursor = extract_precursor(
        cleaned["processed_text"],
        equipment=equipment,
        job_type=job_type,
        fallback_to_rules=True,
    )

    return {
        **cleaned,
        "classification": classification,
        "lsr_tags": tags,
        # Legacy 'triple' key preserved for backward compatibility
        "triple": precursor.to_legacy_triple() if precursor else None,
        # Full 6-dimensional precursor record
        "precursor": precursor,
    }
