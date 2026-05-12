"""TravelResearcher — worry-research methodology.

For a given destination/topic, do live grounded research over Indian travel
forums (TripAdvisor India, Quora India, Reddit r/india / r/IndiaTravel) to
surface frequency-ranked traveller worries specific to Indian travellers
aged 50+.  Then identify the Hero Worry, gather verbatim quotes, and name
real, verifiable trusted solutions (hospitals, apps, helplines, insurers).

Output is a `ResearchDossier` shaped exactly like backend's `ResearcherAgent`,
so the existing Strategist → Writer → Compiler chain consumes it unchanged:

  - traveller worries (questions)        → people_also_ask
  - verbatim forum quotes                → top_competitor_snippets
  - secondary worry clusters             → related_searches
  - "what blogs DON'T cover" angles      → gaps
  - named hospitals / apps / helplines   → unique_angles
  - hero worry-driven title              → suggested_title_direction
  - existing competitor blog patterns    → competitor_topics_covered

We deliberately bypass `app.services.brand_context.get_brand_context` because
its hardcoded substring matcher would falsely return MARZI_BRAND_CONTEXT for
`holidays.marzi.life` (which `endswith("marzi.life")`).  Instead the
`MARZI_HOLIDAYS_BRAND_CONTEXT` dict is injected directly into the dossier.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from google import genai
from google.genai import types as genai_types

from app.config import settings
from app.agents.researcher import (
    ResearchDossier,
    SERP_INTENT_INFORMATIONAL,
    SERP_INTENT_FAQ,
    SERP_INTENT_HOWTO,
    SERP_INTENT_COMPARISON,
    VALID_INTENTS,
    _parse_json_lenient,
)

from marzi_travel.brand_context import MARZI_HOLIDAYS_BRAND_CONTEXT

logger = logging.getLogger(__name__)


def _build_research_prompt(destination: str, brand: dict) -> str:
    """Single grounded-search prompt that does worry-research end-to-end."""
    persona = brand.get("persona", "Senior Marketing Insights Analyst for Marzi Holidays")
    return f"""ROLE: {persona}

GOAL: Produce destination-specific traveller-worry research for the topic below, grounded in *real* posts on Indian travel forums published in the last 24 months. The output drives a long-form blog post for Indian travellers aged 50+ (and the adult children planning trips with their parents).

TOPIC / DESTINATION: "{destination}"

LIVE-SEARCH METHODOLOGY (use the GoogleSearch tool — do NOT fabricate sources):
- Search Indian travel forums and writing: TripAdvisor India, Quora India, Reddit r/india, Reddit r/IndiaTravel, blogs and YouTube comments by Indian travellers.
- Try multiple query variants explicitly: "{destination} 50+ traveller", "{destination} senior citizen India", "{destination} for elderly Indian parents", "{destination} accessibility India", "{destination} medical emergency", "{destination} mobility issues".
- Frequency-rank worries before selecting the Top 4 — count the number of distinct threads/posts per worry cluster across the last 24 months.
- Niche-filter: collapse closely related complaints (e.g. "Uluwatu stairs" + "Besakih steps" + "Ubud hills" → one named worry like "Grade-A Mobility Obstacles").

WHAT TO RETURN (one JSON object, no prose, no markdown fences):

