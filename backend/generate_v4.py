"""Generate v4 Marzi content — all 4 categories with accurate brand context."""

import asyncio
import sys
import os

# Ensure the backend package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.schemas.content import ContentCategory, GenerateRequest
from app.services.generation import generate_content
from app.services.html_builder import build_full_page
from app.services.jsonld import generate_jsonld


CATEGORIES = [
    {
        "category": ContentCategory.FAQ,
        "topic": "Marzi offline social events for people above 55 in Bangalore and Mumbai",
        "filename": "marzi_faq_v4.html",
    },
    {
        "category": ContentCategory.HOW_TO,
        "topic": "How to get started with Marzi — book your first offline event for 55+",
        "filename": "marzi_howto_v4.html",
    },
    {
        "category": ContentCategory.COMPARISON,
        "topic": "Marzi vs other social platforms for people above 55 — offline meetups comparison",
        "filename": "marzi_comparison_v4.html",
    },
    {
        "category": ContentCategory.INFORMATIONAL,
        "topic": "What is Marzi — the offline events platform for people above 55",
        "filename": "marzi_info_v4.html",
    },
]


async def main():
    for item in CATEGORIES:
        cat = item["category"]
        print(f"\n{'='*60}")
        print(f"Generating: {cat.value} — {item['topic']}")
        print(f"{'='*60}")

        request = GenerateRequest(
            topic=item["topic"],
            category=cat,
            brand_url="https://marzi.life",
            num_variations=1,  # 1 variation per category to save time/tokens
        )

        try:
            response = await generate_content(request)
            content = response.variations[0]

            # Generate JSON-LD
            jsonld = generate_jsonld(
                category=cat,
                html=content.content_html,
                title=content.title,
                slug=content.slug,
                specific_data=content.jsonld_data,
                meta_description=content.meta_description,
            )

            # Build full HTML page
            full_html = build_full_page(content, jsonld)

            # Save to backend directory
            filepath = os.path.join(os.path.dirname(__file__), item["filename"])
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(full_html)

            print(f"  Title: {content.title}")
            print(f"  Tags: {content.tags}")
            print(f"  Saved: {filepath}")

        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*60}")
    print("Done! All v4 files generated.")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
