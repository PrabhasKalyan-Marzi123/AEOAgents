"""Agent 2: The Semantic Strategist.

Takes research intelligence and determines:
- The optimal URL slug for AEO discoverability
- The JSON-LD schema type (FAQPage, HowTo, Article)
- A content blueprint: section structure, target questions, key facts to embed
- Entity relationship mapping for schema.org compliance

Output: ContentBlueprint consumed by the Writer agent.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.schemas.content import ContentCategory
from app.agents.researcher import ResearchDossier

logger = logging.getLogger(__name__)


# Mapping from ContentCategory to schema.org type
_SCHEMA_MAP = {
    ContentCategory.FAQ: "FAQPage",
    ContentCategory.HOW_TO: "HowTo",
    ContentCategory.COMPARISON: "Article",       # Review + ItemList embedded
    ContentCategory.INFORMATIONAL: "BlogPosting",
}


@dataclass
class ContentBlueprint:
    """Strategic blueprint that guides the Writer agent."""

    # Identity
    slug: str = ""
    category: ContentCategory = ContentCategory.INFORMATIONAL
    schema_type: str = "BlogPosting"

    # Content structure
    title_direction: str = ""
    target_questions: list[str] = field(default_factory=list)
    section_outline: list[str] = field(default_factory=list)
    key_facts_to_embed: list[str] = field(default_factory=list)
    information_gain_angles: list[str] = field(default_factory=list)

    # Entity mapping for JSON-LD
    primary_entity: str = ""           # e.g., "Marzi"
    related_entities: list[str] = field(default_factory=list)  # e.g., ["Bangalore", "Mumbai"]

    # Research passthrough (writer needs this)
    dossier: ResearchDossier | None = None


def _determine_category(topic: str, dossier: ResearchDossier) -> ContentCategory:
    """Infer the best content category from topic text and research data.

    Heuristic rules:
    - "how to" / "get started" / "guide" → HOW_TO
    - "vs" / "comparison" / "compare" / "review" → COMPARISON
    - "what is" / "about" / "explain" / "guide to" → INFORMATIONAL
    - "faq" / "questions" / question-heavy PAA data → FAQ
    """
    topic_lower = topic.lower()

    if any(kw in topic_lower for kw in ["how to", "get started", "step by step", "book your"]):
        return ContentCategory.HOW_TO
    if any(kw in topic_lower for kw in [" vs ", "comparison", "compare", "review", "versus"]):
        return ContentCategory.COMPARISON
    if any(kw in topic_lower for kw in ["faq", "questions", "q&a"]):
        return ContentCategory.FAQ
    if any(kw in topic_lower for kw in ["what is", "what are", "about", "guide to", "explained"]):
        return ContentCategory.INFORMATIONAL

    # If many PAA questions found, FAQ might be best
    if len(dossier.people_also_ask) >= 5:
        return ContentCategory.FAQ

    return ContentCategory.INFORMATIONAL


def _generate_slug(topic: str, brand_name: str) -> str:
    """Generate an AEO-optimized URL slug.

    Prioritizes brand name + primary keyword for discoverability.
    """
    # Clean and normalize
    text = topic.lower().strip()
    # Normalize dashes (em-dash, en-dash → hyphen)
    text = text.replace("—", " ").replace("–", " ")
    # Remove filler words for tighter slugs (word-boundary safe)
    filler = [r"\bhow to\b", r"\bwhat is\b", r"\ba guide to\b", r"\bthe\b", r"\ban\b", r"\ba\b"]
    for f in filler:
        text = re.sub(f, " ", text)
    # Keep only alphanumeric, spaces, hyphens
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")

    # Ensure brand name is in the slug
    brand_slug = brand_name.lower().strip()
    if brand_slug and not text.startswith(brand_slug):
        text = f"{brand_slug}-{text}"

    return text[:80].strip("-")


def _build_section_outline(
    category: ContentCategory,
    dossier: ResearchDossier,
) -> list[str]:
    """Build a section-by-section outline based on category and research."""
    curated = dossier.curated_context or {}
    brand_name = curated.get("brand_name", dossier.brand_data.get("brand_name", "the brand"))

    if category == ContentCategory.FAQ:
        sections = [
            f"What is {brand_name} and who is it for?",
            f"Where does {brand_name} organize events?",
            f"What types of events does {brand_name} offer?",
            f"How many events happen per month?",
            f"How big are the event groups?",
            f"How do I book an event on {brand_name}?",
            f"Does {brand_name} require a subscription?",
        ]
        # Inject PAA questions that are relevant
        for paa in dossier.people_also_ask[:3]:
            if paa not in sections:
                sections.append(paa)
        return sections

    if category == ContentCategory.HOW_TO:
        return [
            f"Introduction: Why {brand_name} for offline social events",
            f"What you'll need: smartphone + {brand_name} app",
            f"Step 1: Download the {brand_name} app",
            f"Step 2: Create your profile",
            f"Step 3: Browse upcoming events in your city",
            f"Step 4: Pick an event and pay",
            f"Step 5: Show up and connect",
            f"Step 6: Explore new themes",
            "Pro tips for getting the most out of events",
        ]

    if category == ContentCategory.COMPARISON:
        return [
            f"Introduction: The 55+ social landscape",
            f"Comparison table: {brand_name} vs alternatives",
            f"Detailed breakdown: offline vs online platforms",
            f"Pros of {brand_name}",
            f"Cons / limitations of {brand_name}",
            f"Who {brand_name} is best for",
            f"Verdict and recommendation",
        ]

    # INFORMATIONAL
    return [
        f"What is {brand_name}?",
        f"Who is {brand_name} for?",
        f"What types of events does {brand_name} organize?",
        f"How the {brand_name} experience works",
        f"Where {brand_name} operates",
        f"Pricing: pay per event, no subscription",
        f"Key takeaways",
    ]


def _extract_key_facts(dossier: ResearchDossier) -> list[str]:
    """Pull concrete, citable facts from the research dossier."""
    facts = []
    curated = dossier.curated_context

    if curated:
        facts.extend([
            curated["what_it_is"],
            f"Target audience: {curated['target_audience']}",
            f"Cities: {', '.join(curated['cities'])}",
            curated["events_per_month"],
            f"Group size: {curated['event_group_size']}",
            f"Pricing: {curated['pricing_model']}",
            f"Booking: {curated['booking_method']}",
        ])
        for theme in curated.get("event_themes", []):
            facts.append(f"Event theme: {theme}")
    else:
        # Fallback to scraped data
        bd = dossier.brand_data
        if bd.get("description"):
            facts.append(bd["description"])
        for feat in bd.get("features", [])[:5]:
            facts.append(feat)

    return facts


class StrategistAgent:
    """Agent 2: Semantic Strategist.

    Analyzes the ResearchDossier and produces a ContentBlueprint —
    the architectural plan that the Writer agent follows.
    """

    def run(self, dossier: ResearchDossier, category_override: ContentCategory | None = None) -> ContentBlueprint:
        """Produce a content blueprint from research intelligence.

        Args:
            dossier: Research output from Agent 1
            category_override: Force a specific category (skip auto-detection)

        Returns:
            ContentBlueprint with slug, schema type, outline, facts, and angles
        """
        logger.info(f"[Strategist] Planning content for topic='{dossier.topic}'")

        # Determine category
        category = category_override or _determine_category(dossier.topic, dossier)
        schema_type = _SCHEMA_MAP[category]
        logger.info(f"[Strategist] Category={category.value}, Schema={schema_type}")

        # Generate slug
        brand_name = ""
        if dossier.curated_context:
            brand_name = dossier.curated_context.get("brand_name", "")
        if not brand_name:
            brand_name = dossier.brand_data.get("brand_name", "")
        slug = _generate_slug(dossier.topic, brand_name)
        logger.info(f"[Strategist] Slug='{slug}'")

        # Build section outline
        sections = _build_section_outline(category, dossier)

        # Extract key facts
        key_facts = _extract_key_facts(dossier)

        # Title direction
        title_directions = {
            ContentCategory.FAQ: f"{brand_name}: Frequently Asked Questions About Offline Events for 55+",
            ContentCategory.HOW_TO: f"How to Get Started with {brand_name} — Book Your First Offline Event",
            ContentCategory.COMPARISON: f"{brand_name} vs Other 55+ Social Platforms: An Honest Comparison",
            ContentCategory.INFORMATIONAL: f"What Is {brand_name}? The Offline Events Platform for People Above 55",
        }
        title_direction = title_directions.get(category, f"{brand_name}: {dossier.topic}")

        # Entity mapping
        related_entities = list(dossier.curated_context.get("cities", [])) if dossier.curated_context else []
        related_entities.extend(["people above 55", "offline events", "social meetups"])

        blueprint = ContentBlueprint(
            slug=slug,
            category=category,
            schema_type=schema_type,
            title_direction=title_direction,
            target_questions=dossier.people_also_ask[:8],
            section_outline=sections,
            key_facts_to_embed=key_facts,
            information_gain_angles=dossier.unique_angles,
            primary_entity=brand_name,
            related_entities=related_entities,
            dossier=dossier,
        )

        logger.info(
            f"[Strategist] Blueprint ready: {len(sections)} sections, "
            f"{len(key_facts)} facts, {len(dossier.unique_angles)} unique angles"
        )
        return blueprint
