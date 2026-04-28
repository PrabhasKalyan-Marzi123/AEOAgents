"""Tests for the tagging / tag normalization service."""

import pytest

from app.services.tagging import normalize_tags


class TestNormalizeTags:
    """Medium-hard tests for tag normalization edge cases."""

    def test_basic_normalization(self):
        result = normalize_tags(["SEO Tools", "Content Marketing"])
        assert result == ["seo-tools", "content-marketing"]

    def test_deduplication_case_insensitive(self):
        """Tags that differ only in case should deduplicate."""
        result = normalize_tags(["Best Tools", "best tools", "BEST TOOLS", "best-tools"])
        # After normalization all become "best-tools"
        assert result == ["best-tools"]

    def test_special_characters_stripped(self):
        """Non-word characters (except hyphens) should be removed."""
        result = normalize_tags(["C++ Programming!", "Node.js & React", "Price: $99"])
        # Regex [^\w\s-] removes special chars; \s+ replaced with hyphens
        assert all(
            c.isalnum() or c in ("-", "_") for tag in result for c in tag
        )

    def test_max_tags_limit(self):
        tags = [f"tag-{i}" for i in range(20)]
        result = normalize_tags(tags, max_tags=5)
        assert len(result) == 5

    def test_max_tags_custom_limit(self):
        tags = ["a", "b", "c", "d", "e", "f"]
        result = normalize_tags(tags, max_tags=3)
        assert len(result) == 3
        assert result == ["a", "b", "c"]

    def test_empty_tags_filtered(self):
        """Empty strings and whitespace-only tags should be skipped."""
        result = normalize_tags(["", "   ", "valid-tag", "  ", "another"])
        # Empty after strip+regex should not appear
        assert "valid-tag" in result
        assert "" not in result

    def test_whitespace_becomes_hyphen(self):
        result = normalize_tags(["multi word tag with spaces"])
        assert result == ["multi-word-tag-with-spaces"]

    def test_empty_input(self):
        assert normalize_tags([]) == []

    def test_single_tag(self):
        assert normalize_tags(["hello"]) == ["hello"]

    def test_mixed_unicode_and_ascii(self):
        """Unicode word characters should be preserved by \\w."""
        result = normalize_tags(["café", "naïve", "résumé"])
        assert len(result) == 3
        # \w includes unicode letters in Python 3
        assert "café" in result or "caf" in result

    def test_hyphenated_tags_preserved(self):
        """Hyphens in tags should survive normalization."""
        result = normalize_tags(["how-to-guide", "step-by-step"])
        assert result == ["how-to-guide", "step-by-step"]

    def test_underscores_preserved(self):
        result = normalize_tags(["machine_learning", "deep_learning"])
        assert result == ["machine_learning", "deep_learning"]

    def test_dedup_after_normalization(self):
        """Tags that become identical after normalization should deduplicate."""
        result = normalize_tags(["Hello World!", "hello world", "Hello--World"])
        # All normalize to "hello-world" or similar
        # "Hello World!" -> "hello world" -> "hello-world"
        # "hello world" -> "hello-world"
        # "Hello--World" -> "hello--world" -> regex strips nothing since -- is \w adjacent
        # Actually: re.sub(r"[^\w\s-]", "", "hello world!") = "hello world"
        # re.sub(r"\s+", "-", "hello world") = "hello-world"
        assert result[0] == "hello-world"
        assert len(result) <= 2  # at least first two should dedup

    def test_leading_trailing_whitespace(self):
        result = normalize_tags(["  padded tag  "])
        assert result == ["padded-tag"]

    def test_max_tags_zero(self):
        """Edge case: max_tags=0 should return empty."""
        result = normalize_tags(["a", "b", "c"], max_tags=0)
        assert result == []
