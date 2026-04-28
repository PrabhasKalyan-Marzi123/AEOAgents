"""Tests for Pydantic schema validation — medium to hard edge cases."""

import pytest
from pydantic import ValidationError

from app.schemas.content import (
    ContentCategory,
    ContentUpdate,
    GenerateRequest,
    GeneratedContent,
    GenerateResponse,
    PublishRequest,
)


class TestContentCategory:
    def test_valid_categories(self):
        assert ContentCategory.FAQ.value == "faq"
        assert ContentCategory.HOW_TO.value == "how-to"
        assert ContentCategory.COMPARISON.value == "comparison"
        assert ContentCategory.INFORMATIONAL.value == "informational"

    def test_category_from_value(self):
        assert ContentCategory("faq") == ContentCategory.FAQ
        assert ContentCategory("how-to") == ContentCategory.HOW_TO

    def test_invalid_category_raises(self):
        with pytest.raises(ValueError):
            ContentCategory("invalid")


class TestGenerateRequest:
    def test_valid_request(self):
        req = GenerateRequest(
            topic="test topic",
            category=ContentCategory.FAQ,
            brand_url="https://example.com",
        )
        assert req.topic == "test topic"
        assert req.num_variations == 3  # default

    def test_num_variations_bounds(self):
        """num_variations must be between 1 and 5."""
        with pytest.raises(ValidationError):
            GenerateRequest(
                topic="t", category="faq", brand_url="u", num_variations=0
            )
        with pytest.raises(ValidationError):
            GenerateRequest(
                topic="t", category="faq", brand_url="u", num_variations=6
            )

    def test_num_variations_edge_valid(self):
        req1 = GenerateRequest(topic="t", category="faq", brand_url="u", num_variations=1)
        req5 = GenerateRequest(topic="t", category="faq", brand_url="u", num_variations=5)
        assert req1.num_variations == 1
        assert req5.num_variations == 5

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            GenerateRequest(topic="t")  # missing category and brand_url

    def test_context_defaults_empty(self):
        req = GenerateRequest(topic="t", category="faq", brand_url="u")
        assert req.context == ""

    def test_category_as_string(self):
        """Category can be passed as string value."""
        req = GenerateRequest(topic="t", category="how-to", brand_url="u")
        assert req.category == ContentCategory.HOW_TO


class TestGeneratedContent:
    def test_auto_id_generation(self):
        """Each instance should get a unique UUID."""
        c1 = GeneratedContent(
            title="T", slug="t", category="faq", content_html="<p>x</p>",
            jsonld_data={}, meta_description="d", tags=[], topic="t", brand_url="u",
        )
        c2 = GeneratedContent(
            title="T", slug="t", category="faq", content_html="<p>x</p>",
            jsonld_data={}, meta_description="d", tags=[], topic="t", brand_url="u",
        )
        assert c1.id != c2.id

    def test_default_status_is_draft(self):
        c = GeneratedContent(
            title="T", slug="t", category="faq", content_html="<p>x</p>",
            jsonld_data={}, meta_description="d", tags=[], topic="t", brand_url="u",
        )
        assert c.status == "draft"

    def test_created_at_auto_set(self):
        c = GeneratedContent(
            title="T", slug="t", category="faq", content_html="<p>x</p>",
            jsonld_data={}, meta_description="d", tags=[], topic="t", brand_url="u",
        )
        assert c.created_at is not None


class TestContentUpdate:
    def test_all_none_is_valid(self):
        """Model allows all None — endpoint handles the 'no fields' error."""
        update = ContentUpdate()
        assert update.status is None
        assert update.content_html is None

    def test_status_literal_validation(self):
        """Only specific status values are allowed."""
        update = ContentUpdate(status="approved")
        assert update.status == "approved"

        with pytest.raises(ValidationError):
            ContentUpdate(status="invalid_status")

    def test_partial_update(self):
        update = ContentUpdate(status="approved", tags=["new-tag"])
        assert update.status == "approved"
        assert update.tags == ["new-tag"]
        assert update.content_html is None

    def test_all_valid_statuses(self):
        for status in ["draft", "approved", "rejected", "published"]:
            update = ContentUpdate(status=status)
            assert update.status == status


class TestGenerateResponse:
    def test_response_structure(self):
        content = GeneratedContent(
            title="T", slug="t", category="faq", content_html="<p>x</p>",
            jsonld_data={}, meta_description="d", tags=[], topic="t", brand_url="u",
        )
        resp = GenerateResponse(
            variation_group_id="vg-123",
            topic="topic",
            category=ContentCategory.FAQ,
            brand_url="https://example.com",
            variations=[content],
        )
        assert len(resp.variations) == 1
        assert resp.variation_group_id == "vg-123"

    def test_empty_variations_allowed(self):
        resp = GenerateResponse(
            variation_group_id="vg-123",
            topic="t",
            category=ContentCategory.FAQ,
            brand_url="u",
            variations=[],
        )
        assert resp.variations == []
