"""Agent 1: The Competitive Gap Researcher.

Pulls live SerpApi intelligence and uses an LLM to analyze:
- Dominant SERP intent (FAQ-leaning, how-to-leaning, comparison, informational)
- "People Also Ask" questions that the brand can uniquely answer
- Concrete information-gain gaps (what top results don't cover)
- Unique angles the brand can credibly own

Output: ResearchDossier consumed by the Strategist.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

import httpx
from google import genai

from app.config import settings
from app.services.brand_context import get_brand_context
from app.services.generation import scrape_brand_data

logger = logging.getLogger(__name__)


# SERP intent labels — the Strategist maps these onto ContentCategory.
SERP_INTENT_FAQ = "faq"
SERP_INTENT_HOWTO = "howto"
SERP_INTENT_COMPARISON = "comparison"
SERP_INTENT_INFORMATIONAL = "informational"
VALID_INTENTS = {SERP_INTENT_FAQ, SERP_INTENT_HOWTO, SERP_INTENT_COMPARISON, SERP_INTENT_INFORMATIONAL}


@dataclass
class ResearchDossier:
    """Complete intelligence package produced by the Researcher agent."""

    # Brand intelligence
    brand_data: dict = field(default_factory=dict)
    curated_context: dict | None = None

    # Live SERP intelligence
    people_also_ask: list[str] = field(default_factory=list)
    top_competitor_snippets: list[dict] = field(default_factory=list)
    related_searches: list[str] = field(default_factory=list)
    answer_box: dict = field(default_factory=dict)
    knowledge_graph: dict = field(default_factory=dict)

    # Derived intelligence (LLM + heuristic)
    serp_intent: str = SERP_INTENT_INFORMATIONAL
    intent_confidence: float = 0.0
    intent_signals: dict = field(default_factory=dict)
    competitor_topics_covered: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    unique_angles: list[str] = field(default_factory=list)
    suggested_title_direction: str = ""

    # Raw topic
    topic: str = ""
    brand_url: str = ""


async def _fetch_serp_data(query: str) -> dict:
    """Fetch SERP data from SerpApi for a given query.

    Returns organic results, People Also Ask, related searches, answer box,
    knowledge graph. Falls back gracefully if SERPAPI_KEY is not configured.
    """
    api_key = settings.serpapi_key
    if not api_key:
        logger.warning("SERPAPI_KEY not configured — skipping SERP analysis")
        return {
            "organic_results": [],
            "people_also_ask": [],
            "related_searches": [],
            "answer_box": {},
            "knowledge_graph": {},
        }

    params = {
        "q": query,
        "api_key": api_key,
        "engine": "google",
        "num": 10,
        "gl": "in",
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
                    "rich_snippet": r.get("rich_snippet", {}),
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
            "answer_box": data.get("answer_box", {}) or {},
            "knowledge_graph": data.get("knowledge_graph", {}) or {},
        }
    except Exception as e:
        logger.error(f"SerpApi fetch failed: {e}")
        return {
            "organic_results": [],
            "people_also_ask": [],
            "related_searches": [],
            "answer_box": {},
            "knowledge_graph": {},
        }


# ── LLM-driven SERP intent + gap analysis (one Gemini call) ──

def _build_gap_analysis_prompt(
    topic: str,
    curated: dict | None,
    brand_data: dict,
    organic_results: list[dict],
    people_also_ask: list[str],
    related_searches: list[str],
    answer_box: dict,
) -> str:
    """Construct the LLM prompt for Information Gain analysis."""
    brand_name = (curated or {}).get("brand_name") or brand_data.get("brand_name") or "the brand"

    if curated:
        brand_block = json.dumps({
            "brand_name": curated.get("brand_name"),
            "what_it_is": curated.get("what_it_is"),
            "target_audience": curated.get("target_audience"),
            "primary_value": curated.get("primary_value"),
            "cities": curated.get("cities"),
            "events_per_month": curated.get("events_per_month"),
            "event_group_size": curated.get("event_group_size"),
            "event_themes": curated.get("event_themes"),
            "pricing_model": curated.get("pricing_model"),
            "key_differentiators": curated.get("key_differentiators"),
        }, indent=2)
    else:
        brand_block = json.dumps({
            "brand_name": brand_data.get("brand_name"),
            "description": brand_data.get("description"),
            "features": brand_data.get("features", [])[:10],
        }, indent=2)

    competitors = json.dumps(
        [
            {"title": r.get("title"), "snippet": r.get("snippet"), "link": r.get("link")}
            for r in organic_results[:8]
        ],
        indent=2,
    )

    return f"""You are a competitive intelligence analyst doing AEO (Answer Engine Optimization) research.

GOAL: Identify Information Gain opportunities — facts and angles that {brand_name} can credibly own
that the live top-ranking SERP results currently miss.

TOPIC: "{topic}"

BRAND FACTS (treat as ground truth — these are real, verified details about {brand_name}):
{brand_block}

