"""Publisher service — orchestrates content generation, dedup, JSON-LD, HTML building, and WordPress storage.

This is the main entry point that connects all services:
1. generate_content() — scrapes brand site + Gemini AI generates content
2. check_duplicate() — dedup via hash + sentence-transformer similarity
3. generate_jsonld() — builds category-specific JSON-LD structured data
4. build_full_page() — assembles complete HTML with JSON-LD + meta tags
5. Saves to WordPress as a draft page (full HTML hosted directly by WP)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.wordpress_client import wordpress_client
from app.schemas.content import (
    GenerateRequest,
    GeneratedContent,
    GenerateResponse,
)
from app.services.deduplication import check_duplicate, compute_hash
from app.services.generation import generate_content
from app.services.html_builder import build_full_page, build_sitemap, build_robots_txt
from app.services.jsonld import generate_jsonld
from app.services.tagging import normalize_tags

logger = logging.getLogger(__name__)


async def generate_and_store(request: GenerateRequest) -> dict:
    """Full pipeline: generate content -> dedup -> build JSON-LD + HTML -> save to WordPress.

    Args:
        request: GenerateRequest with topic, category, brand_url, num_variations

    Returns:
        {
            "variation_group_id": str,
            "saved": [{"page_id": int, "title": str, "slug": str, "status": str, "link": str}],
            "duplicates_skipped": int,
            "total_generated": int,
        }
    """
    # Step 1: Generate content variations with real-time brand data
    logger.info(f"Generating {request.num_variations} variations for topic='{request.topic}', brand='{request.brand_url}'")
    gen_response: GenerateResponse = await generate_content(request)

    saved_entries = []
    duplicates_skipped = 0

    for content in gen_response.variations:
        # Step 2: Normalize tags
        content.tags = normalize_tags(content.tags)

        # Step 3: Check for duplicates
        dedup_result = await check_duplicate(content.content_html, content.topic)
        if dedup_result["is_duplicate"]:
            logger.info(
                f"Skipping duplicate: '{content.title}' "
                f"(match_type={dedup_result['match_type']}, "
                f"score={dedup_result['similarity_score']:.2f})"
            )
            duplicates_skipped += 1
            continue

        # Step 4: Build JSON-LD structured data
        jsonld = generate_jsonld(
            category=content.category,
            html=content.content_html,
            title=content.title,
            slug=content.slug,
            specific_data=content.jsonld_data,
            meta_description=content.meta_description,
        )

        # Step 5: Build complete HTML page
        full_html = build_full_page(content, jsonld)

        # Step 6: Compute hash for future dedup
        text_hash = compute_hash(content.content_html)

        # Step 7: Save to WordPress as a page
        fields = {
            "title": content.title,
            "slug": content.slug,
            "content": full_html,
            "status": "draft",
            # Extra metadata stored in WP custom fields
            "category": content.category.value,
            "topic": content.topic,
            "tags": json.dumps(content.tags),
            "meta_description": content.meta_description,
            "jsonld_data": json.dumps(jsonld),
            "text_hash": text_hash,
            "variation_group_id": gen_response.variation_group_id,
            "brand_url": content.brand_url,
        }

        try:
            result = wordpress_client.create_page(fields)
            saved_entries.append({
                "page_id": result["id"],
                "title": content.title,
                "slug": result["slug"],
                "category": content.category.value,
                "status": result["status"],
                "link": result["link"],
            })
            logger.info(f"Saved to WordPress: page_id={result['id']}, title='{content.title}'")
        except Exception as e:
            logger.error(f"Failed to save to WordPress: {e}")
            saved_entries.append({
                "page_id": None,
                "title": content.title,
                "slug": content.slug,
                "category": content.category.value,
                "status": "generated_locally",
                "full_html": full_html,
                "jsonld": jsonld,
                "content_html": content.content_html,
            })

    return {
        "variation_group_id": gen_response.variation_group_id,
        "topic": gen_response.topic,
        "category": gen_response.category.value,
        "brand_url": gen_response.brand_url,
        "saved": saved_entries,
        "duplicates_skipped": duplicates_skipped,
        "total_generated": len(gen_response.variations),
    }


async def publish_page(page_id: int) -> dict:
    """Publish a draft page on WordPress, making it publicly accessible.

    Args:
        page_id: The WordPress page ID to publish.

    Returns:
        {"page_id": int, "status": "publish", "link": str}
    """
    result = wordpress_client.publish_page(page_id)
    return {"page_id": page_id, "status": "publish", "link": result["link"]}


async def generate_sitemap() -> str:
    """Generate sitemap.xml from all published pages in WordPress."""
    try:
        published = wordpress_client.get_pages({"status": "publish", "per_page": 100})
        entries = [
            {
                "slug": p["slug"],
                "updated_at": p.get("modified", datetime.now(timezone.utc).strftime("%Y-%m-%d"))[:10],
                "category": p.get("meta", {}).get("category", "informational"),
            }
            for p in published
        ]
    except Exception:
        entries = []

    return build_sitemap(entries)


async def generate_robots() -> str:
    """Generate robots.txt allowing all AI crawlers."""
    return build_robots_txt()
