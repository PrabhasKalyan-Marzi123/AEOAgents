"""ChromaDB-backed vector store for the live blog inventory.

One persistent collection (`inventory_chunks`) keyed by `<slug>::<chunk_index>`.
Each chunk carries page metadata (slug, title, category, content_hash) so we
can update or delete by slug, and query similarity in one shot via Chroma's
HNSW index instead of looping cosine in Python.

Embeddings are produced by the same MiniLM model used elsewhere in the project
(`compute_embedding`) so cross-component similarity scores remain comparable.
"""

from __future__ import annotations

import logging
from pathlib import Path

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from app.services.deduplication import compute_embedding, compute_hash

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_CHROMA_DIR = _DATA_DIR / "chroma"
_COLLECTION = "inventory_chunks"

# Mirror recommender's chunking so embeddings are over the same units.
_CHUNK_CHARS = 1200
_CHUNK_OVERLAP = 200


class _MiniLMEmbeddingFunction(EmbeddingFunction):
    """Adapter so Chroma uses our shared MiniLM encoder."""

    def __call__(self, input: Documents) -> Embeddings:
        return [compute_embedding(t) for t in input]


_client: chromadb.api.ClientAPI | None = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection
    _CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    _client = chromadb.PersistentClient(path=str(_CHROMA_DIR))
    _collection = _client.get_or_create_collection(
        name=_COLLECTION,
        embedding_function=_MiniLMEmbeddingFunction(),
        metadata={"hnsw:space": "cosine"},
    )
    return _collection


def _chunk_text(text: str, max_chars: int = _CHUNK_CHARS, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            for marker in (". ", "? ", "! ", "\n"):
                idx = text.rfind(marker, start + max_chars // 2, end)
                if idx != -1:
                    end = idx + len(marker)
                    break
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]


def _chunk_ids(slug: str, n: int) -> list[str]:
    return [f"{slug}::{i}" for i in range(n)]


def page_hash(slug: str) -> str | None:
    """Return the stored content_hash for a slug, or None if absent."""
    coll = _get_collection()
    res = coll.get(where={"slug": slug}, limit=1, include=["metadatas"])
    metas = res.get("metadatas") or []
    if not metas:
        return None
    return metas[0].get("content_hash")


def upsert_page(
    slug: str,
    title: str,
    category: str,
    embed_source: str,
) -> dict:
    """Embed and persist all chunks for a page.

    Idempotent — if the content_hash matches what's already stored the call is a
    no-op. Otherwise existing chunks for the slug are deleted before reinsert
    (chunk count can change between revisions).

    Returns a dict describing what happened: {"action": "skipped|inserted|updated", "n_chunks": int}.
    """
    coll = _get_collection()
    new_hash = compute_hash(embed_source)

    existing_hash = page_hash(slug)
    if existing_hash == new_hash:
        return {"action": "skipped", "n_chunks": 0}

    if existing_hash is not None:
        coll.delete(where={"slug": slug})
        action = "updated"
    else:
        action = "inserted"

    chunks = _chunk_text(embed_source)
    if not chunks:
        return {"action": "skipped", "n_chunks": 0}

    ids = _chunk_ids(slug, len(chunks))
    metadatas = [
        {
            "slug": slug,
            "title": title,
            "category": category,
            "content_hash": new_hash,
            "chunk_index": i,
        }
        for i in range(len(chunks))
    ]
    coll.add(ids=ids, documents=chunks, metadatas=metadatas)
    return {"action": action, "n_chunks": len(chunks)}


def delete_page(slug: str) -> int:
    """Remove all chunks for a slug. Returns number of chunks deleted."""
    coll = _get_collection()
    existing = coll.get(where={"slug": slug}, include=[])
    n = len(existing.get("ids") or [])
    if n:
        coll.delete(where={"slug": slug})
    return n


def all_slugs() -> set[str]:
    """Return every slug currently indexed."""
    coll = _get_collection()
    res = coll.get(include=["metadatas"])
    return {m["slug"] for m in (res.get("metadatas") or []) if m.get("slug")}


def reconcile(live_slugs: set[str]) -> int:
    """Drop chunks belonging to slugs no longer on disk. Returns slugs removed."""
    indexed = all_slugs()
    stale = indexed - live_slugs
    for slug in stale:
        delete_page(slug)
    return len(stale)


def query_max_similarity(text: str, k: int = 5) -> tuple[float, str | None]:
    """Return (max_cosine_similarity, slug_of_top_match) for `text` against the index.

    Chroma stores cosine *distance* (1 - cos_sim); we convert back so callers
    can keep using the same threshold semantics they had with raw cosine.
    """
    coll = _get_collection()
    if coll.count() == 0:
        return 0.0, None
    res = coll.query(query_texts=[text], n_results=max(1, k), include=["distances", "metadatas"])
    distances = (res.get("distances") or [[]])[0]
    metadatas = (res.get("metadatas") or [[]])[0]
    if not distances:
        return 0.0, None
    best_dist = min(distances)
    best_idx = distances.index(best_dist)
    best_slug = (metadatas[best_idx] or {}).get("slug") if best_idx < len(metadatas) else None
    return max(0.0, 1.0 - float(best_dist)), best_slug


def collection_stats() -> dict:
    coll = _get_collection()
    return {"chunks": coll.count(), "pages": len(all_slugs())}
