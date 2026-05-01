"""Content generation service using Gemini AI with real-time data from brand websites."""

from __future__ import annotations

import json
import uuid
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from google import genai

from app.config import settings
from app.schemas.content import (
    ContentCategory,
    GenerateRequest,
    GeneratedContent,
    GenerateResponse,
)
from app.services.brand_context import get_brand_context


def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug[:80].strip("-")


def _resolve_url(base: str, url: str) -> str:
    """Resolve a potentially relative URL against the base."""
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        from urllib.parse import urlparse
        parsed = urlparse(base)
        return f"{parsed.scheme}://{parsed.netloc}{url}"
    if url.startswith("http"):
        return url
    return base.rstrip("/") + "/" + url


def _hex_to_hsl(hex_color: str) -> tuple[float, float, float]:
    """Convert hex color to HSL. Returns (h: 0-360, s: 0-1, l: 0-1)."""
    h_str = hex_color.lstrip("#")
    if len(h_str) == 3:
        h_str = "".join(c * 2 for c in h_str)
    r, g, b = int(h_str[:2], 16) / 255, int(h_str[2:4], 16) / 255, int(h_str[4:6], 16) / 255
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2
    if mx == mn:
        h = s = 0.0
    else:
        d = mx - mn
        s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
        if mx == r:
            h = (g - b) / d + (6 if g < b else 0)
        elif mx == g:
            h = (b - r) / d + 2
        else:
            h = (r - g) / d + 4
        h /= 6
    return h * 360, s, l


def _color_saturation(hex_color: str) -> float:
    """Return the saturation of a hex color (0-1)."""
    _, s, _ = _hex_to_hsl(hex_color)
    return s


def _is_chromatic(hex_color: str) -> bool:
    """Return True if the color has meaningful saturation (not gray/white/black)."""
    _, s, l = _hex_to_hsl(hex_color)
    return s > 0.3 and 0.15 < l < 0.85


def _filter_colors(colors: list[str]) -> list[str]:
    """Deduplicate colors, prioritize vivid chromatic colors, sorted by saturation."""
    seen = set()
    chromatic = []
    neutral = []
    for c in colors:
        lower = c.lower()
        if lower in seen:
            continue
        seen.add(lower)
        if len(lower.lstrip("#")) not in (3, 6):
            continue
        if _is_chromatic(lower):
            chromatic.append(c)
        else:
            neutral.append(c)
    # Sort chromatic colors by saturation (most vivid first)
    chromatic.sort(key=lambda c: _color_saturation(c.lower()), reverse=True)
    return chromatic + neutral


def _extract_colors_from_css_text(css_text: str) -> list[str]:
    """Extract meaningful hex colors from raw CSS text."""
    hex_re = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
    return hex_re.findall(css_text)


def _extract_colors_from_css(soup: BeautifulSoup) -> list[str]:
    """Extract hex colors from inline <style> blocks and style attributes."""
    colors = []

    # From <style> blocks
    for style_tag in soup.find_all("style"):
        if style_tag.string:
            colors.extend(_extract_colors_from_css_text(style_tag.string))

    # From inline style attributes (first 30 elements)
    for tag in soup.find_all(attrs={"style": True})[:30]:
        colors.extend(_extract_colors_from_css_text(tag["style"]))

    return _filter_colors(colors)[:10]


async def _fetch_external_css_colors(soup: BeautifulSoup, brand_url: str) -> list[str]:
    """Fetch external CSS files linked in the page and extract brand colors."""
    colors = []
    css_links = []
    for link in soup.find_all("link", rel="stylesheet"):
        href = link.get("href", "")
        if href and "fonts.googleapis" not in href and "cdn" not in href:
            css_links.append(_resolve_url(brand_url, href))

    if not css_links:
        return []

    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=10.0,
            headers={"User-Agent": "Mozilla/5.0 (compatible; AEOBot/1.0)"},
        ) as client:
            # Fetch only the first CSS file (main bundle)
            resp = await client.get(css_links[0])
            if resp.status_code == 200:
                css_text = resp.text[:50000]  # cap at 50KB
                raw_colors = _extract_colors_from_css_text(css_text)
                colors = _filter_colors(raw_colors)
    except Exception:
        pass

    return colors[:10]


