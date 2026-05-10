"""Deduplication service using SHA-256 exact match + sentence-transformers semantic similarity.

Uses HuggingFace all-MiniLM-L6-v2 (22M params, ~80MB) for computing embeddings locally.
No external API calls needed — the model runs inside the Docker container.
"""

from __future__ import annotations

import hashlib
import re

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import settings
from app.wordpress_client import wordpress_client

# Lazy-load the model on first use
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _normalize_text(text: str) -> str:
    """Normalize text for consistent hashing: lowercase, collapse whitespace, strip HTML."""
    text = re.sub(r"<[^>]+>", " ", text)  # strip HTML tags
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def compute_hash(text: str) -> str:
    """Compute SHA-256 hash of normalized text for exact dedup."""
    normalized = _normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_embedding(text: str) -> list[float]:
    """Compute sentence embedding using all-MiniLM-L6-v2."""
    model = _get_model()
    normalized = _normalize_text(text)
    embedding = model.encode(normalized, convert_to_numpy=True, show_progress_bar=False)
    return embedding.tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two embedding vectors."""
    a_arr = np.array(a)
    b_arr = np.array(b)
    dot = np.dot(a_arr, b_arr)
    norm = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    if norm == 0:
        return 0.0
    return float(dot / norm)


async def check_duplicate(
    text: str,
    topic: str,
) -> dict:
    """Check if content is a duplicate of existing pages in WordPress.

    Two-tier check:
    1. Exact match: SHA-256 hash comparison (via WP search)
    2. Semantic similarity: all-MiniLM-L6-v2 cosine similarity > threshold

    Returns:
        {
            "is_duplicate": bool,
            "match_type": "exact" | "semantic" | None,
            "similarity_score": float | None,
            "matched_page_id": int | None,
        }
    """
    text_hash = compute_hash(text)

    if not wordpress_client.is_configured:
        # No WordPress configured — skip dedup, allow everything
        return {
            "is_duplicate": False,
            "match_type": None,
            "similarity_score": None,
            "matched_page_id": None,
        }

    # Tier 1: Search for pages with same topic for exact hash match
    try:
        existing = wordpress_client.get_pages({"search": topic, "per_page": 50, "status": "any"})
    except Exception:
        existing = []

    # Check exact hash match
    for page in existing:
        page_hash = page.get("meta", {}).get("text_hash", "")
        if page_hash == text_hash:
            return {
                "is_duplicate": True,
                "match_type": "exact",
                "similarity_score": 1.0,
                "matched_page_id": page["id"],
            }

    # Tier 2: Semantic similarity against same-topic content
    if existing:
        new_embedding = compute_embedding(text)

        for page in existing:
            page_content = page.get("content", "")
            if not page_content:
                continue
            existing_embedding = compute_embedding(page_content)
            score = cosine_similarity(new_embedding, existing_embedding)

            if score >= settings.dedup_similarity_threshold:
                return {
                    "is_duplicate": True,
                    "match_type": "semantic",
                    "similarity_score": score,
                    "matched_page_id": page["id"],
                }

    return {
        "is_duplicate": False,
        "match_type": None,
        "similarity_score": None,
        "matched_page_id": None,
    }
