# Intervention Priority Scoring (IPS)

## Overview & Safety Rationale

In high-hazard industrial environments (such as oil & gas, mining, construction, and power generation), thousands of safety observations, unsafe acts, and near misses are reported annually. While machine learning classifiers identify **SIF Potential** (the likelihood that an event possessed the precursors to cause a Serious Injury or Fatality), HSE teams face a distinct operational question:

> **"Which safety issue should an HSE analyst or site manager investigate or intervene on first, and why?"**

**Intervention Priority Scoring (IPS)** is an **explainable, deterministic decision-support layer** built on top of the SIF classifier. It computes a transparent **0–100 numerical score** and assigns a qualitative **action tier** (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`) without altering or overriding the statistical SIF probability.

---

## The Deterministic Formula

The priority score is computed from 6 weighted components configured centrally in [`configs/business_rules.yaml`](file:///Users/souravranjansamal/Documents/SIH_PROJECT%200/configs/business_rules.yaml):

$$\text{Priority Raw} = \sum_{i=1}^6 w_i \cdot s_i$$
$$\text{Priority Score} = \min(100.0, \max(0.0, \text{Priority Raw} \times 100))$$

### 1. Component Weights & Definitions

| Component | Weight ($w_i$) | Raw Range | Normalization ($s_i$) | Rationale |
|---|---|---|---|---|
| **SIF Potential** | **0.35** | 0.0 – 1.0 | Clamped $[0.0, 1.0]$ | Strongest individual signal from the ML model; already integrates narrative text, energy sources, and barrier state. |
| **Barrier Criticality** | **0.25** | 0.0 – 1.0 | Highest matching barrier criticality $[0.0, 1.0]$ | Missing or bypassed critical safety barriers (e.g., LOTO, isolation, ESD) are the direct precursors to fatal releases. |
| **Recurrence** | **0.15** | $1 \dots N$ | $\frac{\ln(1 + \text{cluster\_size})}{\ln(1 + \text{recurrence\_cap})}$ | Repeated occurrences of the same precursor indicate systematic control failures that will not resolve spontaneously. |
| **Trend Velocity** | **0.10** | Status | Configured status score (0.15 – 1.0) | Accelerating or new patterns demand urgent intervention before escalating. |
| **Exposure Volume** | **0.08** | $1 \dots N$ | $\frac{\ln(1 + \text{report\_count})}{\ln(1 + \text{exposure\_cap})}$ | Higher report volume means wider frontline workforce exposure. |
| **Cross-Site Spread** | **0.07** | $1 \dots N$ | $\min(1.0, \frac{\text{site\_count}}{\text{max\_sites}})$ | Patterns spanning multiple assets indicate enterprise-wide equipment or procedural deficiencies. |

$\sum w_i = 0.35 + 0.25 + 0.15 + 0.10 + 0.08 + 0.07 = 1.00$.

---

## Action Tiers & Response SLA

| Tier | Score Range | Default Action Recommendation |
|---|---|---|
| **CRITICAL** | **70 – 100** | **Immediate HSE intervention required:** Halt related high-risk tasks, verify critical physical barriers (LOTO/isolation/guarding), and convene emergency safety stand-down. |
| **HIGH** | **50 – 69.9** | **Action required in current shift/cycle:** Conduct field barrier verification, review job safety analysis (JSA), and brief frontline supervisors. |
| **MEDIUM** | **30 – 49.9** | **Scheduled action recommended:** Review control trends in next weekly HSE meeting, inspect equipment condition, and reinforce relevant Life-Saving Rules. |
| **LOW** | **0 – 29.9** | **Routine monitoring:** Log observation in periodic safety audit register. |

---

## Centralized Configuration (`configs/business_rules.yaml`)

All parameters are strictly defined in `configs/business_rules.yaml` and validated via Pydantic on application startup:

```yaml
priority:
  version: "priority-v1"
  weights:
    sif_probability: 0.35
    barrier_criticality: 0.25
    recurrence: 0.15
    trend: 0.10
    exposure: 0.08
    cross_site: 0.07
  tiers:
    critical: 70
    high: 50
    medium: 30
  trend_scores:
    growing: 1.0
    new: 0.85
    stable: 0.45
    shrinking: 0.15
    insufficient_data: 0.30
  cross_site:
    enabled: true
    max_sites: 4
  normalization:
    recurrence_cap: 10
    exposure_cap: 20
  barrier_criticality:
    "isolation": 1.0
    "loto": 1.0
    "interlock": 0.9
    "bypassed": 0.9
    "line-of-fire": 0.8
    "permit": 0.8
    "fall protection": 0.8
    # ...
```

---

## System Integration & API Surface

1. **`GET /v1/reports` & `GET /v1/reports/{id}`**:
   Returns the full `priority` object with numerical score, tier, natural language explanation, action recommendation, and detailed 6-factor component breakdown.

2. **`GET /v1/clusters`**:
   Supports `sort_by=priority` to rank precursor hazard patterns by actionable operational risk.

3. **`GET /v1/dashboard/priority-summary`**:
   Provides real-time tier counts and distribution percentages across all scoped facilities.

4. **`GET /v1/admin/priority-config`**:
   Exposes the active business rules configuration for auditability and compliance.
