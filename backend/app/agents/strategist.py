"""Agent 2: The Semantic Strategist.

Consumes the ResearchDossier from Agent 1 and decides:
- ContentCategory (FAQ / HowTo / Comparison / Informational) — driven by live SERP
  intent, NOT by topic-string keywords or hardcoded overrides
- The JSON-LD schema type
- The URL slug, title direction, and section outline — built from real PAA
  questions, related searches, competitor topics, and LLM-derived angles
- Entity mapping for schema.org compliance

Output: ContentBlueprint consumed by the Writer agent.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.schemas.content import ContentCategory
from app.agents.researcher import (
    ResearchDossier,
    SERP_INTENT_FAQ,
    SERP_INTENT_HOWTO,
    SERP_INTENT_COMPARISON,
    SERP_INTENT_INFORMATIONAL,
)

logger = logging.getLogger(__name__)


_INTENT_TO_CATEGORY = {
    SERP_INTENT_FAQ: ContentCategory.FAQ,
    SERP_INTENT_HOWTO: ContentCategory.HOW_TO,
    SERP_INTENT_COMPARISON: ContentCategory.COMPARISON,
    SERP_INTENT_INFORMATIONAL: ContentCategory.INFORMATIONAL,
}

_SCHEMA_MAP = {
    ContentCategory.FAQ: "FAQPage",
    ContentCategory.HOW_TO: "HowTo",
    ContentCategory.COMPARISON: "Article",
    ContentCategory.INFORMATIONAL: "BlogPosting",
}


@dataclass
class ContentBlueprint:
    """Strategic blueprint that guides the Writer agent."""

    slug: str = ""
    category: ContentCategory = ContentCategory.INFORMATIONAL
    schema_type: str = "BlogPosting"

    title_direction: str = ""
    target_questions: list[str] = field(default_factory=list)
    section_outline: list[str] = field(default_factory=list)
    key_facts_to_embed: list[str] = field(default_factory=list)
    information_gain_angles: list[str] = field(default_factory=list)
    competitor_topics_to_outdo: list[str] = field(default_factory=list)

    primary_entity: str = ""
    related_entities: list[str] = field(default_factory=list)

    dossier: ResearchDossier | None = None


# ── Category decision (live SERP intent → category) ──

def _decide_category(dossier: ResearchDossier) -> ContentCategory:
    """Pick a ContentCategory using SERP signals from the Researcher.

    Primary signal: dossier.serp_intent. Topic-string keywords are only used
    as a tie-breaker when SERP confidence is very low.
    """
    intent = dossier.serp_intent
    confidence = dossier.intent_confidence or 0.0

    # High-confidence SERP signal — trust it.
    if confidence >= 0.25 and intent in _INTENT_TO_CATEGORY:
        return _INTENT_TO_CATEGORY[intent]

    # Low confidence — fall back to topic keywords.
    topic_lower = (dossier.topic or "").lower()
    if any(kw in topic_lower for kw in ["how to", "step by step", "get started"]):
        return ContentCategory.HOW_TO
    if any(kw in topic_lower for kw in [" vs ", "versus", "compare", "comparison", "review", "best "]):
        return ContentCategory.COMPARISON
    if any(kw in topic_lower for kw in ["faq", "questions", "q&a"]) or len(dossier.people_also_ask) >= 5:
        return ContentCategory.FAQ
    return _INTENT_TO_CATEGORY.get(intent, ContentCategory.INFORMATIONAL)


# ── Slug ──

def _generate_slug(topic: str, brand_name: str) -> str:
    """Generate an AEO-optimized URL slug. Brand name prefix for discoverability."""
    text = (topic or "").lower().strip()
    text = text.replace("—", " ").replace("–", " ")
    filler = [r"\bhow to\b", r"\bwhat is\b", r"\ba guide to\b", r"\bthe\b", r"\ban\b", r"\ba\b"]
    for f in filler:
        text = re.sub(f, " ", text)
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")

    brand_slug = (brand_name or "").lower().strip()
    if brand_slug and not text.startswith(brand_slug):
        text = f"{brand_slug}-{text}" if text else brand_slug

    return text[:80].strip("-")


# ── Section outlines built from live data ──

def _build_section_outline(
    category: ContentCategory,
    dossier: ResearchDossier,
) -> list[str]:
    """Build a category-appropriate section outline from real research data.

    Sections are derived from PAA, related searches, gaps, and unique angles —
    not hardcoded "What is {brand}?" templates.
    """
    paa = [q for q in dossier.people_also_ask if q]
    related = [r for r in dossier.related_searches if r]
    angles = list(dossier.unique_angles or [])
    gaps = list(dossier.gaps or [])
    curated = dossier.curated_context or {}

    if category == ContentCategory.FAQ:
        sections: list[str] = []
        # Lead with real PAA — what users are actually asking.
        for q in paa[:6]:
            sections.append(q if q.endswith("?") else f"{q}?")
        # Add brand-specific FAQ pulled from gaps the Researcher surfaced.
        for gap in gaps[:3]:
            sections.append(_gap_to_question(gap, curated))
        # Backstop coverage: if PAA was thin, add brand pillars.
        if len(sections) < 5:
            sections.extend(_fallback_brand_questions(curated, dossier))
        return _dedupe(sections)[:9]

    if category == ContentCategory.HOW_TO:
        intro = f"Why this matters: the situation in {_primary_market(curated)}".strip()
        # Use related_searches as scoped sub-tasks where relevant
        steps: list[str] = [intro]
        steps.append("What you'll need before you start")
        # Build steps from PAA "how" questions if present, else use angle-driven steps
        howto_paa = [q for q in paa if re.search(r"\bhow\b", q.lower())]
        for i, q in enumerate(howto_paa[:5], 1):
            steps.append(f"Step {i}: {_paa_to_step(q)}")
        # If still light, augment with angle-driven steps
        if len(steps) < 6:
            for i, angle in enumerate(angles[:5], len(steps) - 1):
                steps.append(f"Step {i}: {_angle_to_step(angle)}")
        steps.append("Pro tips and common pitfalls")
        steps.append("What to do after your first event")
        return _dedupe(steps)[:10]

    if category == ContentCategory.COMPARISON:
        sections = [
            f"The current landscape: what users find when they search '{dossier.topic}'",
            "Comparison criteria that actually matter",
            "Side-by-side comparison table",
        ]
        # Add competitor entities (from organic titles) as comparison axes
        competitors = _extract_competitor_names(dossier)
        if competitors:
            sections.append(f"How {_primary_entity(dossier)} compares to {', '.join(competitors[:3])}")
        # Use gaps as comparison advantages
        for gap in gaps[:3]:
            sections.append(f"Where alternatives fall short: {_short(gap)}")
        sections.extend([
            f"Pros and cons of {_primary_entity(dossier)}",
            "Who each option is best for",
            "Verdict and recommendation",
        ])
        return _dedupe(sections)[:9]

    # INFORMATIONAL
    sections = []
    # Lead with the strongest unique angle, then competitor-uncovered gaps, then PAA, then related.
    if angles:
        sections.append(f"The short answer: {_short(angles[0])}")
    sections.append(f"What '{dossier.topic}' actually means right now")
    for gap in gaps[:3]:
        sections.append(f"What most sources miss: {_short(gap)}")
    for q in paa[:3]:
        sections.append(q if q.endswith("?") else f"{q}?")
    for r in related[:2]:
        sections.append(f"Related: {r.title()}")
    sections.append("Key takeaways")
    return _dedupe(sections)[:9]


# ── Helpers ──

def _gap_to_question(gap: str, curated: dict) -> str:
    """Convert a gap statement into a question for FAQ sections."""
    s = gap.rstrip(".")
    if s.endswith("?"):
        return s
    # Heuristic: if the gap mentions a fact, frame as "what/how" question.
    if re.search(r"\b\d", s):
        return f"What does the data say about {_lowercase_first(s)}?"
    return f"What about {_lowercase_first(s)}?"


def _fallback_brand_questions(curated: dict, dossier: ResearchDossier) -> list[str]:
    """Last-resort questions when PAA + gaps don't yield enough FAQ entries."""
    brand = curated.get("brand_name") or dossier.brand_data.get("brand_name") or "this platform"
    questions = []
    if curated.get("cities"):
        questions.append(f"Which cities does {brand} operate in?")
    if curated.get("pricing_model"):
        questions.append(f"How does pricing work on {brand}?")
    if curated.get("event_themes"):
        questions.append(f"What kinds of events does {brand} run?")
    if curated.get("target_audience"):
        questions.append(f"Who is {brand} actually for?")
    return questions


