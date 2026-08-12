"""Travel Topic Recommender — suggest new travel blog topics for Marzi Holidays.

Pipeline:
  1. Scrape     → fetch holidays.marzi.life to discover current trips/destinations
  2. Inventory  → load published travel blogs via TravelDistributorAgent.discover_existing_pages()
  3. Index      → upsert each page's full text into travel ChromaDB (idempotent)
  4. Histograms → category / theme coverage signals
  5. LLM        → Gemini suggests N+5 candidates mixing trip-specific + general travel topics
  6. Dedup      → ChromaDB cosine similarity — drop candidates too close to existing blogs
  7. Persist    → write recommendations-YYYY-MM-DD.json (one file per week)

Output: ranked list[TravelTopicRecommendation]
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from google import genai

from app.config import settings
from app.agents.compiler import CompiledPage
from app.agents.researcher import _parse_json_lenient
from marzi_travel import site_config
from marzi_travel import vector_store
from marzi_travel.distributor import TravelDistributorAgent

logger = logging.getLogger(__name__)

_DATA_DIR = site_config.DATA_DIR

_BRAND_STOP = {
    "marzi", "holidays", "indian", "seniors", "senior", "above", "50", "55", "60",
    "travel", "travellers", "trip", "international", "india",
}
_ENGLISH_STOP = {
    "the", "a", "an", "and", "or", "but", "for", "with", "to", "of", "in",
    "on", "at", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "this", "that",
    "these", "those", "what", "which", "who", "how", "when", "where",
    "why", "your", "you", "our", "their", "they", "it", "its", "as", "if",
    "than", "then", "so", "such", "no", "not", "vs", "de",
}


# ── Scrape holidays.marzi.life ──

def _scrape_holidays_site(brand_url: str = site_config.BRAND_URL, timeout: int = 20) -> dict:
    """Fetch holidays.marzi.life and extract trip names, destinations, and page copy.

    Returns a dict with:
      - raw_text: cleaned plain text from the site
      - trips: list of extracted trip/destination strings
    """
    result = {"raw_text": "", "trips": []}
    try:
        resp = httpx.get(brand_url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "aside"]):
            tag.decompose()
        raw_text = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True)).strip()
        result["raw_text"] = raw_text[:6000]

        # Extract likely trip/destination names: headings, anchor text, bold copy
        trips: list[str] = []
        for tag in soup.find_all(["h1", "h2", "h3", "h4", "strong", "b", "a"]):
            text = tag.get_text(strip=True)
            if 15 < len(text) < 120 and not text.lower().startswith(("home", "about", "contact", "menu")):
                trips.append(text)

        # Deduplicate preserving order
        seen: set[str] = set()
        unique_trips: list[str] = []
        for t in trips:
            key = t.lower()
            if key not in seen:
                seen.add(key)
                unique_trips.append(t)
        result["trips"] = unique_trips[:40]
        logger.info(f"[TravelRecommender] Scraped {brand_url}: {len(unique_trips)} candidate trips/headings")
    except Exception as e:
        logger.warning(f"[TravelRecommender] Could not scrape {brand_url}: {e}")
    return result


# ── Inventory helpers ──

def _extract_body_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True)).strip()


def _index_inventory(pages: list[CompiledPage]) -> None:
    inserted = updated = skipped = 0
    for page in pages:
        if not page.slug:
            continue
        try:
            html = Path(page.file_path).read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"[TravelRecommender] Cannot read {page.file_path}: {e}")
            continue
        body = _extract_body_text(html)
        embed_source = f"{page.title}\n{page.meta_description}\n{body}"
        result = vector_store.upsert_page(
            slug=page.slug,
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

    removed = vector_store.reconcile({p.slug for p in pages if p.slug})
    stats = vector_store.collection_stats()
    logger.info(
        f"[TravelRecommender] Vector index: +{inserted} new, ~{updated} updated, "
        f"={skipped} unchanged, -{removed} stale → {stats['pages']} pages, {stats['chunks']} chunks"
    )


def _category_histogram(pages: list[CompiledPage]) -> dict[str, int]:
    hist: dict[str, int] = {}
    for p in pages:
        hist[p.category] = hist.get(p.category, 0) + 1
    return hist


def _theme_histogram(pages: list[CompiledPage], top_n: int = 20) -> list[tuple[str, int]]:
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


# ── Past recommendations ──

def _recommendations_path() -> Path:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return _DATA_DIR / f"recommendations-{today}.json"


def _load_recent_recommendations(limit: int = 50) -> list[str]:
    files = sorted(_DATA_DIR.glob("recommendations-*.json"))[-10:]
    recent: list[str] = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            for r in data.get("recommendations", []):
                if isinstance(r, dict) and r.get("topic"):
                    recent.append(r["topic"])
        except Exception:
            continue
    return recent[-limit:]


# ── LLM ideation ──

@dataclass
class TravelTopicRecommendation:
    topic: str
    rationale: str
    target_category: str
    expected_intent: str
    priority_score: float
    topic_type: str = "general"          # "trip_specific" | "general"
    themes_addressed: list[str] = field(default_factory=list)
    max_similarity_to_existing: float = 0.0
    closest_existing_slug: str | None = None


def _build_prompt(
    pages: list[CompiledPage],
    cat_hist: dict[str, int],
    theme_hist: list[tuple[str, int]],
    recent_recs: list[str],
    scraped_trips: list[str],
    scraped_text: str,
    n: int,
) -> str:
    inventory = [{"slug": p.slug, "title": p.title, "category": p.category} for p in pages]
    return f"""You are a content strategist for Marzi Holidays — a premium senior-first travel concierge for mobile, active Indian travellers aged 50+. Your primary focus is INTERNATIONAL travel (Europe, Southeast Asia, USA/Canada) but Indian domestic destinations are also valid.

