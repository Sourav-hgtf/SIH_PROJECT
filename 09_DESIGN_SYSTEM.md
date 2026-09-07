# SIF Sentinel — Dashboard Design System
> A quiet analyst's desk, with risk color where it actually matters

**Theme:** light
**Adapted from:** Seline Analytics style reference — warm-neutral canvas, hairline-bordered flat cards, compact Inter rhythm, pill-shaped filter controls. Marketing-site elements (mascot illustration, testimonial cards, star ratings, avatar cluster) are dropped; a semantic red/amber/green risk scale is added, since severity color-coding is a functional requirement for this tool, not a brand accent.

This system sits on a warm-stone canvas (`#fafaf9`) with flat white cards separated by 1px hairline borders instead of heavy shadows — calm, legible, and unhurried, in the spirit of the source reference. The one meaningful departure: where Seline reserves color for a single brand accent, this system spends color deliberately on **risk severity** — red, amber, and green are reserved exclusively for SIF risk signals, never used decoratively, so a colored badge always means something.

## Tokens — Colors

### Neutrals (carried over from source reference)
| Name | Value | Token | Role |
|------|-------|-------|------|
| Stone Canvas | `#fafaf9` | `--color-stone-canvas` | Page background |
| Pure White | `#ffffff` | `--color-pure-white` | Card surfaces, table rows, input fills |
| Stone Border | `#e8e6e5` | `--color-stone-border` | Hairline borders — primary structural device |
| Stone Muted | `#d6d3d1` | `--color-stone-muted` | Secondary borders, subtle tints |
| Ash Gray | `#a8a29e` | `--color-ash-gray` | Muted helper text, disabled states, unclassified badge |
| Warm Gray | `#78716c` | `--color-warm-gray` | Body copy, secondary labels, table sub-text |
| Ink Black | `#0c0a09` | `--color-ink-black` | Primary text, headings, active nav |
| Soot | `#1c1917` | `--color-soot` | Sidebar background, active tab fill |

### Accent (non-alarm actions only)
| Name | Value | Token | Role |
|------|-------|-------|------|
| Cyan Signal | `#3ba6f1` | `--color-cyan-signal` | Primary action buttons, links, focus rings — informational, never used for risk |
| Cyan Edge | `#3398e1` | `--color-cyan-edge` | Outlined buttons, linked text |
| Sky Wash | `#c1e1f7` | `--color-sky-wash` | Background wash behind cyan-accented elements |

### Risk Severity (new — functional, not decorative)
| Name | Value | Token | Role |
|------|-------|-------|------|
| Risk Critical | `#dc2626` | `--color-risk-critical` | SIF-potential = true, high confidence — badges, alert borders |
| Risk Critical Wash | `#fee2e2` | `--color-risk-critical-wash` | Background fill behind critical badges/rows |
| Risk Medium | `#d97706` | `--color-risk-medium` | Borderline SIF / low-confidence flags needing analyst review |
| Risk Medium Wash | `#fef3c7` | `--color-risk-medium-wash` | Background fill behind medium badges/rows |
| Risk Low | `#16a34a` | `--color-risk-low` | Confirmed non-SIF, or analyst-cleared reports |
| Risk Low Wash | `#dcfce7` | `--color-risk-low-wash` | Background fill behind low-risk badges/rows |
| Risk Unclassified | `#a8a29e` | `--color-risk-unclassified` | Not yet processed / pending classification |

**Rule:** red, amber, and green never appear anywhere except a risk badge, a risk-tier row highlight, or the trend chart's SIF-rate series. No decorative use, no charts unrelated to risk, no marketing accents in these three hues — that's what keeps them trustworthy at a glance.

## Tokens — Typography

Unlike the source reference's two-typeface system (display serif-adjacent + body sans), this dashboard uses **Inter throughout, one family, three weights**. A data-dense analyst tool is read in short bursts all day; a second display typeface adds visual variety the use case doesn't need and slows scanning.

