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

EDITORIAL STANCE — READ FIRST (very important):
The output blog must be DESTINATION/TOPIC FIRST and Marzi LAST. At least 80% of the blog should be real, useful content about the destination or topic: places to see, suggested itineraries, attractions, practical advice, named hospitals/apps/insurers. Marzi Holidays is mentioned only in ONE closing section near the end as a soft, optional resource — NOT threaded through every section. Do NOT frame the entire piece as "how Marzi solves this." The reader should feel they got a useful guide first; the Marzi mention is a soft offer at the end.

Specifically:
- If the topic names a destination (e.g. "Kerala backwaters", "Golden Triangle", "Europe destinations for seniors"), surface real PLACES TO SEE (5–7 named attractions / cities / experiences) and an itinerary outline a traveller could actually use.
- If the topic is service-oriented (e.g. "Cash vs forex card", "Best flight seats", "Travelling without depending on children"), surface practical advice, named tools/products/policies, and real comparisons.
- The marzi_wow_solution field below should be a SHORT, SOFT closing paragraph — one section near the end — NOT the structural anchor of the piece.

AUDIENCE — READ FIRST:
The reader is a MOBILE, ACTIVE, affluent Indian traveller 50+ (or their adult child planning the trip). They walk, climb steps, and enjoy full-day sightseeing. They are NOT mobility-impaired. Do NOT default to "wheelchair", "step-free", "Grade-A mobility obstacles" framing unless the topic explicitly names mobility. The real worries for this audience are:
- International travel anxiety, first-trip-after-retirement confidence
- Country-specific medicine carry rules (BP, diabetes, thyroid, customs)
- Flights, seat choice, transit time, airport navigation
- Hotel selection (floor, room type, lift, neighbourhood) and cheap-hotel traps
- Itinerary pacing and ENERGY MANAGEMENT (NOT mobility management) — slow travel, fewer cities
- Forex card vs credit card vs cash, international roaming, safe money handling
- Destination choice (best first-time international country, Europe walkability)
- Emotional & identity: independence from adult children, dignity, why travel matters after retirement

DEFAULT CONTEXT: Unless the topic names a specific domestic Indian destination, assume INTERNATIONAL travel.