GOAL: Suggest {n + 5} new blog topics that:
1. Fill genuine gaps in the existing content (under-served categories, missing destinations, missing worries)
2. Mix TRIP-SPECIFIC blogs (grounded in the actual trips Marzi Holidays offers) with GENERAL TRAVEL blogs (health, logistics, destination guides, packing, forex, visas, etc.)
3. Are highly searchable — topics Indian seniors above 50 actually Google

EXISTING TRAVEL BLOGS ({len(pages)} published):
{json.dumps(inventory, indent=2)}

CATEGORY COVERAGE (under-served should be prioritised):
{json.dumps(cat_hist, indent=2)}

TOP THEMES ALREADY COVERED (avoid re-covering unless going deeper):
{json.dumps(theme_hist[:15], indent=2)}

CURRENT TRIPS ON holidays.marzi.life (use these to inspire trip-specific blogs):
{json.dumps(scraped_trips[:30], indent=2)}

SITE CONTEXT FROM holidays.marzi.life (brand voice, destinations, services):
{scraped_text[:2000]}

RECENTLY SUGGESTED TOPICS (avoid repeating these):
{json.dumps(recent_recs[-15:], indent=2)}

RULES:
1. At least 40% of suggestions should be TRIP-SPECIFIC — directly tied to a real Marzi Holidays destination/package from the list above.
2. At least 40% should be GENERAL TRAVEL — useful for any Indian senior traveller (medicines, forex, insurance, visa, packing, airports, hotels, etc.)
3. Every topic must be a concrete, searchable blog title — not a vague theme.
4. target_category MUST be exactly one of: "faq", "how-to", "comparison", "informational".
5. topic_type MUST be "trip_specific" or "general".
6. priority_score is 0.0–1.0 — higher = more important gap filled.
7. Brand voice: destination-first (80% destination content), Marzi mentioned only once near the end as a soft closer. NO hard sell.

