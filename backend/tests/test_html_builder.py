"""Tests for HTML page builder, sitemap, and robots.txt generation."""

import json
from datetime import datetime

import pytest
from bs4 import BeautifulSoup

from app.schemas.content import ContentCategory, GeneratedContent
from app.services.html_builder import build_full_page, build_sitemap, build_robots_txt


class TestBuildFullPage:
    def test_returns_valid_html5(self, sample_generated_content):
        html = build_full_page(sample_generated_content)
        assert html.startswith("<!DOCTYPE html>")
        assert "<html lang=\"en\">" in html
        assert "</html>" in html

    def test_contains_title(self, sample_generated_content):
        html = build_full_page(sample_generated_content)
        assert f"<title>{sample_generated_content.title}</title>" in html

    def test_contains_meta_description(self, sample_generated_content):
        html = build_full_page(sample_generated_content)
        assert sample_generated_content.meta_description in html

    def test_contains_canonical_url(self, sample_generated_content):
        html = build_full_page(sample_generated_content)
        expected_url = f"https://example.com/{sample_generated_content.slug}"
        assert f'href="{expected_url}"' in html

    def test_contains_open_graph_tags(self, sample_generated_content):
        html = build_full_page(sample_generated_content)
        assert 'property="og:title"' in html
        assert 'property="og:description"' in html
        assert 'property="og:url"' in html
        assert 'property="og:type"' in html

    def test_contains_robots_meta(self, sample_generated_content):
        html = build_full_page(sample_generated_content)
        assert "index, follow, max-snippet:-1" in html

    def test_contains_jsonld_script(self, sample_generated_content):
        jsonld = {"@type": "FAQPage", "name": "Test"}
        html = build_full_page(sample_generated_content, jsonld=jsonld)
        assert 'application/ld+json' in html
        assert '"FAQPage"' in html

    def test_contains_organization_jsonld(self, sample_generated_content):
        html = build_full_page(sample_generated_content)
        assert '"Organization"' in html

    def test_contains_sitemap_reference(self, sample_generated_content):
        html = build_full_page(sample_generated_content)
        assert 'rel="sitemap"' in html
        assert "sitemap.xml" in html

    def test_article_structure(self, sample_generated_content):
        html = build_full_page(sample_generated_content)
        soup = BeautifulSoup(html, "html.parser")
        assert soup.find("article") is not None
        assert soup.find("header") is not None
        assert soup.find("main") is not None
        assert soup.find("footer") is not None

    def test_content_html_embedded(self, sample_generated_content):
        html = build_full_page(sample_generated_content)
        assert sample_generated_content.content_html in html

    def test_two_jsonld_scripts(self, sample_generated_content):
        """Page should have exactly 2 JSON-LD script tags."""
        html = build_full_page(sample_generated_content)
        count = html.count('type="application/ld+json"')
        assert count == 2

    def test_auto_generates_jsonld_if_none(self, sample_generated_content):
        """If no jsonld passed, it should auto-generate from content."""
        html = build_full_page(sample_generated_content, jsonld=None)
        assert 'application/ld+json' in html
        # Should contain the FAQ-specific JSON-LD since category is FAQ
        assert '"FAQPage"' in html

    def test_keywords_meta_from_tags(self, sample_generated_content):
        html = build_full_page(sample_generated_content)
        assert 'name="keywords"' in html
        assert "seo" in html
        assert "tools" in html

    def test_keywords_fallback_to_topic(self):
        """When tags are empty, keywords should fall back to topic."""
        content = GeneratedContent(
            title="T", slug="t", category=ContentCategory.FAQ,
            content_html="<p>x</p>", jsonld_data={}, meta_description="d",
            tags=[], topic="my topic", brand_url="u",
        )
        html = build_full_page(content)
        assert "my topic" in html