### Inter — the only typeface
- **Weights:** 400 (body), 500 (labels, table headers), 600 (page titles, KPI numbers)
- **Substitute:** system-ui, -apple-system, "Segoe UI", Roboto

### Type Scale
| Role | Size | Line Height | Weight | Token |
|------|------|-------------|--------|-------|
| caption | 11px | 1.4 | 400 | `--text-caption` |
| body-sm | 12px | 1.5 | 400 | `--text-body-sm` |
| body | 14px | 1.6 | 400 | `--text-body` |
| label | 13px | 1.4 | 500 | `--text-label` |
| kpi-number | 28px | 1.2 | 600 | `--text-kpi` |
| heading-sm | 18px | 1.3 | 600 | `--text-heading-sm` |
| heading-lg | 24px | 1.25 | 600 | `--text-heading-lg` |

No 52px display size — this system has no marketing hero to fill. `heading-lg` is the largest text on any screen (page titles like "Dashboard Overview").

## Tokens — Spacing & Shapes

**Base unit:** 4px · **Density:** compact (unchanged from source — right fit for data-dense screens)

### Spacing Scale
| Name | Value | Token |
|------|-------|-------|
| 4 | 4px | `--spacing-4` |
| 8 | 8px | `--spacing-8` |
| 12 | 12px | `--spacing-12` |
| 16 | 16px | `--spacing-16` |
| 24 | 24px | `--spacing-24` |
| 32 | 32px | `--spacing-32` |
| 48 | 48px | `--spacing-48` |
| 64 | 64px | `--spacing-64` |

*(Source reference's 80/96/160px section-gap steps are dropped — those exist for marketing-page pacing; a dashboard's sections sit closer together.)*

### Border Radius
| Element | Value | Note |
|---------|-------|------|
| filter chips / tags | 9999px | Kept from source — pill shape reads well for toggleable filters |
| risk badges | 6px | Small rectangle, not a pill — badges should read as data labels, not buttons |
| cards | 10px | Unchanged |
| inputs | 6px | Unchanged |
| primary/secondary buttons | 8px | **Changed from pill (9999px).** A rounded rectangle reads as enterprise software; reserving pill shapes for filters/tags only prevents every clickable thing on the page looking the same |

### Shadows
| Name | Value | Token | Use |
|------|-------|-------|-----|
| card | `rgba(0,0,0,0.05) 0px 4px 16px 0px` | `--shadow-card` | Flat content cards, cluster cards |
| row-hover | `rgba(0,0,0,0.04) 0px 1px 4px 0px` | `--shadow-row-hover` | Table row hover state |
| dropdown | `rgba(0,0,0,0.1) 0px 4px 6px -1px, rgba(0,0,0,0.1) 0px 2px 4px -2px` | `--shadow-dropdown` | Filter dropdowns, select menus |

