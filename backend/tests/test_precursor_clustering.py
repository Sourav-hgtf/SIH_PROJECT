"""Phase 7 contracts for semantic precursor pattern clustering."""

from datetime import datetime, timezone

import numpy as np

from app.nlp import precursor_clustering


def _triple(triple_id: str, activity: str, location: str = "deck", barrier: str = "lifting barrier failed") -> dict:
    return {
        "triple_id": triple_id,
        "activity": "legacy value must not be embedded",
        "location_asset": "legacy location",
        "barrier_failure": "legacy barrier",
        "normalized_activity": activity,
        "normalized_location_asset": location,
        "normalized_barrier_failure": barrier,
        "reported_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }


def test_semantic_clustering_uses_normalized_values_is_repeatable_and_keeps_noise(monkeypatch):
    """DBSCAN clusters close vectors, exposes no arbitrary DBSCAN label, and leaves outliers out."""
    vectors = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.99, 0.10, 0.0],
            [0.0, 1.0, 0.0],
        ],
        dtype=np.float32,
    )
    embedded_texts: list[str] = []

    def fake_embeddings(texts):
        embedded_texts.extend(texts)
        return vectors

    monkeypatch.setattr(precursor_clustering, "extract_embeddings", fake_embeddings)
    triples = [
        _triple("b", "mechanical lifting"),
        _triple("a", "lifting operation using crane"),
        _triple("c", "office administration"),
    ]

    first_clusters, first_noise = precursor_clustering.semantic_cluster_triples(triples)
    second_clusters, second_noise = precursor_clustering.semantic_cluster_triples(list(reversed(triples)))

    assert "mechanical lifting" in " ".join(embedded_texts)
    assert all("legacy value must not be embedded" not in text for text in embedded_texts)
    assert len(first_clusters) == 1
    cluster = first_clusters[0]
    assert cluster["semantic_cluster_key"].startswith("psc-")
    assert "label" not in cluster
    assert cluster["cluster_size"] == 2
    assert set(cluster["member_similarities"]) == {"a", "b"}
    assert cluster["cluster_confidence"] >= 0.9
    assert [item["triple_id"] for item in first_noise] == ["c"]
    assert first_clusters == second_clusters
    assert first_noise == second_noise


def test_embedding_failure_only_clusters_identical_normalized_triples(monkeypatch):
    monkeypatch.setattr(
        precursor_clustering,
        "extract_embeddings",
        lambda _texts: (_ for _ in ()).throw(RuntimeError("model unavailable")),
    )
    triples = [
        _triple("a", "mechanical lifting"),
        _triple("b", "mechanical lifting"),
        _triple("c", "line dismantling"),
    ]

    clusters, noise = precursor_clustering.semantic_cluster_triples(triples)

    assert len(clusters) == 1
    assert clusters[0]["clustering_model_version"] == "precursor-exact-fallback-v1"
    assert clusters[0]["member_similarities"] == {"a": 1.0, "b": 1.0}
    assert [item["triple_id"] for item in noise] == ["c"]
