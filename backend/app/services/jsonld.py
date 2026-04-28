"""JSON-LD structured data generator for AEO content categories.

Generates schema.org compliant JSON-LD for:
- FAQPage (FAQ/Q&A content)
- HowTo (step-by-step guides)
- Review + ItemList (comparisons/reviews)
- Article / BlogPosting (informational articles)
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from app.config import settings
from app.schemas.content import ContentCategory


def _author_name() -> str:
    return settings.default_author or settings.organization_name or settings.site_name


def _publisher_block() -> dict:
    return {
        "@type": "Organization",
        "name": settings.organization_name or settings.site_name,
        "url": settings.site_url,
    }


def _build_about_entities(mentions: list[str]) -> list[dict]:
    """Build about entities from mentions, handling URLs properly."""
    entities = []
    for m in mentions:
        if re.match(r"https?://", m):
            # URL mention — attach as sameAs on the domain name
            entities.append({"@type": "Thing", "name": m.split("//")[-1].split("/")[0], "sameAs": m})
        else:
            entities.append({"@type": "Thing", "name": m})
    return entities


def _extract_faq_pairs(html: str) -> list[dict]:
    """Extract question-answer pairs from FAQ HTML content."""
    soup = BeautifulSoup(html, "html.parser")
    pairs = []
    for h2 in soup.find_all("h2"):
        question = h2.get_text(strip=True)
        # Collect all text after the h2 until the next h2
        answer_parts = []
        for sibling in h2.find_next_siblings():
            if sibling.name == "h2":
                break
            text = sibling.get_text(strip=True)
            if text:
                answer_parts.append(text)
        if question and answer_parts:
            pairs.append({"question": question, "answer": " ".join(answer_parts)})
    return pairs


def _extract_steps(html: str) -> list[dict]:
    """Extract how-to steps from HTML content."""
    soup = BeautifulSoup(html, "html.parser")
    steps = []
    # Try ordered list first
    ol = soup.find("ol")
    if ol:
        for i, li in enumerate(ol.find_all("li", recursive=False), 1):
            h3 = li.find("h3")
            name = h3.get_text(strip=True) if h3 else f"Step {i}"
            p = li.find("p")
            text = p.get_text(strip=True) if p else li.get_text(strip=True)
            steps.append({"name": name, "text": text, "position": i})
    # Fallback: look for h3 tags as step headings
    if not steps:
        for i, h3 in enumerate(soup.find_all("h3"), 1):
            name = h3.get_text(strip=True)
            text_parts = []
            for sibling in h3.find_next_siblings():
                if sibling.name == "h3":
                    break
                t = sibling.get_text(strip=True)
                if t:
                    text_parts.append(t)
            steps.append({"name": name, "text": " ".join(text_parts), "position": i})
    return steps


def _extract_tools(html: str) -> list[str]:
    """Extract tools/requirements from the 'What You'll Need' section."""
    soup = BeautifulSoup(html, "html.parser")
    tools = []
    # Look for a heading containing "need" or "requirements"
    for heading in soup.find_all(["h2", "h3"]):
        if re.search(r"need|require|prerequisite|tool", heading.get_text(), re.IGNORECASE):
            ul = heading.find_next("ul")
            if ul:
                for li in ul.find_all("li"):
                    tools.append(li.get_text(strip=True))
            break
    return tools


def generate_faq_jsonld(
    html: str,
    title: str,
    url: str,
    specific_data: dict,
    meta_description: str = "",
) -> dict:
    """Generate FAQPage JSON-LD schema from FAQ HTML content."""
    faq_pairs = _extract_faq_pairs(html)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    jsonld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "name": title,
        "description": meta_description,
        "url": url,
        "author": {
            "@type": "Person",
            "name": _author_name(),
        },
        "publisher": _publisher_block(),
        "datePublished": now,
        "dateModified": now,
        "mainEntity": [
            {
                "@type": "Question",
                "name": pair["question"],
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": pair["answer"],
                },
            }
            for pair in faq_pairs
        ],
    }

    # Inject mentions as about entities
    if specific_data.get("mentions"):
        jsonld["about"] = _build_about_entities(specific_data["mentions"])

    return jsonld