def _paa_to_step(q: str) -> str:
    """Turn a 'how' PAA question into an action-oriented step."""
    q = q.rstrip("?").strip()
    q = re.sub(r"^how\s+(do|can|to)\s+(i|you)\s+", "", q, flags=re.IGNORECASE)
    q = re.sub(r"^how\s+to\s+", "", q, flags=re.IGNORECASE)
    return q[:1].upper() + q[1:] if q else "Take the next action"


def _angle_to_step(angle: str) -> str:
    """Turn an angle into a step-style sentence."""
    s = angle.rstrip(".")
    return _short(s, 80)


def _extract_competitor_names(dossier: ResearchDossier) -> list[str]:
    """Pull competitor entity names from organic result titles (best-effort)."""
    names: list[str] = []
    seen = set()
    for r in dossier.top_competitor_snippets[:8]:
        title = r.get("title") or ""
        # Naive: take first capitalized phrase before " - " or " | "
        head = re.split(r"\s[-|–|]\s|: ", title)[-1].strip()
        head = re.sub(r"\s*\(\d{4}\)\s*$", "", head)  # strip trailing year
        if 3 <= len(head) <= 40 and head.lower() not in seen:
            seen.add(head.lower())
            names.append(head)
    return names[:5]


def _primary_entity(dossier: ResearchDossier) -> str:
    return (
        (dossier.curated_context or {}).get("brand_name")
        or dossier.brand_data.get("brand_name")
        or "this brand"
    )


