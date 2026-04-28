"""Shared fixtures for AEO Agents backend tests.

Mocks heavy/unavailable dependencies before any app modules are imported.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Mock heavy third-party modules BEFORE any app imports touch them
# ---------------------------------------------------------------------------
# These modules may not be installed in the test environment (contentful,
# sentence-transformers/torch, google-genai). We insert lightweight mocks
# into sys.modules so that `import X` succeeds at the module level.

_MOCK_MODULES = [
    "contentful_management",
    "contentful",
    "sentence_transformers",
    "torch",
    "torch._C",
    "google",
    "google.genai",
    "google.genai.types",
]

for mod_name in _MOCK_MODULES:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

# Ensure numpy is real (needed for cosine_similarity tests)
# sentence_transformers mock needs a SentenceTransformer class
_mock_st = sys.modules["sentence_transformers"]
_mock_st.SentenceTransformer = MagicMock

# ---------------------------------------------------------------------------
# Set environment variables BEFORE importing app modules
# ---------------------------------------------------------------------------
os.environ.setdefault("CONTENTFUL_SPACE_ID", "test-space")
os.environ.setdefault("CONTENTFUL_MANAGEMENT_TOKEN", "test-mgmt-token")
os.environ.setdefault("CONTENTFUL_DELIVERY_TOKEN", "test-delivery-token")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("SITE_URL", "https://example.com")
os.environ.setdefault("SITE_NAME", "Test Blog")
os.environ.setdefault("ORGANIZATION_NAME", "Test Org")
os.environ.setdefault("DEFAULT_AUTHOR", "Test Author")

# ---------------------------------------------------------------------------
# Now safe to import app modules
# ---------------------------------------------------------------------------
import pytest
from fastapi.testclient import TestClient

from app.schemas.content import (
    ContentCategory,
    GenerateRequest,
    GeneratedContent,
    GenerateResponse,
)


@pytest.fixture
def sample_faq_html():
    return """
    <h1>Frequently Asked Questions about SEO Tools</h1>
    <h2>What is SEO?</h2>
    <p>SEO stands for Search Engine Optimization. It involves optimizing websites to rank higher in search results.</p>
    <h2>How much does SEO cost?</h2>
    <p>SEO costs vary widely. Small businesses typically spend $500-$5000 per month.</p>
    <p>Enterprise companies may spend significantly more on comprehensive strategies.</p>
    <h2>How long does SEO take?</h2>
    <p>Most SEO campaigns take 3-6 months to show meaningful results.</p>
    """


@pytest.fixture
def sample_howto_html():
    return """
    <h1>How to Set Up Google Analytics</h1>
    <p>Follow these steps to get started.</p>
    <h2>What You'll Need</h2>
    <ul>
        <li>A Google account</li>
        <li>Access to your website's code</li>
        <li>A text editor</li>
    </ul>
    <ol>
        <li>
            <h3>Create a Google Analytics Account</h3>
            <p>Go to analytics.google.com and sign in with your Google account.</p>
        </li>
        <li>
            <h3>Set Up a Property</h3>
            <p>Click "Admin" and then "Create Property" to add your website.</p>
        </li>
        <li>
            <h3>Install the Tracking Code</h3>
            <p>Copy the tracking snippet and paste it into your site's &lt;head&gt; tag.</p>
        </li>
    </ol>
    """


@pytest.fixture
def sample_howto_html_h3_fallback():
    """HowTo HTML that uses h3 tags instead of ol for steps."""
    return """
    <h1>How to Optimize Your Website</h1>
    <h3>Audit Your Current Performance</h3>
    <p>Use tools like PageSpeed Insights to check your baseline metrics.</p>
    <p>Note down any critical issues flagged.</p>
    <h3>Optimize Images</h3>
    <p>Compress all images using WebP format for better performance.</p>
    <h3>Enable Caching</h3>
    <p>Set up browser caching with appropriate cache headers.</p>
    """


@pytest.fixture
def sample_comparison_html():
    return """
    <h1>SEMrush vs Ahrefs: Which SEO Tool is Better?</h1>
    <p>We compare two of the leading SEO platforms.</p>
    <table>
        <thead><tr><th>Feature</th><th>SEMrush</th><th>Ahrefs</th></tr></thead>
        <tbody>
            <tr><td>Keyword Research</td><td>Excellent</td><td>Excellent</td></tr>
            <tr><td>Backlink Analysis</td><td>Good</td><td>Excellent</td></tr>
        </tbody>
    </table>
    """


@pytest.fixture
def sample_informational_html():
    return """
    <h1>The Ultimate Guide to Content Marketing</h1>
    <h2>What is Content Marketing?</h2>
    <p>Content marketing is a strategic approach focused on creating valuable content.</p>
    <h2>Why Content Marketing Matters</h2>
    <p>It builds trust, drives organic traffic, and generates leads over time.</p>
    <ul><li>Increases brand awareness</li><li>Improves SEO rankings</li></ul>
    """


@pytest.fixture
def sample_generate_request():
    return GenerateRequest(
        topic="best SEO tools for small businesses",
        category=ContentCategory.FAQ,
        brand_url="https://example.com",
        context="Focus on affordable options",
        num_variations=2,
    )


@pytest.fixture
def sample_generated_content():
    return GeneratedContent(
        title="Best SEO Tools for Small Businesses FAQ",
        slug="best-seo-tools-small-businesses-faq",
        category=ContentCategory.FAQ,
        content_html="<h1>FAQ</h1><h2>What tools?</h2><p>Here are the best tools.</p>",
        jsonld_data={"mentions": ["SEMrush", "Ahrefs"], "key_facts": ["Fact 1"]},
        meta_description="Discover the best SEO tools for small businesses.",
        tags=["seo", "tools", "small-business"],
        topic="best SEO tools",
        brand_url="https://example.com",
    )


@pytest.fixture
def sample_specific_data():
    return {
        "mentions": ["SEMrush", "Ahrefs", "Moz"],
        "features": ["keyword research", "backlink analysis", "site audit"],
        "pricing": {"Pro": "$119.95/mo", "Guru": "$229.95/mo"},
        "ratings": {"score": 4.5, "count": 1200},
        "key_facts": [
            "SEMrush has over 10 million users",
            "Ahrefs crawls 8 billion pages daily",
        ],
    }
