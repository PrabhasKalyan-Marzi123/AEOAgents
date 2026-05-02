"""Agent 3: The Structured Writer (marzi.life Voice).

Takes a ContentBlueprint and produces snippet-ready HTML content via Gemini 2.5 Flash.
Emphasis on:
- Authoritative, factual tone (no vague marketing)
- Information Gain: answers that competitors don't provide
- Snippet-ready structure: direct answers in the first sentence of each section
- Bootstrap 5 HTML with semantic markup
- JSON-LD-compatible data extraction

Output: WrittenContent ready for the Compiler agent.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from google import genai

from app.config import settings
from app.schemas.content import ContentCategory, GeneratedContent
from app.agents.strategist import ContentBlueprint

logger = logging.getLogger(__name__)


@dataclass
class WrittenContent:
    """Output from the Writer agent — ready for compilation."""

    title: str = ""
    slug: str = ""
    category: ContentCategory = ContentCategory.INFORMATIONAL
    content_html: str = ""
    meta_description: str = ""
    tags: list[str] = field(default_factory=list)
    jsonld_data: dict = field(default_factory=dict)
    topic: str = ""
    brand_url: str = ""
    brand_data: dict = field(default_factory=dict)

    def to_generated_content(self) -> GeneratedContent:
        """Convert to the existing GeneratedContent schema for compatibility."""
        return GeneratedContent(
            title=self.title,
            slug=self.slug,
            category=self.category,
            content_html=self.content_html,
            jsonld_data=self.jsonld_data,
            meta_description=self.meta_description,
            tags=self.tags,
            topic=self.topic,
            brand_url=self.brand_url,
            brand_data=self.brand_data,
        )


def _build_writer_prompt(blueprint: ContentBlueprint) -> str:
    """Build the Gemini prompt from the blueprint.

    This is the refactored version of the old _build_prompt() — now driven
    by the blueprint's structured intelligence rather than raw scraped data.
    """
    dossier = blueprint.dossier
    curated = dossier.curated_context if dossier else None

    # ── Brand authority block ──
    if curated:
        brand_block = f"""
AUTHORITATIVE BRAND DATA (use these facts exactly — they override any vague scraped text):
- Brand Name: {curated['brand_name']}
- Website: {curated['brand_url']}
- What it is: {curated['what_it_is']}
- Target Audience: {curated['target_audience']}
- Primary Value Proposition: {curated['primary_value']}
- Cities: {', '.join(curated['cities'])}
- Events per Month: {curated['events_per_month']}
- Event Group Size: {curated['event_group_size']}
- Event Themes: {json.dumps(curated['event_themes'])}
- Pricing Model: {curated['pricing_model']}
- How to Book: {curated['booking_method']}
- Key Differentiators: {json.dumps(curated['key_differentiators'])}
- What this brand is NOT: {json.dumps(curated['what_marzi_is_NOT'])}

CONTENT GUIDELINES (MUST follow these rules):
{chr(10).join('- ' + g for g in curated['content_guidelines'])}
"""
    else:
        bd = dossier.brand_data if dossier else {}
        brand_block = f"""
BRAND DATA (use this actual data — do NOT invent or hallucinate any facts):
- Brand Name: {bd.get('brand_name', 'Unknown')}
- Website: {bd.get('brand_url', '')}
- Description: {bd.get('description', '')}
- Key Features: {json.dumps(bd.get('features', [])[:10])}
- Page Content: {bd.get('page_text', '')[:1500]}
"""

    # ── Information Gain block ──
    info_gain_block = ""
    if blueprint.information_gain_angles:
        info_gain_block = f"""
INFORMATION GAIN — UNIQUE ANGLES (incorporate these into the content):
{chr(10).join('- ' + angle for angle in blueprint.information_gain_angles[:8])}

These are facts and angles that competing content does NOT cover.
Including them makes this content the most authoritative source on the topic.
"""

    # ── Competitor coverage block — what NOT to merely repeat ──
    competitor_block = ""
    if blueprint.competitor_topics_to_outdo:
        competitor_block = f"""
COMPETITORS ALREADY COVER THESE (do not just repeat — go deeper or skip):
{chr(10).join('- ' + t for t in blueprint.competitor_topics_to_outdo[:8])}

If you must touch any of these, add data/specificity competitors lack.
"""

    # ── PAA / target questions ──
    questions_block = ""
    if blueprint.target_questions:
        questions_block = f"""
PEOPLE ALSO ASK (address these questions naturally within the content):
{chr(10).join('- ' + q for q in blueprint.target_questions[:6])}
"""

    # ── Section outline ──
    outline_block = f"""
CONTENT STRUCTURE (follow this section outline):
{chr(10).join(f'{i+1}. {s}' for i, s in enumerate(blueprint.section_outline))}
"""

    # ── Key facts ──
    facts_block = f"""
KEY FACTS TO EMBED (use exact numbers and details):
{chr(10).join('- ' + f for f in blueprint.key_facts_to_embed[:15])}
"""

    # ── Category-specific HTML instructions ──
    category_html = {
        ContentCategory.FAQ: """
Generate a FAQ page with the questions from the outline above.
Use Bootstrap 5 classes:
- Wrap in <div class="accordion" id="faqAccordion">
- Each Q&A as a Bootstrap accordion item with <div class="accordion-item">
- Questions in <h2 class="accordion-header"> with <button class="accordion-button">
- Answers in <div class="accordion-collapse collapse"> with <div class="accordion-body">
- First item expanded by default (show class)
- Answers: 2-4 sentences, genuinely helpful, include concrete data
- SNIPPET RULE: Start each answer with a direct, complete sentence that can stand alone as an AI snippet
""",
        ContentCategory.HOW_TO: """
