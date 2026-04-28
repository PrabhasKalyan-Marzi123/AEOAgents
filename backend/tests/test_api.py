"""API endpoint integration tests using FastAPI TestClient."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


class TestHealthEndpoint:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "aeo-agents"


class TestGenerateEndpoint:
    def test_generate_success(self, client):
        mock_result = {
            "variation_group_id": "vg-1",
            "topic": "SEO tools",
            "category": "faq",
            "brand_url": "https://example.com",
            "saved": [{"entry_id": "e-1", "title": "T", "slug": "t", "status": "draft"}],
            "duplicates_skipped": 0,
            "total_generated": 1,
        }
        with patch("app.api.content.generate_and_store", new_callable=AsyncMock, return_value=mock_result):
            response = client.post("/api/v1/content/generate", json={
                "topic": "SEO tools",
                "category": "faq",
                "brand_url": "https://example.com",
                "num_variations": 1,
            })
            assert response.status_code == 200
            data = response.json()
            assert data["variation_group_id"] == "vg-1"
            assert len(data["saved"]) == 1

    def test_generate_invalid_category(self, client):
        response = client.post("/api/v1/content/generate", json={
            "topic": "SEO",
            "category": "invalid",
            "brand_url": "https://example.com",
        })
        assert response.status_code == 422  # Pydantic validation error

    def test_generate_missing_required_fields(self, client):
        response = client.post("/api/v1/content/generate", json={
            "topic": "SEO",
        })
        assert response.status_code == 422

    def test_generate_num_variations_out_of_range(self, client):
        response = client.post("/api/v1/content/generate", json={
            "topic": "SEO",
            "category": "faq",
            "brand_url": "https://example.com",
            "num_variations": 10,
        })
        assert response.status_code == 422

    def test_generate_server_error(self, client):
        with patch("app.api.content.generate_and_store", new_callable=AsyncMock, side_effect=Exception("boom")):
            response = client.post("/api/v1/content/generate", json={
                "topic": "SEO",
                "category": "faq",
                "brand_url": "https://example.com",
            })
            assert response.status_code == 500


class TestListContentEndpoint:
    def test_list_content_success(self, client):
        mock_entries = [
            {"id": "e-1", "fields": {"title": "T1", "status": "draft"}},
            {"id": "e-2", "fields": {"title": "T2", "status": "published"}},
        ]
        with patch("app.api.content.contentful_client") as mock_cf:
            mock_cf.get_entries.return_value = mock_entries
            response = client.get("/api/v1/content/")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 2
            assert len(data["entries"]) == 2

    def test_list_with_filters(self, client):
        with patch("app.api.content.contentful_client") as mock_cf:
            mock_cf.get_entries.return_value = []
            response = client.get("/api/v1/content/?status=draft&category=faq&limit=5")
            assert response.status_code == 200
            # Verify query was built correctly
            call_args = mock_cf.get_entries.call_args
            query = call_args[0][1]
            assert query["fields.status"] == "draft"
            assert query["fields.category"] == "faq"
            assert query["limit"] == 5

    def test_list_contentful_error(self, client):
        with patch("app.api.content.contentful_client") as mock_cf:
            mock_cf.get_entries.side_effect = Exception("Contentful down")
            response = client.get("/api/v1/content/")
            assert response.status_code == 500
            assert "Contentful" in response.json()["detail"]


class TestGetContentEndpoint:
    def test_get_entry_success(self, client):
        mock_entry = {"id": "e-1", "fields": {"title": "Test", "slug": "test"}}
        with patch("app.api.content.contentful_client") as mock_cf:
            mock_cf.get_entry.return_value = mock_entry
            response = client.get("/api/v1/content/e-1")
            assert response.status_code == 200
            assert response.json()["id"] == "e-1"

    def test_get_entry_not_found(self, client):
        with patch("app.api.content.contentful_client") as mock_cf:
            mock_cf.get_entry.side_effect = Exception("Not found")
            response = client.get("/api/v1/content/nonexistent")
            assert response.status_code == 404


class TestUpdateContentEndpoint:
    def test_update_status(self, client):
        with patch("app.api.content.contentful_client") as mock_cf:
            mock_cf.update_entry.return_value = {"id": "e-1", "fields": {}}
            response = client.patch("/api/v1/content/e-1", json={"status": "approved"})
            assert response.status_code == 200
            call_args = mock_cf.update_entry.call_args
            assert call_args[0][1]["status"]["en-US"] == "approved"

    def test_update_multiple_fields(self, client):
        with patch("app.api.content.contentful_client") as mock_cf:
            mock_cf.update_entry.return_value = {"id": "e-1", "fields": {}}
            response = client.patch("/api/v1/content/e-1", json={
                "status": "approved",
                "tags": ["seo", "tools"],
                "meta_description": "New description",
            })
            assert response.status_code == 200
            fields = mock_cf.update_entry.call_args[0][1]
            assert "status" in fields
            assert "tags" in fields
            assert "metaDescription" in fields

    def test_update_no_fields_returns_400(self, client):
        response = client.patch("/api/v1/content/e-1", json={})
        assert response.status_code == 400
        assert "No fields" in response.json()["detail"]

    def test_update_invalid_status(self, client):
        response = client.patch("/api/v1/content/e-1", json={"status": "invalid"})
        assert response.status_code == 422

    def test_update_contentful_error(self, client):
        with patch("app.api.content.contentful_client") as mock_cf:
            mock_cf.update_entry.side_effect = Exception("Update failed")
            response = client.patch("/api/v1/content/e-1", json={"status": "draft"})
            assert response.status_code == 500


class TestPublishEndpoint:
    def test_publish_success(self, client):
        with patch("app.api.content.publish_entry", new_callable=AsyncMock) as mock_pub:
            mock_pub.return_value = {"entry_id": "e-1", "status": "published"}
            response = client.post("/api/v1/content/e-1/publish")
            assert response.status_code == 200
            assert response.json()["status"] == "published"

    def test_publish_failure(self, client):
        with patch("app.api.content.publish_entry", new_callable=AsyncMock, side_effect=Exception("Publish failed")):
            response = client.post("/api/v1/content/e-1/publish")
            assert response.status_code == 500


class TestSitemapEndpoint:
    def test_returns_xml(self, client):
        with patch("app.api.content.generate_sitemap", new_callable=AsyncMock) as mock_sm:
            mock_sm.return_value = '<?xml version="1.0"?><urlset></urlset>'
            response = client.get("/api/v1/content/site/sitemap.xml")
            assert response.status_code == 200
            assert "xml" in response.headers.get("content-type", "")


class TestRobotsEndpoint:
    def test_returns_plain_text(self, client):
        with patch("app.api.content.generate_robots", new_callable=AsyncMock) as mock_rb:
            mock_rb.return_value = "User-agent: *\nAllow: /"
            response = client.get("/api/v1/content/site/robots.txt")
            assert response.status_code == 200
            assert "text/plain" in response.headers.get("content-type", "")


class TestRouteOrdering:
    """Test that /site/sitemap.xml and /site/robots.txt don't conflict with /{entry_id}."""

    def test_sitemap_not_treated_as_entry_id(self, client):
        """The sitemap route should not be captured by the /{entry_id} route."""
        with patch("app.api.content.generate_sitemap", new_callable=AsyncMock) as mock_sm:
            mock_sm.return_value = '<?xml version="1.0"?><urlset></urlset>'
            response = client.get("/api/v1/content/site/sitemap.xml")
            # Should hit the sitemap endpoint, not the get_content endpoint
            assert response.status_code == 200
            assert "xml" in response.headers.get("content-type", "")

    def test_robots_not_treated_as_entry_id(self, client):
        with patch("app.api.content.generate_robots", new_callable=AsyncMock) as mock_rb:
            mock_rb.return_value = "User-agent: *\nAllow: /"
            response = client.get("/api/v1/content/site/robots.txt")
            assert response.status_code == 200
            assert "text/plain" in response.headers.get("content-type", "")