{{
  "destination": "{destination}",
  "frequency_rank_pre_filter": "1 line: e.g. '52 unique threads scanned across TripAdvisor India + Quora India + Reddit r/india.'",
  "niche_filter_applied": "1 line: e.g. 'Collapsed steps/stairs/hills posts into one Mobility Obstacles cluster.'",
  "top_worries": [
    {{
      "module": "Fit & Design | Readiness | Booking | Health | On-trip Support | Post-trip",
      "specific_worry": "granular, hyper-specific (NOT 'health concerns' but e.g. 'Insulin spoiling in 33°C heat during full-day temple tours, with no Indian-brand pharmacy backup')",
      "verbatim_quotes": [
        {{"quote": "actual Indian English forum text", "source": "TripAdvisor India / Quora India / Reddit r/india / blog name"}},
        {{"quote": "second quote", "source": "..."}}
      ],
      "volume_signal": "concrete evidence (e.g. 'Dedicated TripAdvisor thread with 22 replies', 'Top-voted Quora answer with 88 upvotes'); end with '⚫' rating out of 5.",
      "trusted_solutions": ["named real resource: hospital name + city, app name + platform, helpline + number, insurer + plan"]
    }}
    /* exactly 4 entries, ranked by volume */
  ],
  "hero_worry": {{
    "name": "name of the single hero worry",
    "stated_in_2_3_sentences": "precisely stated; name exact sites, exact physical/emotional challenge, and why skipping them feels like failing the trip",
    "fear_anatomy": [
      {{"name": "Burden Fear", "internal_monologue": "verbatim internal monologue in quotes"}},
      {{"name": "Spiritual/Cultural FOMO", "internal_monologue": "..."}},
      {{"name": "Memory/Photo Fear", "internal_monologue": "..."}},
      {{"name": "Dignity Fear", "internal_monologue": "..."}}
    ],
    "search_intensity": {{
      "tripadvisor_threads": 0,
      "quora_questions": 0,
      "dedicated_guides": 0,
      "youtube_or_social": 0,
      "rationale": "why this worry is more emotionally loaded than the others"
    }},
    "proof_quotes": [
      {{"quote": "Indian English authentic", "source": "TripAdvisor / Quora / Reddit", "emotion": "Heartbreak | Anxiety | Resignation"}},
      {{"quote": "...", "source": "...", "emotion": "..."}},
      {{"quote": "...", "source": "...", "emotion": "..."}}
    ],
    "marzi_wow_solution": "how Marzi Holidays addresses this worry through its ADVISORY services — NOT through operating tours or booking infrastructure (Marzi does NOT do those). Choose one or more of: (a) what a Travel Mitr expert flags and recommends during the 30-minute callback; (b) what the free AI Plan-Trip audit catches in an existing itinerary; (c) which Prepare-for-Trip resource resolves it (medicine eligibility checker, e-visa guidance, forex strategy, senior packing list). Reference real 2025–2026 destination infrastructure the traveller can book themselves on Marzi's advice. End with: 'All infrastructure verified via live search, [current month and year]'.",
    "title_direction": "blog title (60–70 chars) that opens with or names the hero worry; targets the SERP intent for {destination} for Indian travellers 50+"
  }},
  "people_also_ask_equivalents": [
    "6–8 traveller worries phrased as questions, ranked by frequency (e.g. 'Is {destination} safe for elderly Indian travellers with diabetes?')"
  ],
  "competing_blog_topics": [
    "5–8 patterns existing travel blogs cover for {destination} that the new piece must outdo or skip"
  ],
  "gaps": [
    "5–8 SPECIFIC information gaps — facts/angles that existing travel blogs do NOT cover for Indian travellers 50+"
  ],
  "trusted_solutions_global": [
    "8–12 named, verifiable resources for the destination: hospital + city, app, helpline + number, insurer + plan, named pharmacy chain. NEVER generic advice."
  ],
  "serp_intent": "informational | faq | howto | comparison",
  "intent_confidence": 0.0
}}

CRITICAL RULES:
1. Use ONLY real, verifiable resources via live search — never hallucinate hospitals, apps, helpline numbers, or statistics.
2. Quotes MUST sound like authentic Indian English forum writing — not formal, not robotic.
3. Every solution names a specific place / app / person / helpline. No generic advice.
4. Frequency-rank worries BEFORE selecting the Top 4. Niche-filter. Show the logic.
5. FACTUAL ACCURACY ABOUT MARZI HOLIDAYS — NON-NEGOTIABLE:
   - Marzi Holidays is a senior-first travel CONCIERGE and PLANNING service. It is NOT a tour operator and NOT a package seller.
   - Marzi does NOT book hotels, flights, transport, guides, or any on-ground service. The traveller books everything; Marzi advises.
   - Marzi's three services are: Travel Mitr (₹199 / currently free 30-min expert callback at holidays.marzi.life/travel-mitr), Plan Trip (free AI itinerary builder + audit at holidays.marzi.life/plan-trip), and Prepare for Trip (free medicine checker / visa / forex / packing guidance at holidays.marzi.life/prepare).
   - NEVER write that Marzi 'curates stays', 'operates tours', 'arranges transport', 'provides on-trip support staff', 'handles bookings', or sells 'packages' / 'itineraries' as products. Marzi recommends; it does not deliver on the ground.