*(Source reference's 45px-blur hero shadow is dropped entirely — there is no floating hero screenshot in an internal tool.)*

## Components

### Sidebar Navigation *(replaces source reference's top-nav + avatar cluster)*
**Role:** Primary navigation — Dashboard, Triage Queue, Cluster Explorer, Admin (role-gated)

Fixed-width 220px left sidebar, `--color-soot` (#1c1917) background, white text. Active item: `--color-cyan-signal` left border (3px) + white text at weight 500. Inactive items: `#a8a29e` text, hover to white. No avatar cluster — this is an internal tool, not a social-proof surface.

### KPI Tile
**Role:** Top-of-dashboard summary numbers — "Total Reports," "SIF-Flagged," "Avg. Confidence"

White fill, 10px radius, 1px `--color-stone-border`, 16px padding, `--shadow-card`. Number in `--text-kpi` (28px, weight 600, `--color-ink-black`). Label above number in `--text-label`, `--color-warm-gray`. Optional small risk-colored delta indicator (▲/▼ + %) beside the number when comparing to a prior period.

### Risk Badge *(new — the core departure from source)*
**Role:** SIF classification indicator — appears in every report row, report detail, and cluster card

6px-radius rectangle, sized to text + 8px horizontal padding, 4px vertical. Three states:
- **Critical:** text `--color-risk-critical`, background `--color-risk-critical-wash`
- **Medium:** text `--color-risk-medium`, background `--color-risk-medium-wash`
- **Low:** text `--color-risk-low`, background `--color-risk-low-wash`

12px Inter weight 500. Always paired with a text label ("Critical," "Medium," "Low") — never color alone, for accessibility and because color-blind analysts must be able to triage correctly.

### Confidence Indicator
**Role:** Shows model confidence alongside a risk badge

A short 40px-wide horizontal bar, `--color-stone-muted` track, filled proportionally in the same hue as the adjacent risk badge (critical/medium/low), with the percentage in `--text-caption` beside it. Never shown without its paired risk badge.

### Filter Bar *(adapted from source reference's Tab Pill Group + Text Input)*
**Role:** Global dashboard filters — site, date range, LSR category, confidence threshold

Horizontal row of pill-shaped chips (9999px radius), inactive state: transparent fill, 1px `--color-stone-border`, `--color-ink-black` text. Active/selected: `--color-soot` fill, white text — same active-state treatment as source reference's tab group. Date-range and text inputs use the source reference's Text Input component unchanged (white fill, 6px radius, 1px `--color-stone-muted` border, cyan focus ring).

### Data Table Row
**Role:** Triage queue list, report list, audit log

White background, 1px `--color-stone-border` bottom rule (no full cell borders — hairline-as-structure, per source reference's philosophy). Hover state: `--shadow-row-hover` + very light `--color-stone-canvas` tint. Each row: risk badge, confidence indicator, report excerpt (`--text-body`, `--color-ink-black`), site/date in `--text-body-sm`, `--color-warm-gray`, and up to 2 LSR tag chips (cyan-edge outline pills, not risk colors — LSR category is informational, not a severity signal).

### Cluster Card *(replaces source reference's Flat Content Card, same visual bones)*
**Role:** Precursor cluster preview in the Cluster Explorer

White fill, 10px radius, 1px `--color-stone-border`, 24px padding, `--shadow-card` — identical shell to the source reference's Feature Card. Heading: representative activity/location/barrier-failure triple, `--text-heading-sm`, `--color-ink-black`. Cluster size and trend arrow (▲ growing / ▬ stable / ▼ shrinking) in `--text-body-sm`, `--color-warm-gray`, with the trend arrow colored using risk-medium (growing) or risk-low (shrinking) to reuse the severity vocabulary meaningfully.

### Explainability Highlight *(adapted from source reference's Highlighted Text Span)*
**Role:** Inline highlight of the phrases driving a SIF classification, inside report text

Same mechanic as the source reference's cyan highlight span, but re-mapped: text colored in the matching risk hue (critical/medium/low) with a soft matching wash background (pill-shaped, ~2px 8px padding, 4px radius). Multiple phrases may be highlighted per report — unlike the source reference's "one per headline" rule, this is exhaustive by design: an analyst needs to see every phrase that drove the score, not just one.

### Analyst Action Buttons
**Role:** Confirm / override controls in the triage queue

**Confirm:** rounded-rectangle (8px radius), `--color-risk-low` outline, `--color-risk-low` text, transparent fill; fills solid on hover.
**Override:** rounded-rectangle (8px radius), `--color-risk-critical` outline, `--color-risk-critical` text, transparent fill; opens a required-comment field on click. Neither button uses the cyan accent — action buttons that change a safety-relevant record are visually distinct from cyan's "everyday, low-stakes action" meaning.

### Primary Action Button *(adapted from source reference)*
**Role:** Non-safety-relevant primary actions — "Export report," "Save filter view," "Add user" (Admin)

Rounded rectangle (8px radius, changed from source's pill), fill `--color-cyan-signal`, white text weight 500, 8px 16px padding. Reserved for actions with no risk-classification consequence, keeping cyan's meaning consistent everywhere.

### Text Input *(unchanged from source reference)*
White fill, 6px radius, 1px `--color-stone-muted` border, placeholder `--color-warm-gray`, 2px cyan focus ring.

## Components Dropped From the Source Reference
These exist in the Seline style purely to serve a marketing landing page and have no role in an internal analyst tool:
- Mascot sticker illustration
- Testimonial card + star rating display
- Signed-in avatar cluster
- Floating hero dashboard preview (45px shadow, grayscale filter)
- Logo wordmark treatment (replace with OIL/project branding per actual guidelines, not designed here)

## Do's and Don'ts

### Do
- Reserve red/amber/green exclusively for SIF risk severity — never for anything else, including charts, alerts unrelated to classification, or decorative accents
- Pair every risk badge with a text label, not color alone
- Keep the cyan accent for actions that carry no safety-classification weight — exports, saves, admin CRUD
- Use hairline borders (`--color-stone-border`) as the default separator inside cards and tables; reserve shadow for cards that need to visually lift off the canvas (KPI tiles, cluster cards)
- Keep pill shapes for filter chips and LSR tags only — badges and buttons stay rectangular so the eye can tell "toggle" apart from "status" and "action" at a glance

### Don't
- Do not use `--color-cyan-signal` on Confirm/Override buttons — those are safety-relevant actions and must stay visually distinct from routine UI actions
- Do not introduce additional accent hues beyond cyan (informational) and the red/amber/green risk triad — a fourth color erodes the "color always means something specific" contract
- Do not apply the source reference's 45px floating-preview shadow anywhere in this system — there is no marketing hero surface here
- Do not set risk badges as pill-shaped — pills are reserved for filters/tags in this system, so a pill-shaped badge would be misread as a toggle
- Do not mix in a second display typeface for page titles — Inter at weight 600 carries every heading level in this system

## Quick Start — CSS Custom Properties

```css
:root {
  /* Neutrals */
  --color-stone-canvas: #fafaf9;
  --color-pure-white: #ffffff;
  --color-stone-border: #e8e6e5;
  --color-stone-muted: #d6d3d1;
  --color-ash-gray: #a8a29e;
  --color-warm-gray: #78716c;
  --color-ink-black: #0c0a09;
  --color-soot: #1c1917;

  /* Accent (non-risk actions only) */
  --color-cyan-signal: #3ba6f1;
  --color-cyan-edge: #3398e1;
  --color-sky-wash: #c1e1f7;

  /* Risk severity (functional, not decorative) */
  --color-risk-critical: #dc2626;
  --color-risk-critical-wash: #fee2e2;
  --color-risk-medium: #d97706;
  --color-risk-medium-wash: #fef3c7;
  --color-risk-low: #16a34a;
  --color-risk-low-wash: #dcfce7;
  --color-risk-unclassified: #a8a29e;

  /* Typography */
  --font-inter: 'Inter', system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --text-caption: 11px;
  --text-body-sm: 12px;
  --text-body: 14px;
  --text-label: 13px;
  --text-kpi: 28px;
  --text-heading-sm: 18px;
  --text-heading-lg: 24px;

  /* Spacing */
  --spacing-4: 4px;
  --spacing-8: 8px;
  --spacing-12: 12px;
  --spacing-16: 16px;
  --spacing-24: 24px;
  --spacing-32: 32px;
  --spacing-48: 48px;
  --spacing-64: 64px;

  /* Radius */
  --radius-tags: 9999px;
  --radius-badge: 6px;
  --radius-card: 10px;
  --radius-input: 6px;
  --radius-button: 8px;

  /* Shadows */
  --shadow-card: rgba(0, 0, 0, 0.05) 0px 4px 16px 0px;
  --shadow-row-hover: rgba(0, 0, 0, 0.04) 0px 1px 4px 0px;
  --shadow-dropdown: rgba(0, 0, 0, 0.1) 0px 4px 6px -1px, rgba(0, 0, 0, 0.1) 0px 2px 4px -2px;
}
```