LIVE TOP SERP RESULTS (Google, India region):
{competitors}

PEOPLE ALSO ASK ({len(people_also_ask)} questions):
{json.dumps(people_also_ask[:10], indent=2)}

RELATED SEARCHES:
{json.dumps(related_searches[:10], indent=2)}

ANSWER BOX (if present):
{json.dumps(answer_box, indent=2)[:1500]}

ANALYSIS TASKS:
1. serp_intent — classify the dominant intent of the live SERP. Choose exactly one of:
   - "faq" — SERP is dominated by Q&A pages, definitions, "what is/why/who" articles, or strong PAA presence.
   - "howto" — SERP is dominated by step-by-step guides, tutorials, "how to" pages.
   - "comparison" — SERP is dominated by "vs", "best", "top N", reviews, alternative roundups.
   - "informational" — general explanatory articles that don't fit the above (default).
   Decide based on the actual titles/snippets above, not the topic string alone.
2. intent_confidence — float 0.0-1.0 reflecting how strongly the SERP leans one way.
   High confidence (>=0.7) means most top results clearly match the intent.
3. intent_reasoning — one short sentence (≤120 chars) explaining the classification.
4. competitor_topics_covered — list 5-8 short phrases describing the dominant topics/angles
   the SERP results already cover well. Be concrete (e.g. "general overview of senior meetups",
   not "social events").
5. gaps — list 4-8 SPECIFIC information gaps. Each gap must be:
   - A topic, fact, or angle the SERP results genuinely do NOT cover
   - Something {brand_name} can credibly speak to (back it with the BRAND FACTS)
   - Concrete, not generic ("competitors don't quantify event frequency in tier-1 Indian cities",
     not "competitors lack detail")
6. unique_angles — list 4-8 sharp angles {brand_name} should lead with. Each angle should
   reference a concrete brand fact (a number, a city, a theme, a pricing detail).
7. suggested_title_direction — one sentence, ≤80 chars, describing the strongest title
   angle for a piece that would outrank/outshine the current SERP. Should leverage at least
   one gap or unique angle.

