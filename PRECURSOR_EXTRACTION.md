# Precursor Extraction

## Purpose

The Phase 6 extractor identifies evidence-backed SIF precursor patterns without replacing the existing rule engine. It produces a `PrecursorRecord` with six dimensions:

1. Activity
2. Location
3. Barrier failure
4. Hazard or exposure
5. Relevant Life-Saving Rule (LSR)
6. Evidence phrase

The original redacted report remains in the pipeline result as `raw_text_redacted`. Extraction operates on the preprocessed copy and never overwrites that source text.

## Decision flow

```text
Report
  -> NLP preprocessing
  -> explicit rule concepts + conservative semantic patterns
  -> optional local dense similarity when available
  -> legacy triple fallback when no modern activity/barrier is found
  -> evidence-backed PrecursorRecord
```

Exact patterns remain the highest-confidence source. Semantic patterns are narrow, domain-specific paraphrases that require an operational action and its safety meaning. For example, “broke open the process pipe before proving it was isolated” maps to line dismantling and an unverified isolation barrier, with the matching text retained as evidence. Dense similarity is only an additional local signal; it does not create a location.

## Anti-hallucination rules

- `location` is `null` unless a known location appears in the report or explicitly supplied equipment metadata.
- Activity, barrier, hazard, and LSR are `null` when no sufficiently supported extraction exists.
- Evidence is verbatim text from the report (or explicitly marked metadata), never a generated quotation.
- The relevant LSR resolves only from a supported barrier, then activity, then hazard. It is always one of the canonical taxonomy IDs.

## Record contract

`PrecursorRecord` stores:

- `evidence`: per-field evidence spans for activity, location, barrier failure, and hazard/exposure.
- `field_methods`: the source for each field (`rule`, `semantic_pattern`, `dense_semantic`, `metadata`, legacy fallback, or `unknown`).
- `field_confidence`: a field-level confidence score, with zero for unsupported fields.
- `confidence` and `extraction_method`: record-level confidence and version (`hybrid_semantic_v2`).
- `secondary_activities` and `secondary_barriers`: additional justified detections in compound reports.

## Example

Input: “Technician dismantled the pressurized line without confirming isolation.”

- Activity: `Line dismantling / piping break`
- Location: `null`
- Barrier failure: `Isolation not verified`
- Hazard/exposure: `Stored / pressurized energy`
- Relevant LSR: `LSR04 — Energy Isolation`
- Evidence phrase: `without confirming isolation`

The missing location is intentional: an asset or work type is not treated as a stated location.

## Validation

`backend/tests/test_precursors.py` covers explicit and indirect precursors, absent locations, multiple barriers, multiple activities, ambiguous reports, raw-text preservation, evidence, extraction method, and confidence.