async def scrape_brand_data(brand_url: str) -> dict:
    """Scrape real data from the brand website: name, description, features, pricing, logo, colors."""
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=15.0,
        headers={"User-Agent": "Mozilla/5.0 (compatible; AEOBot/1.0)"},
    ) as client:
        response = await client.get(brand_url)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Extract brand name
    brand_name = ""
    og_site = soup.find("meta", property="og:site_name")
    if og_site and og_site.get("content"):
        brand_name = og_site["content"]
    elif soup.title:
        brand_name = soup.title.get_text().split("|")[0].split("-")[0].strip()

    # Extract meta description
    description = ""
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        description = meta_desc["content"]
    og_desc = soup.find("meta", property="og:description")
    if not description and og_desc and og_desc.get("content"):
        description = og_desc["content"]

    # Extract main text content (paragraphs, headings, list items)
    text_blocks = []
    for tag in soup.find_all(["h1", "h2", "h3", "p", "li"]):
        text = tag.get_text(strip=True)
        if len(text) > 20:
            text_blocks.append(text)
    page_text = "\n".join(text_blocks[:50])  # first 50 meaningful blocks

    # Extract structured data already on the page
    existing_jsonld = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            existing_jsonld.append(json.loads(script.string))
        except (json.JSONDecodeError, TypeError):
            pass

    # Extract key features / product info from headings
    features = []
    for h in soup.find_all(["h2", "h3"]):
        h_text = h.get_text(strip=True)
        if 5 < len(h_text) < 100:
            features.append(h_text)

    # Extract pricing info if present
    pricing_text = ""
    pricing_section = soup.find(string=re.compile(r"pric", re.IGNORECASE))
    if pricing_section:
        parent = pricing_section.find_parent(["section", "div"])
        if parent:
            pricing_text = parent.get_text(separator=" ", strip=True)[:500]

    # ── Logo extraction (priority order) ──
    logo_url = ""
    # 1. Look for <img> with "logo" in src, alt, class, or id
    for img in soup.find_all("img"):
        attrs_text = " ".join([
            img.get("src", ""), img.get("alt", ""),
            " ".join(img.get("class", [])), img.get("id", ""),
        ]).lower()
        if "logo" in attrs_text:
            logo_url = _resolve_url(brand_url, img.get("src", ""))
            break

    # 2. Apple touch icon (usually a clean square logo)
    if not logo_url:
        apple_icon = soup.find("link", rel=lambda r: r and "apple-touch-icon" in r)
        if apple_icon and apple_icon.get("href"):
            logo_url = _resolve_url(brand_url, apple_icon["href"])

    # 3. Favicon
    if not logo_url:
        icon_link = soup.find("link", rel=lambda r: r and "icon" in r)
        if icon_link and icon_link.get("href"):
            logo_url = _resolve_url(brand_url, icon_link["href"])

    # 4. og:image as last resort
    if not logo_url:
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            logo_url = _resolve_url(brand_url, og_image["content"])

    # ── Favicon extraction ──
    favicon_url = ""
    fav_link = soup.find("link", rel=lambda r: r and "icon" in r and "apple" not in (r if isinstance(r, str) else " ".join(r)))
    if fav_link and fav_link.get("href"):
        favicon_url = _resolve_url(brand_url, fav_link["href"])
    if not favicon_url:
        favicon_url = brand_url.rstrip("/") + "/favicon.ico"

    # ── Brand colors extraction ──
    brand_colors = []

    # 1. <meta name="theme-color">
    theme_meta = soup.find("meta", attrs={"name": "theme-color"})
    if theme_meta and theme_meta.get("content"):
        brand_colors.append(theme_meta["content"])

    # 2. <meta name="msapplication-TileColor">
    tile_meta = soup.find("meta", attrs={"name": "msapplication-TileColor"})
    if tile_meta and tile_meta.get("content"):
        brand_colors.append(tile_meta["content"])

    # 3. Colors from inline CSS
    css_colors = _extract_colors_from_css(soup)
    brand_colors.extend(css_colors)

    # 4. If still no colors, fetch external CSS bundle
    if len(brand_colors) < 2:
        ext_colors = await _fetch_external_css_colors(soup, brand_url)
        brand_colors.extend(ext_colors)

    # Deduplicate
    seen = set()
    unique_colors = []
    for c in brand_colors:
        if c.lower() not in seen:
            seen.add(c.lower())
            unique_colors.append(c)
    brand_colors = unique_colors[:6]

    return {
        "brand_name": brand_name,
        "brand_url": brand_url,
        "description": description,
        "page_text": page_text[:3000],
        "features": features[:15],
        "pricing_text": pricing_text,
        "logo_url": logo_url,
        "favicon_url": favicon_url,
        "brand_colors": brand_colors,
        "existing_jsonld": existing_jsonld,
    }


