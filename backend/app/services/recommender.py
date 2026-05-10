"""Topic Recommender — suggest new blog topics based on the live page inventory.

Pipeline:
  1. Inventory  → load already-published pages via Distributor.discover_existing_pages()
  2. Index      → upsert each page's full content to ChromaDB (idempotent via content hash)
  3. Histograms → category / theme / city coverage signals (deterministic)
  4. LLM        → single Gemini 2.5 Flash call ideates N+5 candidates with rationale + score
  5. Dedup      → ChromaDB cosine similarity query — drop any candidate whose nearest
                  chunk in the index sits at or above the threshold
  6. Persist    → append run to recommendations.jsonl

Output: ranked list[TopicRecommendation].
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from google import genai

from app.config import settings
from app.services.brand_context import get_brand_context
from app.services import vector_store
from app.agents.distributor import DistributorAgent
from app.agents.compiler import CompiledPage, DEFAULT_OUTPUT_DIR
from app.agents.researcher import _parse_json_lenient

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_RECOMMENDATIONS_LOG = _DATA_DIR / "recommendations.jsonl"

# Brand tokens to drop before computing theme histograms (they appear everywhere).
_BRAND_STOP = {
    "marzi", "bangalore", "mumbai", "seniors", "senior", "55", "above",
    "offline", "events", "event", "social", "people", "india", "indian",
}
_ENGLISH_STOP = {
    "the", "a", "an", "and", "or", "but", "for", "with", "to", "of", "in",
    "on", "at", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "this", "that",
    "these", "those", "what", "which", "who", "how", "when", "where",
    "why", "your", "you", "our", "their", "they", "it", "its", "as", "if",
    "than", "then", "so", "such", "no", "not", "vs", "de",
}


@dataclass
class TopicRecommendation:
    """A recommended topic to feed into the pipeline."""

    topic: str
    rationale: str
    target_category: str
    expected_intent: str
    priority_score: float
    themes_addressed: list[str] = field(default_factory=list)
    max_similarity_to_existing: float = 0.0
    closest_existing_slug: str | None = None


# ── HTML body extraction ──

def _extract_body_text(html: str) -> str:
    """Strip HTML, keep plain readable text. Used as the embedding source per page."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


# ── Inventory indexing (delegates to ChromaDB) ──

def _index_inventory(pages: list[CompiledPage]) -> None:
    """Upsert every live page into the Chroma collection. Idempotent per content hash."""
    inserted = updated = skipped = 0
    for page in pages:
        slug = page.slug
        if not slug:
            continue
        try:
            html = Path(page.file_path).read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"[Recommender] Cannot read {page.file_path}: {e}")
            continue
        body = _extract_body_text(html)
        embed_source = f"{page.title}\n{page.meta_description}\n{body}"
        result = vector_store.upsert_page(
            slug=slug,
            title=page.title,
            category=page.category,
            embed_source=embed_source,
        )
        if result["action"] == "inserted":
            inserted += 1
        elif result["action"] == "updated":
            updated += 1
        else:
            skipped += 1

    # Drop chunks for slugs that no longer exist on disk.
    removed = vector_store.reconcile({p.slug for p in pages if p.slug})

    stats = vector_store.collection_stats()
    logger.info(
        f"[Recommender] Vector index: +{inserted} new, ~{updated} updated, "
        f"={skipped} unchanged, -{removed} stale → {stats['pages']} pages, "
        f"{stats['chunks']} chunks"
    )


# ── Histograms ──

def _category_histogram(pages: list[CompiledPage]) -> dict[str, int]:
    hist = {"faq": 0, "how-to": 0, "comparison": 0, "informational": 0}
    for p in pages:
        if p.category in hist:
            hist[p.category] += 1
        else:
            hist[p.category] = hist.get(p.category, 0) + 1
    return hist


def _theme_histogram(pages: list[CompiledPage], top_n: int = 25) -> list[tuple[str, int]]:
    """Top unigrams + bigrams from titles + meta descriptions, brand+stop tokens filtered."""
    counter: dict[str, int] = {}
    for p in pages:
        text = f"{p.title} {p.meta_description}".lower()
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        tokens = [t for t in text.split() if t and t not in _BRAND_STOP and t not in _ENGLISH_STOP and len(t) > 2]
        for t in tokens:
            counter[t] = counter.get(t, 0) + 1
        for a, b in zip(tokens, tokens[1:]):
            bg = f"{a} {b}"
            counter[bg] = counter.get(bg, 0) + 1
    return sorted(counter.items(), key=lambda kv: kv[1], reverse=True)[:top_n]


