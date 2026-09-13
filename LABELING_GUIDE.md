# LABELING GUIDE — SIF Potential vs Non-SIF

**Audience:** OIL HSE Analysts, Site Managers (review), HSSE Leadership (senior override)  
**Purpose:** Produce defensible `HUMAN_VALIDATED` labels for gold-standard evaluation  
**Related:** `DATASET_CARD.md`, DEKRA / EEI / VelocityEHS pSIF framing, IOGP Life-Saving Rules

---

## 1. What you are labeling

You are labeling **SIF *potential*** (precursor / fatal potential), **not** reported injury severity alone.

| Concept | Meaning |
|---------|---------|
| **SIF** | Serious Injury or Fatality |
| **SIF potential (label = true)** | The described situation had credible potential for serious injury or fatality given the energy, exposure, and barrier state — even if nobody was hurt |
| **Non-SIF (label = false)** | Routine / low-energy condition without credible fatal potential under the criteria below |

**Do not** label solely because a report says “near miss” or “no injury.”  
**Do not** label solely because a public authority marked an outcome fatality — re-judge the *narrative* under precursor rules when creating HUMAN_VALIDATED labels.

---

## 2. Decision rule (project standard)

Mark **SIF potential = true** when the narrative supports **all three** (or a clearly fatal single mechanism):

1. **Hazardous energy** present or reasonably foreseeable  
   Examples: electrical, pressure, chemical/toxic, gravity (height / dropped object), thermal, mechanical (rotating / stored), vehicle/kinetic in industrial context.
2. **Exposure / proximity** of people to that energy  
   Examples: line of fire, under suspended load, in exclusion zone, entering energized/confined space, downstream of loss of containment.
3. **Barrier weakness or failure**  
   Examples: missing/defeated LOTO, incomplete isolation, absent gas test, failed interlock, missing fall protection, inadequate exclusion, PTW not followed for the energy source.

If energy + exposure exist with only thin/uncertain barriers, prefer **SIF** (safety-recall posture) and document uncertainty in `label_comment` / use `UNCERTAIN` in the UI review workflow until consensus.

Mark **Non-SIF = false** when the narrative is low-energy routine noise **without** credible energy–exposure–barrier fatal pathway (see §4).

---

## 3. Label record fields (required)

When recording a human label (UI or labeling queue), complete:

| Field | Requirement |
|-------|-------------|
| `report_id` | Pre-filled |
| `report_text` | Read fully before labeling |
| `sif_label` | `true` / `false` (UI: `SIF` / `NON_SIF`; use `UNCERTAIN` if genuinely undecidable) |
| `label_source` | Becomes `HUMAN_VALIDATED` only after consensus / senior override |
| `labeler_id` | Your authenticated user ID |
| `label_timestamp` | Set by system (UTC) |
| `label_confidence` | Your confidence `0.0–1.0` |
| `label_comment` | **Mandatory** short rationale citing energy / exposure / barrier (or why Non-SIF) |

Never invent labels for records you have not read.  
Never copy synthetic demo “expected” answers into gold without independent judgment — synthetic items are practice-only and **excluded from gold**.

---

## 4. SIF potential — positive examples (illustrative)

Label **SIF** when narratives resemble:

- Work on energized equipment without verified LOTO / isolation.
- Entry to confined space without gas test / attendant / rescue plan.
- Personnel under suspended load / in crane line of fire without exclusion.
- Working at height without harness / incomplete scaffold / unprotected edge.
- Hydrocarbon release with ignition sources or personnel in vapor cloud path.
- H₂S / toxic atmosphere exposure potential with barrier failure.
- High-pressure injection, ruptured pressurized hose in occupied area.
- Vehicle / heavy equipment interaction with pedestrians in blind zones during critical lifts or spotting failures.

Outcome may be “no injury.” Potential still counts.

---

## 5. Non-SIF — negative examples (illustrative)

Label **Non-SIF** when narratives resemble:

