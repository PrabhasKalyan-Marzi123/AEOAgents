"""Tests for JSON-LD generation across all 4 content categories."""

from unittest.mock import patch

import pytest

from app.schemas.content import ContentCategory
from app.services.jsonld import (
    _extract_faq_pairs,
    _extract_steps,
    _extract_tools,
    generate_jsonld,
    generate_faq_jsonld,
    generate_howto_jsonld,
    generate_comparison_jsonld,
    generate_article_jsonld,
)


class TestExtractFaqPairs:
    def test_extracts_multiple_pairs(self, sample_faq_html):
        pairs = _extract_faq_pairs(sample_faq_html)
        assert len(pairs) == 3
        assert pairs[0]["question"] == "What is SEO?"
        assert "Search Engine Optimization" in pairs[0]["answer"]

    def test_multi_paragraph_answer_concatenated(self, sample_faq_html):
        """The 'How much' question has two <p> tags — both should be in the answer."""
        pairs = _extract_faq_pairs(sample_faq_html)
        cost_pair = next(p for p in pairs if "cost" in p["question"].lower())
        assert "$500-$5000" in cost_pair["answer"]
        assert "Enterprise" in cost_pair["answer"]

    def test_no_h2_returns_empty(self):
        html = "<p>Just a paragraph with no headings.</p>"
        assert _extract_faq_pairs(html) == []

    def test_h2_without_following_content(self):
        """h2 with no sibling text should not create a pair."""
        html = "<h2>Empty question</h2>"
        pairs = _extract_faq_pairs(html)
        assert len(pairs) == 0

    def test_nested_html_in_answers(self):
        html = """
        <h2>How to start?</h2>
        <p>First, <strong>install</strong> the <a href="#">package</a>.</p>
        <p>Then configure it.</p>
        """
        pairs = _extract_faq_pairs(html)
        assert len(pairs) == 1
        assert "install" in pairs[0]["answer"]
        assert "configure" in pairs[0]["answer"]


class TestExtractSteps:
    def test_from_ordered_list(self, sample_howto_html):
        steps = _extract_steps(sample_howto_html)
        assert len(steps) == 3
        assert steps[0]["name"] == "Create a Google Analytics Account"
        assert steps[0]["position"] == 1
        assert "analytics.google.com" in steps[0]["text"]

    def test_fallback_to_h3_tags(self, sample_howto_html_h3_fallback):
        steps = _extract_steps(sample_howto_html_h3_fallback)
        assert len(steps) == 3
        assert steps[0]["name"] == "Audit Your Current Performance"
        assert "PageSpeed" in steps[0]["text"]

    def test_empty_html_returns_empty(self):
        assert _extract_steps("<p>No steps here.</p>") == []

    def test_ol_without_h3_uses_default_names(self):
        html = "<ol><li><p>Do this first.</p></li><li><p>Then do this.</p></li></ol>"
        steps = _extract_steps(html)
        assert len(steps) == 2
        assert steps[0]["name"] == "Step 1"
        assert steps[1]["name"] == "Step 2"


class TestExtractTools:
    def test_extracts_from_needs_section(self, sample_howto_html):
        tools = _extract_tools(sample_howto_html)
        assert len(tools) == 3
        assert "A Google account" in tools
        assert "A text editor" in tools

    def test_no_tools_section(self):
        html = "<h2>Introduction</h2><p>Just an intro.</p>"
        assert _extract_tools(html) == []

    def test_prerequisites_heading(self):
        html = """
        <h3>Prerequisites</h3>
        <ul><li>Python 3.12+</li><li>Docker</li></ul>
        """
        tools = _extract_tools(html)
        assert "Python 3.12+" in tools
        assert "Docker" in tools

    def test_requirements_heading(self):
        html = """
        <h2>Requirements</h2>
        <ul><li>Node.js</li><li>npm</li></ul>
        """
        tools = _extract_tools(html)
        assert "Node.js" in tools


