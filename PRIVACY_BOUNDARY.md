# Privacy Boundary for SIF AI Processing

## AI-visible text

The SIF model receives only `processed_text` produced by:

```text
incoming narrative -> PII redaction -> spelling correction -> abbreviation expansion -> TF-IDF/model
```

`processed_text` is derived from `raw_text_redacted`, never from a stored original report. Names, employee IDs, phone numbers, and email addresses are replaced with `[PERSON]`, `[ID]`, `[PHONE]`, and `[EMAIL]` before feature extraction.

## Enforced boundaries

- Training accepts only `Report.raw_text_redacted`. A report missing that value is excluded with the safe reason code `PII_REDACTED_TEXT_REQUIRED`; `processed_text` is not used as a fallback.
- Inference preprocesses the supplied narrative, then checks the final model input with the same PII detector immediately before prediction. Detection blocks prediction with `PII_REDACTION_REQUIRED`; no report text is logged.
- `predict_sif_details` does not return caller-provided raw text. It returns only the safe `processed_text` and prediction metadata.
- Training metadata records only safe report IDs, exclusion reason codes, counts, and preprocessing version. PII values and report narrative are not written to audit metadata.

## Model feature boundary

The fitted SIF pipeline is a TF-IDF vectorizer over the PII-safe `processed_text` narrative. It does not receive report IDs, worker/reporter identity, employee ID, phone number, email, or raw text as features. Permitted safety terminology remains available after redaction.

## Safe metadata

Preprocessing returns `pii_redacted`, `pii_replacements`, and `preprocessing_version`. The ingestion path stores only the redacted and processed narratives. Classification feature metadata can safely include the redaction count and preprocessing version; it never stores detected values.

## Remaining limitation

The detector is intentionally conservative but cannot guarantee removal of every possible free-form identifier (for example, an unusual single-token nickname or a new identifier format). The pre-model boundary detects what the same configured detector recognizes. Production deployments should periodically review false-negative samples through an authorized privacy process and update the existing detector patterns without logging the underlying PII.