def _city_coverage(pages: list[CompiledPage], cities: list[str]) -> dict[str, int]:
    coverage = {c: 0 for c in cities}
    for p in pages:
        haystack = f"{p.title} {p.meta_description}".lower()
        for c in cities:
            if c.lower() in haystack:
                coverage[c] += 1
    return coverage


# ── Past-recommendations recall (avoid re-suggesting the same thing every run) ──

def _load_recent_recommendations(limit: int = 50) -> list[str]:
    if not _RECOMMENDATIONS_LOG.exists():
        return []
    try:
        lines = _RECOMMENDATIONS_LOG.read_text(encoding="utf-8").strip().splitlines()
    except Exception:
        return []
    recent_topics: list[str] = []
    for line in lines[-25:]:  # last 25 runs
        try:
            entry = json.loads(line)
            for r in entry.get("recommendations", []):
                if isinstance(r, dict) and r.get("topic"):
                    recent_topics.append(r["topic"])
        except Exception:
            continue
    return recent_topics[-limit:]


# ── LLM ideation ──

def _build_recommender_prompt(
    brand: dict,
    pages: list[CompiledPage],
    cat_hist: dict[str, int],
    theme_hist: list[tuple[str, int]],
    city_cov: dict[str, int],
    recent_recs: list[str],
    n: int,
) -> str:
    inventory = [
        {"slug": p.slug, "title": p.title, "category": p.category}
        for p in pages
    ]
    return f"""You are a content strategist for {brand.get('brand_name', 'this brand')}, recommending the next blog topics to write.

GOAL: Suggest {n + 5} new blog topics that fill genuine gaps in the existing content, expand under-served categories, and address themes/cities/audiences not yet covered. Diversify — don't recommend N variants of the same topic.

BRAND FACTS:
{json.dumps({k: brand.get(k) for k in ['brand_name', 'what_it_is', 'target_audience', 'cities', 'event_themes', 'pricing_model', 'key_differentiators']}, indent=2)}

EXISTING INVENTORY ({len(pages)} pages):
{json.dumps(inventory, indent=2)}

CATEGORY COVERAGE (under-served categories should be prioritized):
{json.dumps(cat_hist, indent=2)}

TOP THEMES IN EXISTING CONTENT (well-covered already — only revisit if you can go deeper):
{json.dumps(theme_hist[:15], indent=2)}

CITY COVERAGE (under-covered cities should be prioritized):
{json.dumps(city_cov, indent=2)}

RECENTLY SUGGESTED BUT NOT YET WRITTEN (try to suggest different angles this time):
{json.dumps(recent_recs[-15:], indent=2)}

ANALYSIS RULES:
1. Identify 2-3 specific GAPS — under-served categories, missing themes, under-covered cities, missing audiences (women, couples, specific age sub-segments, etc.).
2. Each recommendation must be a concrete, searchable blog topic — not a vague theme.
3. target_category MUST be exactly one of: "faq", "how-to", "comparison", "informational".
4. expected_intent describes the SERP intent (e.g. "users searching for definitions", "users comparing options").
5. priority_score is 0.0–1.0 — higher means it fills a more important gap.
6. themes_addressed lists 2-4 concrete themes the topic covers.

Return ONLY valid JSON:
{{
  "analysis": {{
    "key_gaps_observed": ["...", "..."],
    "under_served_categories": ["..."],
    "under_covered_themes": ["..."]
  }},
  "recommendations": [
    {{
      "topic": "...",
      "rationale": "one sentence explaining the gap this fills",
      "target_category": "faq|how-to|comparison|informational",
      "expected_intent": "...",
      "priority_score": 0.0,
      "themes_addressed": ["...", "..."]
    }}
  ]
}}
"""