- Housekeeping: litter, general untidiness without energy exposure.
- Minor slip on wet floor in office corridor with no industrial energy.
- Missing glove / hard-hat compliance issue with **no** accompanying high-energy task.
- Administrative paperwork / signage gaps alone.
- Trivial first-aid-only office incidents without industrial energy.

If a “routine” observation **also** describes high energy (e.g., “missing glove while racking 11 kV breaker”), judge the **energy pathway**, not the glove alone → usually **SIF**.

---

## 6. Ambiguous / difficult cases

Use UI label `UNCERTAIN` (does **not** enter binary gold) when:

- Text is too sparse to identify energy or exposure.
- Contradictory facts; cannot establish barrier state.
- Indirect language only (“almost”, “could have”) without enough operational detail.

Queue categories in `challenge_candidates.jsonl` / `labeling_queue.json`:

| Category | What to watch for |
|----------|-------------------|
| `paraphrase` | Stay consistent with peer near-duplicates |
| `indirect_safety_description` | Judge potential, not “no injury” wording |
| `ambiguous` | Prefer UNCERTAIN over guessing |
| `unseen_terminology` | Look up domain terms; still apply energy–exposure–barrier |
| `difficult_non_sif_candidate` | Avoid over-flagging routine noise; avoid under-flagging hidden energy |

---

## 7. What does **not** count as gold

| Source | Use |
|--------|-----|
| `SYNTHETIC` | Demo / UI only — never gold |
| `HEURISTIC` | Weak supervision / model — bootstrap only |
| `IMPORTED` | Public PHMSA/CER/OISD/OSHA outcome tags — reference only |
| Single unconfirmed analyst label without consensus | `HUMAN_REVIEW` staging — promote via second reviewer |

Gold promotion rules (existing platform):

1. ≥2 independent agreeing reviews → `CONSENSUS_VALIDATED` → evaluation `HUMAN_VALIDATED`
2. Disagreement → senior (`admin` / `leadership`) override with rationale
3. AI prediction columns remain immutable (audit)

---

## 8. Labeling workflow (operational)

### A. From labeling queue file

1. Open `data/processed/evaluation/labeling_queue.json`.
2. For each item, assign `sif_label`, `label_confidence`, `label_comment`.
3. Enter the same judgment in the product UI (`Report Detail` → Label Review) so consensus and audit trail persist in the database.
4. Do not edit `gold_standard.jsonl` by hand to insert synthetic IDs.

### B. From product UI

1. Triage queue → open report.
2. Submit `LabelReview` with `SIF` / `NON_SIF` / `UNCERTAIN` + reason.
3. Second reviewer repeats.
4. On consensus, record becomes eligible for gold export on next:
   ```bash
   python3 backend/scripts/build_evaluation_dataset.py
   python3 backend/scripts/validate_dataset.py --write-corpus
   ```

### C. Inter-rater quality

- Review Cohen’s Kappa on the dashboard when multiple raters are active.
- Revisit `DISAGREEMENT` cases in calibration sessions.
- Prefer written energy/barrier rationale over one-word comments.

---

## 9. Ethics & integrity

- **Never fabricate labels** to inflate dataset size or metrics.
- **Never** treat synthetic or imported labels as equivalent to HUMAN_VALIDATED.
- If gold count is still low, report `INSUFFICIENT_VALIDATION_DATA` — do not invent evaluation scores.
- Redact PII is handled at ingestion; do not paste personal identifiers into `label_comment`.

---

## 10. Quick checklist

Before submitting a label:

- [ ] I read the full `report_text`
- [ ] I identified energy (or justified Non-SIF without it)
- [ ] I identified exposure / proximity (or justified absence)
- [ ] I identified barrier condition
- [ ] My `label_comment` cites those factors
- [ ] I set an honest `label_confidence`
- [ ] If unsure, I used `UNCERTAIN` instead of guessing

---

## 11. Reference alignment

- Project decision **D1**: classify via hazardous energy + proximity + barrier condition, not injury outcome alone (`memory.md`).
- PRD FR-1: binary SIF-potential vs non-SIF-potential with confidence.
- IOGP Life-Saving Rules: use as tagging aids, not as the sole SIF definition.
