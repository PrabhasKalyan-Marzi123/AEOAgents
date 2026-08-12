"""ChromaDB-backed vector store for the travel blog inventory.

Mirrors backend/app/services/vector_store.py but uses a separate collection
('travel_inventory_chunks') and a separate chroma path (travel-blogs/data/chroma/)
so travel blog embeddings are fully isolated from marzi.life blog embeddings.
"""

from __future__ import annotations

import logging
from pathlib import Path

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from app.services.deduplication import compute_embedding, compute_hash

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_CHROMA_DIR = _DATA_DIR / "chroma"
_COLLECTION = "travel_inventory_chunks"

_CHUNK_CHARS = 1200
_CHUNK_OVERLAP = 200


class _MiniLMEmbeddingFunction(EmbeddingFunction):
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
    coll = _get_collection()
    res = coll.get(where={"slug": slug}, limit=1, include=["metadatas"])
    metas = res.get("metadatas") or []
    return metas[0].get("content_hash") if metas else None


def upsert_page(slug: str, title: str, category: str, embed_source: str) -> dict:
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
        {"slug": slug, "title": title, "category": category, "content_hash": new_hash, "chunk_index": i}
        for i in range(len(chunks))
    ]
    coll.add(ids=ids, documents=chunks, metadatas=metadatas)
    return {"action": action, "n_chunks": len(chunks)}


def reconcile(live_slugs: set[str]) -> int:
    indexed = all_slugs()
    stale = indexed - live_slugs
    for slug in stale:
        coll = _get_collection()
        coll.delete(where={"slug": slug})
    return len(stale)


def all_slugs() -> set[str]:
    coll = _get_collection()
    res = coll.get(include=["metadatas"])
    return {m["slug"] for m in (res.get("metadatas") or []) if m.get("slug")}


def query_max_similarity(text: str, k: int = 5) -> tuple[float, str | None]:
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
