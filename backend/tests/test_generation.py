"""Tests for content generation service — slugify, prompt building, scraping, and Gemini integration."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.content import ContentCategory, GenerateRequest
from app.services.generation import _slugify, _build_prompt, generate_content, scrape_brand_data


class TestSlugify:
    def test_basic_slugification(self):
        assert _slugify("Hello World") == "hello-world"

    def test_special_characters_removed(self):
        assert _slugify("What's the Best SEO Tool?") == "whats-the-best-seo-tool"

    def test_multiple_spaces_collapsed(self):
        assert _slugify("too   many   spaces") == "too-many-spaces"

    def test_max_length_80(self):
        long_title = "a" * 100
        result = _slugify(long_title)
        assert len(result) <= 80

    def test_trailing_hyphens_stripped(self):
        result = _slugify("hello world ---")
        assert not result.endswith("-")

    def test_leading_hyphens_stripped(self):
        result = _slugify("--- hello world")
        assert not result.startswith("-")

    def test_consecutive_hyphens_collapsed(self):
        result = _slugify("hello---world")
        assert "--" not in result

    def test_underscores_become_hyphens(self):
        result = _slugify("hello_world_test")
        assert result == "hello-world-test"

    def test_empty_string(self):
        result = _slugify("")
        assert result == ""

    def test_unicode_handling(self):
        result = _slugify("Café Résumé Tips")
        assert "caf" in result

    def test_numbers_preserved(self):
        result = _slugify("Top 10 SEO Tools in 2024")
        assert "10" in result
        assert "2024" in result

    def test_truncation_at_word_boundary(self):
        """Slug should truncate at 80 chars without breaking mid-word (stripped trailing -)."""
        title = "this is a very long title " * 5  # well over 80 chars
        result = _slugify(title)
        assert len(result) <= 80
        assert not result.endswith("-")


class TestBuildPrompt:
    def test_contains_brand_data(self):
        request = GenerateRequest(
            topic="SEO tools", category=ContentCategory.FAQ,
            brand_url="https://example.com", num_variations=2,
        )
        brand_data = {
            "brand_name": "TestBrand",
            "brand_url": "https://example.com",
            "description": "A great brand",
            "features": ["Feature 1", "Feature 2"],
            "pricing_text": "$99/mo",
            "page_text": "Sample page text content",
        }
        prompt = _build_prompt(request, brand_data)
        assert "TestBrand" in prompt
        assert "https://example.com" in prompt
        assert "A great brand" in prompt
        assert "$99/mo" in prompt

    def test_faq_specific_instructions(self):
        request = GenerateRequest(
            topic="SEO", category=ContentCategory.FAQ,
            brand_url="https://example.com",
        )
        prompt = _build_prompt(request, {"brand_name": "", "brand_url": "", "description": "", "features": [], "pricing_text": "", "page_text": ""})
        assert "FAQ" in prompt
        assert "5-8" in prompt

    def test_howto_specific_instructions(self):
        request = GenerateRequest(
            topic="SEO", category=ContentCategory.HOW_TO,
            brand_url="https://example.com",
        )
        prompt = _build_prompt(request, {"brand_name": "", "brand_url": "", "description": "", "features": [], "pricing_text": "", "page_text": ""})
        assert "how-to" in prompt.lower() or "step" in prompt.lower()
        assert "What You'll Need" in prompt

    def test_comparison_specific_instructions(self):
        request = GenerateRequest(
            topic="SEO", category=ContentCategory.COMPARISON,
            brand_url="https://example.com",
        )
        prompt = _build_prompt(request, {"brand_name": "", "brand_url": "", "description": "", "features": [], "pricing_text": "", "page_text": ""})
        assert "comparison" in prompt.lower() or "review" in prompt.lower()

    def test_informational_specific_instructions(self):
        request = GenerateRequest(
            topic="SEO", category=ContentCategory.INFORMATIONAL,
            brand_url="https://example.com",
        )
        prompt = _build_prompt(request, {"brand_name": "", "brand_url": "", "description": "", "features": [], "pricing_text": "", "page_text": ""})
        assert "informational" in prompt.lower() or "article" in prompt.lower()

    def test_num_variations_in_prompt(self):
        request = GenerateRequest(
            topic="SEO", category=ContentCategory.FAQ,
            brand_url="https://example.com", num_variations=5,
        )
        prompt = _build_prompt(request, {"brand_name": "", "brand_url": "", "description": "", "features": [], "pricing_text": "", "page_text": ""})
        assert "5" in prompt

    def test_context_included(self):
        request = GenerateRequest(
            topic="SEO", category=ContentCategory.FAQ,
            brand_url="https://example.com", context="Focus on beginners",
        )
        prompt = _build_prompt(request, {"brand_name": "", "brand_url": "", "description": "", "features": [], "pricing_text": "", "page_text": ""})
        assert "Focus on beginners" in prompt

    def test_json_output_format_specified(self):
        request = GenerateRequest(
            topic="SEO", category=ContentCategory.FAQ,
            brand_url="https://example.com",
        )
        prompt = _build_prompt(request, {"brand_name": "", "brand_url": "", "description": "", "features": [], "pricing_text": "", "page_text": ""})
        assert "JSON" in prompt
        assert "variations" in prompt


class TestScrapeBrandData:
    @pytest.mark.asyncio
    async def test_extracts_brand_name_from_og(self):
        mock_html = """
        <html><head>
            <meta property="og:site_name" content="TestBrand">
            <meta name="description" content="Great description">
            <title>TestBrand - Home</title>
        </head><body>
            <h1>Welcome to TestBrand</h1>
            <p>We provide the best services for your needs.</p>
        </body></html>
        """
        with patch("app.services.generation.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.text = mock_html
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await scrape_brand_data("https://example.com")
            assert result["brand_name"] == "TestBrand"
            assert result["description"] == "Great description"

    @pytest.mark.asyncio
    async def test_fallback_to_title_tag(self):
        mock_html = """
        <html><head>
            <title>My Brand | Official Site</title>
        </head><body><p>Content here that is long enough to be captured by the scraper.</p></body></html>
        """
        with patch("app.services.generation.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.text = mock_html
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await scrape_brand_data("https://example.com")
            assert result["brand_name"] == "My Brand"

    @pytest.mark.asyncio
    async def test_extracts_existing_jsonld(self):
        mock_html = """
        <html><head>
            <script type="application/ld+json">{"@type": "Organization", "name": "Test"}</script>
        </head><body><p>Some body content for the scraper to find.</p></body></html>
        """
        with patch("app.services.generation.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.text = mock_html
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await scrape_brand_data("https://example.com")
            assert len(result["existing_jsonld"]) == 1
            assert result["existing_jsonld"][0]["@type"] == "Organization"

    @pytest.mark.asyncio
    async def test_extracts_features_from_headings(self):
        mock_html = """
        <html><body>
            <h2>Keyword Research Tool</h2>
            <h2>Backlink Analysis Feature</h2>
            <h3>Site Audit Dashboard</h3>
            <h2>X</h2>
        </body></html>
        """
        with patch("app.services.generation.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.text = mock_html
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await scrape_brand_data("https://example.com")
            # "X" is too short (len 1, needs > 5)
            assert "Keyword Research Tool" in result["features"]
            assert "Backlink Analysis Feature" in result["features"]
            assert "Site Audit Dashboard" in result["features"]
            # "X" should be filtered out (too short)
            assert "X" not in result["features"]

    @pytest.mark.asyncio
    async def test_page_text_truncated(self):
        mock_html = "<html><body>" + "<p>" + "x" * 100 + "</p>" * 100 + "</body></html>"
        with patch("app.services.generation.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.text = mock_html
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await scrape_brand_data("https://example.com")
            assert len(result["page_text"]) <= 3000


class TestGenerateContent:
    @pytest.mark.asyncio
    async def test_full_generation_pipeline(self):
        """Integration test: mock scrape + Gemini, verify response structure."""
        mock_brand = {
            "brand_name": "TestBrand",
            "brand_url": "https://example.com",
            "description": "Test description",
            "features": ["Feature A"],
            "pricing_text": "$10/mo",
            "page_text": "Page content",
            "logo_url": "",
            "existing_jsonld": [],
        }
        gemini_response_text = json.dumps({
            "variations": [
                {
                    "title": "Best SEO Tools FAQ",
                    "html": "<h1>FAQ</h1><h2>Q1?</h2><p>A1.</p>",
                    "meta_description": "Top SEO tools for businesses",
                    "tags": ["seo", "tools"],
                    "jsonld_specific_data": {"mentions": ["Tool1"]},
                },
                {
                    "title": "SEO Tools Guide",
                    "html": "<h1>Guide</h1><p>Content</p>",
                    "meta_description": "Complete SEO guide",
                    "tags": ["guide"],
                    "jsonld_specific_data": {},
                },
            ]
        })

        with patch("app.services.generation.scrape_brand_data", new_callable=AsyncMock, return_value=mock_brand), \
             patch("app.services.generation.genai") as mock_genai:
            mock_client = MagicMock()
            mock_genai.Client.return_value = mock_client
            mock_resp = MagicMock()
            mock_resp.text = gemini_response_text
            mock_client.models.generate_content.return_value = mock_resp

            request = GenerateRequest(
                topic="SEO tools", category=ContentCategory.FAQ,
                brand_url="https://example.com", num_variations=2,
            )
            response = await generate_content(request)

            assert response.topic == "SEO tools"
            assert response.category == ContentCategory.FAQ
            assert len(response.variations) == 2
            assert response.variations[0].title == "Best SEO Tools FAQ"
            assert response.variations[0].slug == "best-seo-tools-faq"
            assert response.variations[0].category == ContentCategory.FAQ

    @pytest.mark.asyncio
    async def test_handles_markdown_code_fence_response(self):
        """Gemini sometimes wraps JSON in markdown code fences."""
        mock_brand = {
            "brand_name": "B", "brand_url": "u", "description": "",
            "features": [], "pricing_text": "", "page_text": "",
            "logo_url": "", "existing_jsonld": [],
        }
        raw = "```json\n" + json.dumps({
            "variations": [{
                "title": "T", "html": "<p>x</p>", "meta_description": "d",
                "tags": [], "jsonld_specific_data": {},
            }]
        }) + "\n```"

        with patch("app.services.generation.scrape_brand_data", new_callable=AsyncMock, return_value=mock_brand), \
             patch("app.services.generation.genai") as mock_genai:
            mock_client = MagicMock()
            mock_genai.Client.return_value = mock_client
            mock_resp = MagicMock()
            mock_resp.text = raw
            mock_client.models.generate_content.return_value = mock_resp

            request = GenerateRequest(
                topic="t", category=ContentCategory.FAQ,
                brand_url="u", num_variations=1,
            )
            response = await generate_content(request)
            assert len(response.variations) == 1

    @pytest.mark.asyncio
    async def test_invalid_json_raises(self):
        """Invalid JSON from Gemini should raise."""
        mock_brand = {
            "brand_name": "B", "brand_url": "u", "description": "",
            "features": [], "pricing_text": "", "page_text": "",
            "logo_url": "", "existing_jsonld": [],
        }

        with patch("app.services.generation.scrape_brand_data", new_callable=AsyncMock, return_value=mock_brand), \
             patch("app.services.generation.genai") as mock_genai:
            mock_client = MagicMock()
            mock_genai.Client.return_value = mock_client
            mock_resp = MagicMock()
            mock_resp.text = "not valid json at all"
            mock_client.models.generate_content.return_value = mock_resp

            request = GenerateRequest(
                topic="t", category=ContentCategory.FAQ,
                brand_url="u", num_variations=1,
            )
            with pytest.raises(json.JSONDecodeError):
                await generate_content(request)
