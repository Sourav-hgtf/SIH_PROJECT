# 06 — Database Schema

Primary store: PostgreSQL (structured data). Embeddings referenced via `vector_id` are stored in FAISS/pgvector.

## Table: `sites`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| name | VARCHAR(255) | Site/facility name |
| region | VARCHAR(100) | |
| created_at | TIMESTAMP | |

## Table: `users`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| username | VARCHAR(100) UNIQUE | |
| password_hash | VARCHAR(255) | bcrypt/argon2 hash |
| role | ENUM('analyst','site_manager','leadership','admin') | |
| site_scope | UUID[] | FK array → sites.id; NULL/empty = org-wide (leadership/admin) |
| email | VARCHAR(255) | |
| is_active | BOOLEAN | default true |
| created_at | TIMESTAMP | |
| last_login_at | TIMESTAMP | |

## Table: `reports`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| source_report_id | VARCHAR(100) | Original ID from HSSE platform |
| report_type | ENUM('ua_uc','near_miss','incident') | |
| site_id | UUID (FK → sites.id) | |
| department | VARCHAR(100) | |
| shift | VARCHAR(50) | |
| equipment_type | VARCHAR(150) | |
| job_type | VARCHAR(150) | |
| raw_text_redacted | TEXT | PII-redacted free text (raw text is never persisted) |
| reported_at | TIMESTAMP | Original report date/time |
| ingested_at | TIMESTAMP | |
| vector_id | VARCHAR(100) | Reference to embedding in vector store |

## Table: `sif_classifications`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| report_id | UUID (FK → reports.id) | |
| sif_probability | FLOAT | 0.0–1.0 |
| sif_label | BOOLEAN | Derived from threshold |
| model_version | VARCHAR(50) | |
| contributing_phrases | JSONB | List of {phrase, weight} |
| classified_at | TIMESTAMP | |

## Table: `lsr_tags`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| report_id | UUID (FK → reports.id) | |
| lsr_category | ENUM(12 IOGP categories) | See list below |
| confidence | FLOAT | 0.0–1.0 |
| source | ENUM('rule','model') | Which layer produced this tag |
| tagged_at | TIMESTAMP | |

**IOGP Life-Saving Rule categories:** Bypassing Safety Controls, Confined Space, Driving, Energy Isolation, Hot Work, Line of Fire, Safe Mechanical Lifting, Managing Change, Fit for Duty, Work Authorization, Working at Height, Personal Protective Equipment (PPE-adjacent, per OIL's specific LSR list if it differs — configurable enum).

## Table: `precursor_triples`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| report_id | UUID (FK → reports.id) | |
| activity | VARCHAR(255) | Extracted entity |
| location_asset | VARCHAR(255) | Extracted entity |
| barrier_failure | VARCHAR(255) | Extracted entity |
| vector_id | VARCHAR(100) | Embedding reference for clustering |
| extracted_at | TIMESTAMP | |

## Table: `precursor_clusters`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| representative_activity | VARCHAR(255) | |
| representative_location | VARCHAR(255) | |
| representative_barrier_failure | VARCHAR(255) | |
| cluster_size | INTEGER | Count of member triples |
| first_seen_at | TIMESTAMP | |
| last_updated_at | TIMESTAMP | |
| trend_status | ENUM('growing','stable','shrinking') | |

## Table: `cluster_members`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| cluster_id | UUID (FK → precursor_clusters.id) | |
| triple_id | UUID (FK → precursor_triples.id) | |
| assigned_at | TIMESTAMP | |

## Table: `analyst_feedback`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| report_id | UUID (FK → reports.id) | |
| user_id | UUID (FK → users.id) | |
| feedback_type | ENUM('confirm_sif','override_sif','adjust_lsr') | |
| previous_value | JSONB | Snapshot before change |
| new_value | JSONB | Snapshot after change |
| comment | TEXT | Required for overrides |
| created_at | TIMESTAMP | |

## Table: `audit_log`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| user_id | UUID (FK → users.id, nullable for system actions) | |
| action_type | VARCHAR(100) | e.g. 'login','override_classification','user_created' |
| entity_type | VARCHAR(100) | e.g. 'report','user','lsr_tag' |
| entity_id | UUID | |
| before_value | JSONB | |
| after_value | JSONB | |
| created_at | TIMESTAMP | |

## Relationships Summary
- `sites` 1—* `reports`
- `reports` 1—1 `sif_classifications` (current version; historical versions retained via `model_version` + timestamp for audit)
- `reports` 1—* `lsr_tags`
- `reports` 1—* `precursor_triples`
- `precursor_triples` *—1 `precursor_clusters` (via `cluster_members`)
- `reports` 1—* `analyst_feedback`
- `users` 1—* `analyst_feedback`, 1—* `audit_log`
