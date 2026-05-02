"""Agent 1: The Competitive Gap Researcher.

Combines brand scraping with SerpApi intelligence to identify:
- What AI models currently say about the brand's niche
- "People Also Ask" questions that marzi.life can uniquely answer
- Competitor content gaps (Information Gain opportunities)
- Real-time SERP landscape for the topic

Output: ResearchDossier used by downstream agents.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import httpx

from app.config import settings
from app.services.brand_context import get_brand_context
from app.services.generation import scrape_brand_data

logger = logging.getLogger(__name__)


@dataclass
class ResearchDossier:
    """Complete intelligence package produced by the Researcher agent."""

    # Brand intelligence
    brand_data: dict = field(default_factory=dict)
    curated_context: dict | None = None

    # SERP intelligence
    people_also_ask: list[str] = field(default_factory=list)
    top_competitor_snippets: list[dict] = field(default_factory=list)
    related_searches: list[str] = field(default_factory=list)

    # Information gain analysis
    gaps: list[str] = field(default_factory=list)
    unique_angles: list[str] = field(default_factory=list)

    # Raw topic
    topic: str = ""
    brand_url: str = ""


async def _fetch_serp_data(query: str) -> dict:
    """Fetch SERP data from SerpApi for a given query.

    Returns organic results, People Also Ask, and related searches.
    Falls back gracefully if SERPAPI_KEY is not configured.
    """
    api_key = settings.serpapi_key
    if not api_key:
        logger.warning("SERPAPI_KEY not configured — skipping SERP analysis")
        return {"organic_results": [], "people_also_ask": [], "related_searches": []}

    params = {
        "q": query,
        "api_key": api_key,
        "engine": "google",
        "num": 10,
        "gl": "in",       # India — primary market
        "hl": "en",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get("https://serpapi.com/search.json", params=params)
            resp.raise_for_status()
            data = resp.json()

        return {
            "organic_results": [
                {
                    "title": r.get("title", ""),
                    "snippet": r.get("snippet", ""),
                    "link": r.get("link", ""),
                    "position": r.get("position", 0),
                }
                for r in data.get("organic_results", [])[:10]
            ],
            "people_also_ask": [
                q.get("question", "")
                for q in data.get("related_questions", [])
            ],
            "related_searches": [
                s.get("query", "")
                for s in data.get("related_searches", [])
            ],
        }
    except Exception as e:
        logger.error(f"SerpApi fetch failed: {e}")
        return {"organic_results": [], "people_also_ask": [], "related_searches": []}


def _identify_gaps(
    curated_context: dict | None,
    competitor_snippets: list[dict],
    people_also_ask: list[str],
) -> tuple[list[str], list[str]]:
    """Analyze competitor content to find Information Gain opportunities.

    Returns (gaps, unique_angles) — what competitors miss and what marzi.life
    can uniquely provide.
    """
    gaps = []
    unique_angles = []

    if not curated_context:
        return gaps, unique_angles

    # Combine all competitor text for analysis
    competitor_text = " ".join(
        s.get("snippet", "") + " " + s.get("title", "")
        for s in competitor_snippets
    ).lower()

    # Check which Marzi differentiators are absent from competitor content
    differentiator_checks = {
        "offline meetups": "Competitors don't emphasize offline/in-person meetups for 55+",
        "pay per event": "No competitor mentions a no-subscription, pay-per-event model",
        "20 to 60": "Competitor content lacks specific group size details (20-60 participants)",
        "bangalore": "Limited competitor coverage of Bangalore-specific 55+ events",
        "mumbai": "Limited competitor coverage of Mumbai-specific 55+ events",
        "above 55": "Most competitors target broader age groups, not specifically 55+",
        "book club": "Competitors rarely mention specific themed events like book clubs for seniors",
        "storytelling": "Storytelling circles for 55+ is an untapped content angle",
        "upskilling": "Upskilling workshops for people above 55 is underrepresented",
    }

    for keyword, gap_description in differentiator_checks.items():
        if keyword not in competitor_text:
            gaps.append(gap_description)

    # Unique angles Marzi can provide based on curated context
    unique_angles = [
        f"Marzi runs 20+ events/month per city — concrete frequency data most competitors lack",
        f"Pay-per-event model with no subscription — unique pricing angle",
        f"Specific event themes (music, dance, book clubs, storytelling, upskilling, social parties) — granular detail",
        f"Group size of 20-60 people — positioned as intimate enough for real conversations",
        f"App-first booking for offline events — tech-enabled but experience-first positioning",
    ]

    # Add PAA questions as content opportunities
    for paa in people_also_ask:
        if any(term in paa.lower() for term in ["55", "senior", "elder", "retire", "meetup", "event"]):
            unique_angles.append(f"PAA opportunity: '{paa}' — marzi.life can directly answer this")

    return gaps, unique_angles


class ResearcherAgent:
    """Agent 1: Competitive Gap Researcher.

    Executes brand scraping + SerpApi intelligence gathering to produce
    a ResearchDossier that downstream agents consume.
    """

    async def run(self, topic: str, brand_url: str) -> ResearchDossier:
        """Execute research phase.

        1. Scrape brand website for current data
        2. Load curated brand context (if available)
        3. Query SerpApi for competitive landscape
        4. Analyze gaps and unique angles

        Args:
            topic: Content topic to research
            brand_url: Brand website URL

        Returns:
            ResearchDossier with all intelligence gathered
        """
        logger.info(f"[Researcher] Starting research for topic='{topic}', brand='{brand_url}'")

        # 1. Scrape brand site
        brand_data = await scrape_brand_data(brand_url)
        logger.info(f"[Researcher] Scraped brand: {brand_data.get('brand_name', 'unknown')}")

        # 2. Load curated context
        curated = get_brand_context(brand_url)
        if curated:
            logger.info("[Researcher] Curated brand context loaded")

        # 3. SERP intelligence — query variations for broader coverage
        serp_queries = [
            topic,
            f"{brand_data.get('brand_name', '')} {topic}",
        ]

        all_paa = []
        all_snippets = []
        all_related = []

        for query in serp_queries:
            if not query.strip():
                continue
            serp = await _fetch_serp_data(query)
            all_paa.extend(serp["people_also_ask"])
            all_snippets.extend(serp["organic_results"])
            all_related.extend(serp["related_searches"])

        # Deduplicate
        seen_paa = set()
        unique_paa = []
        for q in all_paa:
            if q and q.lower() not in seen_paa:
                seen_paa.add(q.lower())
                unique_paa.append(q)

        seen_related = set()
        unique_related = []
        for r in all_related:
            if r and r.lower() not in seen_related:
                seen_related.add(r.lower())
                unique_related.append(r)

        logger.info(
            f"[Researcher] SERP data: {len(unique_paa)} PAA questions, "
            f"{len(all_snippets)} competitor snippets, {len(unique_related)} related searches"
        )

        # 4. Gap analysis
        gaps, unique_angles = _identify_gaps(curated, all_snippets, unique_paa)
        logger.info(f"[Researcher] Found {len(gaps)} gaps, {len(unique_angles)} unique angles")

        return ResearchDossier(
            brand_data=brand_data,
            curated_context=curated,
            people_also_ask=unique_paa,
            top_competitor_snippets=all_snippets,
            related_searches=unique_related,
            gaps=gaps,
            unique_angles=unique_angles,
            topic=topic,
            brand_url=brand_url,
        )

import asyncio

async def main():
    result = await ResearcherAgent().run(
        "anything related freindships for senior living people",
        "https://marzi.life"
    )
    print(result)

if __name__ == "__main__":
    asyncio.run(main())