def _build_prompt(request: GenerateRequest, brand_data: dict) -> str:
    """Build a category-specific prompt for Gemini with real brand data.

    If a curated brand context exists (from brand_context.py), it is injected
    alongside scraped data to ensure accuracy.  The curated context takes
    precedence over vague scraped taglines.
    """

    curated = get_brand_context(request.brand_url)

    if curated:
        # Use authoritative brand context — concrete facts override vague scrapes
        brand_context = f"""
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

SUPPLEMENTARY SCRAPED DATA (use only if it adds detail not covered above):
- Description from website: {brand_data['description']}
- Features/Sections from website: {json.dumps(brand_data['features'][:10])}
"""
    else:
        # Fallback: scraped data only (no curated context available)
        brand_context = f"""
REAL BRAND DATA (use this actual data — do NOT invent or hallucinate any facts):
- Brand Name: {brand_data['brand_name']}
- Website: {brand_data['brand_url']}
- Description: {brand_data['description']}
- Key Features/Sections: {json.dumps(brand_data['features'][:10])}
- Pricing Info: {brand_data['pricing_text'][:300] if brand_data['pricing_text'] else 'Not available on page'}
- Page Content Summary: {brand_data['page_text'][:1500]}
"""

    category_instructions = {
        ContentCategory.FAQ: """
Generate a FAQ page with 5-8 real, useful questions and detailed answers about "{topic}".
Use Bootstrap 5 classes for styling:
- Wrap the whole FAQ in <div class="accordion" id="faqAccordion">
- Each Q&A pair as a Bootstrap accordion item with <div class="accordion-item">
- Questions in <h2 class="accordion-header"> with <button class="accordion-button">
- Answers in <div class="accordion-collapse collapse"> with <div class="accordion-body">
- Make the first accordion item expanded by default (show class)
- Include real data points, numbers, and specifics from the brand data
- Answers should be 2-4 sentences each, genuinely helpful
""",
        ContentCategory.HOW_TO: """
Generate a how-to guide about "{topic}" with 5-8 clear steps.
Use Bootstrap 5 classes for styling:
- Introduction in <p class="lead"> with context about why this matters
- A "What You'll Need" section as <div class="card mb-4"> with <ul class="list-group list-group-flush">
- Steps as <div class="card mb-3"> elements, each with <div class="card-body"> containing <h3 class="card-title"> and <p class="card-text">
- Number each step with a <span class="badge rounded-pill bg-primary me-2">1</span> prefix
- Add estimated time in a <span class="badge bg-info"> if applicable
- Include specific tool names, settings, or values from the brand data
""",
        ContentCategory.COMPARISON: """
Generate a detailed comparison/review about "{topic}".
Use Bootstrap 5 classes for styling:
- Introduction explaining the comparison criteria in <p class="lead">
- Use <table class="table table-striped table-hover"> with <thead class="table-dark"> and <tbody> for feature comparison
- Include a "Pros & Cons" section using <div class="row"> with two <div class="col-md-6"> columns
- Pros in a card with <ul class="list-group list-group-flush"> using green check icons
- Cons in a card with <ul class="list-group list-group-flush"> using red x icons
- Add a rating/recommendation in an <div class="alert alert-success"> at the end
- Use real features, pricing, and data from the brand data — do NOT make up numbers
""",
        ContentCategory.INFORMATIONAL: """
Generate an in-depth informational article about "{topic}".
Use Bootstrap 5 classes for styling:
- 4-6 sections each with <h2> headings
- Content in <p> tags with real data, statistics, and specifics
- Use <div class="card mb-4"> for callout sections or important highlights
- Include <ul class="list-group list-group-flush"> for key points lists
- Add a "Key Takeaways" section at the end in a <div class="card border-primary"> with <ul>
- Use <blockquote class="blockquote"> for any key quotes or important statements
- Reference real features, capabilities, or data from the brand
""",
    }

    return f"""You are an expert content writer specializing in AEO (Answer Engine Optimization).
Your goal is to create content that AI engines (ChatGPT, Perplexity, Google AI Overviews) will crawl, understand, and surface in their answers.

{brand_context}

TASK: Generate {request.num_variations} unique content variations.
Topic: "{request.topic}"
Category: {request.category.value}
Additional Context: {request.context or 'None'}

{category_instructions[request.category].format(topic=request.topic)}

CRITICAL RULES:
1. Use ONLY real data from the brand information provided — never invent features, prices, or claims
2. Write in a helpful, authoritative, non-promotional tone
3. Each variation must be substantively different in structure and angle
4. Content must be factually accurate and up-to-date based on the provided data
5. Include specific numbers, names, and details from the real brand data
6. HTML must use Bootstrap 5 classes for ALL styling — no inline styles, no custom CSS class names
7. HTML must be clean, semantic, and ready to embed in a page (no <html>, <head>, <body> wrappers, no <h1> — the outer template adds the title)
8. Do NOT include any <h1> tag — the page template already renders the title as <h1>

Also generate for each variation:
- A compelling SEO title (60-70 chars)
- A meta description (150-160 chars)
- 3-5 relevant tags
- JSON-LD data object with all the specific data points (names, numbers, features, pricing) that should be injected as structured data

Return ONLY valid JSON in this exact format:
{{
  "variations": [
    {{
      "title": "SEO title here",
      "html": "<h1>...</h1><p>...</p>...",
      "meta_description": "Meta description here",
      "tags": ["tag1", "tag2", "tag3"],
      "jsonld_specific_data": {{
        "mentions": ["entity1", "entity2"],
        "features": ["feature1", "feature2"],
        "pricing": {{"plan": "amount"}},
        "ratings": {{"score": 4.5, "count": 100}},
        "key_facts": ["fact1", "fact2"]
      }}
    }}
  ]
}}
"""