class TestGenerateFaqJsonld:
    def test_schema_structure(self, sample_faq_html, sample_specific_data):
        result = generate_faq_jsonld(
            sample_faq_html, "FAQ Title", "https://example.com/faq", sample_specific_data
        )
        assert result["@context"] == "https://schema.org"
        assert result["@type"] == "FAQPage"
        assert result["name"] == "FAQ Title"
        assert result["url"] == "https://example.com/faq"
        assert len(result["mainEntity"]) == 3

    def test_question_answer_types(self, sample_faq_html, sample_specific_data):
        result = generate_faq_jsonld(
            sample_faq_html, "FAQ", "https://example.com/faq", sample_specific_data
        )
        for item in result["mainEntity"]:
            assert item["@type"] == "Question"
            assert "acceptedAnswer" in item
            assert item["acceptedAnswer"]["@type"] == "Answer"

    def test_about_entities_from_mentions(self, sample_faq_html, sample_specific_data):
        result = generate_faq_jsonld(
            sample_faq_html, "FAQ", "https://example.com/faq", sample_specific_data
        )
        assert "about" in result
        assert len(result["about"]) == 3
        assert result["about"][0]["@type"] == "Thing"
        assert result["about"][0]["name"] == "SEMrush"

    def test_no_mentions_no_about(self, sample_faq_html):
        result = generate_faq_jsonld(
            sample_faq_html, "FAQ", "https://example.com/faq", {}
        )
        assert "about" not in result


class TestGenerateHowtoJsonld:
    def test_schema_structure(self, sample_howto_html, sample_specific_data):
        result = generate_howto_jsonld(
            sample_howto_html, "How To Title", "https://example.com/howto", sample_specific_data
        )
        assert result["@type"] == "HowTo"
        assert len(result["step"]) == 3
        assert result["step"][0]["@type"] == "HowToStep"
        assert result["step"][0]["position"] == 1

    def test_tools_included(self, sample_howto_html, sample_specific_data):
        result = generate_howto_jsonld(
            sample_howto_html, "HT", "https://example.com/ht", sample_specific_data
        )
        assert "tool" in result
        assert result["tool"][0]["@type"] == "HowToTool"

    def test_estimated_time(self, sample_howto_html):
        data = {"estimated_time": "PT30M"}
        result = generate_howto_jsonld(
            sample_howto_html, "HT", "https://example.com/ht", data
        )
        assert result["totalTime"] == "PT30M"

    def test_key_facts_as_description(self, sample_howto_html, sample_specific_data):
        result = generate_howto_jsonld(
            sample_howto_html, "HT", "https://example.com/ht", sample_specific_data
        )
        assert "description" in result
        assert "SEMrush" in result["description"]

    def test_no_tools_section(self, sample_informational_html):
        """HTML without a tools section should not include 'tool' key."""
        result = generate_howto_jsonld(
            sample_informational_html, "HT", "https://example.com/ht", {}
        )
        assert "tool" not in result


class TestGenerateComparisonJsonld:
    def test_schema_structure(self, sample_comparison_html, sample_specific_data):
        result = generate_comparison_jsonld(
            sample_comparison_html, "Comparison", "https://example.com/cmp", sample_specific_data
        )
        assert result["@type"] == "Article"
        assert result["headline"] == "Comparison"
        assert "mainEntity" in result
        assert result["mainEntity"]["@type"] == "ItemList"

    def test_item_list_positions(self, sample_comparison_html, sample_specific_data):
        result = generate_comparison_jsonld(
            sample_comparison_html, "C", "https://example.com/c", sample_specific_data
        )
        items = result["mainEntity"]["itemListElement"]
        assert len(items) == 3  # 3 mentions
        assert items[0]["position"] == 1
        assert items[1]["position"] == 2
        assert items[0]["item"]["@type"] == "Product"

    def test_aggregate_rating(self, sample_comparison_html, sample_specific_data):
        result = generate_comparison_jsonld(
            sample_comparison_html, "C", "https://example.com/c", sample_specific_data
        )
        items = result["mainEntity"]["itemListElement"]
        # Ratings are applied to every item (current implementation)
        for item in items:
            assert "aggregateRating" in item["item"]
            assert item["item"]["aggregateRating"]["ratingValue"] == 4.5
            assert item["item"]["aggregateRating"]["bestRating"] == 5

    def test_pricing_as_offers(self, sample_comparison_html, sample_specific_data):
        result = generate_comparison_jsonld(
            sample_comparison_html, "C", "https://example.com/c", sample_specific_data
        )
        assert "mentions" in result
        offers = result["mentions"]
        assert len(offers) == 2
        assert offers[0]["@type"] == "Offer"

    def test_no_mentions_no_main_entity(self, sample_comparison_html):
        result = generate_comparison_jsonld(
            sample_comparison_html, "C", "https://example.com/c", {}
        )
        assert "mainEntity" not in result

    def test_author_and_publisher(self, sample_comparison_html):
        result = generate_comparison_jsonld(
            sample_comparison_html, "C", "https://example.com/c", {}
        )
        assert result["author"]["@type"] == "Person"
        assert result["publisher"]["@type"] == "Organization"
        assert "datePublished" in result