Generate a how-to guide following the outline above.
Use Bootstrap 5 classes:
- Introduction in <p class="lead">
- "What You'll Need" section as <div class="card mb-4"> with <ul class="list-group list-group-flush">
- Steps as <div class="card mb-3"> with <div class="card-body">, <h3 class="card-title">, <p class="card-text">
- Number steps with <span class="badge rounded-pill bg-primary me-2">1</span>
- Add time estimates in <span class="badge bg-info"> where applicable
- SNIPPET RULE: Each step must open with an actionable instruction sentence
""",
        ContentCategory.COMPARISON: """
Generate a detailed comparison following the outline above.
Use Bootstrap 5 classes:
- Introduction in <p class="lead">
- <table class="table table-striped table-hover"> with <thead class="table-dark"> for feature comparison
- Pros in a card with green check icons, Cons in a card with red x icons
- Rating/recommendation in <div class="alert alert-success">
- Use ONLY real, verified data — never make up competitor features or pricing
- SNIPPET RULE: The comparison table must contain complete, self-contained data in each cell
""",
        ContentCategory.INFORMATIONAL: """
Generate an in-depth article following the outline above.
Use Bootstrap 5 classes:
- 4-6 sections with <h2> headings
- <div class="card mb-4"> for callout sections
- <ul class="list-group list-group-flush"> for key points
- "Key Takeaways" at end in <div class="card border-primary"> with <ul>
- <blockquote class="blockquote"> for important statements
- SNIPPET RULE: Open every section with a direct answer sentence before elaborating
""",
    }

    return f"""You are an expert AEO (Answer Engine Optimization) content architect for {blueprint.primary_entity}.
Your content will be crawled by AI engines (ChatGPT, Perplexity, Google AI Overviews, Gemini).
The goal: make {blueprint.primary_entity} the #1 cited source in AI-generated answers for this topic.

{brand_block}

{info_gain_block}

{competitor_block}

{questions_block}

{outline_block}

{facts_block}

TASK: Generate 1 high-quality content piece.
Topic: "{blueprint.dossier.topic if blueprint.dossier else ''}"
Category: {blueprint.category.value}
Schema Type: {blueprint.schema_type}
Title Direction: "{blueprint.title_direction}"

{category_html.get(blueprint.category, '')}

CRITICAL AEO RULES:
1. Use ONLY real data from the brand information — never invent features, prices, or claims
2. Write in an authoritative, helpful, non-promotional tone
3. EVERY section must open with a direct-answer sentence (this is what AI engines extract as snippets)
4. Include specific numbers: 20+ events/month, 20-60 participants, Bangalore & Mumbai
5. HTML must use Bootstrap 5 classes — no inline styles, no custom CSS
6. No <html>, <head>, <body> wrappers. No <h1> tag (the outer template adds the title)
7. Naturally address PAA questions within the content flow
8. Establish {blueprint.primary_entity} as THE authority — cite concrete differentiators over vague claims

Also generate:
- A compelling SEO title (60-70 chars) that includes "{blueprint.primary_entity}"
- A meta description (150-160 chars)
- 5-8 relevant tags
- JSON-LD data object with specific data points (names, numbers, features) for structured data injection

Return ONLY valid JSON:
{{
  "title": "SEO title here",
  "html": "<div>...</div>",
  "meta_description": "Meta description here",
  "tags": ["tag1", "tag2"],
  "jsonld_specific_data": {{
    "mentions": ["entity1", "entity2"],
    "features": ["feature1", "feature2"],
    "pricing": {{}},
    "ratings": {{}},
    "key_facts": ["fact1", "fact2"]
  }}
}}
"""


class WriterAgent:
    """Agent 3: Structured Writer.

    Uses Gemini 2.5 Flash to produce snippet-ready HTML content
    guided by the ContentBlueprint from the Strategist.
    """

    async def run(self, blueprint: ContentBlueprint) -> WrittenContent:
        """Generate content from the blueprint.

        Args:
            blueprint: Strategic plan from Agent 2

        Returns:
            WrittenContent ready for compilation
        """
        logger.info(f"[Writer] Generating content for slug='{blueprint.slug}'")

        prompt = _build_writer_prompt(blueprint)
        client = genai.Client(api_key=settings.gemini_api_key)

        parsed: dict | None = None
        last_err: Exception | None = None
        for attempt in (1, 2):
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=12000,
                    response_mime_type="application/json",
                ),
            )
            raw_text = (response.text or "").strip()
            if raw_text.startswith("```"):
                raw_text = re.sub(r"^```(?:json)?\n?", "", raw_text)
                raw_text = re.sub(r"\n?```$", "", raw_text)

            try:
                parsed = json.loads(raw_text)
                break
            except json.JSONDecodeError as e:
                last_err = e
                logger.warning(
                    f"[Writer] Attempt {attempt} JSON parse failed ({e}); "
                    f"raw head: {raw_text[:200]!r}"
                )

        if parsed is None:
            raise RuntimeError(f"[Writer] Gemini returned invalid JSON twice: {last_err}")

        written = WrittenContent(
            title=parsed["title"],
            slug=blueprint.slug,
            category=blueprint.category,
            content_html=parsed["html"],
            meta_description=parsed["meta_description"],
            tags=parsed.get("tags", []),
            jsonld_data=parsed.get("jsonld_specific_data", {}),
            topic=blueprint.dossier.topic if blueprint.dossier else "",
            brand_url=blueprint.dossier.brand_url if blueprint.dossier else "",
            brand_data=blueprint.dossier.brand_data if blueprint.dossier else {},
        )

        logger.info(f"[Writer] Content generated: title='{written.title}', {len(written.tags)} tags")
        return written