Return ONLY valid JSON, no prose:
{{
  "serp_intent": "faq|howto|comparison|informational",
  "intent_confidence": 0.0,
  "intent_reasoning": "...",
  "competitor_topics_covered": ["...", "..."],
  "gaps": ["...", "..."],
  "unique_angles": ["...", "..."],
  "suggested_title_direction": "..."
}}
"""


def _llm_gap_analysis(
    topic: str,
    curated: dict | None,
    brand_data: dict,
    organic_results: list[dict],
    people_also_ask: list[str],
    related_searches: list[str],
    answer_box: dict,
) -> dict:
    """Call Gemini for Information Gain analysis. Returns parsed JSON or empty dict on failure."""
    if not settings.gemini_api_key:
        logger.warning("[Researcher] GEMINI_API_KEY not configured — skipping LLM gap analysis")
        return {}

    prompt = _build_gap_analysis_prompt(
        topic, curated, brand_data, organic_results,
        people_also_ask, related_searches, answer_box,
    )

    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                temperature=0.4,
                max_output_tokens=4096,
                response_mime_type="application/json",
            ),
        )
        raw = (response.text or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

        parsed = _parse_json_lenient(raw)
        if not parsed:
            logger.error(f"[Researcher] Could not parse LLM gap analysis JSON. Raw head: {raw[:300]!r}")
            return {}

        intent_raw = (parsed.get("serp_intent") or "").strip().lower()
        intent = intent_raw if intent_raw in VALID_INTENTS else SERP_INTENT_INFORMATIONAL
        try:
            confidence = float(parsed.get("intent_confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        return {
            "serp_intent": intent,
            "intent_confidence": round(confidence, 3),
            "intent_reasoning": (parsed.get("intent_reasoning") or "").strip(),
            "competitor_topics_covered": list(parsed.get("competitor_topics_covered", []))[:10],
            "gaps": list(parsed.get("gaps", []))[:10],
            "unique_angles": list(parsed.get("unique_angles", []))[:10],
            "suggested_title_direction": (parsed.get("suggested_title_direction") or "").strip(),
        }
    except Exception as e:
        logger.error(f"[Researcher] LLM gap analysis failed: {e}")
        return {}


def _parse_json_lenient(raw: str) -> dict:
    """Parse JSON, falling back to best-effort recovery if the response is truncated.

    Gemini sometimes returns JSON cut off mid-string when hitting token limits.
    We try strict parse, then strip a trailing partial item and close brackets.
    """
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Strategy: walk back to last balanced position and close brackets.
    candidate = raw
    # Drop trailing partial string by truncating at last quote.
    last_quote = candidate.rfind('"')
    if last_quote != -1:
        candidate = candidate[: last_quote + 1]
    # Drop a dangling comma + partial item.
    candidate = re.sub(r",\s*[^,\]\}]*$", "", candidate)
    # Close any open arrays / objects (in nesting order).
    open_brackets = []
    in_string = False
    escape = False
    for ch in candidate:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "[{":
            open_brackets.append(ch)
        elif ch in "]}":
            if open_brackets and ((ch == "]" and open_brackets[-1] == "[") or (ch == "}" and open_brackets[-1] == "{")):
                open_brackets.pop()
    closer = {"[": "]", "{": "}"}
    candidate += "".join(closer[b] for b in reversed(open_brackets))
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return {}


class ResearcherAgent:
    """Agent 1: Competitive Gap Researcher.

    Executes brand scraping + SerpApi intelligence + LLM gap analysis
    to produce a ResearchDossier that downstream agents consume.
    """

    async def run(self, topic: str, brand_url: str) -> ResearchDossier:
        logger.info(f"[Researcher] Starting research: topic='{topic}' brand='{brand_url}'")

        # 1. Brand site scrape
        brand_data = await scrape_brand_data(brand_url)
        logger.info(f"[Researcher] Scraped brand: {brand_data.get('brand_name', 'unknown')}")

        # 2. Curated context (overrides scraped data when present)
        curated = get_brand_context(brand_url)
        if curated:
            logger.info("[Researcher] Curated brand context loaded")

        # 3. Live SERP — primary query + brand-augmented query for broader coverage
        brand_name_for_query = (curated or {}).get("brand_name") or brand_data.get("brand_name", "")
        serp_queries = [topic]
        if brand_name_for_query and brand_name_for_query.lower() not in topic.lower():
            serp_queries.append(f"{brand_name_for_query} {topic}")

        all_paa: list[str] = []
        all_snippets: list[dict] = []
        all_related: list[str] = []
        answer_box: dict = {}
        knowledge_graph: dict = {}

        for query in serp_queries:
            if not query.strip():
                continue
            serp = await _fetch_serp_data(query)
            all_paa.extend(serp["people_also_ask"])
            all_snippets.extend(serp["organic_results"])
            all_related.extend(serp["related_searches"])
            if not answer_box and serp["answer_box"]:
                answer_box = serp["answer_box"]
            if not knowledge_graph and serp["knowledge_graph"]:
                knowledge_graph = serp["knowledge_graph"]

        # Dedupe PAA + related (case-insensitive)
        unique_paa = _dedupe_strings(all_paa)
        unique_related = _dedupe_strings(all_related)

        # Dedupe organic by link
        seen_links = set()
        unique_snippets: list[dict] = []
        for r in all_snippets:
            link = r.get("link", "")
            if link and link not in seen_links:
                seen_links.add(link)
                unique_snippets.append(r)

        logger.info(
            f"[Researcher] SERP: {len(unique_snippets)} organic, "
            f"{len(unique_paa)} PAA, {len(unique_related)} related, "
            f"answer_box={'yes' if answer_box else 'no'}"
        )

        # 4. LLM-driven SERP intent classification + Information Gain analysis (one call)
        gap_analysis = _llm_gap_analysis(
            topic=topic,
            curated=curated,
            brand_data=brand_data,
            organic_results=unique_snippets,
            people_also_ask=unique_paa,
            related_searches=unique_related,
            answer_box=answer_box,
        )

        intent = gap_analysis.get("serp_intent") or SERP_INTENT_INFORMATIONAL
        confidence = float(gap_analysis.get("intent_confidence") or 0.0)
        intent_reasoning = gap_analysis.get("intent_reasoning", "") or ""
        gaps = gap_analysis.get("gaps", []) or []
        unique_angles = gap_analysis.get("unique_angles", []) or []
        competitor_topics = gap_analysis.get("competitor_topics_covered", []) or []
        suggested_title = gap_analysis.get("suggested_title_direction", "") or ""

        logger.info(
            f"[Researcher] LLM analysis: intent={intent} (confidence={confidence}) — {intent_reasoning}"
        )
        logger.info(
            f"[Researcher] Gap analysis: {len(gaps)} gaps, "
            f"{len(unique_angles)} angles, {len(competitor_topics)} competitor topics covered"
        )

        return ResearchDossier(
            brand_data=brand_data,
            curated_context=curated,
            people_also_ask=unique_paa,
            top_competitor_snippets=unique_snippets,
            related_searches=unique_related,
            answer_box=answer_box,
            knowledge_graph=knowledge_graph,
            serp_intent=intent,
            intent_confidence=confidence,
            intent_signals={"reasoning": intent_reasoning} if intent_reasoning else {},
            competitor_topics_covered=competitor_topics,
            gaps=gaps,
            unique_angles=unique_angles,
            suggested_title_direction=suggested_title,
            topic=topic,
            brand_url=brand_url,
        )


def _dedupe_strings(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for s in items:
        if not s:
            continue
        key = s.lower().strip()
        if key in seen:
            continue
        seen.add(key)
        out.append(s.strip())
    return out