LIVE-SEARCH METHODOLOGY (use the GoogleSearch tool — do NOT fabricate sources):
- Search Indian travel forums and writing: TripAdvisor India, Quora India, Reddit r/india, Reddit r/IndiaTravel, Reddit r/IndianTravellers, blogs and YouTube comments by Indian travellers.
- Try multiple query variants explicitly: "{destination} 50+ Indian traveller", "{destination} senior citizen India", "{destination} for Indian parents", "{destination} first time abroad India", "{destination} forex India", "{destination} Indian medicine customs", "{destination} jet lag Indian seniors". Tailor query variants to the actual TOPIC (don't force mobility queries unless mobility is the topic).
- Frequency-rank worries before selecting the Top 4 — count the number of distinct threads/posts per worry cluster across the last 24 months.
- Niche-filter: collapse closely related complaints into one named cluster (e.g. "Schengen visa anxiety" + "biometric appointment delay" + "rejection on weak ITR" → one named worry like "Schengen visa confidence gap for Indian retirees").

WHAT TO RETURN (one JSON object, no prose, no markdown fences):

{{
  "destination": "{destination}",
  "frequency_rank_pre_filter": "1 line: e.g. '52 unique threads scanned across TripAdvisor India + Quora India + Reddit r/india.'",
  "niche_filter_applied": "1 line: e.g. 'Collapsed steps/stairs/hills posts into one Mobility Obstacles cluster.'",
  "destination_content": {{
    "is_destination_topic": true,
    "top_places_to_see": [
      "5–7 entries. For destination topics: real named attractions/cities/experiences with a 1-line description (e.g. 'Alleppey backwaters — overnight houseboat on Punnamada Lake, gentle pace, ideal for seniors who tire easily'). For service/info topics: 5–7 named tools/products/policies/insurers/apps relevant to the topic instead."
    ],
    "suggested_itinerary": [
      "4–7 day-by-day high-level outline. For destination topics: e.g. 'Day 1: Arrive Kochi, settle at Brunton Boatyard, light walk along Fort Kochi sea-face'. For service/info topics: a step-by-step recommended process instead (e.g. 'Step 1: Apply for Schengen visa 8 weeks before travel; Step 2: ...')."
    ],
    "practical_facts": [
      "5–8 concrete, verifiable facts about the destination/topic that the blog body should embed (e.g. 'Munnar is at 1,600m elevation; cool 15–25°C year-round', 'Kerala backwater houseboats cost ₹8,000–₹18,000/night per couple'). Real numbers, real names — never generic."
    ]
  }},
  "top_worries": [
    {{
      "module": "Anxiety & Confidence | Medicines & Health | Flights & Airports | Hotels & Stay | Itinerary & Pace (Energy Management) | Forex / Payments / Connectivity | Destination Choice | Emotional & Identity",
      "specific_worry": "granular, hyper-specific (NOT 'health concerns' but e.g. 'Carrying 90-day BP medication into Schengen — original prescription in English vs Hindi, customs declaration risk at Frankfurt'). Match the worry to the active-senior audience, NOT to mobility limitations.",
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
      {{"name": "name fear 1 (e.g. Burden-on-children fear, Customs-and-rules fear, Independence-loss fear, FOMO fear, Dignity fear, Money-mistake fear)", "internal_monologue": "verbatim internal monologue in quotes"}},
      {{"name": "name fear 2", "internal_monologue": "..."}},
      {{"name": "name fear 3", "internal_monologue": "..."}},
      {{"name": "name fear 4", "internal_monologue": "..."}}
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
    "marzi_wow_solution": "ONE SHORT SOFT CLOSING PARAGRAPH (3–4 sentences max) for a single end-of-article section titled 'How Marzi Holidays can help' or 'Planning this trip with Marzi'. Soft offer, NOT a sales pitch — frame Marzi as a free optional resource the reader can choose to use. Mention ONE or TWO of: Travel Mitr (₹199 / currently free 30-min expert callback), Plan Trip (free AI itinerary builder/audit), Prepare for Trip (free medicine/visa/forex/packing). Avoid phrases like 'Marzi solves this', 'choose Marzi', 'book with Marzi'. Do NOT make this the headline of the piece. Do NOT repeat this in earlier sections.",
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
5. STRUCTURE — DESTINATION/TOPIC FIRST, MARZI LAST (non-negotiable):
   - At least 80% of the downstream blog will be real destination/topic content (places, itinerary, practical facts). Make sure `destination_content` is rich and concrete.
   - `marzi_wow_solution` is a soft 3–4 sentence closing paragraph — NOT the article's anchor. Do not let Marzi framing dominate the worry analysis.
6. FACTUAL ACCURACY ABOUT MARZI HOLIDAYS — NON-NEGOTIABLE:
   - Marzi Holidays is a senior-first travel CONCIERGE and PLANNING service. It is NOT a tour operator and NOT a package seller.
   - Marzi does NOT book hotels, flights, transport, guides, or any on-ground service. The traveller books everything; Marzi advises.
   - Marzi's three services are: Travel Mitr (₹199 / currently free 30-min expert callback at holidays.marzi.life/travel-mitr), Plan Trip (free AI itinerary builder + audit at holidays.marzi.life/plan-trip), and Prepare for Trip (free medicine checker / visa / forex / packing guidance at holidays.marzi.life/prepare).
   - NEVER write that Marzi 'curates stays', 'operates tours', 'arranges transport', 'provides on-trip support staff', 'handles bookings', or sells 'packages' / 'itineraries' as products. Marzi recommends; it does not deliver on the ground.
7. No <html>, no markdown fences, no prose — return ONLY the JSON object.
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

    # unique_angles drive Strategist section seeds + Writer information-gain block.
    # Order matters: destination/topic content leads, Marzi appears once at the very end.
    angles: list[str] = []
    dc = research.get("destination_content") or {}
    for place in dc.get("top_places_to_see") or []:
        if isinstance(place, str) and place.strip():
            angles.append(f"Place / highlight: {place.strip()}")
    itinerary = dc.get("suggested_itinerary") or []
    if itinerary:
        joined = " | ".join(s.strip() for s in itinerary if isinstance(s, str) and s.strip())
        if joined:
            angles.append(f"Suggested itinerary outline (build a dedicated section around this): {joined}")
    for fact in dc.get("practical_facts") or []:
        if isinstance(fact, str) and fact.strip():
            angles.append(f"Practical fact to embed: {fact.strip()}")
    for sol in research.get("trusted_solutions_global") or []:
        if isinstance(sol, str) and sol.strip():
            angles.append(sol.strip())
    for w in top_worries:
        for sol in w.get("trusted_solutions") or []:
            if isinstance(sol, str) and sol.strip() and sol.strip() not in angles:
                angles.append(sol.strip())
    # Marzi soft-close appears LAST, framed as a single closing section.
    hero_solution = (hero.get("marzi_wow_solution") or "").strip()
    if hero_solution:
        angles.append(
            "Final section ONLY (do NOT thread through earlier sections) — "
            f"'How Marzi Holidays can help' soft closing paragraph: {hero_solution}"
        )

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