def generate_howto_jsonld(
    html: str,
    title: str,
    url: str,
    specific_data: dict,
    meta_description: str = "",
) -> dict:
    """Generate HowTo JSON-LD schema from how-to HTML content."""
    steps = _extract_steps(html)
    tools = _extract_tools(html)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    jsonld = {
        "@context": "https://schema.org",
        "@type": "HowTo",
        "name": title,
        "url": url,
        "author": {
            "@type": "Person",
            "name": _author_name(),
        },
        "publisher": _publisher_block(),
        "datePublished": now,
        "dateModified": now,
        "step": [
            {
                "@type": "HowToStep",
                "position": step["position"],
                "name": step["name"],
                "text": step["text"],
            }
            for step in steps
        ],
    }

    if tools:
        jsonld["tool"] = [{"@type": "HowToTool", "name": t} for t in tools]

    if specific_data.get("key_facts"):
        jsonld["description"] = ". ".join(specific_data["key_facts"][:3]) + "."
    elif meta_description:
        jsonld["description"] = meta_description

    # Add estimated time if present in specific data
    if specific_data.get("estimated_time"):
        jsonld["totalTime"] = specific_data["estimated_time"]

    return jsonld


def _is_valid_price(value) -> bool:
    """Check if a value looks like an actual price (contains a digit)."""
    return bool(re.search(r"\d", str(value)))


def generate_comparison_jsonld(
    html: str,
    title: str,
    url: str,
    specific_data: dict,
    meta_description: str = "",
) -> dict:
    """Generate Review + ItemList JSON-LD schema from comparison HTML content."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    jsonld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "name": title,
        "headline": title,
        "description": meta_description,
        "url": url,
        "author": {
            "@type": "Person",
            "name": _author_name(),
        },
        "publisher": _publisher_block(),
        "datePublished": now,
        "dateModified": now,
    }

    # Build ItemList from mentioned products/services — use Thing (not Product) as mentions may not be products
    if specific_data.get("mentions"):
        items = []
        for i, mention in enumerate(specific_data["mentions"], 1):
            item = {
                "@type": "ListItem",
                "position": i,
                "item": {
                    "@type": "Thing",
                    "name": mention,
                },
            }
            # Add rating if available
            ratings = specific_data.get("ratings") or {}
            if ratings.get("score"):
                item["item"]["aggregateRating"] = {
                    "@type": "AggregateRating",
                    "ratingValue": ratings["score"],
                    "bestRating": 5,
                    "ratingCount": ratings.get("count", 1),
                }
            items.append(item)

        jsonld["mainEntity"] = {
            "@type": "ItemList",
            "itemListElement": items,
        }

    # Add pricing info — only include entries with actual numeric prices
    pricing = specific_data.get("pricing")
    if isinstance(pricing, dict):
        offers = [
            {"@type": "Offer", "name": plan, "price": str(price), "priceCurrency": "USD"}
            for plan, price in pricing.items()
            if _is_valid_price(price)
        ]
        if offers:
            jsonld["mentions"] = offers

    return jsonld


def generate_article_jsonld(
    html: str,
    title: str,
    url: str,
    specific_data: dict,
    meta_description: str = "",
) -> dict:
    """Generate Article/BlogPosting JSON-LD schema from informational content."""
    jsonld = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": title,
        "name": title,
        "url": url,
        "description": meta_description,
        "author": {
            "@type": "Person",
            "name": _author_name(),
        },
        "publisher": _publisher_block(),
        "datePublished": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "dateModified": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }

    # Add about entities from mentions
    if specific_data.get("mentions"):
        jsonld["about"] = _build_about_entities(specific_data["mentions"])

    # Add key facts as article body summary
    if specific_data.get("key_facts"):
        jsonld["articleBody"] = ". ".join(specific_data["key_facts"]) + "."

    # Add features as keywords
    if specific_data.get("features"):
        jsonld["keywords"] = ", ".join(specific_data["features"][:10])

    return jsonld


# Map category to its JSON-LD generator
_GENERATORS = {
    ContentCategory.FAQ: generate_faq_jsonld,
    ContentCategory.HOW_TO: generate_howto_jsonld,
    ContentCategory.COMPARISON: generate_comparison_jsonld,
    ContentCategory.INFORMATIONAL: generate_article_jsonld,
}


def generate_jsonld(
    category: ContentCategory,
    html: str,
    title: str,
    slug: str,
    specific_data: dict,
    meta_description: str = "",
) -> dict:
    """Generate the appropriate JSON-LD structured data based on content category.

    Args:
        category: Content category (faq, how-to, comparison, informational)
        html: The generated HTML content body
        title: Content title/headline
        slug: URL slug for the content
        specific_data: Real data points to inject (names, numbers, features, pricing)
        meta_description: Meta description for the page

    Returns:
        Complete JSON-LD object ready to embed as <script type="application/ld+json">
    """
    url = f"{settings.site_url}/{slug}"
    generator = _GENERATORS[category]
    return generator(html, title, url, specific_data, meta_description)
