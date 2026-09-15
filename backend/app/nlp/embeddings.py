"""Local sentence embedding extraction module.

Architecture:
  Incident Text
    ↓ Preprocessing (PII redaction, spelling, abbreviation expansion)
  Sentence Transformer Model (all-MiniLM-L6-v2, 384-dimensional dense vectors)
    ↓
  Normalized Embedding Vector (384-d float32)

Guarantees:
1. 100% Local / Offline execution — zero external API calls.
2. Device auto-detection: Apple Silicon MPS if available, otherwise CPU.
3. Preprocessing uniformity: uses app.nlp.preprocess.preprocess() identically
   across training, validation, testing, and inference.
4. Deterministic embeddings: unit-normalized, reproducible across runs.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

# Ensure SSL certificates are properly resolved on macOS
try:
    import certifi
    if "SSL_CERT_FILE" not in os.environ:
        os.environ["SSL_CERT_FILE"] = certifi.where()
except ImportError:
    pass

from app.nlp.preprocess import preprocess

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384

# Local cache directory for model weights
CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "model_artifacts" / "embeddings"

_MODEL_INSTANCE: Any = None
_DEVICE: str = "cpu"


def get_preferred_device() -> str:
    """Select best available local device (Apple Silicon MPS or CPU)."""
    try:
        import torch
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def get_embedding_model(model_name: str = DEFAULT_EMBEDDING_MODEL) -> Any:
    """Load and cache SentenceTransformer model locally."""
    global _MODEL_INSTANCE, _DEVICE
    if _MODEL_INSTANCE is not None:
        return _MODEL_INSTANCE

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _DEVICE = get_preferred_device()
    logger.info(f"Loading local embedding model '{model_name}' on device '{_DEVICE}' (cache={CACHE_DIR})")

    from sentence_transformers import SentenceTransformer

    # Attempt to load from local cache first, or download once and cache locally
    try:
        _MODEL_INSTANCE = SentenceTransformer(
            model_name,
            device=_DEVICE,
            cache_folder=str(CACHE_DIR),
            local_files_only=True,
        )
    except Exception as e:
        logger.warning(f"Failed to load with default settings, attempting CPU fallback: {e}")
        _DEVICE = "cpu"
        _MODEL_INSTANCE = SentenceTransformer(
            model_name,
            device="cpu",
            cache_folder=str(CACHE_DIR),
            local_files_only=True,
        )

    return _MODEL_INSTANCE


def extract_embedding(text: str, model_name: str = DEFAULT_EMBEDDING_MODEL) -> np.ndarray:
    """Extract a single normalized 384-d sentence embedding from raw text with standard preprocessing."""
    prep = preprocess(text)
    clean_text = prep["processed_text"]
    if not clean_text.strip():
        return np.zeros(EMBEDDING_DIMENSION, dtype=np.float32)

    model = get_embedding_model(model_name)
    emb = model.encode(
        clean_text,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return np.asarray(emb, dtype=np.float32)


def extract_embeddings(texts: list[str], model_name: str = DEFAULT_EMBEDDING_MODEL, batch_size: int = 32) -> np.ndarray:
    """Batch extract normalized sentence embeddings with standard uniform preprocessing."""
    if not texts:
        return np.empty((0, EMBEDDING_DIMENSION), dtype=np.float32)

    cleaned_texts = []
    for t in texts:
        prep = preprocess(t)
        clean = prep["processed_text"]
        cleaned_texts.append(clean if clean.strip() else "incident report")

    model = get_embedding_model(model_name)
    embeddings = model.encode(
        cleaned_texts,
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return np.asarray(embeddings, dtype=np.float32)