async def generate_content(request: GenerateRequest) -> GenerateResponse:
    """Generate AEO-optimized content with real-time data from the brand website.

    1. Scrapes the brand URL for real data (names, features, pricing, etc.)
    2. Builds a category-specific prompt with the real data
    3. Calls Gemini to generate content variations
    4. Returns structured content with HTML + JSON-LD data
    """
    # Step 1: Scrape real data from the brand website
    brand_data = await scrape_brand_data(request.brand_url)

    # Step 2: Build the prompt
    prompt = _build_prompt(request, brand_data)

    # Step 3: Call Gemini API
    client = genai.Client(api_key=settings.gemini_api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=8000,
            response_mime_type="application/json",
        ),
    )

    # Step 4: Parse response
    raw_text = response.text.strip()
    # Handle markdown code fences if present
    if raw_text.startswith("```"):
        raw_text = re.sub(r"^```(?:json)?\n?", "", raw_text)
        raw_text = re.sub(r"\n?```$", "", raw_text)

    parsed = json.loads(raw_text)

    # Step 5: Build response objects
    variation_group_id = str(uuid.uuid4())
    variations = []

    for v in parsed["variations"]:
        content = GeneratedContent(
            title=v["title"],
            slug=_slugify(v["title"]),
            category=request.category,
            content_html=v["html"],
            jsonld_data=v.get("jsonld_specific_data", {}),
            meta_description=v["meta_description"],
            tags=v.get("tags", []),
            topic=request.topic,
            brand_url=request.brand_url,
            brand_data=brand_data,
        )
        variations.append(content)

    return GenerateResponse(
        variation_group_id=variation_group_id,
        topic=request.topic,
        category=request.category,
        brand_url=request.brand_url,
        variations=variations,
    )
