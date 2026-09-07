from app.nlp.classify import classify_sif, tag_life_saving_rules
from app.nlp.mining import extract_triple
from app.nlp.preprocess import preprocess


def process_report_text(raw_text: str, equipment: str | None = None, job_type: str | None = None, threshold: float = 0.45) -> dict:
    cleaned = preprocess(raw_text)
    classification = classify_sif(cleaned["processed_text"], threshold=threshold)
    tags = tag_life_saving_rules(cleaned["processed_text"])
    triple = None
    if classification["sif_label"]:
        triple = extract_triple(cleaned["processed_text"], equipment=equipment, job_type=job_type)
    return {
        **cleaned,
        "classification": classification,
        "lsr_tags": tags,
        "triple": triple,
    }