def _llm_recommend(prompt: str) -> list[dict]:
    if not settings.gemini_api_key:
        logger.error("[Recommender] GEMINI_API_KEY not configured")
        return []
    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=8192,
                response_mime_type="application/json",
            ),
        )
        raw = (response.text or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        parsed = _parse_json_lenient(raw)
        if not parsed:
            logger.error(f"[Recommender] Could not parse LLM JSON. Raw head: {raw[:300]!r}")
            return []
        analysis = parsed.get("analysis", {})
        if analysis:
            logger.info(
                f"[Recommender] LLM analysis: gaps={analysis.get('key_gaps_observed', [])}, "
                f"under-served={analysis.get('under_served_categories', [])}"
            )
        return list(parsed.get("recommendations", []))
    except Exception as e:
        logger.error(f"[Recommender] LLM call failed: {e}")
        return []


# ── Semantic dedup against full content (via ChromaDB) ──

_VALID_CATEGORIES = {"faq", "how-to", "comparison", "informational"}


def _dedup_candidates(
    candidates: list[dict],
    threshold: float,
) -> list[TopicRecommendation]:
    """Drop candidates whose nearest neighbour in the vector index sits at ≥ threshold."""
    survivors: list[TopicRecommendation] = []

    for c in candidates:
        topic = (c.get("topic") or "").strip()
        if not topic:
            continue
        category = (c.get("target_category") or "informational").lower()
        if category not in _VALID_CATEGORIES:
            category = "informational"

        max_sim, closest_slug = vector_store.query_max_similarity(topic, k=3)

        if max_sim >= threshold:
            logger.info(
                f"[Recommender] DROP (sim={max_sim:.3f} ≥ {threshold}, "
                f"nearest={closest_slug}): {topic}"
            )
            continue

        try:
            score = float(c.get("priority_score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0

        survivors.append(TopicRecommendation(
            topic=topic,
            rationale=(c.get("rationale") or "").strip(),
            target_category=category,
            expected_intent=(c.get("expected_intent") or "").strip(),
            priority_score=max(0.0, min(1.0, score)),
            themes_addressed=list(c.get("themes_addressed") or [])[:6],
            max_similarity_to_existing=round(max_sim, 3),
            closest_existing_slug=closest_slug,
        ))

    survivors.sort(key=lambda r: r.priority_score, reverse=True)
    return survivors


# ── Persistence ──

def _append_recommendations_log(brand_url: str, inventory_size: int, recs: list[TopicRecommendation]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "brand_url": brand_url,
        "inventory_size": inventory_size,
        "recommendations": [asdict(r) for r in recs],
    }
    with _RECOMMENDATIONS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


# ── Public entry point ──

def recommend_topics(
    brand_url: str = "https://marzi.life",
    n: int = 5,
    output_dir: str | Path | None = None,
    similarity_threshold: float = 0.78,
) -> list[TopicRecommendation]:
    """Generate N topic recommendations grounded in the existing content inventory.

    Args:
        brand_url:             Brand for which to recommend topics.
        n:                     Number of recommendations to return.
        output_dir:            Override for firebase-hosting/public/. None = default.
        similarity_threshold:  Cosine threshold above which a candidate is considered
                               a duplicate of existing content (range 0.0–1.0).

    Returns:
        Ranked list of TopicRecommendation, length ≤ n.
    """
    logger.info(f"[Recommender] Starting: brand={brand_url}, n={n}, threshold={similarity_threshold}")

    # 1. Inventory
    distributor = DistributorAgent(output_dir=output_dir)
    pages = distributor.discover_existing_pages()
    logger.info(f"[Recommender] Inventory: {len(pages)} existing pages")

    # 2. Brand context
    brand = get_brand_context(brand_url) or {"brand_name": "the brand"}

    # 3. Index inventory in ChromaDB (idempotent)
    if pages:
        _index_inventory(pages)

    # 4. Histograms
    cat_hist = _category_histogram(pages)
    theme_hist = _theme_histogram(pages)
    city_cov = _city_coverage(pages, brand.get("cities") or [])
    logger.info(f"[Recommender] Categories: {cat_hist}")
    logger.info(f"[Recommender] City coverage: {city_cov}")

    # 5. Past recommendations recall
    recent_recs = _load_recent_recommendations()

    # 6. LLM ideation (ask for N+5 to leave room for dedup)
    prompt = _build_recommender_prompt(brand, pages, cat_hist, theme_hist, city_cov, recent_recs, n)
    candidates = _llm_recommend(prompt)
    logger.info(f"[Recommender] LLM returned {len(candidates)} candidates")
    if not candidates:
        return []

    # 7. Semantic dedup via vector store
    survivors = _dedup_candidates(candidates, similarity_threshold)
    logger.info(f"[Recommender] After dedup: {len(survivors)} survivors (requested {n})")

    top = survivors[:n]

    # 8. Persist
    _append_recommendations_log(brand_url, len(pages), top)

    return top
