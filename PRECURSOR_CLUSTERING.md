# PRECURSOR_CLUSTERING.md — Semantic Precursor Clustering

## Purpose

The existing precursor triple remains the system of record. Phase 7 adds a second, semantic grouping layer so differently worded but related precursor patterns can be analysed together without changing any original report evidence.

```
source evidence → canonical normalization → local embedding → cosine similarity → DBSCAN → semantic precursor pattern
```

## Stored representations

Each `precursor_triples` row keeps both forms:

- `original_activity`, `original_location_asset`, and `original_barrier_failure` preserve extractor evidence/source wording.
- `normalized_activity`, `normalized_location_asset`, and `normalized_barrier_failure` contain the canonical taxonomy values. The legacy `activity`, `location_asset`, and `barrier_failure` fields remain available and retain those normalized values for compatibility.

Only normalized values are embedded. Raw report text and original evidence are never clustering features.

## Algorithm and reproducibility

`app.nlp.precursor_clustering.semantic_cluster_triples` uses DBSCAN with cosine distance (`eps=0.24`, `min_samples=2`). DBSCAN was selected because the number of recurring safety patterns is unknown and it can assign isolated rows to noise (`-1`) rather than forcing a pattern.

Inputs are sorted by immutable triple ID. The persisted semantic identifier is a SHA-256-derived `semantic_cluster_key` calculated from sorted member IDs; DBSCAN's transient integer label is never exposed as a cluster label. The clustering model version includes the local embedding model (`precursor-semantic-dbscan-cosine-v1:all-MiniLM-L6-v2`). Each membership persists cosine similarity to its cluster centroid, and each cluster persists the mean member similarity as `cluster_confidence`.

If the local embedding model is unavailable, the system records `precursor-exact-fallback-v1` and clusters only identical normalized triples. Singletons remain noise in both paths.

## Summaries and dashboard metrics

Cluster summary fields are deterministic modes of normalized cluster members, with lexical tie-breaking; no generated/arbitrary labels are used. The cluster API exposes activity, location, barrier failure, report count, SIF count, SIF rate, clustering version, and confidence.

`report_count`, `sif_count`, and `sif_rate` are calculated from distinct underlying `reports.id` values joined through memberships. They are never calculated from precursor rows, preventing multi-triple reports from inflating the SIF rate.
