# 04 — Frontend Specialization (Dashboard Spec)

## 1. Tech Stack
- **Framework:** React (prototype may alternatively use Streamlit for speed of delivery)
- **Charts:** Recharts and/or D3.js
- **Styling:** Component-based styling (e.g., Tailwind or CSS Modules); consistent with OIL branding guidelines where available
- **State Management:** React Context or lightweight state library (Zustand/Redux Toolkit) for filters and session state

## 2. Core Pages / Views

### 2.1 Login / Landing
- Authentication form (username/password, MFA prompt where applicable).
- Post-login landing page shows role-appropriate default view (Analyst → Triage Queue; Site Manager/Leadership → Dashboard Overview).

### 2.2 Dashboard Overview
- **SIF-Density Ranking:** Ranked list/heatmap of sites and activities by SIF-precursor density (count and rate).
- **LSR Distribution:** Bar/donut chart showing frequency of each of the 12 IOGP Life-Saving Rules across flagged reports, filterable by site/date.
- **Trend View:** Line chart of SIF-potential rate vs. total report volume over time (to visually demonstrate the two metrics diverging/converging).
- **Global Filters:** Date range, site, department, LSR category, confidence threshold — applied consistently across all dashboard widgets.

### 2.3 Precursor Cluster Explorer
- List/grid of identified precursor clusters, each showing: representative (Activity, Location, Barrier-failure) triple, cluster size, trend (growing/stable/shrinking).
- Click-through to a cluster detail view listing all underlying source reports (text + metadata) belonging to that cluster.

### 2.4 Triage Queue (Analyst view)
- Chronological/priority queue of newly classified reports, sorted by SIF-probability (highest first) and confidence.
- Each queue item shows: report excerpt, SIF-label + confidence, LSR tags, contributing phrases (explainability highlight).
- Inline actions: **Confirm classification**, **Override classification**, **Adjust LSR tags**, with a required short comment on override.

### 2.5 Report Detail View
- Full report text (redacted), metadata (site, shift, department, equipment, job type).
- SIF classification result with confidence score and highlighted contributing phrases.
- Assigned LSR tags with source indicator (rule-based vs. model-based).
- Cluster membership (if part of a precursor cluster), with a link to the cluster view.
- Analyst feedback history for this report.

### 2.6 Admin Panel
- User management (create/edit/deactivate users, assign roles and site-scope).
- Data source/integration configuration (HSSE platform connection settings).
- Audit log viewer (read-only, filterable by user/action/date).

## 3. Explainability UI Requirements
- Contributing phrases for SIF classification must be **visually highlighted inline** within the report text (not just listed separately), so analysts can quickly verify the model's reasoning.
- Confidence scores are shown as both a numeric value and a simple visual indicator (e.g., color-coded badge: high/medium/low confidence).
- LSR tags display their source (rule-based vs. model-based) so analysts understand which layer produced each tag.

## 4. Role-Based UI Behavior
| Role | Dashboard Overview | Triage Queue | Cluster Explorer | Admin Panel |
|---|---|---|---|---|
| Analyst | Site-scoped | Full access | Site-scoped | No access |
| Site Manager | Site-scoped (own site) | View-only | Site-scoped | No access |
| HSSE Leadership | Org-wide, read-only | View-only | Org-wide | No access |
| Admin | Org-wide | No access | Org-wide | Full access |

## 5. Design Principles
- **Clarity over decoration:** Given the fatality-relevant nature of the data, avoid visual gimmicks; prioritize legible charts, clear color-coding (e.g., red/amber/green for SIF risk tiers), and unambiguous labeling.
- **Fast triage:** The Triage Queue is the highest-frequency-use screen for Analysts — optimize for minimal clicks between "see report" → "confirm/override" → "next report."
- **Consistent filtering:** Filters set on the Dashboard Overview should persist (or be easily re-applied) when navigating to the Cluster Explorer.
- **Accessibility:** Sufficient color contrast for red/amber/green risk indicators; do not rely on color alone (use icons/labels alongside).

## 6. Responsive/Device Considerations
- Primary target: desktop/laptop browsers (HSE office and site-office use).
- Dashboard Overview should degrade gracefully to tablet width for field use by Site Managers.
- Triage Queue and Report Detail views should remain usable on tablet for field-based analyst review.
