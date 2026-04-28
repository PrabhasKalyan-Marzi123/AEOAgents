from __future__ import annotations
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ContentCategory(str, Enum):
    FAQ = "faq"
    HOW_TO = "how-to"
    COMPARISON = "comparison"
    INFORMATIONAL = "informational"


class GenerateRequest(BaseModel):
    """Request to generate AEO-optimized content."""

    topic: str = Field(..., description="The topic to generate content about, e.g. 'best SEO tools for small businesses'")
    category: ContentCategory = Field(..., description="Content category determines HTML structure and JSON-LD schema")
    brand_url: str = Field(..., description="Brand website URL to scrape real data from (names, features, pricing, etc.)")
    context: str = Field(default="", description="Additional context or specific angle for the content")
    num_variations: int = Field(default=3, ge=1, le=5, description="Number of content variations to generate")


class GeneratedContent(BaseModel):
    """A single generated content piece."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    slug: str
    category: ContentCategory
    content_html: str
    jsonld_data: dict
    meta_description: str
    tags: list[str]
    topic: str
    brand_url: str
    brand_data: dict = Field(default_factory=dict, exclude=True)
    status: str = "draft"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GenerateResponse(BaseModel):
    """Response containing all generated variations."""

    variation_group_id: str
    topic: str
    category: ContentCategory
    brand_url: str
    variations: list[GeneratedContent]


class ContentUpdate(BaseModel):
    """Request to update a content entry."""

    status: Literal["draft", "approved", "rejected", "published"] | None = None
    content_html: str | None = None
    jsonld_data: dict | None = None
    tags: list[str] | None = None
    meta_description: str | None = None


class PublishRequest(BaseModel):
    """Request to publish content to WordPress."""

    page_id: int