6. No <html>, no markdown fences, no prose — return ONLY the JSON object.
"""


def _strip_fences(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    return raw.strip()


def _grounded_research_call(prompt: str) -> dict:
    """Call Gemini 2.5 Flash with grounded GoogleSearch tool. Returns parsed JSON."""
    if not settings.gemini_api_key:
        logger.error("[TravelResearcher] GEMINI_API_KEY not configured")
        return {}

    client = genai.Client(api_key=settings.gemini_api_key)
    last_err: Exception | None = None
    for attempt in (1, 2):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
                    temperature=0.3,
                    max_output_tokens=12000,
                ),
            )
            raw = _strip_fences(response.text or "")
            if not raw:
                last_err = RuntimeError("Empty response from Gemini")
                continue
            try:
                return json.loads(raw)
            except json.JSONDecodeError as e:
                last_err = e
                lenient = _parse_json_lenient(raw)
                if lenient:
                    return lenient
                logger.warning(
                    f"[TravelResearcher] Attempt {attempt} JSON parse failed ({e}); "
                    f"raw head: {raw[:300]!r}"
                )
        except Exception as e:
            last_err = e
            logger.warning(f"[TravelResearcher] Attempt {attempt} call failed: {e}")

    raise RuntimeError(f"[TravelResearcher] Gemini grounded research failed twice: {last_err}")


def _grounding_links(response_obj: Any) -> list[str]:
    """Best-effort extraction of grounding source URLs (used to enrich snippets)."""
    out: list[str] = []
    try:
        for cand in getattr(response_obj, "candidates", []) or []:
            meta = getattr(cand, "grounding_metadata", None)
            if not meta:
                continue
            for chunk in getattr(meta, "grounding_chunks", []) or []:
                web = getattr(chunk, "web", None)
                uri = getattr(web, "uri", None) if web else None
                if uri:
                    out.append(uri)
    except Exception:
        pass
    # Dedupe preserving order
    seen = set()
    return [u for u in out if not (u in seen or seen.add(u))]


def _to_dossier(
    research: dict,
    destination: str,
    brand_url: str,
    grounding_uris: list[str],
) -> ResearchDossier:
    """Project the worry-research output onto the existing ResearchDossier shape."""
    top_worries = research.get("top_worries") or []
    hero = research.get("hero_worry") or {}

    # PAA equivalents — drive Strategist's section outline.
    paa = list(research.get("people_also_ask_equivalents") or [])
    if not paa:
        # Fallback: derive questions from each top worry.
        for w in top_worries[:6]:
            specific = (w.get("specific_worry") or "").rstrip(".")
            if specific:
                paa.append(specific if specific.endswith("?") else f"{specific}?")

    # Forum quotes → competitor_snippets shape Strategist already understands.
    snippets: list[dict] = []
    for w in top_worries:
        for q in w.get("verbatim_quotes") or []:
            quote = (q.get("quote") or "").strip()
            source = (q.get("source") or "").strip()
            if not quote:
                continue
            snippets.append({
                "title": f"{source}: {w.get('specific_worry', '')[:80]}",
                "snippet": quote,
                "link": "",
                "position": 0,
                "rich_snippet": {},
            })
    for q in (hero.get("proof_quotes") or []):
        quote = (q.get("quote") or "").strip()
        source = (q.get("source") or "").strip()
        emotion = (q.get("emotion") or "").strip()
        if not quote:
            continue
        snippets.append({
            "title": f"{source} (Hero · {emotion})",
            "snippet": quote,
            "link": "",
            "position": 0,
            "rich_snippet": {},
        })
    # Attach grounding URIs to the first N snippets so the writer has citeable links.
    for snippet, uri in zip(snippets, grounding_uris):
        snippet["link"] = uri

    # Trusted solutions → unique_angles (Strategist section seeds + Writer angles).
    angles: list[str] = []
    for sol in research.get("trusted_solutions_global") or []:
        if isinstance(sol, str) and sol.strip():
            angles.append(sol.strip())
    for w in top_worries:
        for sol in w.get("trusted_solutions") or []:
            if isinstance(sol, str) and sol.strip() and sol.strip() not in angles:
                angles.append(sol.strip())
    # Always include the hero solution as the headline angle.
    hero_solution = (hero.get("marzi_wow_solution") or "").strip()
    if hero_solution:
        angles.insert(0, f"Marzi Holidays solution: {hero_solution}")

    gaps = list(research.get("gaps") or [])
    competitor_topics = list(research.get("competing_blog_topics") or [])

    related = []
    for w in top_worries[1:]:  # secondary worry clusters
        s = (w.get("specific_worry") or "").strip()
        if s:
            related.append(s)

    intent_raw = (research.get("serp_intent") or "informational").strip().lower()
    intent = intent_raw if intent_raw in VALID_INTENTS else SERP_INTENT_INFORMATIONAL
    try:
        confidence = float(research.get("intent_confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    title_direction = (hero.get("title_direction") or "").strip()
    if not title_direction:
        title_direction = f"{destination}: A senior-first travel guide for Indian travellers 50+"

    intent_signals: dict = {}
    rationale = ((hero.get("search_intensity") or {}).get("rationale") or "").strip()
    if rationale:
        intent_signals["reasoning"] = rationale
    intent_signals["frequency_rank_pre_filter"] = research.get("frequency_rank_pre_filter", "")
    intent_signals["niche_filter_applied"] = research.get("niche_filter_applied", "")
    intent_signals["hero_worry_name"] = hero.get("name", "")

    # Brand data block — mirrors what scrape_brand_data would have returned.
    brand_data = {
        "brand_name": MARZI_HOLIDAYS_BRAND_CONTEXT["brand_name"],
        "brand_url": MARZI_HOLIDAYS_BRAND_CONTEXT["brand_url"],
        "description": MARZI_HOLIDAYS_BRAND_CONTEXT["what_it_is"],
        "features": list(MARZI_HOLIDAYS_BRAND_CONTEXT.get("key_differentiators", []))[:10],
        "page_text": MARZI_HOLIDAYS_BRAND_CONTEXT.get("tagline", ""),
    }

    return ResearchDossier(
        brand_data=brand_data,
        curated_context=MARZI_HOLIDAYS_BRAND_CONTEXT,
        people_also_ask=paa,
        top_competitor_snippets=snippets,
        related_searches=related,
        answer_box={},
        knowledge_graph={},
        serp_intent=intent,
        intent_confidence=round(confidence, 3),
        intent_signals=intent_signals,
        competitor_topics_covered=competitor_topics,
        gaps=gaps,
        unique_angles=angles,
        suggested_title_direction=title_direction,
        topic=destination,
        brand_url=brand_url,
    )


class TravelResearcherAgent:
    """Async researcher with a `run(topic, brand_url)` signature matching backend's."""

    async def run(self, topic: str, brand_url: str) -> ResearchDossier:
        logger.info(
            f"[TravelResearcher] Starting worry-research: destination='{topic}'"
        )
        prompt = _build_research_prompt(topic, MARZI_HOLIDAYS_BRAND_CONTEXT)

        if not settings.gemini_api_key:
            logger.error("[TravelResearcher] GEMINI_API_KEY missing — returning empty dossier")
            return _to_dossier({}, topic, brand_url, [])

        # Re-implement the call directly here so we keep a handle on the response
        # object (needed for grounding metadata).
        client = genai.Client(api_key=settings.gemini_api_key)
        last_err: Exception | None = None
        research: dict = {}
        grounding_uris: list[str] = []
        for attempt in (1, 2):
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
                        temperature=0.3,
                        max_output_tokens=12000,
                    ),
                )
                raw = _strip_fences(response.text or "")
                if not raw:
                    last_err = RuntimeError("Empty response")
                    continue
                try:
                    research = json.loads(raw)
                except json.JSONDecodeError as e:
                    research = _parse_json_lenient(raw) or {}
                    if not research:
                        last_err = e
                        logger.warning(
                            f"[TravelResearcher] Attempt {attempt} JSON parse failed; "
                            f"raw head: {raw[:300]!r}"
                        )
                        continue
                grounding_uris = _grounding_links(response)
                break
            except Exception as e:
                last_err = e
                logger.warning(f"[TravelResearcher] Attempt {attempt} failed: {e}")

        if not research:
            logger.error(
                f"[TravelResearcher] Grounded research failed twice — falling back to empty dossier "
                f"(last_err={last_err})"
            )

        dossier = _to_dossier(research, topic, brand_url, grounding_uris)
        logger.info(
            f"[TravelResearcher] Dossier built: paa={len(dossier.people_also_ask)}, "
            f"snippets={len(dossier.top_competitor_snippets)}, gaps={len(dossier.gaps)}, "
            f"angles={len(dossier.unique_angles)}, intent={dossier.serp_intent}"
        )
        return dossier
