"""Content API endpoints — generate, list, update, publish via WordPress."""

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, HTMLResponse

from app.schemas.content import GenerateRequest, ContentUpdate
from app.services.publisher import generate_and_store, publish_page, generate_sitemap, generate_robots
from app.wordpress_client import wordpress_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/content", tags=["Content"])


@router.post("/generate")
async def generate_content_endpoint(request: GenerateRequest):
    """Generate AEO-optimized content with real-time data from a brand website.

    Scrapes the brand URL for real data, generates HTML content with JSON-LD
    structured data using Gemini AI, deduplicates, and saves to WordPress.
    """
    try:
        result = await generate_and_store(request)
        return result
    except Exception as e:
        logger.exception("Content generation failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
async def list_content(
    status: str | None = None,
    search: str | None = None,
    per_page: int = 20,
    page: int = 1,
):
    """List content pages from WordPress with optional filters."""
    if not wordpress_client.is_configured:
        return {"entries": [], "total": 0, "warning": "WordPress not configured"}

    query: dict = {"per_page": per_page, "page": page, "orderby": "date", "order": "desc"}
    if status:
        query["status"] = status
    if search:
        query["search"] = search

    try:
        pages = wordpress_client.get_pages(query)
        return {"entries": pages, "total": len(pages)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch from WordPress: {e}")


@router.get("/{page_id}")
async def get_content(page_id: int):
    """Get a single content page by WordPress ID."""
    try:
        page = wordpress_client.get_page(page_id)
        return page
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Page not found: {e}")


@router.get("/{page_id}/html", response_class=HTMLResponse)
async def get_content_html(page_id: int):
    """Serve the full HTML page directly (for preview / hosting)."""
    try:
        page = wordpress_client.get_page(page_id)
        return HTMLResponse(content=page["content"])
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Page not found: {e}")


@router.patch("/{page_id}")
async def update_content(page_id: int, update: ContentUpdate):
    """Update a content page (status, content, tags, etc.)."""
    fields: dict = {}
    if update.status is not None:
        # Map internal statuses to WP statuses
        wp_status = "publish" if update.status == "published" else "draft"
        fields["status"] = wp_status
    if update.content_html is not None:
        fields["content"] = update.content_html
    if update.jsonld_data is not None:
        fields["jsonld_data"] = update.jsonld_data
    if update.tags is not None:
        fields["tags"] = update.tags
    if update.meta_description is not None:
        fields["meta_description"] = update.meta_description

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        result = wordpress_client.update_page(page_id, fields)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update: {e}")


@router.post("/{page_id}/publish")
async def publish_content(page_id: int):
    """Publish a content page to make it live on WordPress."""
    try:
        result = await publish_page(page_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to publish: {e}")


@router.get("/site/sitemap.xml", response_class=PlainTextResponse)
async def get_sitemap():
    """Generate sitemap.xml from all published content."""
    sitemap = await generate_sitemap()
    return PlainTextResponse(content=sitemap, media_type="application/xml")


@router.get("/site/robots.txt", response_class=PlainTextResponse)
async def get_robots():
    """Generate robots.txt allowing AI crawlers."""
    robots = await generate_robots()
    return PlainTextResponse(content=robots, media_type="text/plain")
