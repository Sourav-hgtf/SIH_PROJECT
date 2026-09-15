"""Reproducible semantic clustering for normalized precursor triples.

DBSCAN is used because the number of recurring patterns is not known in advance
and its ``-1`` label preserves isolated reports as noise instead of forcing a
cluster assignment.  It complements, rather than replaces, normalized triples.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import logging
from typing import Any

import numpy as np
from sklearn.cluster import DBSCAN

from app.nlp.embeddings import DEFAULT_EMBEDDING_MODEL, extract_embeddings
from app.nlp.mining import assign_trend

logger = logging.getLogger(__name__)

CLUSTERING_MODEL_VERSION = f"precursor-semantic-dbscan-cosine-v1:{DEFAULT_EMBEDDING_MODEL}"
CLUSTERING_EPS = 0.24  # cosine distance: members must have similarity >= 0.76
CLUSTERING_MIN_SAMPLES = 2


def _normalized_values(item: dict[str, Any]) -> tuple[str, str, str]:
    """Return explicit normalized fields, falling back safely for old rows."""
    return (
        str(item.get("normalized_activity") or item.get("activity") or "unknown"),
        str(item.get("normalized_location_asset") or item.get("location_asset") or "unknown"),
        str(item.get("normalized_barrier_failure") or item.get("barrier_failure") or "unknown"),
    )


def _semantic_text(item: dict[str, Any]) -> str:
    """Embed normalized values only; raw report text is not a cluster feature."""
    return " | ".join(_normalized_values(item))


def _mode(values: list[str], unknown: str) -> str:
    usable = [v for v in values if v]
    if not usable:
        return unknown
    counts = Counter(usable)
    return sorted(counts, key=lambda value: (-counts[value], value.lower()))[0]


def _cluster_key(member_ids: list[str]) -> str:
    digest = hashlib.sha256("|".join(sorted(member_ids)).encode("utf-8")).hexdigest()[:16]
    return f"psc-{digest}"


def _make_cluster(members: list[dict[str, Any]], similarities: dict[str, float]) -> dict[str, Any]:
    activity = _mode([str(m.get("normalized_activity") or m.get("activity") or "") for m in members], "unspecified activity")
    location = _mode([str(m.get("normalized_location_asset") or m.get("location_asset") or "") for m in members], "unspecified location")
    barrier = _mode([str(m.get("normalized_barrier_failure") or m.get("barrier_failure") or "") for m in members], "barrier not identified")
    dates = [m["reported_at"] for m in members if m.get("reported_at")]
    member_ids = [str(m["triple_id"]) for m in members]
    return {
        "semantic_cluster_key": _cluster_key(member_ids),
        "representative_activity": activity,
        "representative_location": location,
        "representative_barrier_failure": barrier,
        # Summary is derived strictly from normalized member values.
        "summary": f"{activity} | {location} | {barrier}",
        "members": members,
        "member_similarities": similarities,
        "cluster_confidence": round(float(np.mean(list(similarities.values()))), 3),
        "cluster_size": len(members),
        "trend_status": assign_trend(dates),
        "clustering_model_version": CLUSTERING_MODEL_VERSION,
    }


def semantic_cluster_triples(triples: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return ``(clusters, noise)`` for sorted precursor triples.

    A cluster requires at least two nearby normalized triples. Any DBSCAN noise
    is returned explicitly and remains unassigned in persistence.
    """
    ordered = sorted(triples, key=lambda item: str(item.get("triple_id", "")))
    if len(ordered) < CLUSTERING_MIN_SAMPLES:
        return [], ordered

    try:
        vectors = np.asarray(extract_embeddings([_semantic_text(item) for item in ordered]), dtype=np.float32)
        if vectors.shape[0] != len(ordered) or vectors.ndim != 2:
            raise ValueError("invalid precursor embedding shape")
        labels = DBSCAN(
            eps=CLUSTERING_EPS,
            min_samples=CLUSTERING_MIN_SAMPLES,
            metric="cosine",
            algorithm="brute",
        ).fit_predict(vectors)
    except Exception as exc:
        # The established normalized triple values remain useful when optional
        # embeddings are unavailable. Only repeated exact triples cluster;
        # singletons stay noise, preserving the no-forced-assignment guarantee.
        logger.warning("Semantic precursor clustering unavailable; using exact normalized fallback: %s", type(exc).__name__)
        buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for item in ordered:
            buckets[_normalized_values(item)].append(item)
        clusters = []
        noise = []
        for members in buckets.values():
            if len(members) < CLUSTERING_MIN_SAMPLES:
                noise.extend(members)
                continue
            similarities = {str(member["triple_id"]): 1.0 for member in members}
            cluster = _make_cluster(members, similarities)
            cluster["clustering_model_version"] = "precursor-exact-fallback-v1"
            clusters.append(cluster)
        return sorted(clusters, key=lambda c: c["semantic_cluster_key"]), noise

    grouped: dict[int, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    noise: list[dict[str, Any]] = []
    for index, label in enumerate(labels):
        if int(label) == -1:
            noise.append(ordered[index])
        else:
            grouped[int(label)].append((index, ordered[index]))

    clusters = []
    for entries in grouped.values():
        indices, members = zip(*entries)
        member_vectors = vectors[list(indices)]
        centroid = member_vectors.mean(axis=0)
        centroid_norm = np.linalg.norm(centroid)
        if centroid_norm:
            centroid = centroid / centroid_norm
        similarities = {
            str(member["triple_id"]): round(float(np.dot(vectors[index], centroid)), 3)
            for index, member in entries
        }
        clusters.append(_make_cluster(list(members), similarities))

    return sorted(clusters, key=lambda c: c["semantic_cluster_key"]), noise
