"""Tests for the publisher orchestration service — full pipeline tests with mocked dependencies."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.content import ContentCategory, GenerateRequest, GeneratedContent, GenerateResponse
from app.services.publisher import generate_and_store, publish_entry, generate_sitemap, generate_robots


def _make_gen_response(num_variations=2):
    """Helper to create a mock GenerateResponse."""
    variations = []
    for i in range(num_variations):
        variations.append(GeneratedContent(
            title=f"Title {i+1}",
            slug=f"title-{i+1}",
            category=ContentCategory.FAQ,
            content_html=f"<h1>Content {i+1}</h1><h2>Q?</h2><p>A.</p>",
            jsonld_data={"mentions": ["Brand"]},
            meta_description=f"Description {i+1}",
            tags=["tag-1", "Tag 2!", "TAG-1"],
            topic="test topic",
            brand_url="https://example.com",
        ))
    return GenerateResponse(
        variation_group_id="vg-test-123",
        topic="test topic",
        category=ContentCategory.FAQ,
        brand_url="https://example.com",
        variations=variations,
    )


class TestGenerateAndStore:
    @pytest.mark.asyncio
    async def test_full_pipeline_saves_to_contentful(self):
        """All non-duplicate variations should be saved to Contentful."""
        gen_resp = _make_gen_response(2)

        with patch("app.services.publisher.generate_content", new_callable=AsyncMock, return_value=gen_resp), \
             patch("app.services.publisher.check_duplicate", new_callable=AsyncMock) as mock_dedup, \
             patch("app.services.publisher.contentful_client") as mock_cf:
            mock_dedup.return_value = {"is_duplicate": False, "match_type": None, "similarity_score": None, "matched_entry_id": None}
            mock_cf.create_entry.return_value = {"id": "entry-abc", "fields": {}}

            request = GenerateRequest(
                topic="test", category=ContentCategory.FAQ,
                brand_url="https://example.com", num_variations=2,
            )
            result = await generate_and_store(request)

            assert result["variation_group_id"] == "vg-test-123"
            assert len(result["saved"]) == 2
            assert result["duplicates_skipped"] == 0
            assert result["total_generated"] == 2
            assert mock_cf.create_entry.call_count == 2

    @pytest.mark.asyncio
    async def test_duplicates_skipped(self):
        """Duplicate variations should be skipped and counted."""
        gen_resp = _make_gen_response(3)

        with patch("app.services.publisher.generate_content", new_callable=AsyncMock, return_value=gen_resp), \
             patch("app.services.publisher.check_duplicate", new_callable=AsyncMock) as mock_dedup, \
             patch("app.services.publisher.contentful_client") as mock_cf:
            # First non-dup, second dup, third non-dup
            mock_dedup.side_effect = [
                {"is_duplicate": False, "match_type": None, "similarity_score": None, "matched_entry_id": None},
                {"is_duplicate": True, "match_type": "semantic", "similarity_score": 0.92, "matched_entry_id": "dup-1"},
                {"is_duplicate": False, "match_type": None, "similarity_score": None, "matched_entry_id": None},
            ]
            mock_cf.create_entry.return_value = {"id": "entry-xyz", "fields": {}}

            request = GenerateRequest(
                topic="t", category=ContentCategory.FAQ,
                brand_url="u", num_variations=3,
            )
            result = await generate_and_store(request)

            assert result["duplicates_skipped"] == 1
            assert len(result["saved"]) == 2
            assert mock_cf.create_entry.call_count == 2

    @pytest.mark.asyncio
    async def test_contentful_failure_returns_local(self):
        """If Contentful save fails, content should still be returned as local."""
        gen_resp = _make_gen_response(1)

        with patch("app.services.publisher.generate_content", new_callable=AsyncMock, return_value=gen_resp), \
             patch("app.services.publisher.check_duplicate", new_callable=AsyncMock) as mock_dedup, \
             patch("app.services.publisher.contentful_client") as mock_cf:
            mock_dedup.return_value = {"is_duplicate": False, "match_type": None, "similarity_score": None, "matched_entry_id": None}
            mock_cf.create_entry.side_effect = Exception("Contentful connection refused")

            request = GenerateRequest(
                topic="t", category=ContentCategory.FAQ,
                brand_url="u", num_variations=1,
            )
            result = await generate_and_store(request)

            assert len(result["saved"]) == 1
            assert result["saved"][0]["entry_id"] is None
            assert result["saved"][0]["status"] == "generated_locally"
            assert "full_html" in result["saved"][0]
            assert "jsonld" in result["saved"][0]

    @pytest.mark.asyncio
    async def test_tags_normalized_during_pipeline(self):
        """Tags should be normalized (lowercased, deduped, limited) during the pipeline."""
        gen_resp = _make_gen_response(1)
        # Tags in fixture: ["tag-1", "Tag 2!", "TAG-1"]

        with patch("app.services.publisher.generate_content", new_callable=AsyncMock, return_value=gen_resp), \
             patch("app.services.publisher.check_duplicate", new_callable=AsyncMock) as mock_dedup, \
             patch("app.services.publisher.contentful_client") as mock_cf:
            mock_dedup.return_value = {"is_duplicate": False, "match_type": None, "similarity_score": None, "matched_entry_id": None}
            mock_cf.create_entry.return_value = {"id": "e-1", "fields": {}}

            request = GenerateRequest(
                topic="t", category=ContentCategory.FAQ,
                brand_url="u", num_variations=1,
            )
            await generate_and_store(request)

            # Verify the tags were normalized in the Contentful fields
            call_args = mock_cf.create_entry.call_args
            fields = call_args[0][1]  # second positional arg
            tags = fields["tags"]["en-US"]
            # After normalization: "tag-1", "tag-2", "TAG-1" -> "tag-1" deduped
            assert all(t == t.lower() for t in tags)
            assert len(tags) == len(set(tags))  # no duplicates

    @pytest.mark.asyncio
    async def test_contentful_fields_locale_keyed(self):
        """All fields saved to Contentful should be locale-keyed with en-US."""
        gen_resp = _make_gen_response(1)

        with patch("app.services.publisher.generate_content", new_callable=AsyncMock, return_value=gen_resp), \
             patch("app.services.publisher.check_duplicate", new_callable=AsyncMock) as mock_dedup, \
             patch("app.services.publisher.contentful_client") as mock_cf:
            mock_dedup.return_value = {"is_duplicate": False, "match_type": None, "similarity_score": None, "matched_entry_id": None}
            mock_cf.create_entry.return_value = {"id": "e-1", "fields": {}}

            request = GenerateRequest(
                topic="t", category=ContentCategory.FAQ,
                brand_url="u", num_variations=1,
            )
            await generate_and_store(request)

            fields = mock_cf.create_entry.call_args[0][1]
            for field_name, value in fields.items():
                assert "en-US" in value, f"Field '{field_name}' missing en-US locale key"

    @pytest.mark.asyncio
    async def test_all_duplicates_results_in_empty_saved(self):
        """If all variations are duplicates, saved should be empty."""
        gen_resp = _make_gen_response(2)

        with patch("app.services.publisher.generate_content", new_callable=AsyncMock, return_value=gen_resp), \
             patch("app.services.publisher.check_duplicate", new_callable=AsyncMock) as mock_dedup, \
             patch("app.services.publisher.contentful_client") as mock_cf:
            mock_dedup.return_value = {"is_duplicate": True, "match_type": "exact", "similarity_score": 1.0, "matched_entry_id": "dup"}

            request = GenerateRequest(
                topic="t", category=ContentCategory.FAQ,
                brand_url="u", num_variations=2,
            )
            result = await generate_and_store(request)

            assert len(result["saved"]) == 0
            assert result["duplicates_skipped"] == 2
            assert mock_cf.create_entry.call_count == 0


class TestPublishEntry:
    @pytest.mark.asyncio
    async def test_publishes_and_updates_status(self):
        with patch("app.services.publisher.contentful_client") as mock_cf:
            mock_cf.publish_entry.return_value = {"id": "e-1", "status": "published"}
            mock_cf.update_entry.return_value = {"id": "e-1", "fields": {}}

            result = await publish_entry("e-1")

            assert result["entry_id"] == "e-1"
            assert result["status"] == "published"
            mock_cf.publish_entry.assert_called_once_with("e-1")
            mock_cf.update_entry.assert_called_once_with("e-1", {"status": {"en-US": "published"}})


class TestGenerateSitemap:
    @pytest.mark.asyncio
    async def test_sitemap_from_published_entries(self):
        with patch("app.services.publisher.contentful_client") as mock_cf:
            mock_cf.get_entries.return_value = [
                {"fields": {"slug": "post-1", "category": "faq"}},
                {"fields": {"slug": "post-2", "category": "informational"}},
            ]
            sitemap = await generate_sitemap()
            assert "post-1" in sitemap
            assert "post-2" in sitemap
            assert '<?xml version="1.0"' in sitemap

    @pytest.mark.asyncio
    async def test_sitemap_on_contentful_error(self):
        """Should return empty sitemap (just homepage) on error."""
        with patch("app.services.publisher.contentful_client") as mock_cf:
            mock_cf.get_entries.side_effect = Exception("Connection refused")
            sitemap = await generate_sitemap()
            assert '<?xml version="1.0"' in sitemap
            # Should still have homepage
            assert "<priority>1.0</priority>" in sitemap


class TestGenerateRobots:
    @pytest.mark.asyncio
    async def test_returns_robots_txt(self):
        robots = await generate_robots()
        assert "User-agent: *" in robots
        assert "GPTBot" in robots