class TestGenerateArticleJsonld:
    def test_schema_structure(self, sample_informational_html, sample_specific_data):
        result = generate_article_jsonld(
            sample_informational_html, "Article Title", "https://example.com/article",
            sample_specific_data, meta_description="A great article",
        )
        assert result["@type"] == "BlogPosting"
        assert result["headline"] == "Article Title"
        assert result["description"] == "A great article"

    def test_about_from_mentions(self, sample_informational_html, sample_specific_data):
        result = generate_article_jsonld(
            sample_informational_html, "A", "https://example.com/a",
            sample_specific_data,
        )
        assert "about" in result
        assert result["about"][0]["name"] == "SEMrush"

    def test_keywords_from_features(self, sample_informational_html, sample_specific_data):
        result = generate_article_jsonld(
            sample_informational_html, "A", "https://example.com/a",
            sample_specific_data,
        )
        assert "keywords" in result
        assert "keyword research" in result["keywords"]

    def test_article_body_from_key_facts(self, sample_informational_html, sample_specific_data):
        result = generate_article_jsonld(
            sample_informational_html, "A", "https://example.com/a",
            sample_specific_data,
        )
        assert "articleBody" in result
        assert "10 million" in result["articleBody"]

    def test_publisher_url(self, sample_informational_html):
        result = generate_article_jsonld(
            sample_informational_html, "A", "https://example.com/a", {},
        )
        assert "url" in result["publisher"]

    def test_date_fields_present(self, sample_informational_html):
        result = generate_article_jsonld(
            sample_informational_html, "A", "https://example.com/a", {},
        )
        assert "datePublished" in result
        assert "dateModified" in result


class TestGenerateJsonldDispatcher:
    def test_faq_dispatch(self, sample_faq_html):
        result = generate_jsonld(
            ContentCategory.FAQ, sample_faq_html, "Title", "slug", {}, ""
        )
        assert result["@type"] == "FAQPage"

    def test_howto_dispatch(self, sample_howto_html):
        result = generate_jsonld(
            ContentCategory.HOW_TO, sample_howto_html, "Title", "slug", {}, ""
        )
        assert result["@type"] == "HowTo"

    def test_comparison_dispatch(self, sample_comparison_html):
        result = generate_jsonld(
            ContentCategory.COMPARISON, sample_comparison_html, "Title", "slug", {}, ""
        )
        assert result["@type"] == "Article"

    def test_informational_dispatch(self, sample_informational_html):
        result = generate_jsonld(
            ContentCategory.INFORMATIONAL, sample_informational_html, "Title", "slug",
            {}, "meta desc",
        )
        assert result["@type"] == "BlogPosting"
        assert result["description"] == "meta desc"

    def test_url_built_from_slug(self, sample_faq_html):
        result = generate_jsonld(
            ContentCategory.FAQ, sample_faq_html, "T", "my-slug", {}, ""
        )
        assert result["url"].endswith("/my-slug")