Return ONLY valid JSON:
{{
  "analysis": {{
    "key_gaps_observed": ["..."],
    "under_served_categories": ["..."],
    "trip_specific_opportunities": ["..."]
  }},
  "recommendations": [
    {{
      "topic": "...",
      "rationale": "one sentence explaining the gap this fills",
      "target_category": "faq|how-to|comparison|informational",
      "expected_intent": "...",
      "priority_score": 0.0,
      "topic_type": "trip_specific|general",
      "themes_addressed": ["...", "..."]
    }}
  ]
}}
"""


_VALID_CATEGORIES = {"faq", "how-to", "comparison", "informational"}


def _dedup_candidates(candidates: list[dict], threshold: float) -> list[TravelTopicRecommendation]:
    survivors: list[TravelTopicRecommendation] = []
    for c in candidates:
        topic = (c.get("topic") or "").strip()
        if not topic:
            continue
        category = (c.get("target_category") or "informational").lower()
        if category not in _VALID_CATEGORIES:
            category = "informational"

        max_sim, closest_slug = vector_store.query_max_similarity(topic, k=3)
        if max_sim >= threshold:
            logger.info(f"[TravelRecommender] DROP (sim={max_sim:.3f}, nearest={closest_slug}): {topic}")
            continue

        try:
            score = float(c.get("priority_score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0

        survivors.append(TravelTopicRecommendation(
            topic=topic,
            rationale=(c.get("rationale") or "").strip(),
            target_category=category,
            expected_intent=(c.get("expected_intent") or "").strip(),
            priority_score=max(0.0, min(1.0, score)),
            topic_type=(c.get("topic_type") or "general"),
            themes_addressed=list(c.get("themes_addressed") or [])[:6],
            max_similarity_to_existing=round(max_sim, 3),
            closest_existing_slug=closest_slug,
        ))

    survivors.sort(key=lambda r: r.priority_score, reverse=True)
    return survivors


def _persist(recs: list[TravelTopicRecommendation], inventory_size: int) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "brand_url": site_config.BRAND_URL,
        "inventory_size": inventory_size,
        "recommendations": [asdict(r) for r in recs],
    }
    _recommendations_path().write_text(json.dumps(entry, indent=2), encoding="utf-8")


# ── Public entry point ──

def recommend_travel_topics(
    n: int = 5,
    similarity_threshold: float = 0.78,
) -> list[TravelTopicRecommendation]:
    """Generate N travel topic recommendations grounded in existing content and live trips.

    Args:
        n:                     Number of recommendations to return.
        similarity_threshold:  Cosine threshold above which a candidate is a duplicate.

    Returns:
        Ranked list of TravelTopicRecommendation, length ≤ n.
    """
    logger.info(f"[TravelRecommender] Starting: n={n}, threshold={similarity_threshold}")

    # 1. Inventory
    distributor = TravelDistributorAgent(output_dir=site_config.OUTPUT_DIR)
    pages = distributor.discover_existing_pages()
    logger.info(f"[TravelRecommender] Inventory: {len(pages)} existing travel blogs")

    # 2. Scrape holidays.marzi.life for current trips
    scraped = _scrape_holidays_site()

    # 3. Index inventory in ChromaDB (idempotent)
    if pages:
        _index_inventory(pages)

    # 4. Histograms
    cat_hist = _category_histogram(pages)
    theme_hist = _theme_histogram(pages)
    logger.info(f"[TravelRecommender] Categories: {cat_hist}")

    # 5. Past recommendations (avoid re-suggesting)
    recent_recs = _load_recent_recommendations()

    # 6. LLM ideation
    if not settings.gemini_api_key:
        logger.error("[TravelRecommender] GEMINI_API_KEY not configured")
        return []

    prompt = _build_prompt(pages, cat_hist, theme_hist, recent_recs, scraped["trips"], scraped["raw_text"], n)
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
            logger.error(f"[TravelRecommender] Could not parse LLM response: {raw[:300]!r}")
            return []
        analysis = parsed.get("analysis", {})
        if analysis:
            logger.info(f"[TravelRecommender] LLM analysis: gaps={analysis.get('key_gaps_observed', [])}")
        candidates = list(parsed.get("recommendations", []))
    except Exception as e:
        logger.error(f"[TravelRecommender] LLM call failed: {e}")
        return []

    logger.info(f"[TravelRecommender] LLM returned {len(candidates)} candidates")

    # 7. Semantic dedup
    survivors = _dedup_candidates(candidates, similarity_threshold)
    logger.info(f"[TravelRecommender] After dedup: {len(survivors)} survivors (requested {n})")

    top = survivors[:n]

    # 8. Persist
    _persist(top, len(pages))

    return top
