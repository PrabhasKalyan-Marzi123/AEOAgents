"""Tests for the deduplication service — hash, embeddings, cosine similarity, full dedup check."""

import hashlib
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from app.services.deduplication import (
    _normalize_text,
    compute_hash,
    cosine_similarity,
)


class TestNormalizeText:
    def test_strips_html(self):
        result = _normalize_text("<p>Hello <b>world</b></p>")
        assert "<" not in result
        assert ">" not in result
        assert "hello" in result
        assert "world" in result

    def test_lowercases(self):
        assert _normalize_text("HELLO WORLD") == "hello world"

    def test_collapses_whitespace(self):
        result = _normalize_text("hello    world\n\t  foo")
        assert result == "hello world foo"

    def test_strips_nested_html(self):
        html = '<div class="x"><span style="color:red">Text</span></div>'
        result = _normalize_text(html)
        assert "div" not in result
        assert "span" not in result
        assert "text" in result

    def test_empty_string(self):
        assert _normalize_text("") == ""

    def test_only_html(self):
        result = _normalize_text("<br><hr><img src='x'>")
        assert result.strip() == ""

    def test_preserves_content_between_tags(self):
        html = "<h1>Title</h1><p>Body paragraph with <a href='#'>link</a> inside.</p>"
        result = _normalize_text(html)
        assert "title" in result
        assert "body paragraph with" in result
        assert "link" in result


class TestComputeHash:
    def test_deterministic(self):
        """Same input always gives same hash."""
        assert compute_hash("hello world") == compute_hash("hello world")

    def test_different_inputs_different_hashes(self):
        assert compute_hash("hello") != compute_hash("world")

    def test_normalization_applied(self):
        """HTML-wrapped text and plain text with same content should hash the same."""
        h1 = compute_hash("<p>Hello World</p>")
        h2 = compute_hash("hello   world")
        assert h1 == h2

    def test_hash_format(self):
        """Should return a 64-char hex string (SHA-256)."""
        h = compute_hash("test")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_case_insensitive_hashing(self):
        assert compute_hash("HELLO") == compute_hash("hello")

    def test_whitespace_insensitive(self):
        assert compute_hash("a  b  c") == compute_hash("a b c")


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_zero_vector_returns_zero(self):
        """Division by zero should return 0.0, not NaN."""
        a = [0.0, 0.0, 0.0]
        b = [1.0, 2.0, 3.0]
        assert cosine_similarity(a, b) == 0.0

    def test_both_zero_vectors(self):
        a = [0.0, 0.0]
        b = [0.0, 0.0]
        assert cosine_similarity(a, b) == 0.0

    def test_high_dimensional_similarity(self):
        """Simulate real embedding vectors (384-dim for MiniLM)."""
        rng = np.random.default_rng(42)
        a = rng.normal(size=384).tolist()
        b = [x + rng.normal(scale=0.01) for x in a]  # very similar
        sim = cosine_similarity(a, b)
        assert sim > 0.99  # nearly identical

    def test_symmetry(self):
        a = [1.0, 2.0, 3.0]
        b = [4.0, 5.0, 6.0]
        assert cosine_similarity(a, b) == pytest.approx(cosine_similarity(b, a))

    def test_scale_invariance(self):
        """Cosine similarity should be the same regardless of vector magnitude."""
        a = [1.0, 2.0, 3.0]
        b = [4.0, 5.0, 6.0]
        a_scaled = [x * 100 for x in a]
        b_scaled = [x * 0.01 for x in b]
        assert cosine_similarity(a, b) == pytest.approx(
            cosine_similarity(a_scaled, b_scaled), abs=1e-6
        )