class TestBuildSitemap:
    def test_valid_xml_structure(self):
        entries = [
            {"slug": "test-article", "updated_at": "2024-01-15", "category": "faq"},
        ]
        sitemap = build_sitemap(entries)
        assert '<?xml version="1.0"' in sitemap
        assert "<urlset" in sitemap
        assert "</urlset>" in sitemap

    def test_homepage_always_included(self):
        sitemap = build_sitemap([])
        assert "<priority>1.0</priority>" in sitemap
        assert "https://example.com/" in sitemap

    def test_faq_weekly_priority(self):
        entries = [{"slug": "faq-page", "updated_at": "2024-01-15", "category": "faq"}]
        sitemap = build_sitemap(entries)
        assert "<changefreq>weekly</changefreq>" in sitemap
        assert "<priority>0.8</priority>" in sitemap

    def test_howto_weekly_priority(self):
        entries = [{"slug": "howto-page", "updated_at": "2024-01-15", "category": "how-to"}]
        sitemap = build_sitemap(entries)
        assert "<changefreq>weekly</changefreq>" in sitemap
        assert "<priority>0.8</priority>" in sitemap

    def test_informational_daily_priority(self):
        entries = [{"slug": "info-page", "updated_at": "2024-01-15", "category": "informational"}]
        sitemap = build_sitemap(entries)
        assert "<changefreq>daily</changefreq>" in sitemap
        assert "<priority>0.7</priority>" in sitemap

    def test_comparison_daily_priority(self):
        entries = [{"slug": "cmp-page", "updated_at": "2024-01-15", "category": "comparison"}]
        sitemap = build_sitemap(entries)
        assert "<changefreq>daily</changefreq>" in sitemap
        assert "<priority>0.7</priority>" in sitemap

    def test_multiple_entries(self):
        entries = [
            {"slug": "page-1", "updated_at": "2024-01-15", "category": "faq"},
            {"slug": "page-2", "updated_at": "2024-02-01", "category": "informational"},
            {"slug": "page-3", "updated_at": "2024-03-10", "category": "how-to"},
        ]
        sitemap = build_sitemap(entries)
        assert "page-1" in sitemap
        assert "page-2" in sitemap
        assert "page-3" in sitemap
        # Homepage + 3 entries = 4 <url> blocks
        assert sitemap.count("<url>") == 4

    def test_loc_uses_site_url(self):
        entries = [{"slug": "my-page", "updated_at": "2024-01-15"}]
        sitemap = build_sitemap(entries)
        assert "<loc>https://example.com/my-page</loc>" in sitemap

    def test_lastmod_included(self):
        entries = [{"slug": "p", "updated_at": "2024-06-30", "category": "faq"}]
        sitemap = build_sitemap(entries)
        assert "<lastmod>2024-06-30</lastmod>" in sitemap


class TestBuildRobotsTxt:
    def test_allows_all_user_agents(self):
        robots = build_robots_txt()
        assert "User-agent: *" in robots
        assert "Allow: /" in robots

    def test_ai_crawlers_explicitly_allowed(self):
        robots = build_robots_txt()
        for bot in ["GPTBot", "Google-Extended", "PerplexityBot", "ClaudeBot", "Bytespider", "CCBot"]:
            assert f"User-agent: {bot}" in robots

    def test_no_disallow_directives(self):
        robots = build_robots_txt()
        assert "Disallow" not in robots

    def test_sitemap_reference(self):
        robots = build_robots_txt()
        assert "Sitemap: https://example.com/sitemap.xml" in robots

    def test_contains_no_empty_sections(self):
        """Each User-agent line should be followed by Allow."""
        robots = build_robots_txt()
        lines = [l.strip() for l in robots.strip().split("\n") if l.strip() and not l.strip().startswith("#")]
        for i, line in enumerate(lines):
            if line.startswith("User-agent:") and line != "Sitemap:":
                # Next non-comment line should be Allow
                if i + 1 < len(lines):
                    assert lines[i + 1].startswith("Allow") or lines[i + 1].startswith("User-agent") or lines[i + 1].startswith("Sitemap")
