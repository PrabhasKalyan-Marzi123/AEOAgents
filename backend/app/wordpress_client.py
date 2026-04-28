"""WordPress.com REST API client for storing and serving HTML pages.

Uses WordPress.com OAuth2 for authentication.
Pages are stored as WordPress pages with full HTML in the content field,
making them directly hostable from WordPress.com.

API base: https://public-api.wordpress.com/wp/v2/sites/{site}/
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

WP_COM_API_BASE = "https://public-api.wordpress.com/wp/v2/sites"


class WordPressClient:
    """Wrapper around the WordPress.com REST API (v2)."""

    def __init__(self):
        self._base_url: str | None = None

    @property
    def is_configured(self) -> bool:
        """Check if WordPress.com credentials are present."""
        return bool(settings.wordpress_site and settings.wordpress_access_token)

    @property
    def base_url(self) -> str:
        if self._base_url is None:
            if not settings.wordpress_site:
                raise RuntimeError("WORDPRESS_SITE is not configured — set it in .env")
            self._base_url = f"{WP_COM_API_BASE}/{settings.wordpress_site}"
        return self._base_url

    def _headers(self) -> dict:
        if not settings.wordpress_access_token:
            raise RuntimeError("WORDPRESS_ACCESS_TOKEN is not configured — run the OAuth flow first")
        return {
            "Authorization": f"Bearer {settings.wordpress_access_token}",
            "Content-Type": "application/json",
        }

    # ── Health / connectivity ──

    def check_connection(self) -> bool:
        """Verify WordPress.com API is reachable and token works."""
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                f"{WP_COM_API_BASE}/{settings.wordpress_site}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return True

    # ── Create ──

    def create_page(self, fields: dict) -> dict:
        """Create a WordPress page with full HTML content.

        Args:
            fields: dict with keys like title, slug, content (full HTML),
                    status ('draft'/'publish'), and optional meta fields.

        Returns:
            {"id": int, "slug": str, "link": str, "status": str}
        """
        payload = {
            "title": fields.get("title", ""),
            "slug": fields.get("slug", ""),
            "content": fields.get("content", ""),
            "status": fields.get("status", "draft"),
        }

        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{self.base_url}/pages",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        return {
            "id": data["id"],
            "slug": data["slug"],
            "link": data["link"],
            "status": data["status"],
        }

    # ── Read ──

    def get_page(self, page_id: int) -> dict:
        """Fetch a single page by ID."""
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                f"{self.base_url}/pages/{page_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()

        return self._normalize_page(data)

    def get_pages(self, query: dict | None = None) -> list[dict]:
        """Fetch pages with optional query filters."""
        params = {"per_page": 20, "orderby": "date", "order": "desc"}
        if query:
            params.update(query)

        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{self.base_url}/pages",
                headers=self._headers(),
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

        return [self._normalize_page(p) for p in data]

    # ── Update ──

    def update_page(self, page_id: int, fields: dict) -> dict:
        """Update fields on an existing page."""
        payload = {}
        for key in ("title", "slug", "content", "status"):
            if key in fields:
                payload[key] = fields[key]

        with httpx.Client(timeout=15) as client:
            resp = client.post(
                f"{self.base_url}/pages/{page_id}",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        return {
            "id": data["id"],
            "slug": data["slug"],
            "link": data["link"],
            "status": data["status"],
        }

    # ── Publish ──

    def publish_page(self, page_id: int) -> dict:
        """Publish a draft page, making it publicly accessible."""
        return self.update_page(page_id, {"status": "publish"})

    # ── Delete ──

    def delete_page(self, page_id: int, force: bool = False) -> dict:
        """Trash (or permanently delete) a page."""
        with httpx.Client(timeout=10) as client:
            resp = client.delete(
                f"{self.base_url}/pages/{page_id}",
                headers=self._headers(),
                params={"force": force},
            )
            resp.raise_for_status()
            data = resp.json()

        return {"id": data["id"], "status": data.get("status", "trash")}

    # ── Helpers ──

    @staticmethod
    def _normalize_page(data: dict) -> dict:
        """Normalize WP REST API page response into a flat dict."""
        return {
            "id": data["id"],
            "title": data.get("title", {}).get("rendered", ""),
            "slug": data.get("slug", ""),
            "content": data.get("content", {}).get("rendered", ""),
            "status": data.get("status", ""),
            "link": data.get("link", ""),
            "date": data.get("date", ""),
            "modified": data.get("modified", ""),
        }


wordpress_client = WordPressClient()