class TestCheckDuplicate:
    """Tests for the full check_duplicate async function."""

    @pytest.mark.asyncio
    async def test_no_duplicate_when_contentful_empty(self):
        """When Contentful returns no matches, content is not a duplicate."""
        with patch("app.services.deduplication.contentful_client") as mock_cf:
            mock_cf.get_entries.return_value = []
            from app.services.deduplication import check_duplicate

            result = await check_duplicate("<p>Brand new content</p>", "new topic")
            assert result["is_duplicate"] is False
            assert result["match_type"] is None

    @pytest.mark.asyncio
    async def test_exact_hash_match_detected(self):
        """When Contentful returns an entry with matching hash, detect as exact dup."""
        with patch("app.services.deduplication.contentful_client") as mock_cf:
            # First call (hash check) returns a match
            mock_cf.get_entries.side_effect = [
                [{"id": "existing-123"}],  # hash match
            ]
            from app.services.deduplication import check_duplicate

            result = await check_duplicate("<p>Duplicate text</p>", "topic")
            assert result["is_duplicate"] is True
            assert result["match_type"] == "exact"
            assert result["similarity_score"] == 1.0
            assert result["matched_entry_id"] == "existing-123"

    @pytest.mark.asyncio
    async def test_contentful_error_gracefully_handled(self):
        """If Contentful throws, dedup should not crash."""
        with patch("app.services.deduplication.contentful_client") as mock_cf:
            mock_cf.get_entries.side_effect = Exception("Contentful down")
            from app.services.deduplication import check_duplicate

            result = await check_duplicate("<p>Some text</p>", "topic")
            # Should not raise; returns not-duplicate
            assert result["is_duplicate"] is False

    @pytest.mark.asyncio
    async def test_semantic_duplicate_detected(self):
        """When semantic similarity exceeds threshold, detect as semantic dup."""
        with patch("app.services.deduplication.contentful_client") as mock_cf, \
             patch("app.services.deduplication.compute_embedding") as mock_embed:
            # First call (hash check): no match
            # Second call (topic entries): return one entry
            mock_cf.get_entries.side_effect = [
                [],  # no hash match
                [{"id": "sem-123", "fields": {"contentHtml": "<p>Very similar content</p>"}}],
            ]
            # Return identical embeddings to guarantee similarity = 1.0
            mock_embed.return_value = [1.0] * 384

            from app.services.deduplication import check_duplicate

            result = await check_duplicate("<p>Very similar content</p>", "topic")
            assert result["is_duplicate"] is True
            assert result["match_type"] == "semantic"
            assert result["similarity_score"] >= 0.85

    @pytest.mark.asyncio
    async def test_below_threshold_not_duplicate(self):
        """When similarity is below threshold, content is not a duplicate."""
        with patch("app.services.deduplication.contentful_client") as mock_cf, \
             patch("app.services.deduplication.compute_embedding") as mock_embed:
            mock_cf.get_entries.side_effect = [
                [],  # no hash match
                [{"id": "other-123", "fields": {"contentHtml": "<p>Different content</p>"}}],
            ]
            # Return orthogonal embeddings for low similarity
            embed_a = [1.0] + [0.0] * 383
            embed_b = [0.0, 1.0] + [0.0] * 382
            mock_embed.side_effect = [embed_a, embed_b]

            from app.services.deduplication import check_duplicate

            result = await check_duplicate("<p>Completely different</p>", "topic")
            assert result["is_duplicate"] is False

    @pytest.mark.asyncio
    async def test_entries_with_empty_html_skipped(self):
        """Entries with empty contentHtml should be skipped during semantic check."""
        with patch("app.services.deduplication.contentful_client") as mock_cf:
            mock_cf.get_entries.side_effect = [
                [],  # no hash match
                [
                    {"id": "empty-1", "fields": {"contentHtml": ""}},
                    {"id": "empty-2", "fields": {"contentHtml": None}},
                    {"id": "empty-3", "fields": {}},
                ],
            ]
            from app.services.deduplication import check_duplicate

            result = await check_duplicate("<p>Some content</p>", "topic")
            assert result["is_duplicate"] is False