def _primary_market(curated: dict) -> str:
    cities = curated.get("cities") if curated else None
    return ", ".join(cities) if cities else "your market"


def _short(text: str, limit: int = 90) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "…"


def _lowercase_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s else s


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        if not item:
            continue
        key = item.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out


# ── Key facts ──

def _extract_key_facts(dossier: ResearchDossier) -> list[str]:
    """Pull concrete, citable facts. Prefers curated context, falls back to scrape."""
    facts: list[str] = []
    curated = dossier.curated_context

    if curated:
        if curated.get("what_it_is"):
            facts.append(curated["what_it_is"])
        if curated.get("target_audience"):
            facts.append(f"Target audience: {curated['target_audience']}")
        if curated.get("cities"):
            facts.append(f"Cities: {', '.join(curated['cities'])}")
        if curated.get("events_per_month"):
            facts.append(curated["events_per_month"])
        if curated.get("event_group_size"):
            facts.append(f"Group size: {curated['event_group_size']}")
        if curated.get("pricing_model"):
            facts.append(f"Pricing: {curated['pricing_model']}")
        if curated.get("booking_method"):
            facts.append(f"Booking: {curated['booking_method']}")
        for theme in (curated.get("event_themes") or [])[:6]:
            facts.append(f"Event theme: {theme}")
    else:
        bd = dossier.brand_data
        if bd.get("description"):
            facts.append(bd["description"])
        for feat in bd.get("features", [])[:5]:
            facts.append(feat)

    # Add answer-box snippets as supporting facts (real, current data from SERP)
    if dossier.answer_box:
        ab_snippet = dossier.answer_box.get("snippet") or dossier.answer_box.get("answer")
        if ab_snippet and isinstance(ab_snippet, str):
            facts.append(f"SERP answer-box: {ab_snippet[:200]}")

    return facts


# ── Title direction ──

def _build_title_direction(
    category: ContentCategory,
    dossier: ResearchDossier,
    brand_name: str,
) -> str:
    """Title direction prefers the LLM's suggestion from research, then category templates."""
    suggested = (dossier.suggested_title_direction or "").strip()
    if suggested:
        return suggested

    topic_clean = (dossier.topic or "").strip().rstrip(".")
    if category == ContentCategory.FAQ:
        return f"{brand_name}: Answers to the Top Questions About {topic_clean}".strip()
    if category == ContentCategory.HOW_TO:
        return f"How to: {topic_clean} — A Step-by-Step Guide"
    if category == ContentCategory.COMPARISON:
        return f"{brand_name} vs Alternatives: {topic_clean}"
    return f"{brand_name}: {topic_clean}"


class StrategistAgent:
    """Agent 2: Semantic Strategist."""

    def run(
        self,
        dossier: ResearchDossier,
        category_override: ContentCategory | None = None,
    ) -> ContentBlueprint:
        """Produce a ContentBlueprint from research intelligence.

        The Strategist chooses the category based on live SERP intent.
        category_override is honored only if explicitly passed (for manual control);
        the default flow lets the Strategist decide.
        """
        logger.info(f"[Strategist] Planning content for topic='{dossier.topic}'")

        # Decide category — SERP-driven by default
        if category_override is not None:
            category = category_override
            logger.info(f"[Strategist] Using explicit category override: {category.value}")
        else:
            category = _decide_category(dossier)
            logger.info(
                f"[Strategist] SERP-derived category: {category.value} "
                f"(intent={dossier.serp_intent}, confidence={dossier.intent_confidence})"
            )

        schema_type = _SCHEMA_MAP[category]

        # Brand name + slug
        brand_name = (
            (dossier.curated_context or {}).get("brand_name")
            or dossier.brand_data.get("brand_name", "")
        )
        slug = _generate_slug(dossier.topic, brand_name)
        logger.info(f"[Strategist] Slug='{slug}'")

        # Sections built from research data (PAA, gaps, angles, related)
        sections = _build_section_outline(category, dossier)

        # Key facts and angles
        key_facts = _extract_key_facts(dossier)
        title_direction = _build_title_direction(category, dossier, brand_name)

        # Entity mapping
        related_entities = list((dossier.curated_context or {}).get("cities") or [])
        if not related_entities:
            related_entities = ["primary market"]

        blueprint = ContentBlueprint(
            slug=slug,
            category=category,
            schema_type=schema_type,
            title_direction=title_direction,
            target_questions=dossier.people_also_ask[:8],
            section_outline=sections,
            key_facts_to_embed=key_facts,
            information_gain_angles=list(dossier.unique_angles or [])[:8],
            competitor_topics_to_outdo=list(dossier.competitor_topics_covered or [])[:8],
            primary_entity=brand_name,
            related_entities=related_entities,
            dossier=dossier,
        )

        logger.info(
            f"[Strategist] Blueprint: category={category.value}, "
            f"{len(sections)} sections, {len(key_facts)} facts, "
            f"{len(blueprint.information_gain_angles)} angles, "
            f"{len(blueprint.competitor_topics_to_outdo)} competitor topics"
        )
        return blueprint
