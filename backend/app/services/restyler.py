"""Gemini-powered HTML restyler — adds clean, minimal brand-matched inline styling.

Takes a complete HTML page and uses Gemini to add tasteful inline styles
that match the brand's visual identity. Keeps the design simple and clean —
brand colors only where they matter (navbar, headings, accents), white space
everywhere else.
"""

from __future__ import annotations

import logging
import re

from google import genai

from app.config import settings

logger = logging.getLogger(__name__)


async def restyle_html(full_html: str, brand_data: dict) -> str:
    """Send the full HTML to Gemini for clean, brand-matched inline restyling.

    Args:
        full_html: Complete HTML page (with JSON-LD, meta tags, Bootstrap).
        brand_data: Scraped brand info (brand_name, brand_colors, logo_url, etc.).

    Returns:
        Restyled HTML with inline styles. Falls back to original on error.
    """
    brand_name = brand_data.get("brand_name", "")
    brand_colors = brand_data.get("brand_colors", [])
    logo_url = brand_data.get("logo_url", "")
    brand_url = brand_data.get("brand_url", "")
    description = brand_data.get("description", "")

    colors_info = ""
    if brand_colors:
        colors_info = f"Brand color palette (use sparingly): {', '.join(brand_colors[:4])}"
    else:
        colors_info = "No brand colors extracted — pick a single professional accent color that fits the brand."

    prompt = f"""You are a minimalist web designer. Restyle the given HTML page to look CLEAN, SIMPLE, and PROFESSIONAL — like a well-designed blog on a top SaaS website.

BRAND:
- Name: {brand_name}
- URL: {brand_url}
- About: {description[:300]}
- {colors_info}

DESIGN PHILOSOPHY — LESS IS MORE:
- White/light gray background (#fff or #f8f9fa) for the main content area
- Brand primary color ONLY on: navbar background, footer background, h2 bottom-borders, and a few accent elements (badges, buttons)
- Body text: dark gray (#1a1a1a or #2d3436), NOT black
- Generous white space — padding and margins should feel airy
- Clean sans-serif typography (system fonts)
- Cards: white background, subtle border (#e5e7eb), light shadow (0 1px 3px rgba(0,0,0,0.08))
- NO heavy gradients on the hero — use a SOLID brand color or very subtle gradient
- Accordion items: clean borders, brand color only on the active/expanded button
- Tables: light gray header (#f1f3f5), NOT heavy dark headers
- Tags/badges: light tinted background (brand color at 10% opacity) with brand-colored text
- Overall vibe: Apple/Stripe-level cleanliness — spacious, readable, elegant

ADD inline style="" attributes to elements in <body> for all visual styling.
REPLACE the existing <style> block with a clean, minimal one that:
- Sets base typography and colors
- Styles the navbar, hero, footer with the brand color
- Keeps everything else light and minimal
- Uses responsive rules only where needed

ABSOLUTELY DO NOT CHANGE:
- Any <script type="application/ld+json"> blocks — preserve EXACTLY
- Any <meta> tags — preserve EXACTLY
- Any <link> tags in <head> — preserve EXACTLY
- HTML structure (do NOT add/remove elements, do NOT change classes or IDs)
- Text content (do NOT rewrite any words)
- Image src URLs

Return ONLY the complete HTML. No markdown fences, no explanation.
"""

    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"{prompt}\n\n---HTML TO RESTYLE---\n\n{full_html}",
            config=genai.types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=32000,
            ),
        )

        restyled = response.text.strip()

        # Strip markdown code fences if Gemini wraps them
        if restyled.startswith("```"):
            restyled = re.sub(r"^```(?:html)?\n?", "", restyled)
            restyled = re.sub(r"\n?```$", "", restyled)

        # Validate: must still contain JSON-LD and basic HTML structure
        if (
            "application/ld+json" not in restyled
            or "<html" not in restyled
            or "</html>" not in restyled
        ):
            logger.warning("Restyled HTML missing critical elements, falling back to original")
            return full_html

        # Validate: JSON-LD blocks preserved (count should match)
        original_ld_count = full_html.count("application/ld+json")
        restyled_ld_count = restyled.count("application/ld+json")
        if restyled_ld_count < original_ld_count:
            logger.warning(
                f"Restyled HTML lost JSON-LD blocks ({original_ld_count} → {restyled_ld_count}), "
                "falling back to original"
            )
            return full_html

        logger.info("HTML restyled successfully with clean brand-matched styling")
        return restyled

    except Exception as e:
        logger.error(f"Gemini restyling failed: {e}")
        return full_html
